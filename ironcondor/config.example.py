# ============================================================
#  Iron Condor Strategy — Configuration Template
#  Copy this file to config.py and fill in your values.
# ============================================================

ALPACA_API_KEY    = "YOUR_ALPACA_API_KEY"
ALPACA_SECRET_KEY = "YOUR_ALPACA_SECRET_KEY"
ALPACA_BASE_URL   = "https://paper-api.alpaca.markets/v2"
ALPACA_DATA_URL   = "https://data.alpaca.markets/v2"

SYMBOL = "SPY"

TARGET_DTE         = 14
DTE_TOLERANCE      =  2
MAX_SHORT_DELTA    = 0.20
WING_WIDTH         = 5

USE_SR_LEVELS      = True
SR_LOOKBACK_DAYS   = 60
SR_SWING_WINDOW    = 5
SR_MAX_DISTANCE    = 0.08

USE_TREND_BIAS     = True
TREND_NEUTRAL_BAND = 0.01

MIN_CREDIT_RATIO   = 0.33
ADJUST_DELTA       = 0.45
MIN_DTE_FOR_ADJUST = 4
PROFIT_TARGET_PCT  = 0.50
MAX_LOSS_RATIO     = 2.00

CONDOR_QTY       = 1
MAX_OPEN_CONDORS = 1

NOTIFY_EMAIL  = "your@email.com"
SMTP_HOST     = "smtp.gmail.com"
SMTP_PORT     = 587
SMTP_USER     = "your@email.com"
SMTP_PASSWORD = "your gmail app password"

STATE_FILE = "ironcondor_state.json"
LOG_DIR    = "logs"
