"""
option_selector.py  --  Select the four legs of the SPY Iron Condor

Iron Condor = Bull Put Spread  +  Bear Call Spread
  Leg 1: Sell OTM Put  (short put)  — collects premium
  Leg 2: Buy  OTM Put  (long put)   — defines max loss on downside
  Leg 3: Sell OTM Call (short call) — collects premium
  Leg 4: Buy  OTM Call (long call)  — defines max loss on upside

Strike selection logic (in priority order):
  1. Short strikes must have |delta| ≤ MAX_SHORT_DELTA (0.20)
  2. If USE_SR_LEVELS=True, nudge the short strike to just BEYOND a nearby
     S/R level (put short below nearest support, call short above nearest
     resistance) — but only if that level also satisfies the delta constraint
  3. If USE_TREND_BIAS=True and SPY is above MA50, use a call strike one step
     closer to the money (tighter call wing) to collect more premium on the
     more likely direction of risk
  4. Long strike = short strike ± WING_WIDTH (e.g. $5 wide on each side)
  5. Only open if net credit ≥ MIN_CREDIT_RATIO × max_risk
"""

import logging
from datetime import date, timedelta
import alpaca_client as ac
from config import (
    MAX_SHORT_DELTA, WING_WIDTH, MIN_CREDIT_RATIO,
    TARGET_DTE, DTE_TOLERANCE,
    USE_SR_LEVELS, USE_TREND_BIAS, TREND_NEUTRAL_BAND,
)

log = logging.getLogger(__name__)


# ── Expiry selection ─────────────────────────────────────────────────────────

def find_target_expiry(symbol: str) -> str | None:
    """
    Find the closest Friday expiry to TARGET_DTE days out.
    SPY has weekly options. We look for the expiry where:
      TARGET_DTE - DTE_TOLERANCE <= days_to_expiry <= TARGET_DTE + DTE_TOLERANCE
    """
    today    = date.today()
    min_days = TARGET_DTE - DTE_TOLERANCE
    max_days = TARGET_DTE + DTE_TOLERANCE

    # Use Alpaca contracts endpoint to find available expiries
    contracts = ac.get_option_contracts(
        symbol, "call", min_days, max_days,
        strike_gte=1, strike_lte=9999,
    )
    expiries = sorted({c["expiration_date"] for c in contracts})
    if not expiries:
        log.info("  No expiries found in %d–%d DTE window", min_days, max_days)
        return None

    # Pick the expiry closest to TARGET_DTE
    target_date = today + timedelta(days=TARGET_DTE)
    best = min(expiries, key=lambda e: abs((date.fromisoformat(e) - target_date).days))
    days_out = (date.fromisoformat(best) - today).days
    log.info("  Target expiry: %s  (%d DTE)", best, days_out)
    return best


# ── Contract filtering ───────────────────────────────────────────────────────

def _filter_by_delta(
    contracts: list,
    snapshots: dict,
    max_delta: float,
    prefer_below: float = None,
) -> list:
    """
    Filter contracts to those with |delta| ≤ max_delta.
    If prefer_below given, sort so contracts closest to (but not above)
    prefer_below strike come first — used for SR-based selection.
    """
    valid = []
    for c in contracts:
        snap = snapshots.get(c["symbol"], {})
        if not snap:
            continue
        d = ac.delta(snap)
        if d <= max_delta:
            valid.append((c, snap, d))

    if prefer_below is not None:
        valid.sort(key=lambda x: abs(float(x[0]["strike_price"]) - prefer_below))
    else:
        # Sort by delta descending — closest to max_delta = most premium
        valid.sort(key=lambda x: x[2], reverse=True)

    return valid


def _pick_short_put(
    spy_price: float,
    expiry: str,
    sr_data: dict | None,
) -> tuple[dict, dict] | tuple[None, None]:
    """
    Find the best short put strike:
      - |delta| ≤ MAX_SHORT_DELTA
      - Ideally just below the nearest support level
      - If no S/R guidance, pick the highest-delta qualifying put
    """
    min_dte = max(1, TARGET_DTE - DTE_TOLERANCE)
    max_dte = TARGET_DTE + DTE_TOLERANCE

    # Restrict search range: puts between 5% and 15% below current price
    candidates = ac.get_option_contracts(
        "SPY", "put", min_dte, max_dte,
        strike_gte=spy_price * 0.85,
        strike_lte=spy_price * 0.97,
    )
    # Filter to target expiry
    candidates = [c for c in candidates if c.get("expiration_date") == expiry]
    if not candidates:
        return None, None

    snaps = ac.get_option_snapshots([c["symbol"] for c in candidates])

    # Determine preferred strike level
    preferred_strike = None
    if USE_SR_LEVELS and sr_data and sr_data.get("support"):
        # Short put goes just BELOW the nearest support level
        nearest_support = sr_data["support"][0]
        if nearest_support > spy_price * (1 - 0.15):   # within search range
            preferred_strike = nearest_support - 0.50  # one tick below support
            log.info("  SR guidance: short put target near $%.2f (support=%.2f)",
                     preferred_strike, nearest_support)

    valid = _filter_by_delta(candidates, snaps, MAX_SHORT_DELTA, preferred_strike)
    if not valid:
        log.info("  No qualifying short put found (delta ≤ %.2f)", MAX_SHORT_DELTA)
        return None, None

    contract, snap, d = valid[0]
    log.info("  Short put: %s  strike=%.2f  delta=%.3f  mid=$%.2f",
             contract["symbol"], float(contract["strike_price"]), d, ac.mid(snap))
    return contract, snap


