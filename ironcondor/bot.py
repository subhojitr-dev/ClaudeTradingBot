"""
bot.py  --  Iron Condor Strategy on SPY
=========================================

Strategy: sell a bull-put spread + bear-call spread simultaneously on SPY,
collecting a net credit. Profit if SPY stays between the two short strikes
through expiry (14 DTE entry).

Run every 30 minutes via Task Scheduler during market hours.

Each run does three things and nothing else:
  1. If a condor is already open → monitor it (check profit target, stop-loss,
     and adjustment trigger on each short strike's delta)
  2. If no condor is open → scan for a valid entry (14 DTE window, S/R levels,
     delta ≤ 0.20, credit ≥ 33% of max risk)
  3. Save state

Adjustment logic (0.45 delta trigger):
  When a short strike's |delta| reaches 0.45 it means SPY has moved
  significantly toward that wing.  The bot rolls the threatened spread:
  - Buys back the original short + long (closes the threatened spread)
  - Sells a new spread at a strike 5-10 points further OTM, same expiry
  - If rolling produces a net credit → ideal; if small debit, still worth it
    to reduce risk of full assignment
  - If DTE < MIN_DTE_FOR_ADJUST → close the whole condor instead of rolling
"""

import logging
import os
import sys
from datetime import date

os.makedirs("logs", exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    handlers=[
        logging.FileHandler(os.path.join("logs", "ironcondor.log"), encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)

import config
import alpaca_client    as ac
import support_resistance as sr_module
import option_selector  as os_
import state_manager    as sm
import notifier


# ── Helpers ───────────────────────────────────────────────────────────────────

def market_is_open() -> bool:
    try:
        return ac.get_clock().get("is_open", False)
    except Exception as e:
        log.error("Clock check failed: %s", e)
        return False


def days_to_expiry(expiry_str: str) -> int:
    return (date.fromisoformat(expiry_str) - date.today()).days


# ── Opening a new condor ──────────────────────────────────────────────────────

def try_open_condor(state: dict) -> None:
    log.info("-- Scanning for Iron Condor entry --")

    spy_price = ac.get_spy_price()
    if spy_price <= 0:
        log.info("  Cannot get SPY price — skipping")
        return

    log.info("  SPY price: $%.2f", spy_price)

    # Fetch S/R data
    sr_data = None
    sr_notes = "S/R analysis disabled"
    if config.USE_SR_LEVELS:
        sr_data = sr_module.analyse(
            symbol        = config.SYMBOL,
            lookback_days = config.SR_LOOKBACK_DAYS,
            swing_window  = config.SR_SWING_WINDOW,
            max_distance  = config.SR_MAX_DISTANCE,
        )
        if sr_data:
            trend     = sr_data.get("trend", "neutral")
            supports  = [f"${s:.0f}" for s in sr_data.get("support",    [])[:3]]
            resistances = [f"${r:.0f}" for r in sr_data.get("resistance", [])[:3]]
            sr_notes  = (
                f"trend={trend}  "
                f"support={','.join(supports)}  "
                f"resistance={','.join(resistances)}  "
                f"MA50=${sr_data['ma50']:.1f}"
            )
            log.info("  %s", sr_notes)

    # Find legs
    legs = os_.find_iron_condor(spy_price, sr_data)
    if legs is None:
        log.info("  No valid condor found this run — will retry next cycle")
        return

    # Stamp the SPY price onto the legs dict for state record
    legs["spy_price"] = spy_price

    # Place the 4 orders (2 sells, 2 buys)
    log.info("  Placing 4 orders...")
    try:
        ac.place_option_order(legs["short_put"],  "sell", config.CONDOR_QTY, legs["short_put_credit"])
        ac.place_option_order(legs["long_put"],   "buy",  config.CONDOR_QTY, legs["long_put_debit"])
        ac.place_option_order(legs["short_call"], "sell", config.CONDOR_QTY, legs["short_call_credit"])
        ac.place_option_order(legs["long_call"],  "buy",  config.CONDOR_QTY, legs["long_call_debit"])
    except Exception as e:
        log.error("  Order placement failed: %s", e)
        return

    sm.open_condor(state, config.SYMBOL, legs)

    trend = sr_data.get("trend", "unknown") if sr_data else "unknown"
    notifier.notify_condor_opened(
        spy_price         = spy_price,
        expiry            = legs["expiry"],
        sp_strike         = legs["short_put_strike"],
        sp_delta          = legs["short_put_delta"],
        sp_credit         = legs["short_put_credit"],
        sc_strike         = legs["short_call_strike"],
        sc_delta          = legs["short_call_delta"],
        sc_credit         = legs["short_call_credit"],
        lp_strike         = legs["long_put_strike"],
        lc_strike         = legs["long_call_strike"],
        lp_debit          = legs.get("long_put_debit",  0),
        lc_debit          = legs.get("long_call_debit", 0),
        net_credit        = legs["net_credit"],
        max_risk          = legs["max_risk"],
        credit_ratio      = legs["credit_ratio"],
        trend             = trend,
        sr_notes          = sr_notes,
        support_levels    = sr_data.get("support",    []) if sr_data else [],
        resistance_levels = sr_data.get("resistance", []) if sr_data else [],
    )
    log.info(
        "  Condor opened: put_spread=[%.0f/%.0f]  call_spread=[%.0f/%.0f]"
        "  net_credit=$%.2f  expiry=%s",
        legs["short_put_strike"], legs["long_put_strike"],
        legs["short_call_strike"], legs["long_call_strike"],
        legs["net_credit"], legs["expiry"],
    )


# ── Monitoring an open condor ─────────────────────────────────────────────────

def _current_cost_to_close(pos: dict) -> float:
    """
    Fetch live prices for all four legs and compute the cost to buy back
    the spread (what we'd pay to close the condor now).
    """
    snaps = ac.get_option_snapshots([
        pos["short_put"], pos["long_put"],
        pos["short_call"], pos["long_call"],
    ])
    # To close: buy back the two shorts (pay ask), sell the two longs (receive bid)
    sp_ask = ac.ask(snaps.get(pos["short_put"],  {})) or ac.mid(snaps.get(pos["short_put"],  {}))
    lp_bid = ac.bid_price(snaps.get(pos["long_put"],   {})) or ac.mid(snaps.get(pos["long_put"],   {}))
    sc_ask = ac.ask(snaps.get(pos["short_call"], {})) or ac.mid(snaps.get(pos["short_call"], {}))
    lc_bid = ac.bid_price(snaps.get(pos["long_call"],  {})) or ac.mid(snaps.get(pos["long_call"],  {}))
    return round((sp_ask - lp_bid) + (sc_ask - lc_bid), 4)


def _close_condor(state: dict, pos: dict, reason: str) -> None:
    """Buy back the two short legs and sell the two long legs to close."""
    log.info("  Closing condor: %s", reason)
    cost = _current_cost_to_close(pos)
    try:
        ac.place_option_order(pos["short_put"],  "buy",  config.CONDOR_QTY, cost / 2)
        ac.place_option_order(pos["long_put"],   "sell", config.CONDOR_QTY, 0.01)
        ac.place_option_order(pos["short_call"], "buy",  config.CONDOR_QTY, cost / 2)
        ac.place_option_order(pos["long_call"],  "sell", config.CONDOR_QTY, 0.01)
    except Exception as e:
        log.error("  Close orders failed: %s", e)
        return
    sm.close_condor(state, config.SYMBOL, cost, reason)
    # pos is now in history; grab the archived copy for the notification
    archived = state["history"][-1] if state["history"] else pos
    notifier.notify_closed(
        reason        = reason,
        net_credit    = archived.get("net_credit", pos["net_credit"]),
        cost_to_close = cost,
        net_pnl       = archived.get("net_pnl", round((pos["net_credit"] - cost) * 100, 2)),
        pos           = archived,
    )


def _roll_side(state: dict, pos: dict, side: str, spy_price: float) -> None:
    """
    Roll the threatened side 5-10 points further OTM (same expiry).
    If the roll produces a credit → great.
    If it produces a small debit (<= 0.50) → still worth it to reduce risk.
    If the debit is large → close the whole condor instead.
    """
    expiry = pos["expiry"]
    dtr    = days_to_expiry(expiry)

    if dtr < config.MIN_DTE_FOR_ADJUST:
        log.info("  Only %d DTE left — closing instead of rolling", dtr)
        _close_condor(state, pos, f"Too close to expiry to adjust ({dtr} DTE)")
        return

    log.info("  Rolling %s side (DTE=%d)...", side.upper(), dtr)

    if side == "put":
        old_short_strike = pos["short_put_strike"]
        # New short put 5-10 points lower (further OTM)
        new_short_target = old_short_strike - 7.5   # aim 7.5 pts lower
        new_long_target  = new_short_target - config.WING_WIDTH
        option_type      = "put"
    else:
        old_short_strike = pos["short_call_strike"]
        new_short_target = old_short_strike + 7.5
        new_long_target  = new_short_target + config.WING_WIDTH
        option_type      = "call"

    # Find new contracts around those targets
    from option_selector import _find_wing
    import alpaca_client as ac2

    min_dte = max(1, dtr - 1)
    max_dte = dtr + 1

    new_short_contracts = ac.get_option_contracts(
        "SPY", option_type, min_dte, max_dte,
        strike_gte=new_short_target - 2.5,
        strike_lte=new_short_target + 2.5,
    )
    new_short_contracts = [c for c in new_short_contracts if c.get("expiration_date") == expiry]

    if not new_short_contracts:
        log.info("  No contracts found for roll target — closing condor instead")
        _close_condor(state, pos, "No roll contracts available")
        return

    # Pick the one closest to the target
    new_short_c = min(new_short_contracts,
                      key=lambda c: abs(float(c["strike_price"]) - new_short_target))
    new_short_strike = float(new_short_c["strike_price"])

    # New long wing
    new_long_c, new_long_snap = _find_wing("SPY", expiry, new_short_strike, option_type,
                                           config.WING_WIDTH)
    if new_long_c is None:
        log.info("  No long wing found for roll — closing instead")
        _close_condor(state, pos, "No long wing for roll")
        return

    new_long_strike = float(new_long_c["strike_price"])

    # Snapshot old contracts to get close prices
    if side == "put":
        old_short_occ = pos["short_put"]
        old_long_occ  = pos["long_put"]
    else:
        old_short_occ = pos["short_call"]
        old_long_occ  = pos["long_call"]

    snaps_old = ac.get_option_snapshots([old_short_occ, old_long_occ])
    snaps_new = ac.get_option_snapshots([new_short_c["symbol"], new_long_c["symbol"]])

    old_short_ask = ac.ask(snaps_old.get(old_short_occ, {})) or ac.mid(snaps_old.get(old_short_occ, {}))
    old_long_bid  = ac.bid_price(snaps_old.get(old_long_occ,  {})) or ac.mid(snaps_old.get(old_long_occ,  {}))
    new_short_bid = ac.bid_price(snaps_new.get(new_short_c["symbol"], {})) or ac.mid(snaps_new.get(new_short_c["symbol"], {}))
    new_long_ask  = ac.ask(snaps_new.get(new_long_c["symbol"],  {})) or ac.mid(snaps_new.get(new_long_c["symbol"],  {}))

    # Net cost of the roll
    # Close old spread: buy old short (pay ask), sell old long (receive bid)
    # Open new spread: sell new short (receive bid), buy new long (pay ask)
    roll_debit  = (old_short_ask - old_long_bid)    # cost to close old spread
    roll_credit = (new_short_bid - new_long_ask)    # credit from new spread
    net_roll    = round(roll_credit - roll_debit, 4)

    log.info(
        "  Roll %s: close old [%.0f/%.0f] debit=$%.2f | open new [%.0f/%.0f] credit=$%.2f | net=$%.2f",
        side.upper(),
        old_short_strike, float(new_long_c["strike_price"]),
        roll_debit,
        new_short_strike, new_long_strike,
        roll_credit,
        net_roll,
    )

    # If the roll costs more than $0.75/share debit, close instead
    if net_roll < -0.75:
        log.info("  Roll debit $%.2f too large — closing condor", abs(net_roll))
        _close_condor(state, pos, f"Roll debit ${abs(net_roll):.2f} exceeds threshold")
        return

    # Place the 4 roll orders
    try:
        ac.place_option_order(old_short_occ,          "buy",  config.CONDOR_QTY, old_short_ask)
        ac.place_option_order(old_long_occ,           "sell", config.CONDOR_QTY, max(old_long_bid, 0.01))
        ac.place_option_order(new_short_c["symbol"],  "sell", config.CONDOR_QTY, new_short_bid)
        ac.place_option_order(new_long_c["symbol"],   "buy",  config.CONDOR_QTY, new_long_ask)
    except Exception as e:
        log.error("  Roll orders failed: %s", e)
        return

    sm.record_adjustment(
        state, config.SYMBOL, side,
        old_short_occ, new_short_c["symbol"], new_long_c["symbol"],
        new_short_strike, new_long_strike, net_roll,
    )
    notifier.notify_adjustment(
        side              = side,
        old_short_strike  = old_short_strike,
        new_short_strike  = new_short_strike,
        new_long_strike   = new_long_strike,
        roll_credit       = net_roll,
        days_remaining    = dtr,
        spy_price         = spy_price,
        cumulative_credit = state["active"].get(config.SYMBOL, {}).get("net_credit"),
    )


def monitor_condor(state: dict) -> None:
    pos = state["active"].get(config.SYMBOL)
    if not pos:
        return

    expiry = pos["expiry"]
    dtr    = days_to_expiry(expiry)

    if dtr < 0:
        log.info("  Condor has expired — marking closed")
        sm.close_condor(state, config.SYMBOL, 0.0, "Expired worthless (max profit)")
        archived = state["history"][-1] if state["history"] else pos
        notifier.notify_closed(
            reason        = "Expired worthless (max profit)",
            net_credit    = archived.get("net_credit", pos["net_credit"]),
            cost_to_close = 0.0,
            net_pnl       = archived.get("net_pnl", pos["net_credit"] * 100),
            pos           = archived,
        )
        return

    log.info("  Condor open: %d DTE  net_credit=$%.2f  put_spread=[%.0f/%.0f]  call_spread=[%.0f/%.0f]",
             dtr, pos["net_credit"],
             pos["short_put_strike"], pos["long_put_strike"],
             pos["short_call_strike"], pos["long_call_strike"])

    # ── Fetch live Greeks for the two short legs ─────────────────────────────
    snaps = ac.get_option_snapshots([pos["short_put"], pos["short_call"]])
    sp_snap = snaps.get(pos["short_put"],  {})
    sc_snap = snaps.get(pos["short_call"], {})

    sp_delta = ac.delta(sp_snap)   # absolute value
    sc_delta = ac.delta(sc_snap)

    log.info("  Short put Δ=%.3f  |  Short call Δ=%.3f  (trigger=%.2f)",
             sp_delta, sc_delta, config.ADJUST_DELTA)

    spy_price = ac.get_spy_price()

    # ── Adjustment check ─────────────────────────────────────────────────────
    if sp_delta >= config.ADJUST_DELTA and not pos.get("put_adjusted"):
        log.info("  PUT side delta %.3f >= %.2f — rolling put spread",
                 sp_delta, config.ADJUST_DELTA)
        _roll_side(state, pos, "put", spy_price)
        return   # re-evaluate on next run

    if sc_delta >= config.ADJUST_DELTA and not pos.get("call_adjusted"):
        log.info("  CALL side delta %.3f >= %.2f — rolling call spread",
                 sc_delta, config.ADJUST_DELTA)
        _roll_side(state, pos, "call", spy_price)
        return

    # ── Profit target ─────────────────────────────────────────────────────────
    cost_to_close = _current_cost_to_close(pos)
    pct_profit    = 1 - (cost_to_close / pos["net_credit"]) if pos["net_credit"] > 0 else 0

    log.info("  Cost to close=$%.2f  profit captured=%.0f%%  (target=%.0f%%)",
             cost_to_close, pct_profit * 100, config.PROFIT_TARGET_PCT * 100)

    if pct_profit >= config.PROFIT_TARGET_PCT:
        log.info("  PROFIT TARGET HIT — closing condor")
        _close_condor(state, pos, f"Profit target {config.PROFIT_TARGET_PCT*100:.0f}% reached")
        return

    # ── Stop-loss ─────────────────────────────────────────────────────────────
    loss_ratio = cost_to_close / pos["net_credit"] if pos["net_credit"] > 0 else 0
    if loss_ratio >= config.MAX_LOSS_RATIO:
        log.info("  STOP-LOSS — cost_to_close $%.2f is %.1fx original credit — closing",
                 cost_to_close, loss_ratio)
        _close_condor(state, pos, f"Stop-loss: cost {loss_ratio:.1f}x credit")
        return

    log.info("  No action needed — holding condor")


# ── Main ─────────────────────────────────────────────────────────────────────

def run() -> None:
    log.info("=" * 62)
    log.info("  IRON CONDOR BOT — %s", date.today().isoformat())
    log.info("=" * 62)

    if not market_is_open():
        log.info("Market closed — exiting.")
        return

    state = sm.load(config.STATE_FILE)

    if state["active"]:
        log.info("-- Phase 1: Monitoring open condor --")
        monitor_condor(state)
    else:
        log.info("-- No open condor — scanning for entry --")
        try_open_condor(state)

    sm.save(config.STATE_FILE, state)
    active_count = len(state["active"])
    log.info("State saved. Active condors: %d", active_count)
    log.info("=" * 62)


if __name__ == "__main__":
    run()
