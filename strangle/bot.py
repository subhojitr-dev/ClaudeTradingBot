"""
bot.py  --  Bi-Directional Strangle Strategy (Earnings Play)
=============================================================

Strategy overview
-----------------
2–3 weeks before earnings on a watched stock:
  1. Check IV is average or below (≤ 50th percentile of own history)
  2. Confirm stock has historically moved ≥ 4% on at least 4 of last 8 reports
  3. Buy 1 OTM CALL + 1 OTM PUT, both ~0.30 delta, ~90 DTE

Combined-position monitoring (every 30 min during market hours, pre- or
post-earnings alike):
  - Judge the call + put TOGETHER against total cost, never one leg alone --
    the two legs move opposite each other on the same stock move, so
    watching only one leg misrepresents the position's real P&L.
  - If combined value is +20% of cost or more → sell whatever legs are
    still open, trade fully closed (profit).
  - If combined value is -20% of cost or worse → sell whatever legs are
    still open, trade fully closed (stop-loss).

Runs every 30 min via Windows Task Scheduler (same window as other bots).
"""

import logging
import os
import sys
from datetime import date

# ── Bootstrap ────────────────────────────────────────────────
_LOG_DIR = os.path.join(os.path.dirname(__file__), "logs")
os.makedirs(_LOG_DIR, exist_ok=True)
_today = date.today().strftime("%Y%m%d")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(_LOG_DIR, f"strangle_{_today}.log"), encoding="utf-8"),
        logging.FileHandler(os.path.join(_LOG_DIR, f"errors_{_today}.log"),   encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logging.getLogger().handlers[1].setLevel(logging.ERROR)
log = logging.getLogger(__name__)

import config
import alpaca_client    as ac
import earnings_scanner as es
import iv_checker       as ivc
import option_selector  as os_
import state_manager    as sm
import notifier         as notify


# ── Helpers ──────────────────────────────────────────────────

def market_is_open() -> bool:
    try:
        clock = ac.get_clock()
        return clock.get("is_open", False)
    except Exception as e:
        log.error("Clock check failed: %s", e)
        return False


# ── Entry logic ──────────────────────────────────────────────

def try_open_strangle(symbol: str, earnings_date: str, state: dict) -> None:
    """Evaluate all entry criteria and, if passed, open the strangle."""

    log.info("-- Evaluating entry for %s (earnings %s) --", symbol, earnings_date)

    # Get current stock price
    price = ac.get_stock_price(symbol)
    if price <= 0:
        log.info("  %s: cannot get stock price — skip", symbol)
        return

    # Find option contracts
    legs = os_.find_strangle_legs(
        symbol, price,
        target_dte=config.TARGET_DTE,
        dte_tol=config.DTE_TOLERANCE,
        target_delta=config.TARGET_DELTA,
        delta_tol=config.DELTA_TOLERANCE,
    )
    if legs is None:
        log.info("  %s: no suitable contracts found — skip", symbol)
        return

    # IV filter — record today's ATM IV and check percentile
    atm_iv = (legs["call_iv"] + legs["put_iv"]) / 2
    iv_ok, iv_reason = ivc.passes_iv_filter(
        config.IV_CACHE, symbol, atm_iv,
        config.IV_PERCENTILE_THRESHOLD,
        config.IV_HISTORY_DAYS,
    )
    log.info("  %s: IV check: %s — %s", symbol, "PASS" if iv_ok else "FAIL", iv_reason)
    if not iv_ok:
        notify.notify_iv_skip(symbol, atm_iv, ivc.iv_percentile(config.IV_CACHE, symbol) or 0,
                              config.IV_PERCENTILE_THRESHOLD)
        return

    # All criteria passed — place orders
    log.info("  %s: ALL CRITERIA PASSED — opening strangle", symbol)

    try:
        ac.place_option_order(legs["call_contract"], "buy", 1, legs["call_ask"])
        ac.place_option_order(legs["put_contract"],  "buy", 1, legs["put_ask"])
    except Exception as e:
        log.error("  %s: order placement failed: %s", symbol, e)
        return

    sm.open_strangle(state, symbol, legs, earnings_date, stock_price=price)
    # Save right away: a later step in this run (e.g. a hung earnings scan)
    # must not be able to lose the record of orders already placed.
    sm.save(config.STATE_FILE, state)

    notify.notify_strangle_opened(
        symbol, earnings_date,
        legs["call_contract"], legs["put_contract"],
        legs["call_ask"], legs["put_ask"],
        legs["total_cost"] if "total_cost" in legs else (legs["call_ask"] + legs["put_ask"]) * 100,
    )
    log.info(
        "  %s: strangle opened — CALL %s @ $%.2f | PUT %s @ $%.2f",
        symbol, legs["call_contract"], legs["call_ask"],
        legs["put_contract"], legs["put_ask"],
    )


# Mutable container so monitor helpers can mutate state
state_ref = [None]


# ── Combined-position monitoring ────────────────────────────────

def _leg_value(pos: dict, positions: dict, sold_key: str, contract_key: str):
    """Return (value_in_dollars, live_mid_or_None, still_open: bool) for one leg.

    Already-sold legs contribute their locked-in proceeds. Still-open legs
    contribute their current mid price -- or None if the contract isn't in
    our Alpaca positions at all (expired/exercised/removed unexpectedly).
    """
    sold_price = pos.get(sold_key)
    if sold_price is not None:
        return sold_price * 100, None, False

    occ = pos[contract_key]
    if occ not in positions:
        return None, None, False

    mid = ac.extract_mid(ac.get_option_snapshot(occ))
    if mid <= 0:
        return None, None, True
    return mid * 100, mid, True


def monitor_combined(symbol: str, pos: dict, positions: dict) -> None:
    """Judge the WHOLE position (call + put together) against its total
    cost, and close whatever legs are still open once it moves +/-
    COMBINED_PROFIT_TARGET_PCT / COMBINED_STOP_LOSS_PCT -- never decide
    based on one leg's price in isolation."""
    call_value, call_mid, call_open = _leg_value(pos, positions, "call_sold_price", "call_contract")
    put_value,  put_mid,  put_open  = _leg_value(pos, positions, "put_sold_price",  "put_contract")

    if call_value is None or put_value is None:
        log.info("  %s: a leg's price is unavailable this run -- skipping", symbol)
        return

    total_cost   = pos["total_cost"]
    current_value = call_value + put_value
    gain_pct      = (current_value - total_cost) / total_cost if total_cost else 0

    log.info(
        "  %s: combined value $%.2f vs cost $%.2f -> gain %.1f%% (call_open=%s put_open=%s)",
        symbol, current_value, total_cost, gain_pct * 100, call_open, put_open,
    )

    if gain_pct >= config.COMBINED_PROFIT_TARGET_PCT:
        reason = f"combined profit target hit ({gain_pct * 100:+.1f}% >= {config.COMBINED_PROFIT_TARGET_PCT * 100:.0f}%)"
    elif gain_pct <= -config.COMBINED_STOP_LOSS_PCT:
        reason = f"combined stop-loss hit ({gain_pct * 100:+.1f}% <= -{config.COMBINED_STOP_LOSS_PCT * 100:.0f}%)"
    else:
        return  # nothing to do yet

    log.info("  %s: %s -- CLOSING WHATEVER LEGS ARE STILL OPEN", symbol, reason)

    # Record why and at what stock price we exited (pos is the same dict that
    # gets archived to history, so these fields travel with the trade).
    try:
        pos["exit_stock_price"] = round(ac.get_stock_price(symbol), 2) or None
    except Exception as e:
        log.error("  %s: could not fetch stock price for exit record: %s", symbol, e)
        pos["exit_stock_price"] = None
    pos["close_reason"] = reason

    if call_open:
        try:
            ac.place_option_order(pos["call_contract"], "sell", 1, call_mid)
        except Exception as e:
            log.error("  %s: sell call failed: %s", symbol, e)
            return
        sm.record_call_sold(state_ref[0], symbol, call_mid)

    if put_open:
        try:
            ac.place_option_order(pos["put_contract"], "sell", 1, put_mid)
        except Exception as e:
            log.error("  %s: sell put failed: %s", symbol, e)
            return
        sm.record_put_sold(state_ref[0], symbol, put_mid)

    # Save right away, before the (slow, sometimes hanging) entry scan runs --
    # runs killed mid-scan previously lost the record of these sells.
    sm.save(config.STATE_FILE, state_ref[0])

    history = state_ref[0]["history"]
    closed = history[-1] if history else {}
    notify.notify_combined_close(
        symbol=symbol,
        reason=reason,
        call_sold_price=closed.get("call_sold_price"),
        put_sold_price=closed.get("put_sold_price"),
        total_cost=total_cost,
        total_proceeds=closed.get("total_proceeds", current_value),
        net_pnl=closed.get("net_pnl", current_value - total_cost),
    )


# ── Main ─────────────────────────────────────────────────────

def run() -> None:
    log.info("=" * 62)
    log.info("  STRANGLE BOT — %s", date.today().isoformat())
    log.info("=" * 62)

    if not market_is_open():
        log.info("Market closed — exiting.")
        return

    # Load state
    state = sm.load(config.STATE_FILE)
    state_ref[0] = state

    # Fetch all current option positions from Alpaca
    try:
        positions = ac.get_positions()
    except Exception as e:
        log.error("Cannot fetch positions: %s", e)
        return

    today = date.today()

    # ── 1. Monitor existing open strangles ──────────────────
    # This is the primary job each run: only stocks already in the
    # active state are checked here.  If there are none, this is a no-op.
    log.info("-- Phase 1: Monitoring %d active strangle(s) --", len(state["active"]))

    for symbol, pos in list(state["active"].items()):
        earnings_dt = date.fromisoformat(pos["earnings_date"])

        # Switch phase after earnings date has passed
        if pos["phase"] == "PRE_EARNINGS" and today > earnings_dt:
            log.info("  %s: earnings date passed — switching to POST_EARNINGS", symbol)
            sm.switch_to_post_earnings(state, symbol)
            pos["phase"] = "POST_EARNINGS"

        status = pos["status"]

        if status in ("OPEN", "CALL_SOLD"):
            # Same combined-position check whether we're pre- or post-earnings --
            # phase only matters for other bookkeeping, not for this decision.
            monitor_combined(symbol, pos, positions)

        elif status == "CLOSED":
            # Shouldn't be in active, but clean it up
            sm._archive(state, symbol)

    # ── 2. Scan for new strangle entries ────────────────────
    # For each watched stock NOT already in an open strangle, check whether
    # earnings are 14-21 days away.  If they are not, the stock is skipped
    # silently — we do nothing until that window arrives.
    open_symbols = set(state["active"].keys())
    open_count   = len(open_symbols)

    if open_count >= config.MAX_OPEN_STRANGLES:
        log.info("At max open strangles (%d/%d) — skipping entry scan.",
                 open_count, config.MAX_OPEN_STRANGLES)
    else:
        candidates_to_check = [s for s in config.WATCHED_STOCKS if s not in open_symbols]
        remaining_slots     = config.MAX_OPEN_STRANGLES - open_count
        log.info(
            "-- Phase 2: Checking %d stock(s) for earnings in %d-%d day window --",
            len(candidates_to_check), config.EARNINGS_MIN_DAYS, config.EARNINGS_MAX_DAYS,
        )
        log.info("  (Stocks with no earnings in that window are skipped — nothing to do)")

        candidates = es.scan_for_entries(
            symbols         = candidates_to_check,
            min_days        = config.EARNINGS_MIN_DAYS,
            max_days        = config.EARNINGS_MAX_DAYS,
            look_back       = config.LOOK_BACK_EARNINGS,
            min_qualifying  = config.MIN_QUALIFYING_EARNINGS,
            min_move_pct    = config.MIN_EARNINGS_MOVE_PCT,
        )

        if not candidates:
            log.info("  No stocks are in the earnings entry window right now — nothing to do.")
        else:
            log.info("  %d stock(s) in earnings window and passed move-history filter:", len(candidates))
            for c in candidates:
                log.info("    %s — earnings %s (%d days away)  %s",
                         c["symbol"], c["earnings_date"],
                         c["days_to_earnings"], c["move_history"])

        for c in candidates[:remaining_slots]:
            if c["symbol"] in state["active"]:
                continue
            try_open_strangle(c["symbol"], c["earnings_date"], state)

    # ── 3. Save state ────────────────────────────────────────
    sm.save(config.STATE_FILE, state)
    log.info("State saved. Active strangles: %d", len(state["active"]))
    log.info("=" * 62)


if __name__ == "__main__":
    run()
