# ============================================================
#  Copy-Trading Bot — Configuration Template
#  Copy this file to config.py and fill in your values.
# ============================================================

ALPACA_API_KEY    = "YOUR_ALPACA_API_KEY"
ALPACA_SECRET_KEY = "YOUR_ALPACA_SECRET_KEY"
ALPACA_BASE_URL   = "https://paper-api.alpaca.markets/v2"

# Politicians to monitor (Capitol Trades IDs)
POLITICIANS = [
    {"name": "Nancy Pelosi",   "ct_id": "P000197"},
    {"name": "Michael McCaul", "ct_id": "M001157"},
]

MAX_COPY_POSITIONS = 10
STOCK_QTY          = 10
OPTION_CONTRACTS   = 1

NOTIFY_EMAIL  = "your@email.com"
SMTP_HOST     = "smtp.gmail.com"
SMTP_PORT     = 587
SMTP_USER     = "your@email.com"
SMTP_PASSWORD = "your gmail app password"

TRACKER_FILE = "trades_tracker.json"
LOG_DIR      = "logs"
