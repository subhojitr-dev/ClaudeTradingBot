"""
report.py  --  Daily Strangle Strategy End-of-Day Report
=========================================================
Runs at 4:00 PM ET (market close) Mon-Fri via Task Scheduler.
Sends an HTML email with:
  - All active strangles: phase, earnings date, leg prices, live P&L
  - Closed trades from today + recent history (last 10)
  - Total realised and unrealised P&L summary
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
    STATE_FILE, LOG_DIR,
    NOTIFY_EMAIL, SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD,
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
  body { font-family: Arial, sans-serif; background:#f4f4f4; margin:0; padding:20px; }
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
  .pill  { display:inline-block; padding:2px 10px; border-radius:12px;
           font-size:12px; font-weight:bold; }
  .pill-green { background:#d4edda; color:#155724; }
  .pill-red   { background:#f8d7da; color:#721c24; }
  .pill-blue  { background:#cce5ff; color:#004085; }
  .pill-amber { background:#fff3cd; color:#856404; }
  .kv   { display:flex; justify-content:space-between; padding:4px 0;
          font-size:13px; border-bottom:1px solid #f8f8f8; }
  .kv .k { color:#555; }
  .kv .v { font-weight:bold; }
  .footer { margin-top:20px; font-size:11px; color:#aaa; text-align:center; }
"""


