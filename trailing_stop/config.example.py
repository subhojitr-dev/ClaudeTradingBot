# ============================================================
#  Trailing Stop Strategy — Configuration Template
#  Copy this file to config.py and fill in your values.
# ============================================================

ALPACA_API_KEY    = "YOUR_ALPACA_API_KEY"
ALPACA_SECRET_KEY = "YOUR_ALPACA_SECRET_KEY"
ALPACA_BASE_URL   = "https://paper-api.alpaca.markets/v2"
ALPACA_DATA_URL   = "https://data.alpaca.markets/v2"

# Trailing stop percentage (e.g. 0.05 = 5%)
TRAILING_STOP_PCT = 0.05

# Stocks to trade
WATCHLIST = ["AAPL", "MSFT", "NVDA"]

# Email notifications
NOTIFY_EMAIL  = "your@email.com"
SMTP_HOST     = "smtp.gmail.com"
SMTP_PORT     = 587
SMTP_USER     = "your@email.com"
SMTP_PASSWORD = "your gmail app password"
