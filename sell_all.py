"""
sell_all.py — Emergency liquidation script
Sells ALL open positions in BOTH Alpaca paper accounts.
Run once to clear the slate before a fresh start.

Credentials are read from each bot's config.py (gitignored).
"""

import requests
import sys
import time

# Pull credentials from the two bot configs
sys.path.insert(0, "trailing_stop")
import config as cfg1
sys.path.pop(0)

sys.path.insert(0, "flywheel")
import config as cfg2
sys.path.pop(0)

ACCOUNTS = [
    {
        "name":       "Claude Trading (PA31HKOPMG4M) — Trailing Stop + Copy Trade",
        "api_key":    cfg1.ALPACA_API_KEY,
        "secret_key": cfg1.ALPACA_SECRET_KEY,
        "base_url":   cfg1.ALPACA_BASE_URL,
    },
    {
        "name":       "Paper Trading (PA34EFPV3B80) — Flywheel / Options",
        "api_key":    cfg2.ALPACA_API_KEY,
        "secret_key": cfg2.ALPACA_SECRET_KEY,
        "base_url":   cfg2.ALPACA_BASE_URL,
    },
]


def headers(acct):
    return {
        "APCA-API-KEY-ID":     acct["api_key"],
        "APCA-API-SECRET-KEY": acct["secret_key"],
    }


def close_all(acct):
    print(f"\n{'='*60}")
    print(f"  {acct['name']}")
    print(f"{'='*60}")

    # Cancel all open orders first
    r = requests.delete(f"{acct['base_url']}/orders", headers=headers(acct))
    if r.ok:
        cancelled = r.json() if r.text else []
        print(f"  Cancelled {len(cancelled) if isinstance(cancelled, list) else 0} open orders.")
    else:
        print(f"  Order cancel: {r.status_code} {r.text[:100]}")

    time.sleep(1)

    # Get all positions
    r = requests.get(f"{acct['base_url']}/positions", headers=headers(acct))
    if not r.ok:
        print(f"  ERROR fetching positions: {r.status_code} {r.text[:100]}")
        return
    positions = r.json()

    if not positions:
        print("  No open positions.")
        return

    print(f"  Found {len(positions)} position(s) — closing all...")

    # Close all via bulk endpoint
    r = requests.delete(
        f"{acct['base_url']}/positions",
        headers=headers(acct),
        params={"cancel_orders": True},
    )
    if r.ok:
        results = r.json() if r.text else []
        print(f"  Close-all submitted. {len(results) if isinstance(results, list) else '?'} position(s) sent.")
    else:
        print(f"  Close-all ERROR: {r.status_code} {r.text[:200]}")


def run():
    print("\n" + "!"*60)
    print("  EMERGENCY LIQUIDATION — SELL ALL POSITIONS")
    print("!"*60)
    print("\n  This will close ALL positions in BOTH accounts.")
    confirm = input("  Type YES to confirm: ").strip()
    if confirm != "YES":
        print("  Aborted.")
        return

    for acct in ACCOUNTS:
        close_all(acct)

    print(f"\n{'='*60}")
    print("  Done. Check Alpaca dashboards to confirm all positions closed.")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    run()
