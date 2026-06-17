# ============================================================
#  Daily Top-Up Check — Configuration Template
#  Copy this file to config.py and fill in your values.
# ============================================================

ALPACA_API_KEY    = "YOUR_ALPACA_API_KEY"
ALPACA_SECRET_KEY = "YOUR_ALPACA_SECRET_KEY"
ALPACA_BASE_URL   = "https://paper-api.alpaca.markets/v2"

TARGET_CASH = 100_000.00   # alert if cash drops below this
LOG_FILE    = "topup_log.json"
LOG_DIR     = "logs"

NOTIFY_EMAIL  = "your@email.com"
SMTP_HOST     = "smtp.gmail.com"
SMTP_PORT     = 587
SMTP_USER     = "your@email.com"
SMTP_PASSWORD = "your gmail app password"
