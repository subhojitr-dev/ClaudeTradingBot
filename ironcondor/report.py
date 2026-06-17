"""
report.py  --  Daily Iron Condor End-of-Day Report
====================================================
Runs at 4:00 PM ET (market close) Mon-Fri via Task Scheduler.

Shows per-symbol breakdown (SPY / IWM / GLD) plus combined P&L so you
can see at a glance which condor is winning, which is losing, and what
the portfolio-level result is.
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
    SYMBOLS, SYMBOL_CONFIGS, STATE_FILE, LOG_DIR,
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
  body { font-family:Arial,sans-serif; background:#f4f4f4; margin:0; padding:20px; }
  .card { background:#fff; border-radius:8px; max-width:720px; margin:0 auto;
          padding:24px; box-shadow:0 2px 8px rgba(0,0,0,.12); }
  h2   { margin:0 0 4px 0; font-size:20px; }
  .sub { color:#666; font-size:13px; margin-bottom:20px; }
  .section { margin-top:18px; }
  .section-title { font-weight:bold; font-size:13px; color:#444;
                   text-transform:uppercase; letter-spacing:.5px;
                   border-bottom:1px solid #e0e0e0; padding-bottom:4px; margin-bottom:10px; }
  table  { width:100%; border-collapse:collapse; font-size:13px; }
  th     { text-align:left; background:#f0f0f0; padding:6px 8px; font-size:12px; color:#555; }
  td     { padding:6px 8px; border-bottom:1px solid #f5f5f5; vertical-align:top; }
  .mono  { font-family:monospace; }
  .green { color:#1a7a1a; font-weight:bold; }
  .red   { color:#c0392b; font-weight:bold; }
  .amber { color:#d68910; font-weight:bold; }
  .warn  { background:#fff3cd; border-left:4px solid #ffc107; padding:6px 10px;
           font-size:12px; color:#856404; margin-top:4px; border-radius:4px; }
  .pill  { display:inline-block; padding:2px 8px; border-radius:12px;
           font-size:11px; font-weight:bold; }
  .pill-green  { background:#d4edda; color:#155724; }
  .pill-red    { background:#f8d7da; color:#721c24; }
  .pill-blue   { background:#cce5ff; color:#004085; }
  .pill-amber  { background:#fff3cd; color:#856404; }
  .pill-grey   { background:#e2e3e5; color:#383d41; }
  .summary-box { background:#f8f9fa; border:1px solid #dee2e6; border-radius:6px;
                 padding:12px 16px; margin-top:6px; font-size:14px; }
  .footer { margin-top:20px; font-size:11px; color:#aaa; text-align:center; }
"""


def _wrap(body_html: str, ts: str) -> str:
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<style>{_CSS}</style></head><body>
<div class="card">
  <h2>Iron Condor — End of Day Report</h2>
  <div class="sub">
    <span class="pill pill-blue">DAILY SUMMARY</span>
    &nbsp; {ts} &nbsp;&middot;&nbsp;
    SPY &middot; IWM &middot; GLD &nbsp;&middot;&nbsp; Account: PA34EFPV3B80
  </div>
  {body_html}
  <div class="footer">Iron Condor Bot &mdash; Multi-Symbol Paper Trading</div>
