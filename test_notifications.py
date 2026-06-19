# test_notifications.py -- Send one sample email for every notification type
#
# Run: cd C:/Users/subho/tradingbot && python test_notifications.py
#
# Sends real emails to NOTIFY_EMAIL and saves HTML to email_archive/.
# No Alpaca API calls, no market needed.

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "ironcondor"))
import config as ic_cfg

class _Cfg:
    NOTIFY_EMAIL  = ic_cfg.NOTIFY_EMAIL
    SMTP_HOST     = ic_cfg.SMTP_HOST
    SMTP_PORT     = ic_cfg.SMTP_PORT
    SMTP_USER     = ic_cfg.SMTP_USER
    SMTP_PASSWORD = ic_cfg.SMTP_PASSWORD

cfg = _Cfg()

print("=" * 62)
print("  TradingBot - Notification Test Run")
print("  Sending sample email for every notification type")
print("=" * 62)
print()


# ----------------------------------------------------------------------
#  1. IRON CONDOR
# ----------------------------------------------------------------------
print("-- Iron Condor ----------------------------------------------")

import notifier as ic_notifier

print("  [1/4] Condor opened (SPY)...")
ic_notifier.notify_condor_opened(
    symbol="SPY",
    spy_price=547.32,
    expiry="2026-07-03",
    sp_strike=520.0, sp_delta=0.18, sp_credit=1.45,
    sc_strike=575.0, sc_delta=0.17, sc_credit=1.30,
    lp_strike=515.0, lc_strike=580.0,
    lp_debit=0.55, lc_debit=0.50,
    net_credit=1.70, max_risk=3.30, credit_ratio=0.34,
    trend="neutral",
    sr_notes="trend=neutral  support=$518,$505  resistance=$560,$575  MA50=$541.2",
    support_levels=[518.0, 505.0, 492.0],
    resistance_levels=[560.0, 575.0, 588.0],
)

print("  [2/4] Adjustment -- put side rolled...")
ic_notifier.notify_adjustment(
    symbol="SPY",
    side="put",
    old_short_strike=520.0,
    new_short_strike=510.0,
    new_long_strike=505.0,
    roll_credit=0.12,
    days_remaining=9,
    spy_price=521.80,
    current_pnl_pct=-45,
    cumulative_credit=1.82,
)

print("  [3/4] Condor closed -- profit...")
ic_notifier.notify_closed(
    symbol="IWM",
    reason="50% profit target",
    net_credit=0.70,
    cost_to_close=0.35,
    net_pnl=70.00,
    pos={
        "entry_date": "2026-06-05",
        "close_date": "2026-06-16",
        "expiry": "2026-06-19",
        "spy_price_at_entry": 210.45,
        "short_put_strike": 200.0,
        "long_put_strike": 198.0,
        "short_call_strike": 222.0,
        "long_call_strike": 224.0,
        "put_adjusted": False,
        "call_adjusted": False,
        "adjustment_log": [],
    },
)

