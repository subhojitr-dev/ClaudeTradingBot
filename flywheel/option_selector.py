"""
option_selector.py  --  Smart Option Contract Picker
=====================================================
Delta rules (both legs of the wheel):
  CSP : sell put  with delta < 0.25  (<25% chance of assignment)
  CC  : sell call with delta < 0.25  (<25% chance of being called away)

Delta is always the absolute value (the Alpaca API returns negative delta
for puts, e.g. -0.22, which we treat as 0.22).
"""

import logging
from datetime import date
from typing import Optional, Tuple
import alpaca_client as ac

log = logging.getLogger(__name__)


# ── Cash-Secured Put Selector ──────────────────────────────────────────────────

def find_csp_contract(
    symbol: str,
    current_price: float,
    strike_discount: float,
    max_delta: float,           # e.g. 0.25 → only accept puts with delta < 0.25
    min_dte: int,
    max_dte: int,
) -> Optional[Tuple[dict, dict, float]]:
    """
    Find the best cash-secured put to sell.

    Target strike : current_price * (1 - strike_discount)  e.g. 20% OTM
    Delta filter  : |delta| < max_delta  (< 25% probability of assignment)

    Strategy: search a wide band around target strike, then pick the contract
    with delta closest to (but below) max_delta.  This gives maximum premium
    while staying within the probability-of-assignment limit.

    Returns (contract, snapshot, sell_price) or None.
    """
    target_strike = current_price * (1 - strike_discount)
    log.info(
        "  CSP target for %s: strike ~$%.2f  (%d%% OTM)  delta < %.2f",
        symbol, target_strike, int(strike_discount * 100), max_delta,
    )

    # Search a wide band -- the delta filter will narrow it down
    contracts = ac.get_option_contracts(
        underlying=symbol,
        option_type="put",
        min_dte=min_dte,
        max_dte=max_dte,
        strike_gte=current_price * (1 - strike_discount - 0.15),
        strike_lte=current_price * (1 - strike_discount + 0.10),
    )
    if not contracts:
        log.warning("  No put contracts found for %s near $%.2f", symbol, target_strike)
        return None

    return _pick_best_contract(
        contracts=contracts,
        target_strike=target_strike,
        option_type="put",
        max_delta=max_delta,
    )


# ── Covered Call Selector ──────────────────────────────────────────────────────

def find_cc_contract(
    symbol: str,
    current_price: float,
    strike_premium: float,
    max_delta: float,           # e.g. 0.25 → only accept calls with delta < 0.25
    min_dte: int,
    max_dte: int,
) -> Optional[Tuple[dict, dict, float]]:
    """
    Find the best covered call to sell.

    Target strike : current_price * (1 + strike_premium)  e.g. 10% OTM
    Delta filter  : delta < max_delta  (< 25% probability of being called away)

    If the 10% OTM strike has a delta slightly above 0.25 (common in high-IV
    environments), the selector automatically moves to a slightly further OTM
    strike that satisfies the delta limit.

    Returns (contract, snapshot, sell_price) or None.
    """
    target_strike = current_price * (1 + strike_premium)
    log.info(
        "  CC target for %s: strike ~$%.2f  (%d%% OTM)  delta < %.2f",
        symbol, target_strike, int(strike_premium * 100), max_delta,
    )

    # Search from target strike up to 30% OTM (to accommodate delta filter)
    contracts = ac.get_option_contracts(
        underlying=symbol,
        option_type="call",
        min_dte=min_dte,
        max_dte=max_dte,
        strike_gte=target_strike * 0.95,
        strike_lte=current_price * 1.35,
    )
    if not contracts:
        log.warning("  No call contracts found for %s near $%.2f", symbol, target_strike)
        return None

    result = _pick_best_contract(
        contracts=contracts,
        target_strike=target_strike,
        option_type="call",
        max_delta=max_delta,
    )
    if result is None:
        log.warning(
            "  %s: no calls with delta < %.2f found in search range. "
            "All available contracts may have delta >= %.2f (high IV environment). "
            "Will retry next run.",
            symbol, max_delta, max_delta,
        )
    return result


# ── Roll-Up Put Selector ───────────────────────────────────────────────────────

