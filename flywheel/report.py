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


def build_report() -> str:
    sm        = WheelState(STATE_FILE)
    positions = ac.get_positions()

    try:
        acct    = ac.get_account()
        cash    = float(acct.get("cash", 0))
        port_val = float(acct.get("portfolio_value", 0))
        bp       = float(acct.get("buying_power", 0))
    except Exception as e:
        log.error("Cannot reach Alpaca: %s", e)
        cash = port_val = bp = 0

    now  = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    W    = 82   # report width

    lines = [
        "=" * W,
        "  WHEEL STRATEGY -- DAILY SUMMARY REPORT",
        f"  {now}     Account: PA34EFPV3B80",
        "=" * W,
        "",
        f"  Cash Balance    : ${cash:>12,.2f}",
        f"  Buying Power    : ${bp:>12,.2f}",
        f"  Portfolio Value : ${port_val:>12,.2f}",
        f"  Grand Total Premium Collected : ${sm.total_premium():>10,.2f}",
        "",
    ]

    # ── Options positions table ──────────────────────────────────────────────
    lines += [
        "-" * W,
        f"{'SYM':<6} {'STAGE':<6} {'CONTRACT':<26} {'ENTRY':<8} {'NOW':<8} "
        f"{'P&L$':<9} {'P&L%':<7} {'EXPIRY':<12} {'COLLECTED':<11} {'POTENTIAL':<10}",
        "-" * W,
    ]

    grand_collected = 0.0
    grand_potential = 0.0

    for sym in WHEEL_STOCKS:
        s = sm.get(sym)
        if not s:
            lines.append(f"{sym:<6} {'N/A':<6} {'-'*26}")
            continue

        stage        = s.get("stage", "IDLE")
        contract_sym = s.get("contract_symbol") or ""
        entry_prem   = s.get("entry_premium", 0)
        expiry       = s.get("contract_expiry", "--")
        total_coll   = s.get("total_premium_collected", 0)
        contracts    = s.get("contracts", 1)
        grand_collected += total_coll

        curr_val   = 0.0
        pnl_dollar = 0.0
        pnl_pct    = 0.0
        potential  = 0.0

        if stage in ("CSP", "CC") and contract_sym:
            snap     = ac.get_option_snapshot(contract_sym)
            curr_val = ac.get_mid_price(snap)
            if entry_prem > 0 and curr_val >= 0:
                pnl_dollar = (entry_prem - curr_val) * 100 * contracts
                pnl_pct    = (entry_prem - curr_val) / entry_prem * 100
                potential  = entry_prem * 100 * contracts   # if expires worthless
            grand_potential += potential

        short_contract = (contract_sym[:25] if contract_sym else "--")

        lines.append(
            f"{sym:<6} {stage:<6} {short_contract:<26} "
            f"${entry_prem:<7.2f} ${curr_val:<7.4f} "
            f"${pnl_dollar:<8.2f} {pnl_pct:<6.1f}% "
            f"{expiry:<12} ${total_coll:<10.2f} ${potential:<9.2f}"
        )

    lines += [
        "-" * W,
        f"{'TOTAL':<6} {'':<6} {'':<26} {'':<8} {'':<8} {'':<9} {'':<7} {'':<12} "
        f"${grand_collected:<10.2f} ${grand_potential:<9.2f}",
        "=" * W,
    ]

    # ── Stock positions table (Stage 2 -- holding shares) ───────────────────
    stock_sections = []
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
        stock_sections.append(
            f"  {sym:<6} {qty:>4} shares | cost ${cost_basis:.2f} | "
            f"now ${curr_price:.2f} | P&L ${stock_pnl:+.2f} ({stock_pct:+.1f}%)"
        )

    if stock_sections:
        lines += ["", "STOCK POSITIONS (Stage 2 -- awaiting covered call to expire):", "-" * W]
        lines += stock_sections

    # ── Returns summary ──────────────────────────────────────────────────────
    lines += [
        "",
        "RETURNS BREAKDOWN:",
        "-" * W,
    ]

    for sym in WHEEL_STOCKS:
        s = sm.get(sym)
        if not s:
            continue
        total_coll   = s.get("total_premium_collected", 0)
        cycle_count  = s.get("cycle_count", 0)
        stock_cost   = s.get("stock_avg_cost", 0)
        stock_qty    = s.get("stock_qty", 0)
        cost_basis   = stock_cost * stock_qty if stock_qty else 0

        # Return on collateral: total premium / (strike * 100)
        strike = 0
        for h in reversed(s.get("history", [])):
            if h.get("strike"):
                strike = h["strike"]
                break
        collateral = strike * 100 if strike else 0
        ret_on_col = (total_coll / collateral * 100) if collateral > 0 else 0

        lines.append(
            f"  {sym:<6} | ${total_coll:.2f} total premium "
            f"| {cycle_count} cycles "
            f"| {ret_on_col:.1f}% return on collateral"
        )

    # ── Column legend ────────────────────────────────────────────────────────
    lines += [
        "",
        "LEGEND:",
        "  ENTRY    = Premium received/share when option was sold",
        "  NOW      = Current option market price (cost to close now)",
        "  P&L$     = Profit if position closed right now (per contract)",
        "  P&L%     = % of maximum possible profit captured",
        "  COLLECTED= Total premium collected for this symbol (all cycles)",
        "  POTENTIAL= Additional profit if current option expires worthless",
        "  STAGE    = IDLE (looking) | CSP (short put) | CC (covered call)",
        "=" * W,
    ]

    return "\n".join(lines)


def run():
    log.info("Generating daily wheel strategy report...")
    try:
        report_text = build_report()
        print(report_text)

        notifier.send_email(
            subject=f"[Flywheel] Daily Report -- {datetime.now().strftime('%Y-%m-%d')}",
            body=report_text,
            to=NOTIFY_EMAIL,
            smtp_host=SMTP_HOST, smtp_port=SMTP_PORT,
            smtp_user=SMTP_USER, smtp_password=SMTP_PASSWORD,
        )
        log.info("Report emailed to %s", NOTIFY_EMAIL)

        # Save report to file
        report_path = os.path.join(
            LOG_DIR, f"report_{datetime.now().strftime('%Y%m%d')}.txt"
        )
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(report_text)
        log.info("Report saved to %s", report_path)

    except Exception as e:
        log.error("Report generation failed: %s", e, exc_info=True)


if __name__ == "__main__":
    run()
