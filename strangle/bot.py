"""
bot.py  --  Bi-Directional Strangle Strategy (Earnings Play)
=============================================================

Strategy overview
-----------------
2–3 weeks before earnings on a watched stock:
  1. Check IV is average or below (≤ 50th percentile of own history)
  2. Confirm stock has historically moved ≥ 4% on at least 4 of last 8 reports
  3. Buy 1 OTM CALL + 1 OTM PUT, both ~0.30 delta, ~90 DTE

PRE-EARNINGS monitoring (every 30 min during market hours):
  - If CALL price rises 15%+ → sell the call, keep the put

After earnings date passes → POST-EARNINGS phase:
  - Stock can run, then revert; put gains value
  - If PUT price rises 10%+ → sell the put → trade fully closed

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

    sm.open_strangle(state, symbol, legs, earnings_date)

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


# ── Pre-earnings monitoring ────────────────────────────────────

def monitor_pre_earnings(symbol: str, pos: dict, positions: dict) -> None:
    """Check if call has hit 15% profit target — sell it if so."""
    call_occ   = pos["call_contract"]
    entry      = pos["call_entry_price"]

    # Check whether call is still in our Alpaca positions
    if call_occ not in positions:
        log.info("  %s: call %s no longer in positions (may have been filled/expired)", symbol, call_occ)
        return

    snap       = ac.get_option_snapshot(call_occ)
    mid        = ac.extract_mid(snap)
    if mid <= 0:
        log.info("  %s: call price unavailable", symbol)
        return

    gain_pct = (mid - entry) / entry
    log.info("  %s: CALL @ $%.2f vs entry $%.2f → gain %.1f%%",
             symbol, mid, entry, gain_pct * 100)

    if gain_pct >= config.CALL_PROFIT_TARGET_PCT:
        log.info("  %s: CALL profit target hit (%.1f%% ≥ %.0f%%) — SELLING CALL",
                 symbol, gain_pct * 100, config.CALL_PROFIT_TARGET_PCT * 100)
        try:
            ac.place_option_order(call_occ, "sell", 1, mid)
        except Exception as e:
            log.error("  %s: sell call failed: %s", symbol, e)
            return
        sm.record_call_sold(state_ref[0], symbol, mid)
        notify.notify_call_sold(symbol, call_occ, entry, mid, gain_pct)


# Mutable container so monitor helpers can mutate state
state_ref = [None]


# ── Post-earnings monitoring ───────────────────────────────────

def monitor_post_earnings(symbol: str, pos: dict, positions: dict) -> None:
    """Check if put has hit 10% profit target — sell it if so."""
    put_occ = pos["put_contract"]
    entry   = pos["put_entry_price"]

    if put_occ not in positions:
        log.info("  %s: put %s no longer in positions — abandoning", symbol, put_occ)
        sm.abandon(state_ref[0], symbol, "put position disappeared")
        return

    snap = ac.get_option_snapshot(put_occ)
    mid  = ac.extract_mid(snap)
    if mid <= 0:
        log.info("  %s: put price unavailable", symbol)
        return

    gain_pct = (mid - entry) / entry
    log.info("  %s: PUT @ $%.2f vs entry $%.2f → gain %.1f%%",
             symbol, mid, entry, gain_pct * 100)

    if gain_pct >= config.PUT_PROFIT_TARGET_PCT:
        log.info("  %s: PUT profit target hit (%.1f%% ≥ %.0f%%) — SELLING PUT",
                 symbol, gain_pct * 100, config.PUT_PROFIT_TARGET_PCT * 100)
        try:
            ac.place_option_order(put_occ, "sell", 1, mid)
        except Exception as e:
            log.error("  %s: sell put failed: %s", symbol, e)
            return
        sm.record_put_sold(state_ref[0], symbol, mid)
        s = state_ref[0]["active"].get(symbol, state_ref[0]["history"][-1])
        notify.notify_put_sold(symbol, put_occ, entry, mid, gain_pct, s.get("net_pnl", 0))


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
        phase  = pos["phase"]

        if status == "OPEN" and phase == "PRE_EARNINGS":
            monitor_pre_earnings(symbol, pos, positions)

        elif status in ("OPEN", "CALL_SOLD") and phase == "POST_EARNINGS":
            # If OPEN in post-earnings, the call was never sold — it can still
            # be sold now too, but our primary focus is the put.
            if status == "OPEN" and pos["call_contract"] in positions:
                monitor_pre_earnings(symbol, pos, positions)
            monitor_post_earnings(symbol, pos, positions)

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
