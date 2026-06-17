"""
dashboard.py  –  Quick status dashboard for the copy-trading bot.
Run: python dashboard.py

Shows:
  - Alpaca account summary
  - Current positions
  - All orders placed by the bot (from tracker)
  - Last N trades seen on Capitol Trades
"""

import json
import os
import sys
from datetime import datetime, timezone

# Allow running from any working directory
os.chdir(os.path.dirname(os.path.abspath(__file__)))

from alpaca_client import get_account, get_positions, get_open_orders, is_market_open
from trade_tracker import TradeTracker
from config import POLITICIAN_NAME, TRACKER_FILE


def hr(char="─", width=60):
    print(char * width)


def run():
    print()
    hr("═")
    print(f"  COPY-TRADING BOT DASHBOARD")
    print(f"  Target: {POLITICIAN_NAME}")
    print(f"  Time:   {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    hr("═")

    # ── Market status ───────────────────────────────────────────
    try:
        open_flag = is_market_open()
        status = "🟢 OPEN" if open_flag else "🔴 CLOSED"
        print(f"\n  Market Status: {status}")
    except Exception as e:
        print(f"\n  Market Status: ERROR ({e})")

    # ── Account summary ─────────────────────────────────────────
    try:
        acct = get_account()
        print(f"\n{'─'*60}")
        print(f"  ACCOUNT SUMMARY  (Paper Trading)")
        print(f"{'─'*60}")
        print(f"  Account #:      {acct.get('account_number')}")
        print(f"  Portfolio Value: ${float(acct.get('portfolio_value', 0)):>12,.2f}")
        print(f"  Buying Power:    ${float(acct.get('buying_power', 0)):>12,.2f}")
        print(f"  Cash:            ${float(acct.get('cash', 0)):>12,.2f}")
        today_pl = float(acct.get('equity', 0)) - float(acct.get('last_equity', 0))
        print(f"  Today's P&L:     ${today_pl:>+12,.2f}")
    except Exception as e:
        print(f"\n  Could not fetch account: {e}")

    # ── Current positions ────────────────────────────────────────
    try:
        positions = get_positions()
        print(f"\n{'─'*60}")
        print(f"  CURRENT POSITIONS ({len(positions)} total)")
        print(f"{'─'*60}")
        if positions:
            print(f"  {'Symbol':<12} {'Qty':>6}  {'Avg Cost':>10}  {'Mkt Val':>12}  {'P&L':>10}")
            print(f"  {'-'*12} {'-'*6}  {'-'*10}  {'-'*12}  {'-'*10}")
            for p in positions:
                print(
                    f"  {p['symbol']:<12} {p['qty']:>6}  "
                    f"${float(p['avg_entry_price']):>9,.2f}  "
                    f"${float(p['market_value']):>11,.2f}  "
                    f"${float(p['unrealized_pl']):>+9,.2f}"
                )
        else:
            print("  (no open positions)")
    except Exception as e:
        print(f"\n  Could not fetch positions: {e}")

    # ── Open orders ──────────────────────────────────────────────
    try:
        orders = get_open_orders()
        if orders:
            print(f"\n{'─'*60}")
            print(f"  OPEN ORDERS ({len(orders)})")
            print(f"{'─'*60}")
            for o in orders:
                print(
                    f"  {o['side'].upper():<5} {o['symbol']:<12} "
                    f"qty={o['qty']}  status={o['status']}"
                )
    except Exception as e:
        print(f"\n  Could not fetch orders: {e}")

    # ── Bot trade history ────────────────────────────────────────
    tracker = TradeTracker(TRACKER_FILE)
    orders_placed = tracker._data.get("orders_placed", [])

    print(f"\n{'─'*60}")
    print(f"  BOT TRADE HISTORY  ({len(orders_placed)} orders placed)")
    print(f"{'─'*60}")
    if orders_placed:
        recent = orders_placed[-20:]  # last 20
        for rec in reversed(recent):
            ts = rec.get("timestamp", "")[:19].replace("T", " ")
            print(
                f"  {ts}  {rec.get('ct_action','').upper():<5}  "
                f"{rec.get('alpaca_symbol',''):<15}  "
                f"qty={rec.get('alpaca_qty','')}  "
                f"[{rec.get('alpaca_status','')}]"
            )
    else:
        print("  (no orders placed yet)")

    print(f"\n{'═'*60}\n")


if __name__ == "__main__":
    run()