print("  [4/4] Daily report (stub)...")
report_html = (
    '<!DOCTYPE html><html><head><meta charset="utf-8">'
    '<style>body{font-family:Arial,sans-serif;background:#f4f4f4;padding:20px;}'
    '.card{background:#fff;border-radius:8px;max-width:640px;margin:0 auto;padding:24px;box-shadow:0 2px 8px rgba(0,0,0,.12);}'
    'h2{margin:0 0 4px 0;}table{width:100%;border-collapse:collapse;font-size:14px;}'
    'th{background:#f0f0f0;padding:6px 8px;text-align:left;}td{padding:6px 8px;border-bottom:1px solid #f0f0f0;}'
    '.green{color:#1a7a1a;font-weight:bold;}.footer{margin-top:20px;font-size:11px;color:#aaa;text-align:center;}'
    '</style></head><body><div class="card">'
    '<h2>Iron Condor Daily Report</h2>'
    '<p style="color:#666;font-size:13px;">2026-06-19 (SAMPLE)</p>'
    '<table><tr><th>Symbol</th><th>Status</th><th>Credit</th><th>P&amp;L</th><th>DTE</th></tr>'
    '<tr><td>SPY</td><td>Open</td><td>$1.70</td><td class="green">+$85</td><td>14</td></tr>'
    '<tr><td>IWM</td><td>Open</td><td>$0.70</td><td class="green">+$35</td><td>14</td></tr>'
    '<tr><td>GLD</td><td>No position</td><td>--</td><td>--</td><td>--</td></tr>'
    '</table>'
    '<div class="footer">Iron Condor Bot &mdash; Paper Trading</div>'
    '</div></body></html>'
)
ic_notifier._send(
    "TradingBot: [IronCondor] Daily Report -- 2026-06-19  SPY . IWM . GLD (SAMPLE)",
    report_html,
)
print("  Iron Condor done.\n")


# ----------------------------------------------------------------------
#  2. STRANGLE
# ----------------------------------------------------------------------
print("-- Strangle -------------------------------------------------")

for p in [p for p in sys.path if "ironcondor" in p]:
    sys.path.remove(p)
for mod in list(sys.modules.keys()):
    if mod in ("notifier", "config"):
        del sys.modules[mod]

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "strangle"))
import notifier as st_notifier

print("  [1/4] Strangle opened...")
st_notifier.notify_strangle_opened(
    symbol="NVDA",
    earnings_date="2026-07-09",
    call="NVDA260718C00160000",
    put="NVDA260718P00120000",
    call_price=3.80,
    put_price=2.95,
    total_cost=675.0,
)

print("  [2/4] Call sold pre-earnings...")
st_notifier.notify_call_sold(
    symbol="NVDA",
    contract="NVDA260718C00160000",
    entry=3.80,
    exit_price=4.57,
    gain_pct=0.203,
)

print("  [3/4] Put sold post-earnings...")
st_notifier.notify_put_sold(
    symbol="NVDA",
    contract="NVDA260718P00120000",
    entry=2.95,
    exit_price=3.28,
    gain_pct=0.112,
    net_pnl=110.00,
)

print("  [4/4] IV skip...")
st_notifier.notify_iv_skip(
    symbol="AMZN",
    iv=0.52,
    pct=74,
    threshold=50,
)
print("  Strangle done.\n")


# ----------------------------------------------------------------------
#  3. FLYWHEEL
# ----------------------------------------------------------------------
print("-- Flywheel -------------------------------------------------")

for p in [p for p in sys.path if "strangle" in p]:
    sys.path.remove(p)
for mod in list(sys.modules.keys()):
    if mod in ("notifier", "config"):
        del sys.modules[mod]

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "flywheel"))
import notifier as fw_notifier

print("  [1/10] CSP opened...")
fw_notifier.notify_csp_opened(
    symbol="AAPL", contract_sym="AAPL260717P00185000",
    strike=185.0, sell_price=1.12,
    expiry="2026-07-17", stock_price=198.45,
    cash_required=18500.0, csp_strike_discount=0.07,
    order_id="abc123def456",
)

print("  [2/10] CSP expired worthless...")
fw_notifier.notify_csp_expired(
    symbol="AAPL", entry_prem=1.12,
    total_premium=447.00, grand_total=1283.50,
)

print("  [3/10] Assigned...")
fw_notifier.notify_assigned(
    symbol="AAPL", shares=100,
    strike=185.0, entry_prem=1.12, eff_cost=183.88,
)

print("  [4/10] Put rolled up...")
fw_notifier.notify_rolled_up(
    symbol="MSFT", old_strike=415.0, new_strike=425.0,
    net_credit=0.45, expiry="2026-07-17",
)

print("  [5/10] CSP closed early (70% profit)...")
fw_notifier.notify_csp_closed_early(
    symbol="AAPL", entry_prem=1.12, current_val=0.34,
)