def _pick_short_call(
    spy_price: float,
    expiry: str,
    sr_data: dict | None,
    trend: str,
) -> tuple[dict, dict] | tuple[None, None]:
    """
    Find the best short call strike:
      - |delta| ≤ MAX_SHORT_DELTA
      - Ideally just above the nearest resistance level
      - If trend is above_ma50, can tighten slightly (pick one step closer to ATM)
    """
    min_dte = max(1, TARGET_DTE - DTE_TOLERANCE)
    max_dte = TARGET_DTE + DTE_TOLERANCE

    candidates = ac.get_option_contracts(
        "SPY", "call", min_dte, max_dte,
        strike_gte=spy_price * 1.01,
        strike_lte=spy_price * 1.12,
    )
    candidates = [c for c in candidates if c.get("expiration_date") == expiry]
    if not candidates:
        return None, None

    snaps = ac.get_option_snapshots([c["symbol"] for c in candidates])

    preferred_strike = None
    if USE_SR_LEVELS and sr_data and sr_data.get("resistance"):
        nearest_res = sr_data["resistance"][0]
        if nearest_res < spy_price * (1 + 0.12):
            preferred_strike = nearest_res + 0.50   # one tick above resistance
            log.info("  SR guidance: short call target near $%.2f (resistance=%.2f)",
                     preferred_strike, nearest_res)

    # Trend bias: above MA50 → tighten call side (pick slightly higher delta)
    effective_max_delta = MAX_SHORT_DELTA
    if USE_TREND_BIAS:
        if trend == "above_ma50":
            effective_max_delta = MAX_SHORT_DELTA + 0.03   # allow up to 0.23 delta
            log.info("  Trend bias: SPY above MA50, allowing call delta up to %.2f",
                     effective_max_delta)
        elif trend == "below_ma50":
            effective_max_delta = MAX_SHORT_DELTA - 0.03   # tighter, 0.17 delta
            log.info("  Trend bias: SPY below MA50, tightening call delta to %.2f",
                     effective_max_delta)

    valid = _filter_by_delta(candidates, snaps, effective_max_delta, preferred_strike)
    if not valid:
        log.info("  No qualifying short call found (delta ≤ %.2f)", effective_max_delta)
        return None, None

    contract, snap, d = valid[0]
    log.info("  Short call: %s  strike=%.2f  delta=%.3f  mid=$%.2f",
             contract["symbol"], float(contract["strike_price"]), d, ac.mid(snap))
    return contract, snap


def _find_wing(
    symbol: str,
    expiry: str,
    short_strike: float,
    option_type: str,   # "put" or "call"
    wing_width: float,
) -> tuple[dict, dict] | tuple[None, None]:
    """
    Find the long wing contract exactly WING_WIDTH points further OTM than
    the short strike.  Searches a tight ±0.50 window around the target.
    """
    if option_type == "put":
        target_strike = short_strike - wing_width
    else:
        target_strike = short_strike + wing_width

    min_dte = max(1, TARGET_DTE - DTE_TOLERANCE)
    max_dte = TARGET_DTE + DTE_TOLERANCE

    candidates = ac.get_option_contracts(
        symbol, option_type, min_dte, max_dte,
        strike_gte=target_strike - 0.50,
        strike_lte=target_strike + 0.50,
    )
    candidates = [c for c in candidates if c.get("expiration_date") == expiry]
    if not candidates:
        log.info("  No wing contract found for %s at ~%.2f", option_type, target_strike)
        return None, None

    snaps  = ac.get_option_snapshots([c["symbol"] for c in candidates])
    # Pick the one whose strike is closest to target
    best   = min(candidates, key=lambda c: abs(float(c["strike_price"]) - target_strike))
    snap   = snaps.get(best["symbol"], {})
    price  = ac.ask(snap) or ac.mid(snap)
    log.info("  Long  %s:  %s  strike=%.2f  ask=$%.2f",
             option_type, best["symbol"], float(best["strike_price"]), price)
    return best, snap