def _wrap(body_html: str, ts: str) -> str:
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<style>{_CSS}</style></head><body>
<div class="card">
  <h2>Strangle Bot — End of Day Report</h2>
  <div class="sub">
    <span class="pill pill-blue">DAILY SUMMARY</span>
    &nbsp; {ts} &nbsp;&middot;&nbsp; Account: PA34EFPV3B80
  </div>
  {body_html}
  <div class="footer">Strangle Bot &mdash; Bi-Directional Earnings Plays</div>
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

    # ── Active strangles ──────────────────────────────────────────────────────
    if active:
        rows = ""
        total_cost       = 0.0
        total_unrealised = 0.0

        for sym, pos in active.items():
            status       = pos.get("status", "?")
            phase        = pos.get("phase", "?")
            earnings_dt  = pos.get("earnings_date", "?")
            entry_dt     = pos.get("entry_date", "?")
            expiry       = pos.get("expiry", "?")
            cost         = pos.get("total_cost", 0)
            proceeds_so_far = pos.get("total_proceeds", 0)
            total_cost  += cost

            call_contract   = pos.get("call_contract", "")
            put_contract    = pos.get("put_contract",  "")
            call_entry      = pos.get("call_entry_price", 0)
            put_entry       = pos.get("put_entry_price",  0)
            call_sold_price = pos.get("call_sold_price")
            put_sold_price  = pos.get("put_sold_price")

            # Fetch live prices for open legs
            open_contracts = []
            if call_sold_price is None and call_contract:
                open_contracts.append(call_contract)
            if put_sold_price is None and put_contract:
                open_contracts.append(put_contract)

            snaps    = ac.get_option_snapshots(open_contracts) if open_contracts else {}
            call_now = ac.extract_mid(snaps.get(call_contract, {})) if call_contract in snaps else None
            put_now  = ac.extract_mid(snaps.get(put_contract,  {})) if put_contract  in snaps else None

            # Unrealised P&L on open legs
            call_pnl = 0.0
            put_pnl  = 0.0
            if call_sold_price is not None:
                call_pnl = (call_sold_price - call_entry) * 100
            elif call_now is not None:
                call_pnl = (call_now - call_entry) * 100

            if put_sold_price is not None:
                put_pnl = (put_sold_price - put_entry) * 100
            elif put_now is not None:
                put_pnl = (put_now - put_entry) * 100

            combined_pnl = call_pnl + put_pnl
            total_unrealised += combined_pnl

            phase_pill = {
                "PRE_EARNINGS":  '<span class="pill pill-amber">PRE-EARNINGS</span>',
                "POST_EARNINGS": '<span class="pill pill-blue">POST-EARNINGS</span>',
            }.get(phase, phase)

            status_pill = {
                "OPEN":      '<span class="pill pill-green">OPEN</span>',
                "CALL_SOLD": '<span class="pill pill-amber">CALL SOLD</span>',
            }.get(status, status)

            call_now_str = f"${call_sold_price:.2f} <em>(sold)</em>" if call_sold_price else \
                           (f"${call_now:.2f}" if call_now else "—")
            put_now_str  = f"${put_sold_price:.2f} <em>(sold)</em>" if put_sold_price else \
                           (f"${put_now:.2f}" if put_now else "—")

            pnl_c = _pnl_colour(combined_pnl)
            rows += f"""
            <tr style="background:#fafafa;">
              <td colspan="6" style="padding:8px 8px 2px;">
                <strong>{sym}</strong> &nbsp; {status_pill} &nbsp; {phase_pill}
                &nbsp;&nbsp; earnings: <strong>{earnings_dt}</strong>
                &nbsp;&middot;&nbsp; entry: {entry_dt}
                &nbsp;&middot;&nbsp; expiry: {expiry}
              </td>
            </tr>
            <tr>
              <td class="mono">Call {pos.get('call_strike',0):.0f}</td>
              <td>Δ={pos.get('call_delta',0):.2f}</td>
              <td>entry ${call_entry:.2f}</td>
              <td>now {call_now_str}</td>
              <td colspan="2" class="{'green' if call_pnl>=0 else 'red'}">{'+' if call_pnl>=0 else ''}${call_pnl:.2f}</td>
            </tr>
            <tr>
              <td class="mono">Put {pos.get('put_strike',0):.0f}</td>
              <td>Δ={pos.get('put_delta',0):.2f}</td>
              <td>entry ${put_entry:.2f}</td>
              <td>now {put_now_str}</td>
              <td colspan="2" class="{'green' if put_pnl>=0 else 'red'}">{'+' if put_pnl>=0 else ''}${put_pnl:.2f}</td>
            </tr>
            <tr>
              <td colspan="4" style="padding-bottom:10px;">
                Total cost: ${cost:.2f} &nbsp;|&nbsp;
                Proceeds so far: ${proceeds_so_far:.2f} &nbsp;|&nbsp;
                Combined P&amp;L: <span class="{pnl_c}">{'+' if combined_pnl>=0 else ''}${combined_pnl:.2f}</span>
              </td>
            </tr>"""

        total_pnl_c = _pnl_colour(total_unrealised)
        sections.append(f"""
        <div class="section">
          <div class="section-title">Active Strangles ({len(active)})</div>
          <table>
            <tr><th>Leg</th><th>Delta</th><th>Entry</th><th>Current</th><th colspan="2">P&amp;L</th></tr>
            {rows}
          </table>
          <div style="margin-top:8px; font-size:13px;">
            Total capital at risk: <strong>${total_cost:.2f}</strong> &nbsp;&middot;&nbsp;
            Combined unrealised P&amp;L: <strong class="{total_pnl_c}">{'+' if total_unrealised>=0 else ''}${total_unrealised:.2f}</strong>
          </div>
        </div>""")
    else:
        sections.append("""
        <div class="section">
          <div class="section-title">Active Strangles</div>
          <p style="font-size:13px; color:#666; margin:0;">No open strangles at market close.</p>
        </div>""")

    # ── Closed today ──────────────────────────────────────────────────────────
    closed_today = [h for h in history if h.get("put_sold_date") == today
                    or h.get("call_sold_date") == today]
    if closed_today:
        rows = ""
        for h in closed_today:
            pnl   = h.get("net_pnl", 0) or 0
            pnl_c = _pnl_colour(pnl)
            rows += (
                f"<tr>"
                f"<td><strong>{h.get('status','?')[:3]}</strong></td>"
                f"<td>{h.get('earnings_date','?')}</td>"
                f"<td>${h.get('total_cost',0):.2f}</td>"
                f"<td>${h.get('total_proceeds',0):.2f}</td>"
                f"<td class='{pnl_c}'>{'+' if pnl>=0 else ''}${pnl:.2f}</td>"
                f"</tr>"
            )
        sections.append(f"""
        <div class="section">
          <div class="section-title">Closed Today ({len(closed_today)})</div>
          <table>
            <tr><th>Symbol</th><th>Earnings date</th><th>Cost</th><th>Proceeds</th><th>Net P&amp;L</th></tr>
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
            sym   = h.get("call_contract", "?")[:4]   # first 4 chars = ticker
            rows += (
                f"<tr>"
                f"<td class='mono'>{sym}</td>"
                f"<td>{h.get('entry_date','?')}</td>"
                f"<td>{h.get('earnings_date','?')}</td>"
                f"<td>${h.get('total_cost',0):.2f}</td>"
                f"<td>${h.get('total_proceeds',0):.2f}</td>"
                f"<td class='{pnl_c}'>{'+' if pnl>=0 else ''}${pnl:.2f}</td>"
                f"<td>{h.get('status','?')}</td>"
                f"</tr>"
            )
        t_c = _pnl_colour(total_pnl)
        sections.append(f"""
        <div class="section">
          <div class="section-title">Last {len(recent)} Closed Trades</div>
          <table>
            <tr><th>Symbol</th><th>Entry</th><th>Earnings</th><th>Cost</th><th>Proceeds</th><th>Net P&amp;L</th><th>Status</th></tr>
            {rows}
          </table>
          <div style="margin-top:8px; font-size:13px;">
            Cumulative P&amp;L (last {len(recent)}):
            <strong class="{t_c}">{'+' if total_pnl>=0 else ''}${total_pnl:.2f}</strong>
          </div>
        </div>""")
    else:
        sections.append("""
        <div class="section">
          <div class="section-title">Closed Trade History</div>
          <p style="font-size:13px; color:#666; margin:0;">No closed trades yet.</p>
        </div>""")

    html = _wrap("\n".join(sections), ts)
    return html


def run():
    log.info("Generating strangle daily report...")
    try:
        html = build_report()
        today_str = datetime.now().strftime("%Y-%m-%d")
        subject   = f"TradingBot: [Strangle] Daily Report — {today_str}"
        _send(subject, html)
        log.info("Strangle report emailed to %s", NOTIFY_EMAIL)

        report_path = os.path.join(LOG_DIR, f"report_{datetime.now().strftime('%Y%m%d')}.html")
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(html)
        log.info("Report saved to %s", report_path)

    except Exception as e:
        log.error("Strangle report failed: %s", e, exc_info=True)


if __name__ == "__main__":
    run()