</div></body></html>"""


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


# ── Per-symbol snapshot ───────────────────────────────────────────────────────

def _symbol_row(symbol: str, pos: dict) -> tuple[str, float]:
    """
    Build one table row for an active condor.
    Returns (html_row, current_pnl_dollars).
    """
    expiry = pos.get("expiry", "?")
    dtr    = (date.fromisoformat(expiry) - date.today()).days
    credit = pos.get("net_credit", 0)

    contracts = [pos["short_put"], pos["long_put"], pos["short_call"], pos["long_call"]]
    snaps     = ac.get_option_snapshots(contracts)

    sp_snap  = snaps.get(pos["short_put"],  {})
    lp_snap  = snaps.get(pos["long_put"],   {})
    sc_snap  = snaps.get(pos["short_call"], {})
    lc_snap  = snaps.get(pos["long_call"],  {})

    sp_mid = ac.mid(sp_snap); sp_d = ac.delta(sp_snap)
    lp_mid = ac.mid(lp_snap)
    sc_mid = ac.mid(sc_snap); sc_d = ac.delta(sc_snap)
    lc_mid = ac.mid(lc_snap)

    put_cost  = sp_mid - lp_mid
    call_cost = sc_mid - lc_mid
    total_ctc = put_cost + call_cost
    pnl_share = credit - total_ctc
    pnl_total = round(pnl_share * 100, 2)
    pct_max   = (1 - total_ctc / credit) * 100 if credit > 0 else 0

    pnl_c  = _pnl_colour(pnl_total)
    put_adj  = " ®" if pos.get("put_adjusted")  else ""
    call_adj = " ®" if pos.get("call_adjusted") else ""

    # Delta warnings
    delta_warn = ""
    if sp_d >= 0.35 or sc_d >= 0.35:
        delta_warn = f'<div class="warn">⚠ delta elevated (put {sp_d:.3f} / call {sc_d:.3f})</div>'

    adj_count = len(pos.get("adjustment_log", []))
    adj_tag   = f' <span class="pill pill-amber">{adj_count} adj</span>' if adj_count else ""

    row = f"""
    <tr>
      <td><strong>{symbol}</strong>{adj_tag}</td>
      <td class="mono">${pos.get('short_put_strike',0):.0f}/{pos.get('long_put_strike',0):.0f}P{put_adj}
          <br>${pos.get('short_call_strike',0):.0f}/{pos.get('long_call_strike',0):.0f}C{call_adj}</td>
      <td>{expiry}<br><span style="color:#888;font-size:11px;">{dtr} days left</span></td>
      <td class="mono">${credit:.2f}<br>
          <span style="color:#888;font-size:11px;">${credit*100:.0f} total</span></td>
      <td class="mono">put Δ={sp_d:.3f}<br>call Δ={sc_d:.3f}</td>
      <td class="mono {pnl_c}">{'+' if pnl_total>=0 else ''}${pnl_total:.2f}
          <br><span style="font-size:11px;">{pct_max:+.0f}% of max</span></td>
    </tr>
    {'<tr><td colspan="6">' + delta_warn + '</td></tr>' if delta_warn else ''}"""

    return row, pnl_total


# ── Report builder ────────────────────────────────────────────────────────────

def build_report() -> str:
    state   = sm.load(STATE_FILE)
    active  = state.get("active", {})
    history = state.get("history", [])
    today   = date.today().isoformat()
    ts      = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    sections = []

    # ── Per-symbol active condors ──────────────────────────────────────────────
    rows         = ""
    combined_pnl = 0.0
    open_count   = 0

    for symbol in SYMBOLS:
        pos = active.get(symbol)
        if pos:
            row, pnl = _symbol_row(symbol, pos)
            rows        += row
            combined_pnl += pnl
            open_count   += 1
        else:
            rows += f"""
            <tr>
              <td><strong>{symbol}</strong></td>
              <td colspan="5" style="color:#888; font-style:italic;">
                No open condor — scanning for entry each cycle
              </td>
            </tr>"""

    comb_c = _pnl_colour(combined_pnl)

    sections.append(f"""
    <div class="section">
      <div class="section-title">Active Condors ({open_count} / {len(SYMBOLS)} open)</div>
      <table>
        <tr>
          <th>Symbol</th>
          <th>Strikes</th>
          <th>Expiry</th>
          <th>Credit</th>
          <th>Short Deltas</th>
          <th>P&amp;L Today</th>
        </tr>
        {rows}
      </table>

      <div class="summary-box" style="margin-top:12px;">
        <strong>Combined Portfolio P&amp;L:</strong>
        &nbsp; <span class="{comb_c}" style="font-size:16px;">
          {'+' if combined_pnl>=0 else ''}${combined_pnl:.2f}
        </span>
        &nbsp;&nbsp;
        <span style="color:#666; font-size:12px;">
          ({open_count} condor{'s' if open_count!=1 else ''} open across {len(SYMBOLS)} symbols)
        </span>
      </div>
    </div>""")

    # ── Correlation reminder ───────────────────────────────────────────────────
    sections.append("""
    <div class="section">
      <div class="section-title">Diversification Context</div>
      <table>
        <tr><th>Pair</th><th>Correlation</th><th>Implication</th></tr>
        <tr><td>SPY + IWM</td><td>~0.75</td>
            <td>Moderate — small-cap diverges from large-cap in risk-off events</td></tr>
        <tr><td>SPY + GLD</td><td>~0.05</td>
            <td>Near-zero — gold often rises when stocks fall (true hedge)</td></tr>
        <tr><td>IWM + GLD</td><td>~0.02</td>
            <td>Near-zero — essentially independent</td></tr>
      </table>
      <p style="font-size:12px; color:#666; margin:6px 0 0;">
        Probability all three lose simultaneously: ~0.8% per cycle (&lt;1 in 100).
      </p>
    </div>""")

    # ── Closed today ──────────────────────────────────────────────────────────
    closed_today = [h for h in history if h.get("close_date") == today]
    if closed_today:
        rows = ""
        day_pnl = 0.0
        for h in closed_today:
            pnl   = h.get("net_pnl", 0) or 0
            day_pnl += pnl
            sym   = h.get("symbol", "?")
            pnl_c = _pnl_colour(pnl)
            rows += (
                f"<tr>"
                f"<td><strong>{sym}</strong></td>"
                f"<td>{h.get('entry_date','?')}</td>"
                f"<td>{h.get('expiry','?')}</td>"
                f"<td class='mono'>${h.get('net_credit',0):.2f}</td>"
                f"<td class='mono {pnl_c}'>{'+' if pnl>=0 else ''}${pnl:.2f}</td>"
                f"<td style='font-size:11px;color:#666;'>{h.get('close_reason','?')[:35]}</td>"
                f"</tr>"
            )
        day_c = _pnl_colour(day_pnl)
        sections.append(f"""
        <div class="section">
          <div class="section-title">Closed Today ({len(closed_today)})</div>
          <table>
            <tr><th>Symbol</th><th>Entry</th><th>Expiry</th>
                <th>Credit</th><th>P&amp;L</th><th>Reason</th></tr>
            {rows}
          </table>
          <div style="margin-top:6px; font-size:13px;">
            Today's realised P&amp;L: <strong class="{day_c}">{'+' if day_pnl>=0 else ''}${day_pnl:.2f}</strong>
          </div>
        </div>""")

    # ── Recent history with combined totals ───────────────────────────────────
    recent = history[-15:] if history else []
    if recent:
        rows          = ""
        total_pnl     = 0.0
        wins = losses = 0

        for h in reversed(recent):
            pnl   = h.get("net_pnl", 0) or 0
            total_pnl += pnl
            sym   = h.get("symbol", "?")
            pnl_c = _pnl_colour(pnl)
            adjs  = len(h.get("adjustment_log", []))
            if pnl >= 0:
                wins += 1
            else:
                losses += 1
            rows += (
                f"<tr>"
                f"<td><strong>{sym}</strong></td>"
                f"<td>{h.get('entry_date','?')}</td>"
                f"<td>{h.get('close_date','?')}</td>"
                f"<td>{h.get('expiry','?')}</td>"
                f"<td class='mono'>${h.get('net_credit',0):.2f}</td>"
                f"<td class='mono {pnl_c}'>{'+' if pnl>=0 else ''}${pnl:.2f}</td>"
                f"<td style='text-align:center;'>{'✓ '+str(adjs) if adjs else '—'}</td>"
                f"<td style='font-size:11px;color:#666;'>{h.get('close_reason','?')[:28]}</td>"
                f"</tr>"
            )

        t_c      = _pnl_colour(total_pnl)
        win_rate = round(wins / (wins + losses) * 100) if (wins + losses) else 0
        sections.append(f"""
        <div class="section">
          <div class="section-title">Last {len(recent)} Closed Trades (All Symbols)</div>
          <table>
            <tr><th>Symbol</th><th>Entry</th><th>Closed</th><th>Expiry</th>
                <th>Credit</th><th>P&amp;L</th><th>Adj</th><th>Reason</th></tr>
            {rows}
          </table>
          <div class="summary-box" style="margin-top:10px;">
            <strong>Last {len(recent)} trades:</strong>
            &nbsp; Net P&amp;L: <span class="{t_c}"><strong>{'+' if total_pnl>=0 else ''}${total_pnl:.2f}</strong></span>
            &nbsp;&nbsp;&middot;&nbsp;&nbsp;
            Win rate: <strong>{win_rate}%</strong>
            ({wins}W / {losses}L)
            &nbsp;&nbsp;&middot;&nbsp;&nbsp;
            Expected ≥80%
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
    log.info("Generating Iron Condor daily report (SPY + IWM + GLD)...")
    try:
        html      = build_report()
        today_str = datetime.now().strftime("%Y-%m-%d")
        subject   = f"[IronCondor] Daily Report — {today_str}  SPY · IWM · GLD"
        _send(subject, html)
        log.info("Report emailed to %s", NOTIFY_EMAIL)

        report_path = os.path.join(LOG_DIR, f"report_{datetime.now().strftime('%Y%m%d')}.html")
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(html)
        log.info("Report saved to %s", report_path)

    except Exception as e:
        log.error("Iron Condor report failed: %s", e, exc_info=True)


if __name__ == "__main__":
    run()