# ── Main selector ────────────────────────────────────────────────────────────

def find_iron_condor(
    spy_price: float,
    sr_data: dict | None,
) -> dict | None:
    """
    Find all four legs of the iron condor.

    Returns:
    {
      "expiry":            "2026-06-27",
      "short_put":         "SPY260627P00515000",
      "short_put_strike":  515.0,
      "short_put_delta":   0.18,
      "short_put_credit":  1.45,
      "long_put":          "SPY260627P00510000",
      "long_put_strike":   510.0,
      "long_put_debit":    0.55,
      "short_call":        "SPY260627C00565000",
      "short_call_strike": 565.0,
      "short_call_delta":  0.17,
      "short_call_credit": 1.30,
      "long_call":         "SPY260627C00570000",
      "long_call_strike":  570.0,
      "long_call_debit":   0.50,
      "net_credit":        1.70,     # total credit per share
      "max_risk":          3.30,     # wing_width - net_credit per share
      "credit_ratio":      0.34,     # net_credit / wing_width
      "put_spread_width":  5.0,
      "call_spread_width": 5.0,
    }
    or None if no valid condor is found.
    """
    trend = sr_data.get("trend", "neutral") if sr_data else "neutral"

    # Step 1: find target expiry
    expiry = find_target_expiry("SPY")
    if not expiry:
        return None

    # Step 2: short put
    sp_contract, sp_snap = _pick_short_put(spy_price, expiry, sr_data)
    if sp_contract is None:
        return None
    sp_strike = float(sp_contract["strike_price"])
    sp_credit = ac.bid_price(sp_snap) or ac.mid(sp_snap)   # sell at bid

    # Step 3: long put (wing)
    lp_contract, lp_snap = _find_wing("SPY", expiry, sp_strike, "put", WING_WIDTH)
    if lp_contract is None:
        return None
    lp_debit = ac.ask(lp_snap) or ac.mid(lp_snap)          # buy at ask

    # Step 4: short call
    sc_contract, sc_snap = _pick_short_call(spy_price, expiry, sr_data, trend)
    if sc_contract is None:
        return None
    sc_strike = float(sc_contract["strike_price"])
    sc_credit = ac.bid_price(sc_snap) or ac.mid(sc_snap)

    # Step 5: long call (wing)
    lc_contract, lc_snap = _find_wing("SPY", expiry, sc_strike, "call", WING_WIDTH)
    if lc_contract is None:
        return None
    lc_debit = ac.ask(lc_snap) or ac.mid(lc_snap)

    # Step 6: credit quality check
    put_width  = sp_strike - float(lp_contract["strike_price"])
    call_width = float(lc_contract["strike_price"]) - sc_strike
    wing_width = max(put_width, call_width)

    net_credit   = round((sp_credit - lp_debit) + (sc_credit - lc_debit), 4)
    max_risk      = round(wing_width - net_credit, 4)
    credit_ratio  = round(net_credit / wing_width, 4) if wing_width > 0 else 0

    log.info(
        "  Condor: put_spread=[%.0f/%.0f] call_spread=[%.0f/%.0f]"
        "  net_credit=$%.2f  max_risk=$%.2f  credit_ratio=%.0f%%",
        sp_strike, float(lp_contract["strike_price"]),
        sc_strike, float(lc_contract["strike_price"]),
        net_credit, max_risk, credit_ratio * 100,
    )

    if credit_ratio < MIN_CREDIT_RATIO:
        log.info(
            "  Credit ratio %.0f%% < minimum %.0f%% — skipping entry",
            credit_ratio * 100, MIN_CREDIT_RATIO * 100,
        )
        return None

    return {
        "expiry":            expiry,
        "short_put":         sp_contract["symbol"],
        "short_put_strike":  sp_strike,
        "short_put_delta":   ac.delta(sp_snap),
        "short_put_credit":  round(sp_credit, 4),
        "long_put":          lp_contract["symbol"],
        "long_put_strike":   float(lp_contract["strike_price"]),
        "long_put_debit":    round(lp_debit, 4),
        "short_call":        sc_contract["symbol"],
        "short_call_strike": sc_strike,
        "short_call_delta":  ac.delta(sc_snap),
        "short_call_credit": round(sc_credit, 4),
        "long_call":         lc_contract["symbol"],
        "long_call_strike":  float(lc_contract["strike_price"]),
        "long_call_debit":   round(lc_debit, 4),
        "net_credit":        net_credit,
        "max_risk":          max_risk,
        "credit_ratio":      credit_ratio,
        "put_spread_width":  put_width,
        "call_spread_width": call_width,
    }
