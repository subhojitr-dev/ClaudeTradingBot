"""
topup_check.py  --  Daily Balance Top-Up Checker
=================================================
Runs every weekday at 9:25 AM (5 min before market open).

What it does:
1. Pulls current cash balance from Alpaca paper account
2. If cash < $100,000, calculates the shortfall
3. Records it in topup_log.json
4. Prints a clear alert with EXACT dashboard steps to top up
5. Opens the Alpaca dashboard in your browser automatically

Why we can't do it automatically:
Alpaca's retail paper trading API does not expose a cash-injection
endpoint. Only the Broker-level API supports journaling, which requires
separate broker credentials. This script is the best practical solution.
"""

import json
import os
import sys
import webbrowser
import requests
import subprocess
from datetime import datetime, timezone, date

# ── Config ─────────────────────────────────────────────────────────────────────
from config import (
    ALPACA_API_KEY, ALPACA_SECRET_KEY, ALPACA_BASE_URL,
    TARGET_CASH, LOG_FILE, LOG_DIR,
)

DASHBOARD_URL = "https://app.alpaca.markets/paper/dashboard/overview"

HEADERS = {
    "APCA-API-KEY-ID":     ALPACA_API_KEY,
    "APCA-API-SECRET-KEY": ALPACA_SECRET_KEY,
}

os.makedirs(LOG_DIR, exist_ok=True)


# ── Helpers ────────────────────────────────────────────────────────────────────

def get_account():
    r = requests.get(f"{ALPACA_BASE_URL}/account", headers=HEADERS)
    r.raise_for_status()
    return r.json()


def load_log():
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE) as f:
            return json.load(f)
    return {"checks": [], "total_manual_topup_needed": 0.0}


def save_log(data):
    with open(LOG_FILE, "w") as f:
        json.dump(data, f, indent=2, default=str)


def already_checked_today(log_data):
    """Return True if we already ran a check today."""
    today = date.today().isoformat()
    return any(c.get("date") == today for c in log_data.get("checks", []))


def show_alert(current_cash, shortfall):
    """Print a very visible alert with exact manual steps."""
    bar  = "!" * 62
    bar2 = "=" * 62
    msg = f"""
{bar}
  LOW CASH ALERT  --  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
{bar}

  Account   : PA31HKOPMG4M  (Alpaca Paper Trading)
  Cash Now  : ${current_cash:>12,.2f}
  Target    : ${TARGET_CASH:>12,.2f}
  SHORTFALL : ${shortfall:>12,.2f}  <-- add this amount

{bar2}
  HOW TO TOP UP (takes 60 seconds):
{bar2}

  STEP 1: The Alpaca dashboard will open in your browser now.
          (or go to: https://app.alpaca.markets)

  STEP 2: Make sure top-left shows "Paper - PA31HKOPMG4M"
          If not, click the dropdown and switch to that account.

  STEP 3: Click your account number/name in the TOP LEFT corner

  STEP 4: Look for one of these options in the dropdown menu:
          --> "Add Paper Money"
          --> "Fund Account"
          --> "Deposit"
          --> "Manage Paper Account"

  STEP 5: Enter ${shortfall:,.2f} and confirm.

  ALTERNATIVE -- Create a new paper account with $100K:
  STEP 3: Click the dropdown --> "Open New Paper Account"
          This gives you a fresh $100K (different account number)
          Your current positions stay in the old account.

{bar}
  Opening Alpaca dashboard in your browser now...
{bar}
"""
    print(msg)

    # Write to daily log file too
    log_path = os.path.join(LOG_DIR, f"topup_{date.today().isoformat()}.log")
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(msg)

    # Open browser
    try:
        webbrowser.open(DASHBOARD_URL)
        print("  Browser opened: " + DASHBOARD_URL)
    except Exception as e:
        print(f"  Could not open browser automatically: {e}")
        print(f"  Please open manually: {DASHBOARD_URL}")

    # Also show a Windows toast notification
    try:
        toast_script = f'''
Add-Type -AssemblyName System.Windows.Forms
$notify = New-Object System.Windows.Forms.NotifyIcon
$notify.Icon = [System.Drawing.SystemIcons]::Warning
$notify.Visible = $true
$notify.ShowBalloonTip(10000, "Alpaca Low Cash Alert", "Cash: ${current_cash:,.0f} | Add ${shortfall:,.0f} to reach $100,000. Dashboard opening now.", [System.Windows.Forms.ToolTipIcon]::Warning)
Start-Sleep -Seconds 5
$notify.Dispose()
'''
        subprocess.run(
            ["powershell.exe", "-Command", toast_script],
            capture_output=True, timeout=10
        )
    except Exception:
        pass   # toast is nice-to-have, not critical


def show_ok(current_cash):
    print(f"""
{'='*62}
  BALANCE CHECK OK  --  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
{'='*62}
  Account   : PA31HKOPMG4M
  Cash Now  : ${current_cash:>12,.2f}
  Target    : ${TARGET_CASH:>12,.2f}
  Status    : SUFFICIENT -- no top-up needed today
{'='*62}
""")


# ── Main ───────────────────────────────────────────────────────────────────────

def run():
    print(f"\n{'='*62}")
    print(f"  DAILY TOP-UP CHECK  --  {datetime.now(timezone.utc).isoformat()}")
    print(f"{'='*62}")

    # Load persistent log
    log_data = load_log()

    # Avoid running twice in one day
    if already_checked_today(log_data):
        print("  Already checked today -- skipping.")
        return

    # Pull account
    try:
        acct = get_account()
    except Exception as e:
        print(f"  ERROR: Cannot reach Alpaca API: {e}")
        sys.exit(1)

    current_cash   = float(acct["cash"])
    portfolio_val  = float(acct["portfolio_value"])
    buying_power   = float(acct["buying_power"])
    shortfall      = max(0.0, TARGET_CASH - current_cash)

    print(f"  Cash:          ${current_cash:>12,.2f}")
    print(f"  Portfolio:     ${portfolio_val:>12,.2f}")
    print(f"  Buying Power:  ${buying_power:>12,.2f}")
    print(f"  Target Cash:   ${TARGET_CASH:>12,.2f}")
    print(f"  Shortfall:     ${shortfall:>12,.2f}")

    # Log this check
    check_record = {
        "date":          date.today().isoformat(),
        "time_utc":      datetime.now(timezone.utc).isoformat(),
        "cash":          current_cash,
        "portfolio":     portfolio_val,
        "buying_power":  buying_power,
        "shortfall":     shortfall,
        "action_needed": shortfall > 0,
    }
    log_data["checks"].append(check_record)
    log_data["total_manual_topup_needed"] = sum(
        c["shortfall"] for c in log_data["checks"]
    )
    save_log(log_data)

    # Alert or confirm
    if shortfall > 0:
        show_alert(current_cash, shortfall)
    else:
        show_ok(current_cash)

    # Print running history
    print(f"\n  --- Top-Up History (last 10 days) ---")
    recent = log_data["checks"][-10:]
    for c in recent:
        status = f"  NEED +${c['shortfall']:,.2f}" if c["shortfall"] > 0 else "  OK"
        print(f"  {c['date']}  Cash=${c['cash']:>10,.2f}  {status}")
    total = log_data["total_manual_topup_needed"]
    print(f"\n  Total top-ups needed since tracking started: ${total:,.2f}")
    print(f"{'='*62}\n")


if __name__ == "__main__":
    run()
