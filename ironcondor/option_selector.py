"""
option_selector.py  --  Select the four legs of an Iron Condor

Works for any liquid ETF (SPY, IWM, GLD, etc.).
Per-symbol config (wing width, max delta) passed in from caller.

Strike selection logic (in priority order):
  1. Short strikes must have |delta| ≤ MAX_SHORT_DELTA
  2. If USE_SR_LEVELS=True, nudge the short strike just beyond a nearby S/R level
  3. If USE_TREND_BIAS=True, tighten/loosen call side based on trend vs MA50
  4. Long strike = short strike ± WING_WIDTH
  5. Only open if net credit ≥ MIN_CREDIT_RATIO × max_risk
"""

import logging
from datetime import date, timedelta
import alpaca_client as ac
from config import (
    MIN_CREDIT_RATIO,
    TARGET_DTE, DTE_TOLERANCE,
    USE_SR_LEVELS, USE_TREND_BIAS, TREND_NEUTRAL_BAND,
)

log = logging.getLogger(__name__)


# ── Expiry selection ─────────────────────────────────────────────────────────

def find_target_expiry(symbol: str) -> str | None:
    today    = date.today()
    min_days = TARGET_DTE - DTE_TOLERANCE
    max_days = TARGET_DTE + DTE_TOLERANCE

    contracts = ac.get_option_contracts(
        symbol, "call", min_days, max_days,
        strike_gte=1, strike_lte=99999,
    )
    expiries = sorted({c["expiration_date"] for c in contracts})
    if not expiries:
        log.info("  [%s] No expiries found in %d–%d DTE window", symbol, min_days, max_days)
        return None

    target_date = today + timedelta(days=TARGET_DTE)
    best = min(expiries, key=lambda e: abs((date.fromisoformat(e) - target_date).days))
    days_out = (date.fromisoformat(best) - today).days
    log.info("  [%s] Target expiry: %s  (%d DTE)", symbol, best, days_out)
    return best


# ── Contract filtering ───────────────────────────────────────────────────────

def _filter_by_delta(
    contracts: list,
    snapshots: dict,
    max_delta: float,
    prefer_strike: float = None,
) -> list:
    valid = []
    for c in contracts:
        snap = snapshots.get(c["symbol"], {})
        if not snap:
            continue
        d = ac.delta(snap)
        if d <= max_delta:
            valid.append((c, snap, d))

    if prefer_strike is not None:
        valid.sort(key=lambda x: abs(float(x[0]["strike_price"]) - prefer_strike))
    else:
        valid.sort(key=lambda x: x[2], reverse=True)

    return valid


# ── Short put selection ───────────────────────────────────────────────────────

def _pick_short_put(
    symbol: str,
    price: float,
    expiry: str,
    sr_data: dict | None,
    max_delta: float,
) -> tuple[dict, dict] | tuple[None, None]:
    min_dte = max(1, TARGET_DTE - DTE_TOLERANCE)
    max_dte = TARGET_DTE + DTE_TOLERANCE

    candidates = ac.get_option_contracts(
        symbol, "put", min_dte, max_dte,
        strike_gte=price * 0.85,
        strike_lte=price * 0.97,
    )
    candidates = [c for c in candidates if c.get("expiration_date") == expiry]
    if not candidates:
        return None, None

    snaps = ac.get_option_snapshots([c["symbol"] for c in candidates])

    preferred_strike = None
    if USE_SR_LEVELS and sr_data and sr_data.get("support"):
        nearest_support = sr_data["support"][0]
        if nearest_support > price * 0.85:
            preferred_strike = nearest_support - 0.50
            log.info("  [%s] SR: short put near $%.2f (support=%.2f)",
                     symbol, preferred_strike, nearest_support)

    valid = _filter_by_delta(candidates, snaps, max_delta, preferred_strike)
    if not valid:
        log.info("  [%s] No qualifying short put (delta ≤ %.2f)", symbol, max_delta)
        return None, None

    contract, snap, d = valid[0]
    log.info("  [%s] Short put: strike=%.2f  delta=%.3f  mid=$%.2f",
             symbol, float(contract["strike_price"]), d, ac.mid(snap))
    return contract, snap


# ── Short call selection ──────────────────────────────────────────────────────