print("  [6/10] Covered call opened...")
fw_notifier.notify_cc_opened(
    symbol="AAPL", contract_sym="AAPL260717C00210000",
    c_strike=210.0, sell_price=0.95,
    expiry="2026-07-17", stock_price=198.45,
    delta=0.28, stock_cost=183.88,
    cc_strike_premium=0.10, order_id="xyz789uvw012",
)

print("  [7/10] Called away...")
fw_notifier.notify_called_away(
    symbol="AAPL", stock_qty=100, call_strike=210.0,
    stock_pnl=2612.0, stock_cost=183.88, entry_prem=0.95,
)

print("  [8/10] Covered call expired worthless...")
fw_notifier.notify_cc_expired(
    symbol="MSFT", entry_prem=0.95, stock_qty=100,
    total_premium=892.00,
)

print("  [9/10] Covered call closed early...")
fw_notifier.notify_cc_closed_early(
    symbol="AAPL", entry_prem=0.95, current_val=0.29, stock_qty=100,
)

print("  [10/10] Skipped -- insufficient cash...")
fw_notifier.notify_skipped(
    symbol="TSLA", cash=12430.0, cash_required=25000.0, strike=250.0,
)
print("  Flywheel done.\n")


# ----------------------------------------------------------------------
#  4. COPY TRADE + TRAILING STOP (shared notifier)
# ----------------------------------------------------------------------
print("-- Copy Trade & Trailing Stop -------------------------------")

for p in [p for p in sys.path if "flywheel" in p]:
    sys.path.remove(p)
for mod in list(sys.modules.keys()):
    if mod in ("notifier", "config"):
        del sys.modules[mod]

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import notifier as shared_notifier

print("  [1/5] Copy trade -- BUY...")
shared_notifier.notify_copy_trade(
    politician="Nancy Pelosi",
    action="buy",
    symbol="NVDA",
    qty=5,
    price_ref=0.0,
    order_id="pol_order_001",
    cfg=cfg,
)

print("  [2/5] Copy trade -- SELL...")
shared_notifier.notify_copy_trade(
    politician="Michael McCaul",
    action="sell",
    symbol="MSFT",
    qty=10,
    price_ref=0.0,
    order_id="pol_order_002",
    cfg=cfg,
)

print("  [3/5] Stop loss hit...")
shared_notifier.notify_stop_loss(
    symbol="AMGN",
    qty=50,
    price=285.40,
    stop=288.00,
    pct_from_entry=-4.2,
    order_id="stop_order_001",
    cfg=cfg,
)

print("  [4/5] Ladder in...")
shared_notifier.notify_ladder_in(
    symbol="AMGN",
    qty=25,
    price=274.10,
    drop_pct=22.4,
    ladder_num=1,
    new_stop=260.40,
    new_entry=281.20,
    order_id="ladder_order_001",
    cfg=cfg,
)

print("  [5/5] Pharma catalyst...")
shared_notifier.notify_pharma_catalyst(
    ticker="MRNA",
    event_type="FDA Approval",
    headline="FDA grants full approval to Moderna mRNA-1283 next-gen COVID vaccine",
    source="FDA RSS Feed",
    initial_qty=20,
    cfg=cfg,
)
print("  Copy Trade & Trailing Stop done.\n")


# ----------------------------------------------------------------------
#  Summary
# ----------------------------------------------------------------------
import email_archive
archive_root = os.path.join(os.path.dirname(os.path.abspath(__file__)), "email_archive")
total_files = sum(len(files) for _, _, files in os.walk(archive_root))

print("=" * 62)
print("  Test complete.")
print("  Emails sent to: " + cfg.NOTIFY_EMAIL)
print("  Archived locally: " + str(total_files) + " HTML file(s)")
print("  Archive path: " + archive_root)
print("=" * 62)
