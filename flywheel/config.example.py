# ============================================================
#  Wheel Strategy Bot — Configuration Template
#  Copy this file to config.py and fill in your values.
# ============================================================

ALPACA_API_KEY    = "YOUR_ALPACA_API_KEY"
ALPACA_SECRET_KEY = "YOUR_ALPACA_SECRET_KEY"
ALPACA_BASE_URL   = "https://paper-api.alpaca.markets/v2"
ALPACA_DATA_URL   = "https://data.alpaca.markets/v2"

WHEEL_STOCKS        = ["AVGO", "COHR", "NBIS", "GLW"]

CSP_STRIKE_DISCOUNT = 0.20
CSP_MIN_DTE         = 14
CSP_MAX_DTE         = 28
CSP_CONTRACTS       = 1

CC_STRIKE_PREMIUM   = 0.10
CC_MIN_DTE          = 14
CC_MAX_DTE          = 28
CC_CONTRACTS        = 1

PROFIT_TARGET_PCT   = 0.70
MIN_PREMIUM         = 0.50
MAX_DELTA           = 0.25
FLYWHEEL_MIN_CASH   = 20000

NOTIFY_EMAIL  = "your@email.com"
SMTP_HOST     = "smtp.gmail.com"
SMTP_PORT     = 587
SMTP_USER     = "your@email.com"
SMTP_PASSWORD = "your gmail app password"

STATE_FILE = "wheel_state.json"
LOG_DIR    = "logs"
