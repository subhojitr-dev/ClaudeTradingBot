"""
report.py  --  Daily Wheel Strategy Summary Report
===================================================
Runs at 4:00 PM ET (market close) Mon-Fri.
Sends an email with:
  - All positions, current P&L
  - Total premium collected (per symbol + grand total)
  - Returns vs cost basis
  - Potential return if all open options expire worthless
"""

import logging
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import (
    WHEEL_STOCKS, STATE_FILE, LOG_DIR,
    NOTIFY_EMAIL, SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD,
)
import alpaca_client as ac
from state_manager import WheelState
import notifier

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


def build_report() -> str:  # noqa: C901
    sm        = WheelState(STATE_FILE)
    positions = ac.get_positions()

    try:
        acct     = ac.get_account()
        cash     = float(acct.get("cash", 0))
        port_val = float(acct.get("portfolio_value", 0))
        bp       = float(acct.get("buying_power", 0))
    except Exception as e:
        log.error("Cannot reach Alpaca: %s", e)
        cash = port_val = bp = 0

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    CSS = """
      body{font-family:Arial,sans-serif;background:#f4f4f4;margin:0;padding:20px}
      .card{background:#fff;border-radius:8px;max-width:700px;margin:0 auto;
            padding:24px;box-shadow:0 2px 8px rgba(0,0,0,.12)}
      h2{margin:0 0 4px;font-size:20px}
      .sub{color:#666;font-size:13px;margin-bottom:20px}
      .section{margin-top:18px}
      .section-title{font-weight:bold;font-size:13px;color:#444;text-transform:uppercase;
                     letter-spacing:.5px;border-bottom:1px solid #e0e0e0;
                     padding-bottom:4px;margin-bottom:10px}
      table{width:100%;border-collapse:collapse;font-size:13px}
      th{text-align:left;background:#f0f0f0;padding:6px 8px;font-size:12px;color:#555}
      td{padding:6px 8px;border-bottom:1px solid #f0f0f0}
      .mono{font-family:monospace;font-size:12px}
      .green{color:#1a7a1a;font-weight:bold}
      .red{color:#c0392b;font-weight:bold}
      .amber{color:#d68910;font-weight:bold}
      .pill{display:inline-block;padding:1px 8px;border-radius:10px;font-size:11px;font-weight:bold}
      .pill-blue{background:#cce5ff;color:#004085}
      .pill-amber{background:#fff3cd;color:#856404}
      .pill-gray{background:#e2e3e5;color:#383d41}
      .kv{display:flex;justify-content:space-between;padding:4px 0;
          font-size:14px;border-bottom:1px solid #f5f5f5}
      .kv .k{color:#555} .kv .v{font-weight:bold}
      .summary-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:8px}
      .metric{background:#f8f8f8;border-radius:6px;padding:10px 12px}
      .metric-label{font-size:11px;color:#888;margin-bottom:3px}
      .metric-value{font-size:18px;font-weight:bold;color:#222}
      .footer{margin-top:20px;font-size:11px;color:#aaa;text-align:center}
    """

    # ── Account metrics ──────────────────────────────────────────────────────
    grand_total = sm.total_premium()
    metrics_html = f"""
    <div class="summary-grid">
      <div class="metric"><div class="metric-label">Cash</div>
        <div class="metric-value">${cash:,.0f}</div></div>
      <div class="metric"><div class="metric-label">Buying power</div>
        <div class="metric-value">${bp:,.0f}</div></div>
      <div class="metric"><div class="metric-label">Portfolio value</div>
        <div class="metric-value">${port_val:,.0f}</div></div>
      <div class="metric"><div class="metric-label">Total premium collected</div>
        <div class="metric-value green">${grand_total:,.2f}</div></div>
    </div>"""

    # ── Options positions table ──────────────────────────────────────────────
    grand_collected = 0.0
    grand_potential = 0.0
    rows = ""

    for sym in WHEEL_STOCKS:
        s = sm.get(sym)
        if not s:
            rows += f"<tr><td>{sym}</td><td colspan='8'>—</td></tr>"
            continue

        stage        = s.get("stage", "IDLE")
        contract_sym = s.get("contract_symbol") or ""
        entry_prem   = s.get("entry_premium", 0)
        expiry       = s.get("contract_expiry", "—")
        total_coll   = s.get("total_premium_collected", 0)
        contracts    = s.get("contracts", 1)
        grand_collected += total_coll

        curr_val = pnl_dollar = pnl_pct = potential = 0.0

        if stage in ("CSP", "CC") and contract_sym:
            snap     = ac.get_option_snapshot(contract_sym)
            curr_val = ac.get_mid_price(snap)
            if entry_prem > 0 and curr_val >= 0:
                pnl_dollar = (entry_prem - curr_val) * 100 * contracts
                pnl_pct    = (entry_prem - curr_val) / entry_prem * 100
                potential  = entry_prem * 100 * contracts
            grand_potential += potential

        stage_pill = {
            "IDLE": '<span class="pill pill-gray">IDLE</span>',
            "CSP":  '<span class="pill pill-blue">CSP</span>',
            "CC":   '<span class="pill pill-amber">CC</span>',
        }.get(stage, stage)

        pnl_cls  = "green" if pnl_dollar >= 0 else "red"
        rows += (
            f"<tr>"
            f"<td><b>{sym}</b></td>"
            f"<td>{stage_pill}</td>"
            f"<td class='mono'>{contract_sym[:22] if contract_sym else '—'}</td>"
            f"<td class='mono'>${entry_prem:.2f}</td>"
            f"<td class='mono'>${curr_val:.4f}</td>"
            f"<td class='mono {pnl_cls}'>${pnl_dollar:.2f}</td>"
            f"<td class='mono {pnl_cls}'>{pnl_pct:.0f}%</td>"
            f"<td class='mono'>{expiry}</td>"
            f"<td class='mono green'>${total_coll:.2f}</td>"
            f"</tr>"
        )

    rows += (
        f"<tr style='background:#f8f8f8;font-weight:bold'>"
        f"<td colspan='8'>Grand total</td>"
        f"<td class='mono green'>${grand_collected:.2f}</td>"
        f"</tr>"
    )

    positions_html = f"""
    <table>
      <tr>
        <th>Symbol</th><th>Stage</th><th>Contract</th>
        <th>Entry</th><th>Now</th><th>P&L $</th><th>P&L %</th>
        <th>Expiry</th><th>Collected</th>
      </tr>
      {rows}
    </table>
    <p style="font-size:11px;color:#888;margin-top:6px">
      Entry = premium/share sold &nbsp;·&nbsp; Now = current cost to close &nbsp;·&nbsp;
      P&L = profit captured so far &nbsp;·&nbsp; Collected = all-time premium this symbol
    </p>"""

    # ── Stock positions (Stage 2) ────────────────────────────────────────────
    stock_rows = ""
    for sym in WHEEL_STOCKS:
        s = sm.get(sym)
        if not s or s.get("stage") != "CC" or sym not in positions:
            continue
        pos        = positions[sym]
        qty        = int(float(pos.get("qty") or 0))
        curr_price = float(pos.get("current_price") or 0)
        cost_basis = s.get("stock_avg_cost", 0)
        mkt_val    = qty * curr_price
        cost_total = qty * cost_basis
        stock_pnl  = mkt_val - cost_total
        stock_pct  = stock_pnl / cost_total * 100 if cost_total else 0
        pnl_cls    = "green" if stock_pnl >= 0 else "red"
        stock_rows += (
            f"<tr><td><b>{sym}</b></td><td>{qty} shares</td>"
            f"<td class='mono'>${cost_basis:.2f}</td>"
            f"<td class='mono'>${curr_price:.2f}</td>"
            f"<td class='mono {pnl_cls}'>${stock_pnl:+.2f} ({stock_pct:+.1f}%)</td></tr>"
        )

    stocks_html = ""
    if stock_rows:
        stocks_html = f"""
        <div class="section">
          <div class="section-title">Stock Positions (Stage 2 — holding shares)</div>
          <table>
            <tr><th>Symbol</th><th>Qty</th><th>Cost basis</th><th>Current price</th><th>Stock P&L</th></tr>
            {stock_rows}
          </table>
        </div>"""

    # ── Returns summary ──────────────────────────────────────────────────────
    return_rows = ""
    for sym in WHEEL_STOCKS:
        s = sm.get(sym)
        if not s:
            continue
        total_coll  = s.get("total_premium_collected", 0)
        cycle_count = s.get("cycle_count", 0)
        strike = 0
        for h in reversed(s.get("history", [])):
            if h.get("strike"):
                strike = h["strike"]
                break
        collateral  = strike * 100 if strike else 0
        ret_on_col  = (total_coll / collateral * 100) if collateral > 0 else 0
        return_rows += (
            f"<tr><td><b>{sym}</b></td>"
            f"<td class='mono green'>${total_coll:.2f}</td>"
            f"<td class='mono'>{cycle_count}</td>"
            f"<td class='mono'>{ret_on_col:.1f}%</td></tr>"
        )

    returns_html = f"""
    <table>
      <tr><th>Symbol</th><th>Total premium</th><th>Cycles</th><th>Return on collateral</th></tr>
      {return_rows}
    </table>"""

    body = f"""
    <div class="section">
      <div class="section-title">Account — {now}</div>
      {metrics_html}
    </div>
    <div class="section">
      <div class="section-title">Open Positions</div>
      {positions_html}
    </div>
    {stocks_html}
    <div class="section">
      <div class="section-title">Returns Summary</div>
      {returns_html}
    </div>"""

    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<style>{CSS}</style></head><body>
<div class="card">
  <h2>Flywheel — Daily Report</h2>
  <div class="sub"><span class="pill pill-gray">WHEEL STRATEGY</span> &nbsp; {ts}</div>
  {body}
  <div class="footer">Flywheel Bot &mdash; Wheel Strategy Paper Trading &mdash; Account PA34EFPV3B80</div>
</div></body></html>"""


def run():
    log.info("Generating daily wheel strategy report...")
    try:
        report_html = build_report()
        notifier.send_report(report_html, datetime.now().strftime("%Y-%m-%d"))
        log.info("Report emailed to %s", NOTIFY_EMAIL)

    except Exception as e:
        log.error("Report generation failed: %s", e, exc_info=True)


if __name__ == "__main__":
    run()
