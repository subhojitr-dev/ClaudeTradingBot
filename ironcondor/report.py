"""
report.py  --  Daily Iron Condor End-of-Day Report
====================================================
Runs at 4:00 PM ET (market close) Mon-Fri via Task Scheduler.
Sends an HTML email with:
  - Active condor: all 4 legs, live prices and deltas, P&L per spread, adjustment log
  - Closed trades from today + recent history (last 10)
  - Total realised P&L
"""

import logging
import os
import sys
import re
import smtplib
from datetime import datetime, date, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import (
    SYMBOL, STATE_FILE, LOG_DIR,
    NOTIFY_EMAIL, SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD,
    PROFIT_TARGET_PCT, ADJUST_DELTA,
)
import alpaca_client as ac
import state_manager as sm

os.makedirs(LOG_DIR, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    handlers=[
        logging.FileHandler(
            os.path.join(LOG_DIR, f"report_{datetime.now().strftime('%Y%m%d')}.log"),
            encoding="utf-8",
        ),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)

# ── HTML helpers ──────────────────────────────────────────────────────────────

_CSS = """
  body { font-family:Arial, sans-serif; background:#f4f4f4; margin:0; padding:20px; }
  .card { background:#fff; border-radius:8px; max-width:680px; margin:0 auto;
          padding:24px; box-shadow:0 2px 8px rgba(0,0,0,.12); }
  h2   { margin:0 0 4px 0; font-size:20px; }
  .sub { color:#666; font-size:13px; margin-bottom:20px; }
  .section { margin-top:18px; }
  .section-title { font-weight:bold; font-size:13px; color:#444;
                   text-transform:uppercase; letter-spacing:.5px;
                   border-bottom:1px solid #e0e0e0; padding-bottom:4px; margin-bottom:10px; }
  table  { width:100%; border-collapse:collapse; font-size:13px; }
  th     { text-align:left; background:#f0f0f0; padding:6px 8px; font-size:12px; color:#555; }
  td     { padding:6px 8px; border-bottom:1px solid #f5f5f5; }
  .mono  { font-family:monospace; }
  .green { color:#1a7a1a; font-weight:bold; }
  .red   { color:#c0392b; font-weight:bold; }
  .amber { color:#d68910; font-weight:bold; }
  .warn  { background:#fff3cd; border-left:4px solid #ffc107; padding:8px 12px;
           font-size:13px; color:#856404; margin-top:8px; border-radius:4px; }
  .pill  { display:inline-block; padding:2px 10px; border-radius:12px;
           font-size:12px; font-weight:bold; }
  .pill-green { background:#d4edda; color:#155724; }
  .pill-red   { background:#f8d7da; color:#721c24; }
  .pill-blue  { background:#cce5ff; color:#004085; }
  .pill-amber { background:#fff3cd; color:#856404; }
  .kv  { display:flex; justify-content:space-between; padding:4px 0;
         font-size:13px; border-bottom:1px solid #f8f8f8; }
  .kv .k { color:#555; }
  .kv .v { font-weight:bold; }
  .footer { margin-top:20px; font-size:11px; color:#aaa; text-align:center; }
"""


def _wrap(body_html: str, ts: str) -> str:
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<style>{_CSS}</style></head><body>
<div class="card">
  <h2>Iron Condor Bot — End of Day Report</h2>
  <div class="sub">
    <span class="pill pill-blue">DAILY SUMMARY</span>
    &nbsp; {ts} &nbsp;&middot;&nbsp; SPY &nbsp;&middot;&nbsp; Account: PA34EFPV3B80
  </div>
  {body_html}
  <div class="footer">Iron Condor Bot &mdash; SPY Paper Trading</div>
</div></body></html>"""


def _kv(label: str, value: str) -> str:
    return f'<div class="kv"><span class="k">{label}</span><span class="v">{value}</span></div>'


def _pnl_colour(val: float) -> str:
    return "green" if val >= 0 else "red"


def _send(subject: str, html: str) -> None:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = SMTP_USER
    msg["To"]      = NOTIFY_EMAIL
    plain = re.sub(r"<[^>]+>", "", html).strip()
    msg.attach(MIMEText(plain, "plain"))
    msg.attach(MIMEText(html,  "html"))
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as s:
        s.starttls()
        s.login(SMTP_USER, SMTP_PASSWORD.replace(" ", ""))
        s.send_message(msg)


# ── Report builder ────────────────────────────────────────────────────────────

def build_report() -> str:
    state   = sm.load(STATE_FILE)
    active  = state.get("active", {})
    history = state.get("history", [])
    today   = date.today().isoformat()
    ts      = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    sections = []

    # ── Active condor ─────────────────────────────────────────────────────────
    pos = active.get(SYMBOL)
    if pos:
        expiry  = pos.get("expiry", "?")
        dtr     = (date.fromisoformat(expiry) - date.today()).days
        credit  = pos.get("net_credit", 0)
        max_risk= pos.get("max_risk", 0)

        # Fetch live snapshots for all 4 legs
        contracts = [pos["short_put"], pos["long_put"], pos["short_call"], pos["long_call"]]
        snaps     = ac.get_option_snapshots(contracts)

        sp_snap = snaps.get(pos["short_put"],  {})
        lp_snap = snaps.get(pos["long_put"],   {})
        sc_snap = snaps.get(pos["short_call"], {})
        lc_snap = snaps.get(pos["long_call"],  {})

        sp_mid   = ac.mid(sp_snap);   sp_d = ac.delta(sp_snap)
        lp_mid   = ac.mid(lp_snap)
        sc_mid   = ac.mid(sc_snap);   sc_d = ac.delta(sc_snap)
        lc_mid   = ac.mid(lc_snap)

        put_cost  = sp_mid - lp_mid
        call_cost = sc_mid - lc_mid
        total_ctc = put_cost + call_cost
        pnl_share = credit - total_ctc
        pnl_total = pnl_share * 100
        pct_max   = (1 - total_ctc / credit) * 100 if credit > 0 else 0

        profit_target_dollar = credit * PROFIT_TARGET_PCT * 100

        put_adj_tag  = " <em style='color:#888'>(rolled)</em>" if pos.get("put_adjusted")  else ""
        call_adj_tag = " <em style='color:#888'>(rolled)</em>" if pos.get("call_adjusted") else ""

        pnl_c = _pnl_colour(pnl_total)

        # Warning if either short delta is elevated
        warnings = ""
        if sp_d >= 0.35:
            warnings += f'<div class="warn">⚠ PUT side delta {sp_d:.3f} is elevated — adjustment triggers at {ADJUST_DELTA}</div>'
        if sc_d >= 0.35:
            warnings += f'<div class="warn">⚠ CALL side delta {sc_d:.3f} is elevated — adjustment triggers at {ADJUST_DELTA}</div>'

        # Adjustment log
        adj_rows = ""
        for a in pos.get("adjustment_log", []):
            sign = "+" if a["roll_credit"] >= 0 else ""
            adj_rows += (
                f"<tr><td>{a['date']}</td>"
                f"<td>{a['side'].upper()}</td>"
                f"<td class='mono'>${a.get('new_short_strike',0):.0f} / ${a.get('new_long_strike',0):.0f}</td>"
                f"<td class='mono'>{sign}${abs(a['roll_credit']):.2f}</td></tr>"
            )
        adj_section = ""
        if adj_rows:
            adj_section = f"""
            <div style="margin-top:10px;">
              <strong style="font-size:12px;">Adjustments made:</strong>
              <table style="margin-top:4px;">
                <tr><th>Date</th><th>Side</th><th>New spread</th><th>Roll credit</th></tr>
                {adj_rows}
              </table>
            </div>"""

        sections.append(f"""
        <div class="section">
          <div class="section-title">Active Iron Condor — SPY</div>
          {_kv("Entry date", pos.get('entry_date','?'))}
          {_kv("Expiry", f"{expiry}  ({dtr} days remaining)")}
          {_kv("SPY at entry", f"${pos.get('spy_price_at_entry',0):.2f}")}
          {_kv("Net credit collected", f"${credit:.2f}/share  (${credit*100:.0f} total)")}
          {_kv("Maximum risk", f"${max_risk:.2f}/share  (${max_risk*100:.0f} total)")}
          {_kv("Profit target (50%)", f"${profit_target_dollar:.0f}")}

          <div style="margin-top:12px;">
          <table>
            <tr><th>Leg</th><th>Strike</th><th>Delta</th><th>Entry</th><th>Now</th><th>Leg P&amp;L</th></tr>
            <tr>
              <td>Sell Put{put_adj_tag}</td>
              <td class="mono">${pos.get('short_put_strike',0):.0f}</td>
              <td class="mono {'amber' if sp_d >= 0.35 else ''}">{sp_d:.3f}</td>
              <td class="mono">${pos.get('short_put_credit',0):.2f}</td>
              <td class="mono">${sp_mid:.2f}</td>
              <td class="mono {'green' if pos.get('short_put_credit',0)-sp_mid>=0 else 'red'}">{'+' if pos.get('short_put_credit',0)-sp_mid>=0 else ''}${(pos.get('short_put_credit',0)-sp_mid)*100:.2f}</td>
            </tr>
            <tr>
              <td>Buy Put</td>
              <td class="mono">${pos.get('long_put_strike',0):.0f}</td>
              <td class="mono">—</td>
              <td class="mono">${pos.get('long_put_debit',0):.2f}</td>
              <td class="mono">${lp_mid:.2f}</td>
              <td class="mono {'green' if lp_mid-pos.get('long_put_debit',0)>=0 else 'red'}">{'+' if lp_mid-pos.get('long_put_debit',0)>=0 else ''}${(lp_mid-pos.get('long_put_debit',0))*100:.2f}</td>
            </tr>
            <tr>
              <td>Sell Call{call_adj_tag}</td>
              <td class="mono">${pos.get('short_call_strike',0):.0f}</td>
              <td class="mono {'amber' if sc_d >= 0.35 else ''}">{sc_d:.3f}</td>
              <td class="mono">${pos.get('short_call_credit',0):.2f}</td>
              <td class="mono">${sc_mid:.2f}</td>
              <td class="mono {'green' if pos.get('short_call_credit',0)-sc_mid>=0 else 'red'}">{'+' if pos.get('short_call_credit',0)-sc_mid>=0 else ''}${(pos.get('short_call_credit',0)-sc_mid)*100:.2f}</td>
            </tr>
            <tr>
              <td>Buy Call</td>
              <td class="mono">${pos.get('long_call_strike',0):.0f}</td>
              <td class="mono">—</td>
              <td class="mono">${pos.get('long_call_debit',0):.2f}</td>
              <td class="mono">${lc_mid:.2f}</td>
              <td class="mono {'green' if lc_mid-pos.get('long_call_debit',0)>=0 else 'red'}">{'+' if lc_mid-pos.get('long_call_debit',0)>=0 else ''}${(lc_mid-pos.get('long_call_debit',0))*100:.2f}</td>
            </tr>
          </table>
          </div>

          <div style="margin-top:10px; font-size:13px; border-top:2px solid #e0e0e0; padding-top:8px;">
            Cost to close now: <strong>${total_ctc:.2f}/share</strong> &nbsp;&middot;&nbsp;
            Net P&amp;L: <strong class="{pnl_c}">{'+' if pnl_total>=0 else ''}${pnl_total:.2f}</strong>
            &nbsp;&middot;&nbsp;
            <strong class="{pnl_c}">{pct_max:+.0f}%</strong> of max profit captured
          </div>
          {warnings}
          {adj_section}
        </div>""")
    else:
        sections.append("""
        <div class="section">
          <div class="section-title">Active Iron Condor</div>
          <p style="font-size:13px; color:#666; margin:0;">No open condor at market close.</p>
        </div>""")

    # ── Closed today ──────────────────────────────────────────────────────────
    closed_today = [h for h in history if h.get("close_date") == today]
    if closed_today:
        rows = ""
        for h in closed_today:
            pnl   = h.get("net_pnl", 0) or 0
            pnl_c = _pnl_colour(pnl)
            rows += (
                f"<tr>"
                f"<td>{h.get('entry_date','?')}</td>"
                f"<td>{h.get('expiry','?')}</td>"
                f"<td class='mono'>${h.get('short_put_strike',0):.0f}/{h.get('long_put_strike',0):.0f}P · "
                f"${h.get('short_call_strike',0):.0f}/{h.get('long_call_strike',0):.0f}C</td>"
                f"<td class='mono'>${h.get('net_credit',0):.2f}</td>"
                f"<td class='mono {pnl_c}'>{'+' if pnl>=0 else ''}${pnl:.2f}</td>"
                f"<td style='font-size:12px;color:#666;'>{h.get('close_reason','?')}</td>"
                f"</tr>"
            )
        sections.append(f"""
        <div class="section">
          <div class="section-title">Closed Today ({len(closed_today)})</div>
          <table>
            <tr><th>Entry</th><th>Expiry</th><th>Strikes</th><th>Credit</th><th>P&amp;L</th><th>Reason</th></tr>
            {rows}
          </table>
        </div>""")

    # ── Recent history ────────────────────────────────────────────────────────
    recent = history[-10:] if history else []
    if recent:
        rows      = ""
        total_pnl = 0.0
        for h in reversed(recent):
            pnl   = h.get("net_pnl", 0) or 0
            total_pnl += pnl
            pnl_c = _pnl_colour(pnl)
            adjs  = len(h.get("adjustment_log", []))
            rows += (
                f"<tr>"
                f"<td>{h.get('entry_date','?')}</td>"
                f"<td>{h.get('close_date','?')}</td>"
                f"<td>{h.get('expiry','?')}</td>"
                f"<td class='mono'>${h.get('net_credit',0):.2f}</td>"
                f"<td class='mono {pnl_c}'>{'+' if pnl>=0 else ''}${pnl:.2f}</td>"
                f"<td style='text-align:center;'>{'✓' if adjs else '—'} {adjs or ''}</td>"
                f"<td style='font-size:11px;color:#666;'>{h.get('close_reason','?')[:30]}</td>"
                f"</tr>"
            )
        t_c = _pnl_colour(total_pnl)
        sections.append(f"""
        <div class="section">
          <div class="section-title">Last {len(recent)} Closed Trades</div>
          <table>
            <tr><th>Entry</th><th>Closed</th><th>Expiry</th><th>Credit</th><th>P&amp;L</th><th>Adj</th><th>Reason</th></tr>
            {rows}
          </table>
          <div style="margin-top:8px; font-size:13px;">
            Cumulative P&amp;L (last {len(recent)} trades):
            <strong class="{t_c}">{'+' if total_pnl>=0 else ''}${total_pnl:.2f}</strong>
          </div>
        </div>""")
    else:
        sections.append("""
        <div class="section">
          <div class="section-title">Closed Trade History</div>
          <p style="font-size:13px; color:#666; margin:0;">No closed trades yet.</p>
        </div>""")

    return _wrap("\n".join(sections), ts)


def run():
    log.info("Generating Iron Condor daily report...")
    try:
        html      = build_report()
        today_str = datetime.now().strftime("%Y-%m-%d")
        subject   = f"[IronCondor] Daily Report — {today_str}"
        _send(subject, html)
        log.info("Iron Condor report emailed to %s", NOTIFY_EMAIL)

        report_path = os.path.join(LOG_DIR, f"report_{datetime.now().strftime('%Y%m%d')}.html")
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(html)
        log.info("Report saved to %s", report_path)

    except Exception as e:
        log.error("Iron Condor report failed: %s", e, exc_info=True)


if __name__ == "__main__":
    run()
