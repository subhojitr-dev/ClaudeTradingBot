"""
dashboard.py  --  Terminal P&L summary for all active strangles
Run manually: python dashboard.py
"""

import json
import os
from datetime import date
import alpaca_client as ac
import state_manager as sm
import config


def fmt(n, prefix="$"):
    sign = "+" if n >= 0 else "-"
    return f"{sign}{prefix}{abs(n):.2f}"


def run():
    state = sm.load(config.STATE_FILE)
    active = state["active"]
    history = state["history"]

    if not active:
        print("\n  No active strangles.\n")
    else:
        print(f"\n{'='*80}")
        print(f"  ACTIVE STRANGLES — {date.today()}")
        print(f"{'='*80}")
        hdr = f"{'SYM':<7} {'PHASE':<14} {'EARNDATE':<11} {'CALL CONTRACT':<26} {'PUT CONTRACT':<26} {'COST':>8} {'PROCEEDS':>10}"
        print(hdr)
        print("-" * 80)
        for sym, pos in active.items():
            print(
                f"{sym:<7} {pos['phase']:<14} {pos['earnings_date']:<11} "
                f"{pos['call_contract']:<26} {pos['put_contract']:<26} "
                f"${pos['total_cost']:>7.2f} ${pos['total_proceeds']:>9.2f}"
            )
        print()

        # Live prices
        for sym, pos in active.items():
            legs = []
            if pos["call_sold_price"] is None:
                snap = ac.get_option_snapshot(pos["call_contract"])
                mid  = ac.extract_mid(snap)
                gain = (mid - pos["call_entry_price"]) / pos["call_entry_price"] * 100 if mid else 0
                legs.append(f"  CALL {pos['call_contract']}: entry ${pos['call_entry_price']:.2f}  now ${mid:.2f}  ({'+' if gain>=0 else ''}{gain:.1f}%)")
            else:
                legs.append(f"  CALL SOLD @ ${pos['call_sold_price']:.2f} on {pos['call_sold_date']}")

            if pos["put_sold_price"] is None:
                snap = ac.get_option_snapshot(pos["put_contract"])
                mid  = ac.extract_mid(snap)
                gain = (mid - pos["put_entry_price"]) / pos["put_entry_price"] * 100 if mid else 0
                legs.append(f"  PUT  {pos['put_contract']}: entry ${pos['put_entry_price']:.2f}  now ${mid:.2f}  ({'+' if gain>=0 else ''}{gain:.1f}%)")
            else:
                legs.append(f"  PUT  SOLD @ ${pos['put_sold_price']:.2f} on {pos['put_sold_date']}")

            print(f"  {sym}:")
            for l in legs:
                print(l)
            print()

    if history:
        print(f"{'='*80}")
        print(f"  CLOSED TRADES ({len(history)} total)")
        print(f"{'='*80}")
        total_pnl = 0
        for pos in history[-10:]:
            status = pos.get("status", "?")
            pnl    = pos.get("net_pnl", 0)
            total_pnl += pnl
            print(f"  {pos.get('call_contract','?')[:8]:>8}  {status:<12}  "
                  f"earnings={pos.get('earnings_date','')}  P&L={fmt(pnl)}")
        print(f"\n  Last {min(len(history),10)} trades net P&L: {fmt(total_pnl)}")
        print()


if __name__ == "__main__":
    run()
