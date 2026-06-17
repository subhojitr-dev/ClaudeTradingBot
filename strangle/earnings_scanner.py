"""
earnings_scanner.py  --  Finds stocks with earnings in the entry window
                         and verifies they have a history of big moves.

Uses yfinance for:
  - Next earnings date (ticker.calendar)
  - Historical earnings move size (price change the day after each past report)
"""

import logging
from datetime import date, timedelta

log = logging.getLogger(__name__)

try:
    import yfinance as yf
except ImportError:
    yf = None
    log.warning("yfinance not installed — run: pip install yfinance")


def get_next_earnings_date(symbol: str) -> date | None:
    """Return the next scheduled earnings date for symbol, or None."""
    if yf is None:
        return None
    try:
        tk  = yf.Ticker(symbol)
        cal = tk.calendar          # dict with 'Earnings Date' as a list of Timestamps
        if cal is None:
            return None
        dates = cal.get("Earnings Date", [])
        if not dates:
            return None
        # calendar returns dates in ascending order; pick the soonest future date
        today = date.today()
        for d in dates:
            ed = d.date() if hasattr(d, "date") else d
            if ed >= today:
                return ed
    except Exception as e:
        log.debug("get_next_earnings_date(%s) error: %s", symbol, e)
    return None


def historical_earnings_moves(symbol: str, look_back: int = 8) -> list[float]:
    """
    Return the absolute % price change on the day after each of the last
    `look_back` earnings reports.  Returns a list of floats (e.g. [5.2, 12.1, ...]).
    """
    if yf is None:
        return []
    try:
        tk = yf.Ticker(symbol)

        # earnings_dates DataFrame — index is the earnings date
        edf = tk.earnings_dates
        if edf is None or edf.empty:
            return []

        # Keep only past earnings (not future)
        today = date.today()
        past  = [d for d in edf.index if d.date() < today]
        past  = sorted(past, reverse=True)[:look_back]

        if not past:
            return []

        # Fetch 2 years of daily history to look up the close before/after each date
        hist = tk.history(period="2y", interval="1d")
        if hist.empty:
            return []

        moves = []
        for earn_ts in past:
            earn_date = earn_ts.date()
            # Get closing prices for the day of and day after earnings
            future_dates = [
                d.date() for d in hist.index if d.date() > earn_date
            ]
            if not future_dates:
                continue
            after_date = future_dates[0]

            before_dates = [
                d.date() for d in hist.index if d.date() <= earn_date
            ]
            if not before_dates:
                continue
            before_date = before_dates[-1]

            closes = {d.date(): hist.loc[d]["Close"] for d in hist.index}
            c_before = closes.get(before_date)
            c_after  = closes.get(after_date)

            if c_before and c_after and c_before > 0:
                move = abs((c_after - c_before) / c_before) * 100
                moves.append(round(move, 2))

        return moves

    except Exception as e:
        log.debug("historical_earnings_moves(%s) error: %s", symbol, e)
        return []


def qualifies_on_history(
    symbol: str,
    look_back: int,
    min_qualifying: int,
    min_move_pct: float,
) -> tuple[bool, str]:
    """
    Returns (True, reason) if the stock has historically moved strongly on earnings,
    or (False, reason) if not.
    """
    moves = historical_earnings_moves(symbol, look_back)
    if not moves:
        return False, f"no earnings history available"

    big_moves = [m for m in moves if m >= min_move_pct]
    passes    = len(big_moves) >= min_qualifying
    reason    = (
        f"{len(big_moves)}/{len(moves)} past reports moved ≥{min_move_pct}% "
        f"(need {min_qualifying})"
    )
    return passes, reason


def scan_for_entries(
    symbols: list[str],
    min_days: int,
    max_days: int,
    look_back: int,
    min_qualifying: int,
    min_move_pct: float,
) -> list[dict]:
    """
    For each symbol, check:
      1. Earnings are min_days..max_days from today.
      2. Stock has historically moved min_move_pct% on at least min_qualifying reports.

    Returns list of dicts: {symbol, earnings_date, moves, days_to_earnings}
    """
    today    = date.today()
    eligible = []

    for sym in symbols:
        log.info("  Scanning %s for earnings...", sym)
        ed = get_next_earnings_date(sym)
        if ed is None:
            log.info("    %s: no earnings date found — skip", sym)
            continue

        days_away = (ed - today).days
        if not (min_days <= days_away <= max_days):
            log.info("    %s: earnings in %d days (need %d–%d) — skip",
                     sym, days_away, min_days, max_days)
            continue

        log.info("    %s: earnings on %s (%d days away) — checking move history...",
                 sym, ed, days_away)

        ok, reason = qualifies_on_history(sym, look_back, min_qualifying, min_move_pct)
        log.info("    %s: history check: %s — %s", sym, "PASS" if ok else "FAIL", reason)

        if ok:
            eligible.append({
                "symbol":         sym,
                "earnings_date":  ed.isoformat(),
                "days_to_earnings": days_away,
                "move_history":   reason,
            })

    return eligible
