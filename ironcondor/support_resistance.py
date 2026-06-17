"""
support_resistance.py  --  Identify SPY support and resistance levels

Three sources are combined and ranked by "strength" (how many times the level
has been touched / how recently it formed):

  1. Swing highs / swing lows from recent daily candles
     A swing high is a candle whose HIGH is the highest in a ±N candle window.
     A swing low is a candle whose LOW is the lowest in a ±N candle window.

  2. Key moving averages (20-day, 50-day, 200-day SMA)
     These act as dynamic support/resistance and are widely watched by traders.

  3. Round-number psychological levels
     SPY traders strongly respect $5 and $10 increments. These are always in
     the output when they are near the current price.

Output is a dict:
  {
    "price":      540.12,          # current SPY price
    "resistance": [542.0, 548.5, 555.0],   # sorted ascending, nearest first
    "support":    [535.0, 528.0, 520.0],   # sorted descending, nearest first
    "ma20":       539.4,
    "ma50":       532.1,
    "ma200":      510.8,
    "trend":      "above_ma50" | "below_ma50" | "neutral",
  }

Call:  analyse(symbol, lookback_days, swing_window, max_distance_pct)
"""

import logging
from datetime import date, timedelta

log = logging.getLogger(__name__)

try:
    import yfinance as yf
except ImportError:
    yf = None
    log.warning("yfinance not installed — run: pip install yfinance")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _round_to_nearest(value: float, increment: float) -> float:
    return round(round(value / increment) * increment, 2)


def _swing_highs_lows(hist, window: int) -> tuple[list, list]:
    """
    Return (swing_highs, swing_lows) as lists of price levels.
    A swing high: the High at index i is the max High in [i-window, i+window].
    A swing low:  the Low  at index i is the min Low  in [i-window, i+window].
    """
    highs_col = hist["High"].values
    lows_col  = hist["Low"].values
    n         = len(highs_col)

    swing_highs = []
    swing_lows  = []

    for i in range(window, n - window):
        window_highs = highs_col[i - window: i + window + 1]
        window_lows  = lows_col[i - window: i + window + 1]
        if highs_col[i] == max(window_highs):
            swing_highs.append(round(float(highs_col[i]), 2))
        if lows_col[i] == min(window_lows):
            swing_lows.append(round(float(lows_col[i]), 2))

    return swing_highs, swing_lows


def _cluster_levels(levels: list, tolerance: float = 1.5) -> list:
    """
    Merge price levels that are within `tolerance` points of each other.
    Returns one representative level per cluster (the mean).
    """
    if not levels:
        return []
    levels = sorted(levels)
    clusters = [[levels[0]]]
    for lvl in levels[1:]:
        if lvl - clusters[-1][-1] <= tolerance:
            clusters[-1].append(lvl)
        else:
            clusters.append([lvl])
    return [round(sum(c) / len(c), 2) for c in clusters]


def _psychological_levels(price: float, band_pct: float) -> list:
    """Return $5-increment round numbers within band_pct of price."""
    lo  = price * (1 - band_pct)
    hi  = price * (1 + band_pct)
    lvl = _round_to_nearest(lo, 5)
    levels = []
    while lvl <= hi:
        levels.append(round(lvl, 2))
        lvl += 5
    return levels


# ── Main Analysis ─────────────────────────────────────────────────────────────

def analyse(
    symbol: str       = "SPY",
    lookback_days: int = 60,
    swing_window: int  = 5,
    max_distance: float = 0.08,
) -> dict | None:
    """
    Identify support and resistance levels for `symbol`.

    Returns the SR dict described in the module docstring, or None on error.
    """
    if yf is None:
        log.error("yfinance not available — cannot compute S/R levels")
        return None

    try:
        tk   = yf.Ticker(symbol)
        hist = tk.history(period=f"{lookback_days + 50}d", interval="1d")
        if hist.empty:
            log.error("No price history returned for %s", symbol)
            return None

        # Trim to lookback window
        hist = hist.tail(lookback_days)

        price = float(hist["Close"].iloc[-1])

        # ── Moving averages ──────────────────────────────────────────────────
        full_hist = tk.history(period="1y", interval="1d")
        closes    = full_hist["Close"]
        ma20  = float(closes.rolling(20).mean().iloc[-1])
        ma50  = float(closes.rolling(50).mean().iloc[-1])
        ma200 = float(closes.rolling(200).mean().iloc[-1])

        # ── Swing highs/lows ─────────────────────────────────────────────────
        swing_highs, swing_lows = _swing_highs_lows(hist, swing_window)

        # ── Psychological levels ─────────────────────────────────────────────
        psych = _psychological_levels(price, max_distance)

        # ── Build resistance list (above price) ──────────────────────────────
        resistance_candidates = []
        resistance_candidates += [h for h in swing_highs if h > price]
        resistance_candidates += [m for m in [ma20, ma50, ma200] if m > price]
        resistance_candidates += [p for p in psych if p > price]
        resistance = _cluster_levels(resistance_candidates)
        # Keep only within max_distance of current price
        resistance = [r for r in resistance if r <= price * (1 + max_distance)]
        resistance = sorted(resistance)   # nearest first

        # ── Build support list (below price) ─────────────────────────────────
        support_candidates = []
        support_candidates += [l for l in swing_lows if l < price]
        support_candidates += [m for m in [ma20, ma50, ma200] if m < price]
        support_candidates += [p for p in psych if p < price]
        support = _cluster_levels(support_candidates)
        support = [s for s in support if s >= price * (1 - max_distance)]
        support = sorted(support, reverse=True)   # nearest first

        # ── Trend bias ───────────────────────────────────────────────────────
        if price > ma50 * 1.01:
            trend = "above_ma50"
        elif price < ma50 * 0.99:
            trend = "below_ma50"
        else:
            trend = "neutral"

        result = {
            "price":      round(price, 2),
            "resistance": resistance,
            "support":    support,
            "ma20":       round(ma20,  2),
            "ma50":       round(ma50,  2),
            "ma200":      round(ma200, 2),
            "trend":      trend,
        }

        log.info(
            "S/R: SPY=%.2f  trend=%s  "
            "support=%s  resistance=%s  "
            "MA20=%.1f  MA50=%.1f  MA200=%.1f",
            price, trend,
            support[:3], resistance[:3],
            ma20, ma50, ma200,
        )
        return result

    except Exception as e:
        log.error("S/R analysis failed: %s", e)
        return None