def _pick_short_call(
    symbol: str,
    price: float,
    expiry: str,
    sr_data: dict | None,
    trend: str,
    max_delta: float,
) -> tuple[dict, dict] | tuple[None, None]:
    min_dte = max(1, TARGET_DTE - DTE_TOLERANCE)
    max_dte = TARGET_DTE + DTE_TOLERANCE

    candidates = ac.get_option_contracts(
        symbol, "call", min_dte, max_dte,
        strike_gte=price * 1.01,
        strike_lte=price * 1.12,
    )
    candidates = [c for c in candidates if c.get("expiration_date") == expiry]
    if not candidates:
        return None, None

    snaps = ac.get_option_snapshots([c["symbol"] for c in candidates])

    preferred_strike = None
    if USE_SR_LEVELS and sr_data and sr_data.get("resistance"):
        nearest_res = sr_data["resistance"][0]
        if nearest_res < price * 1.12:
            preferred_strike = nearest_res + 0.50
            log.info("  [%s] SR: short call near $%.2f (resistance=%.2f)",
                     symbol, preferred_strike, nearest_res)

    effective_max_delta = max_delta
    if USE_TREND_BIAS:
        if trend == "above_ma50":
            effective_max_delta = max_delta + 0.03
            log.info("  [%s] Trend: above MA50, call delta up to %.2f", symbol, effective_max_delta)
        elif trend == "below_ma50":
            effective_max_delta = max_delta - 0.03
            log.info("  [%s] Trend: below MA50, call delta down to %.2f", symbol, effective_max_delta)

    valid = _filter_by_delta(candidates, snaps, effective_max_delta, preferred_strike)
    if not valid:
        log.info("  [%s] No qualifying short call (delta ≤ %.2f)", symbol, effective_max_delta)
        return None, None

    contract, snap, d = valid[0]
    log.info("  [%s] Short call: strike=%.2f  delta=%.3f  mid=$%.2f",
             symbol, float(contract["strike_price"]), d, ac.mid(snap))
    return contract, snap


# ── Wing selection ────────────────────────────────────────────────────────────

def _find_wing(
    symbol: str,
    expiry: str,
    short_strike: float,
    option_type: str,
    wing_width: float,
) -> tuple[dict, dict] | tuple[None, None]:
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
        log.info("  [%s] No wing contract for %s at ~%.2f", symbol, option_type, target_strike)
        return None, None

    snaps = ac.get_option_snapshots([c["symbol"] for c in candidates])
    best  = min(candidates, key=lambda c: abs(float(c["strike_price"]) - target_strike))
    snap  = snaps.get(best["symbol"], {})
    price = ac.ask(snap) or ac.mid(snap)
    log.info("  [%s] Long %s: strike=%.2f  ask=$%.2f",
             symbol, option_type, float(best["strike_price"]), price)
    return best, snap


# ── Main selector ─────────────────────────────────────────────────────────────

def find_iron_condor(
    symbol: str,
    price: float,
    sr_data: dict | None,
    sym_cfg: dict,
) -> dict | None:
    """
    Find all four legs of the iron condor for the given symbol.
    sym_cfg must contain WING_WIDTH and MAX_SHORT_DELTA for this symbol.
    Returns a leg dict or None if no valid condor found.
    """
    wing_width = sym_cfg.get("WING_WIDTH",      5)
    max_delta  = sym_cfg.get("MAX_SHORT_DELTA", 0.20)
    trend      = sr_data.get("trend", "neutral") if sr_data else "neutral"

    expiry = find_target_expiry(symbol)
    if not expiry:
        return None

    sp_contract, sp_snap = _pick_short_put(symbol, price, expiry, sr_data, max_delta)
    if sp_contract is None:
        return None
    sp_strike = float(sp_contract["strike_price"])
    sp_credit = ac.bid_price(sp_snap) or ac.mid(sp_snap)

    lp_contract, lp_snap = _find_wing(symbol, expiry, sp_strike, "put", wing_width)
    if lp_contract is None:
        return None
    lp_debit = ac.ask(lp_snap) or ac.mid(lp_snap)

    sc_contract, sc_snap = _pick_short_call(symbol, price, expiry, sr_data, trend, max_delta)
    if sc_contract is None:
        return None
    sc_strike = float(sc_contract["strike_price"])
    sc_credit = ac.bid_price(sc_snap) or ac.mid(sc_snap)

    lc_contract, lc_snap = _find_wing(symbol, expiry, sc_strike, "call", wing_width)
    if lc_contract is None:
        return None
    lc_debit = ac.ask(lc_snap) or ac.mid(lc_snap)

    put_width    = sp_strike - float(lp_contract["strike_price"])
    call_width   = float(lc_contract["strike_price"]) - sc_strike
    eff_width    = max(put_width, call_width)
    net_credit   = round((sp_credit - lp_debit) + (sc_credit - lc_debit), 4)
    max_risk     = round(eff_width - net_credit, 4)
    credit_ratio = round(net_credit / eff_width, 4) if eff_width > 0 else 0

    log.info(
        "  [%s] Condor: [%.0f/%.0f]P · [%.0f/%.0f]C  "
        "credit=$%.2f  risk=$%.2f  ratio=%.0f%%",
        symbol,
        sp_strike, float(lp_contract["strike_price"]),
        sc_strike, float(lc_contract["strike_price"]),
        net_credit, max_risk, credit_ratio * 100,
    )

    if credit_ratio < MIN_CREDIT_RATIO:
        log.info("  [%s] Credit ratio %.0f%% < minimum %.0f%% — skipping",
                 symbol, credit_ratio * 100, MIN_CREDIT_RATIO * 100)
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