def find_roll_up_contract(
    symbol: str,
    current_price: float,
    current_strike: float,
    expiry_date: str,
    min_net_credit: float,
    current_put_value: float,
    max_delta: float = 0.25,
) -> Optional[Tuple[dict, dict, float]]:
    """
    Find a higher-strike put on the SAME expiry for rolling up.
    Only rolls if:
      - New put still has delta < max_delta (stay within probability limit)
      - Roll generates net credit >= min_net_credit per share
    Returns (contract, snapshot, new_mid) or None.
    """
    new_strike_min = current_strike * 1.05
    new_strike_max = current_price * 0.87   # never roll closer than 13% OTM

    if new_strike_max <= new_strike_min:
        log.info("  No roll-up room for %s (stock too close to current strike)", symbol)
        return None

    contracts = ac.get_option_contracts(
        underlying=symbol,
        option_type="put",
        min_dte=0,
        max_dte=60,
        strike_gte=new_strike_min,
        strike_lte=new_strike_max,
    )
    # Must match exact expiry date
    contracts = [c for c in contracts if c.get("expiration_date") == expiry_date]
    if not contracts:
        log.info("  No roll-up contracts for %s on expiry %s", symbol, expiry_date)
        return None

    syms      = [c["symbol"] for c in contracts]
    snapshots = ac.get_option_snapshots(syms)

    best_credit = 0.0
    best_result = None

    for c in contracts:
        snap      = snapshots.get(c["symbol"], {})
        new_mid   = ac.get_mid_price(snap)
        delta     = ac.get_delta(snap)
        if new_mid <= 0:
            continue
        if delta >= max_delta:
            continue   # stay within delta limit even after roll
        net_credit = new_mid - current_put_value
        if net_credit >= min_net_credit and net_credit > best_credit:
            best_credit = net_credit
            best_result = (c, snap, new_mid)

    if best_result:
        new_strike = float(best_result[0].get("strike_price", 0))
        log.info(
            "  Roll-up: $%.2f -> $%.2f | net credit $%.2f/share ($%.2f/contract) | delta OK",
            current_strike, new_strike, best_credit, best_credit * 100,
        )
    return best_result


# ── Internal helper ────────────────────────────────────────────────────────────

def _pick_best_contract(
    contracts: list,
    target_strike: float,
    option_type: str,
    max_delta: float,
) -> Optional[Tuple[dict, dict, float]]:
    """
    From a list of contracts, pick the one that:
      1. Has |delta| < max_delta  (probability-of-ITM filter)
      2. Is closest to target_strike  (maximises premium within limit)
      3. Has valid bid/ask pricing

    For the wheel, we want to be as close to the target strike as possible
    without exceeding the delta limit -- this gives the highest premium
    while keeping assignment/call-away probability < 25%.
    """
    syms      = [c["symbol"] for c in contracts]
    snapshots = ac.get_option_snapshots(syms)

    eligible = []
    skipped_delta = 0

    for c in contracts:
        snap  = snapshots.get(c["symbol"], {})
        mid   = ac.get_mid_price(snap)
        bid   = ac.get_bid_price(snap)
        delta = ac.get_delta(snap)   # absolute value

        if mid <= 0 or bid <= 0:
            continue

        if delta >= max_delta:
            skipped_delta += 1
            continue   # too high probability of being ITM

        strike = float(c.get("strike_price", 0))
        # Score: prefer strikes closest to target (most premium within limit)
        score  = abs(strike - target_strike)
        eligible.append((score, c, snap, mid, bid, delta))

    if not eligible:
        log.warning(
            "  No eligible %s contracts (delta < %.2f) from %d candidates "
            "(%d skipped for delta). Try widening DTE range or check IV.",
            option_type.upper(), max_delta, len(contracts), skipped_delta,
        )
        return None

    eligible.sort(key=lambda x: x[0])
    _, best_c, best_snap, best_mid, best_bid, best_delta = eligible[0]

    # Use bid price when selling (what market makers will pay us)
    # Fall back to mid if bid looks too low (< 70% of mid)
    sell_price = best_bid if best_bid >= best_mid * 0.70 else best_mid
    sell_price = round(max(sell_price, 0.01), 2)

    log.info(
        "  Selected %s: %-28s  strike=$%.2f  delta=%.3f (<%.2f)  "
        "bid=$%.4f  mid=$%.4f  IV=%.1f%%",
        option_type.upper(),
        best_c["symbol"],
        float(best_c.get("strike_price", 0)),
        best_delta, max_delta,
        best_bid, best_mid,
        ac.get_iv(best_snap) * 100,
    )
    return best_c, best_snap, sell_price
