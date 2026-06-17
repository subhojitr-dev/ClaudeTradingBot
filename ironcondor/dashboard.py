"""
dashboard.py  --  Live terminal view of the active Iron Condor
Run manually any time: python dashboard.py
"""

import json
from datetime import date
import alpaca_client as ac
import state_manager as sm
import config


def fmt_pnl(n):
    return f"+${n:.2f}" if n >= 0 else f"-${abs(n):.2f}"


def run():
    state   = sm.load(config.STATE_FILE)
    active  = state["active"]
    history = state["history"]

    spy = ac.get_spy_price()
    print(f"\n{'='*72}")
    print(f"  IRON CONDOR DASHBOARD — {date.today()}   SPY=${spy:.2f}")
    print(f"{'='*72}")

    if not active:
        print("\n  No active condor.\n")
    else:
        pos    = active[config.SYMBOL]
        expiry = pos["expiry"]
        dtr    = (date.fromisoformat(expiry) - date.today()).days

        print(f"\n  Status   : {pos['status']}")
        print(f"  Entry    : {pos['entry_date']}  (SPY was ${pos['spy_price_at_entry']:.2f})")
        print(f"  Expiry   : {expiry}  ({dtr} days remaining)")
        print(f"  Net credit collected: ${pos['net_credit']:.2f}/share  (${pos['net_credit']*100:.0f} total)")
        print(f"  Max risk            : ${pos['max_risk']:.2f}/share    (${pos['max_risk']*100:.0f} total)\n")

        # Bull Put Spread
        print(f"  ── Bull Put Spread ─────────────────────────────────────────")
        snaps_put = ac.get_option_snapshots([pos["short_put"], pos["long_put"]])
        sp_snap = snaps_put.get(pos["short_put"], {})
        lp_snap = snaps_put.get(pos["long_put"],  {})
        sp_mid  = ac.mid(sp_snap)
        lp_mid  = ac.mid(lp_snap)
        sp_d    = ac.delta(sp_snap)
        put_cost_to_close = sp_mid - lp_mid
        put_entry_credit  = pos["short_put_credit"] - pos["long_put_debit"]
        put_pnl_pct       = (1 - put_cost_to_close / put_entry_credit) * 100 if put_entry_credit else 0

        adj_tag = "  [ADJUSTED]" if pos.get("put_adjusted") else ""
        print(f"  Sell {pos['short_put_strike']:.0f}P  {pos['short_put']:<26}  "
              f"entry=${pos['short_put_credit']:.2f}  now=${sp_mid:.2f}  Δ={sp_d:.3f}{adj_tag}")
        print(f"  Buy  {pos['long_put_strike']:.0f}P  {pos['long_put']:<26}  "
              f"entry=${pos['long_put_debit']:.2f}  now=${lp_mid:.2f}")
        print(f"  Put spread P&L: {put_pnl_pct:+.0f}% of max profit captured\n")

        # Bear Call Spread
        print(f"  ── Bear Call Spread ────────────────────────────────────────")
        snaps_call = ac.get_option_snapshots([pos["short_call"], pos["long_call"]])
        sc_snap = snaps_call.get(pos["short_call"], {})
        lc_snap = snaps_call.get(pos["long_call"],  {})
        sc_mid  = ac.mid(sc_snap)
        lc_mid  = ac.mid(lc_snap)
        sc_d    = ac.delta(sc_snap)
        call_cost_to_close = sc_mid - lc_mid
        call_entry_credit  = pos["short_call_credit"] - pos["long_call_debit"]
        call_pnl_pct       = (1 - call_cost_to_close / call_entry_credit) * 100 if call_entry_credit else 0

        adj_tag = "  [ADJUSTED]" if pos.get("call_adjusted") else ""
        print(f"  Sell {pos['short_call_strike']:.0f}C  {pos['short_call']:<26}  "
              f"entry=${pos['short_call_credit']:.2f}  now=${sc_mid:.2f}  Δ={sc_d:.3f}{adj_tag}")
        print(f"  Buy  {pos['long_call_strike']:.0f}C  {pos['long_call']:<26}  "
              f"entry=${pos['long_call_debit']:.2f}  now=${lc_mid:.2f}")
        print(f"  Call spread P&L: {call_pnl_pct:+.0f}% of max profit captured\n")

        # Overall P&L
        total_cost_to_close = put_cost_to_close + call_cost_to_close
        pnl_per_share       = pos["net_credit"] - total_cost_to_close
        pnl_total           = pnl_per_share * 100
        pct_of_max          = (1 - total_cost_to_close / pos["net_credit"]) * 100 if pos["net_credit"] else 0

        print(f"  ── Combined ────────────────────────────────────────────────")
        print(f"  Cost to close now : ${total_cost_to_close:.2f}/share")
        print(f"  Net P&L now       : {fmt_pnl(pnl_per_share)}/share  ({fmt_pnl(pnl_total)} total)")
        print(f"  % of max profit   : {pct_of_max:+.0f}%")
        print(f"  Profit target     : 50% = close when P&L = ${pos['net_credit']*0.50*100:.0f}")
        print(f"  Adjustment trigger: either short Δ reaches 0.45")
        if sp_d >= 0.35 or sc_d >= 0.35:
            print(f"\n  ⚠ WARNING: Short strike delta approaching trigger"
                  f" (put Δ={sp_d:.3f}  call Δ={sc_d:.3f})")

        if pos["adjustment_log"]:
            print(f"\n  Adjustment history:")
            for adj in pos["adjustment_log"]:
                print(f"    {adj['date']}  {adj['side'].upper()} rolled "
                      f"from ${adj['old_short'][-8:]} → ${adj['new_short_strike']:.0f}  "
                      f"roll_credit=${adj['roll_credit']:.2f}")

    if history:
        print(f"\n{'='*72}")
        print(f"  CLOSED TRADES  ({len(history)} total)")
        print(f"{'='*72}")
        total = 0
        for h in history[-10:]:
            pnl = h.get("net_pnl", 0) or 0
            total += pnl
            print(f"  {h.get('entry_date','?')} → {h.get('close_date','?')}  "
                  f"expiry={h.get('expiry','?')}  "
                  f"P&L={fmt_pnl(pnl):>10}  "
                  f"{h.get('close_reason','')}")
        print(f"\n  Last {min(len(history),10)} trades net P&L: {fmt_pnl(total)}")
    print()


if __name__ == "__main__":
    run()
