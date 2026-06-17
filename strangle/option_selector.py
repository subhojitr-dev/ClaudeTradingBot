"""
option_selector.py  --  Find the best OTM call and put for the strangle

Selection rules:
  - Target DTE: ~90 days (configurable ± tolerance)
  - Target delta: ~0.30 OTM (configurable ± tolerance)
  - For the CALL: strike ABOVE current price, delta ≈ 0.30
  - For the PUT:  strike BELOW current price, delta ≈ 0.30
  - When multiple contracts match, pick the one whose delta is closest to target
"""

import logging
import alpaca_client as ac

log = logging.getLogger(__name__)


def _best_contract(
    candidates: list,
    snapshots: dict,
    target_delta: float,
    delta_tol: float,
) -> tuple[dict | None, dict | None]:
    """
    From a list of contract dicts and their snapshots, return the (contract, snapshot)
    whose delta is closest to target_delta within ±delta_tol.
    """
    best_contract  = None
    best_snapshot  = None
    best_dist      = float("inf")

    for c in candidates:
        occ  = c.get("symbol", "")
        snap = snapshots.get(occ, {})
        if not snap:
            continue
        delta = ac.extract_delta(snap)
        if delta < (target_delta - delta_tol) or delta > (target_delta + delta_tol):
            continue
        dist = abs(delta - target_delta)
        if dist < best_dist:
            best_dist     = dist
            best_contract = c
            best_snapshot = snap

    return best_contract, best_snapshot


def find_strangle_legs(
    symbol: str,
    stock_price: float,
    target_dte: int,
    dte_tol: int,
    target_delta: float,
    delta_tol: float,
) -> dict | None:
    """
    Find matching OTM call and put contracts.

    Returns a dict:
        {
          "call_contract": <OCC symbol str>,
          "call_delta":    float,
          "call_iv":       float,
          "call_ask":      float,      # price to pay (ask for buy-to-open)
          "put_contract":  <OCC symbol str>,
          "put_delta":     float,
          "put_iv":        float,
          "put_ask":       float,
          "expiry":        str,        # shared expiry date (ISO)
        }
    or None if no valid pair found.
    """
    min_dte = max(1, target_dte - dte_tol)
    max_dte = target_dte + dte_tol

    # Fetch candidates — calls above price, puts below price
    call_candidates = ac.get_option_contracts(
        symbol, "call", min_dte, max_dte,
        strike_gte=stock_price * 0.95,    # start slightly below for delta search
        strike_lte=stock_price * 1.50,
    )
    put_candidates = ac.get_option_contracts(
        symbol, "put", min_dte, max_dte,
        strike_gte=stock_price * 0.50,
        strike_lte=stock_price * 1.05,
    )

    if not call_candidates and not put_candidates:
        log.info("  %s: no contracts found in DTE window %d–%d", symbol, min_dte, max_dte)
        return None

    # Bulk snapshot lookup for all candidates
    all_occs  = [c["symbol"] for c in call_candidates + put_candidates]
    snapshots = ac.get_option_snapshots(all_occs)

    # Select best call
    call_c, call_snap = _best_contract(call_candidates, snapshots, target_delta, delta_tol)
    if call_c is None:
        log.info("  %s: no call found with delta ≈ %.2f ± %.2f", symbol, target_delta, delta_tol)
        return None

    # Select best put
    put_c, put_snap = _best_contract(put_candidates, snapshots, target_delta, delta_tol)
    if put_c is None:
        log.info("  %s: no put found with delta ≈ %.2f ± %.2f", symbol, target_delta, delta_tol)
        return None

    call_ask = ac.extract_ask(call_snap) or ac.extract_mid(call_snap)
    put_ask  = ac.extract_ask(put_snap)  or ac.extract_mid(put_snap)

    if call_ask <= 0 or put_ask <= 0:
        log.info("  %s: zero price on call ($%.2f) or put ($%.2f) — skip", symbol, call_ask, put_ask)
        return None

    result = {
        "call_contract": call_c["symbol"],
        "call_strike":   float(call_c.get("strike_price", 0)),
        "call_delta":    ac.extract_delta(call_snap),
        "call_iv":       ac.extract_iv(call_snap),
        "call_ask":      call_ask,
        "put_contract":  put_c["symbol"],
        "put_strike":    float(put_c.get("strike_price", 0)),
        "put_delta":     ac.extract_delta(put_snap),
        "put_iv":        ac.extract_iv(put_snap),
        "put_ask":       put_ask,
        "expiry":        call_c.get("expiration_date", ""),
    }

    log.info(
        "  %s strangle selected: CALL %s Δ=%.2f $%.2f | PUT %s Δ=%.2f $%.2f | Expiry %s",
        symbol,
        result["call_contract"], result["call_delta"], result["call_ask"],
        result["put_contract"],  result["put_delta"],  result["put_ask"],
        result["expiry"],
    )
    return result
