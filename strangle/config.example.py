# ============================================================
#  Bi-Directional Strangle Strategy — Configuration Template
#  Copy this file to config.py and fill in your values.
# ============================================================

ALPACA_API_KEY    = "YOUR_ALPACA_API_KEY"
ALPACA_SECRET_KEY = "YOUR_ALPACA_SECRET_KEY"
ALPACA_BASE_URL   = "https://paper-api.alpaca.markets/v2"
ALPACA_DATA_URL   = "https://data.alpaca.markets/v2"

WATCHED_STOCKS = [
    "NVDA", "AAPL", "MSFT", "GOOGL", "AVGO",
    "AMD",  "TSLA", "META", "AMZN",  "MU",
    "PANW", "COHR", "MRVL", "RKLB",  "NBIS",
]

EARNINGS_MIN_DAYS        = 14
EARNINGS_MAX_DAYS        = 21
IV_PERCENTILE_THRESHOLD  = 50
IV_HISTORY_DAYS          = 60
LOOK_BACK_EARNINGS       = 8
MIN_QUALIFYING_EARNINGS  = 4
MIN_EARNINGS_MOVE_PCT    = 4.0

TARGET_DTE       = 90
DTE_TOLERANCE    = 14
TARGET_DELTA     = 0.30
DELTA_TOLERANCE  = 0.07

COMBINED_PROFIT_TARGET_PCT = 0.20
COMBINED_STOP_LOSS_PCT     = 0.20

POLL_HOURS         = 2
MAX_OPEN_STRANGLES = 5

NOTIFY_EMAIL  = "your@email.com"
SMTP_HOST     = "smtp.gmail.com"
SMTP_PORT     = 587
SMTP_USER     = "your@email.com"
SMTP_PASSWORD = "your gmail app password"

STATE_FILE = "strangle_state.json"
IV_CACHE   = "iv_history.json"
LOG_DIR    = "logs"
