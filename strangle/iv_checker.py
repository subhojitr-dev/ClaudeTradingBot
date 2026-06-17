"""
iv_checker.py  --  IV percentile check for strangle entry

Maintains a rolling JSON file (iv_history.json) that records the ATM IV
observed on each bot run for each symbol.  On entry, the current IV is
compared to the stored history: if current IV is at or below the configured
percentile threshold (default 50th), the IV filter passes.

Why local history instead of a paid data feed:
  Alpaca's indicative-feed options snapshots give us live IV for free.
  After a few weeks of running, the history is rich enough to be useful.
  On early runs (< 5 observations) the filter is skipped (benefit of the doubt).
"""

import json
import logging
import os
from datetime import date

log = logging.getLogger(__name__)

MIN_OBSERVATIONS = 5   # need at least this many data points before filtering


def load_iv_history(cache_file: str) -> dict:
    """Load {symbol: [{date, iv}, ...]} from cache."""
    if os.path.exists(cache_file):
        try:
            with open(cache_file) as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_iv_history(cache_file: str, history: dict) -> None:
    with open(cache_file, "w") as f:
        json.dump(history, f, indent=2)


def record_iv(cache_file: str, symbol: str, iv: float, max_days: int = 90) -> None:
    """Append today's IV observation for symbol and prune old records."""
    history = load_iv_history(cache_file)
    records = history.get(symbol, [])

    today_str = date.today().isoformat()
    # Avoid duplicate entries for the same day
    records = [r for r in records if r["date"] != today_str]
    records.append({"date": today_str, "iv": round(iv, 4)})

    # Keep only the last max_days observations
    records = sorted(records, key=lambda r: r["date"])[-max_days:]
    history[symbol] = records
    save_iv_history(cache_file, history)


def iv_percentile(cache_file: str, symbol: str) -> float | None:
    """
    Return the percentile rank of the most recent IV observation vs history.
    Returns None if not enough history exists.
    """
    history = load_iv_history(cache_file)
    records = history.get(symbol, [])

    if len(records) < MIN_OBSERVATIONS:
        return None

    sorted_ivs = sorted(r["iv"] for r in records)
    current_iv = records[-1]["iv"]   # most recent observation (already recorded)

    below = sum(1 for v in sorted_ivs if v < current_iv)
    pct   = (below / len(sorted_ivs)) * 100
    return round(pct, 1)


def get_atm_iv_from_snapshots(symbol: str, stock_price: float, snapshots: dict) -> float:
    """
    From a batch of option snapshots for a symbol, find the contract closest
    to ATM and return its IV.  `snapshots` is the full Alpaca snapshot dict
    filtered to this symbol's contracts.
    """
    if not snapshots:
        return 0.0

    best_iv   = 0.0
    best_dist = float("inf")

    for occ, snap in snapshots.items():
        if not occ.startswith(symbol):
            continue
        # Parse strike from OCC symbol (last 8 chars before type indicator)
        # OCC format: NVDA251003C00160000  → strike = 00160000 / 1000 = 160.0
        try:
            strike = float(occ[-8:]) / 1000
        except Exception:
            continue
        dist = abs(strike - stock_price)
        if dist < best_dist:
            best_dist = dist
            best_iv   = float(snap.get("impliedVolatility") or 0)

    return best_iv


def passes_iv_filter(
    cache_file: str,
    symbol: str,
    current_iv: float,
    threshold_pct: float,
    max_history_days: int,
) -> tuple[bool, str]:
    """
    Record the current IV observation, then check the percentile filter.
    Returns (passes: bool, reason: str).
    """
    record_iv(cache_file, symbol, current_iv, max_history_days)
    pct = iv_percentile(cache_file, symbol)

    if pct is None:
        return True, f"IV={current_iv:.1%} — not enough history yet, allowing entry"

    passes = pct <= threshold_pct
    reason = (
        f"IV={current_iv:.1%} is at {pct:.0f}th percentile "
        f"({'≤' if passes else '>'}{threshold_pct:.0f} threshold)"
    )
    return passes, reason
