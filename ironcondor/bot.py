"""
bot.py  --  Iron Condor Strategy — SPY · IWM · GLD
====================================================

Runs three independent Iron Condors simultaneously on uncorrelated ETFs:
  SPY  (S&P 500)    — ~0.75 correlation with IWM, ~0.05 with GLD
  IWM  (Russell 2K) — genuinely diversified vs large-cap
  GLD  (Gold)       — near-zero correlation to equities

Each symbol is managed independently: its own condor, its own state key,
its own adjustment logic. A loss on SPY does not force a close on IWM/GLD.

Run every 30 minutes via Task Scheduler during market hours.

Each run per symbol:
  1. If a condor is open  → monitor (profit target / stop-loss / delta adjustment)
  2. If no condor is open → scan for a valid entry
  3. Save state
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


def get_price(symbol: str) -> float:
    """Fetch current mid-price for any ETF."""
    try:
        import requests
        headers = {
            "APCA-API-KEY-ID":     config.ALPACA_API_KEY,
            "APCA-API-SECRET-KEY": config.ALPACA_SECRET_KEY,
        }
        r = requests.get(
            f"{config.ALPACA_DATA_URL}/stocks/{symbol}/quotes/latest",
            headers=headers, timeout=10,
        )
        if r.ok:
            q   = r.json().get("quote", {})
            ask = float(q.get("ap") or 0)
            bid = float(q.get("bp") or 0)
            if ask > 0 and bid > 0:
                return (ask + bid) / 2
        r2 = requests.get(
            f"{config.ALPACA_DATA_URL}/stocks/{symbol}/trades/latest",
            headers=headers, timeout=10,
        )
        if r2.ok:
            return float(r2.json().get("trade", {}).get("p") or 0)
    except Exception as e:
        log.error("Price fetch failed for %s: %s", symbol, e)
    return 0.0


# ── Opening a new condor ──────────────────────────────────────────────────────

def try_open_condor(symbol: str, state: dict, sym_cfg: dict) -> None:
    log.info("-- [%s] Scanning for Iron Condor entry --", symbol)

    price = get_price(symbol)
    if price <= 0:
        log.info("  [%s] Cannot get price — skipping", symbol)
        return

    log.info("  [%s] Price: $%.2f", symbol, price)

    sr_data  = None
    sr_notes = "S/R disabled"
    if config.USE_SR_LEVELS:
        sr_data = sr_module.analyse(
            symbol        = symbol,
            lookback_days = config.SR_LOOKBACK_DAYS,
            swing_window  = config.SR_SWING_WINDOW,
            max_distance  = config.SR_MAX_DISTANCE,
        )
        if sr_data:
            trend       = sr_data.get("trend", "neutral")
            supports    = [f"${s:.0f}" for s in sr_data.get("support",    [])[:3]]
            resistances = [f"${r:.0f}" for r in sr_data.get("resistance", [])[:3]]
            sr_notes    = (
                f"trend={trend}  "
                f"support={','.join(supports)}  "
                f"resistance={','.join(resistances)}  "
                f"MA50=${sr_data['ma50']:.1f}"
            )
            log.info("  [%s] %s", symbol, sr_notes)

    legs = os_.find_iron_condor(symbol, price, sr_data, sym_cfg)
    if legs is None:
        log.info("  [%s] No valid condor found — will retry next cycle", symbol)
        return

    legs["spy_price"] = price   # stored as entry price in state

    log.info("  [%s] Placing 4 orders...", symbol)
    try:
        ac.place_option_order(legs["short_put"],  "sell", config.CONDOR_QTY, legs["short_put_credit"])
        ac.place_option_order(legs["long_put"],   "buy",  config.CONDOR_QTY, legs["long_put_debit"])
        ac.place_option_order(legs["short_call"], "sell", config.CONDOR_QTY, legs["short_call_credit"])
        ac.place_option_order(legs["long_call"],  "buy",  config.CONDOR_QTY, legs["long_call_debit"])
    except Exception as e:
        log.error("  [%s] Order placement failed: %s", symbol, e)
        return

    sm.open_condor(state, symbol, legs)

    trend = sr_data.get("trend", "unknown") if sr_data else "unknown"
    notifier.notify_condor_opened(
        symbol            = symbol,
        spy_price         = price,
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
        "  [%s] Condor opened: [%.0f/%.0f]P · [%.0f/%.0f]C  credit=$%.2f  expiry=%s",
        symbol,
        legs["short_put_strike"], legs["long_put_strike"],
        legs["short_call_strike"], legs["long_call_strike"],
        legs["net_credit"], legs["expiry"],
    )


# ── Monitoring an open condor ─────────────────────────────────────────────────

def _current_cost_to_close(pos: dict) -> float:
    snaps  = ac.get_option_snapshots([
        pos["short_put"], pos["long_put"],
        pos["short_call"], pos["long_call"],
    ])
    sp_ask = ac.ask(snaps.get(pos["short_put"],  {})) or ac.mid(snaps.get(pos["short_put"],  {}))
    lp_bid = ac.bid_price(snaps.get(pos["long_put"],   {})) or ac.mid(snaps.get(pos["long_put"],   {}))
    sc_ask = ac.ask(snaps.get(pos["short_call"], {})) or ac.mid(snaps.get(pos["short_call"], {}))
    lc_bid = ac.bid_price(snaps.get(pos["long_call"],  {})) or ac.mid(snaps.get(pos["long_call"],  {}))
    return round((sp_ask - lp_bid) + (sc_ask - lc_bid), 4)


def _close_condor(symbol: str, state: dict, pos: dict, reason: str) -> None:
    log.info("  [%s] Closing condor: %s", symbol, reason)
    cost = _current_cost_to_close(pos)
    try:
        ac.place_option_order(pos["short_put"],  "buy",  config.CONDOR_QTY, cost / 2)
        ac.place_option_order(pos["long_put"],   "sell", config.CONDOR_QTY, 0.01)
        ac.place_option_order(pos["short_call"], "buy",  config.CONDOR_QTY, cost / 2)
        ac.place_option_order(pos["long_call"],  "sell", config.CONDOR_QTY, 0.01)
    except Exception as e:
        log.error("  [%s] Close orders failed: %s", symbol, e)
        return
    sm.close_condor(state, symbol, cost, reason)
    archived = state["history"][-1] if state["history"] else pos
    notifier.notify_closed(
        symbol        = symbol,
        reason        = reason,
        net_credit    = archived.get("net_credit", pos["net_credit"]),
        cost_to_close = cost,
        net_pnl       = archived.get("net_pnl", round((pos["net_credit"] - cost) * 100, 2)),
        pos           = archived,
    )


def _roll_side(symbol: str, state: dict, pos: dict, side: str, price: float) -> None:
    expiry = pos["expiry"]
    dtr    = days_to_expiry(expiry)

    if dtr < config.MIN_DTE_FOR_ADJUST:
        log.info("  [%s] Only %d DTE — closing instead of rolling", symbol, dtr)
        _close_condor(symbol, state, pos, f"Too close to expiry to adjust ({dtr} DTE)")
        return

    sym_cfg    = config.SYMBOL_CONFIGS.get(symbol, {})
    wing_width = sym_cfg.get("WING_WIDTH", config.WING_WIDTH)
    roll_dist  = wing_width * 1.5   # roll 1.5× wing width further OTM

    log.info("  [%s] Rolling %s side (DTE=%d)...", symbol, side.upper(), dtr)

    if side == "put":
        old_short_strike = pos["short_put_strike"]
        new_short_target = old_short_strike - roll_dist
        new_long_target  = new_short_target - wing_width
        option_type      = "put"
    else:
        old_short_strike = pos["short_call_strike"]
        new_short_target = old_short_strike + roll_dist
        new_long_target  = new_short_target + wing_width
        option_type      = "call"

    min_dte = max(1, dtr - 1)
    max_dte = dtr + 1

    new_short_contracts = ac.get_option_contracts(
        symbol, option_type, min_dte, max_dte,
        strike_gte=new_short_target - wing_width * 0.5,
        strike_lte=new_short_target + wing_width * 0.5,
    )
    new_short_contracts = [c for c in new_short_contracts
                           if c.get("expiration_date") == expiry]

    if not new_short_contracts:
        log.info("  [%s] No roll contracts available — closing", symbol)
        _close_condor(symbol, state, pos, "No roll contracts available")
        return

    new_short_c = min(new_short_contracts,
                      key=lambda c: abs(float(c["strike_price"]) - new_short_target))
    new_short_strike = float(new_short_c["strike_price"])

    from option_selector import _find_wing
    new_long_c, new_long_snap = _find_wing(symbol, expiry, new_short_strike,
                                           option_type, wing_width)
    if new_long_c is None:
        log.info("  [%s] No long wing for roll — closing", symbol)
        _close_condor(symbol, state, pos, "No long wing for roll")
        return

    new_long_strike = float(new_long_c["strike_price"])

    old_short_occ = pos["short_put"]  if side == "put" else pos["short_call"]
    old_long_occ  = pos["long_put"]   if side == "put" else pos["long_call"]

    snaps_old = ac.get_option_snapshots([old_short_occ, old_long_occ])
    snaps_new = ac.get_option_snapshots([new_short_c["symbol"], new_long_c["symbol"]])

    old_short_ask = ac.ask(snaps_old.get(old_short_occ, {})) or ac.mid(snaps_old.get(old_short_occ, {}))
    old_long_bid  = ac.bid_price(snaps_old.get(old_long_occ,  {})) or ac.mid(snaps_old.get(old_long_occ, {}))
    new_short_bid = ac.bid_price(snaps_new.get(new_short_c["symbol"], {})) or ac.mid(snaps_new.get(new_short_c["symbol"], {}))
    new_long_ask  = ac.ask(snaps_new.get(new_long_c["symbol"],  {})) or ac.mid(snaps_new.get(new_long_c["symbol"], {}))

    roll_debit  = old_short_ask - old_long_bid
    roll_credit = new_short_bid - new_long_ask
    net_roll    = round(roll_credit - roll_debit, 4)

    max_roll_debit = wing_width * 0.15   # allow debit up to 15% of wing width
    if net_roll < -max_roll_debit:
        log.info("  [%s] Roll debit $%.2f too large — closing", symbol, abs(net_roll))
        _close_condor(symbol, state, pos, f"Roll debit ${abs(net_roll):.2f} exceeds threshold")
        return

    try:
        ac.place_option_order(old_short_occ,         "buy",  config.CONDOR_QTY, old_short_ask)
        ac.place_option_order(old_long_occ,          "sell", config.CONDOR_QTY, max(old_long_bid, 0.01))
        ac.place_option_order(new_short_c["symbol"], "sell", config.CONDOR_QTY, new_short_bid)
        ac.place_option_order(new_long_c["symbol"],  "buy",  config.CONDOR_QTY, new_long_ask)
    except Exception as e:
        log.error("  [%s] Roll orders failed: %s", symbol, e)
        return

    sm.record_adjustment(
        state, symbol, side,
        old_short_occ, new_short_c["symbol"], new_long_c["symbol"],
        new_short_strike, new_long_strike, net_roll,
    )
    notifier.notify_adjustment(
        symbol            = symbol,
        side              = side,
        old_short_strike  = old_short_strike,
        new_short_strike  = new_short_strike,
        new_long_strike   = new_long_strike,
        roll_credit       = net_roll,
        days_remaining    = dtr,
        spy_price         = price,
        cumulative_credit = state["active"].get(symbol, {}).get("net_credit"),
    )


def monitor_condor(symbol: str, state: dict) -> None:
    pos = state["active"].get(symbol)
    if not pos:
        return

    expiry = pos["expiry"]
    dtr    = days_to_expiry(expiry)

    if dtr < 0:
        log.info("  [%s] Condor expired — marking closed (max profit)", symbol)
        sm.close_condor(state, symbol, 0.0, "Expired worthless (max profit)")
        archived = state["history"][-1] if state["history"] else pos
        notifier.notify_closed(
            symbol        = symbol,
            reason        = "Expired worthless (max profit)",
            net_credit    = archived.get("net_credit", pos["net_credit"]),
            cost_to_close = 0.0,
            net_pnl       = archived.get("net_pnl", pos["net_credit"] * 100),
            pos           = archived,
        )
        return

    log.info(
        "  [%s] Open: %d DTE  credit=$%.2f  [%.0f/%.0f]P · [%.0f/%.0f]C",
        symbol, dtr, pos["net_credit"],
        pos["short_put_strike"], pos["long_put_strike"],
        pos["short_call_strike"], pos["long_call_strike"],
    )

    snaps    = ac.get_option_snapshots([pos["short_put"], pos["short_call"]])
    sp_delta = ac.delta(snaps.get(pos["short_put"],  {}))
    sc_delta = ac.delta(snaps.get(pos["short_call"], {}))

    log.info("  [%s] Short put Δ=%.3f  |  Short call Δ=%.3f  (trigger=%.2f)",
             symbol, sp_delta, sc_delta, config.ADJUST_DELTA)

    price = get_price(symbol)

    if sp_delta >= config.ADJUST_DELTA and not pos.get("put_adjusted"):
        log.info("  [%s] PUT delta %.3f >= %.2f — rolling", symbol, sp_delta, config.ADJUST_DELTA)
        _roll_side(symbol, state, pos, "put", price)
        return

    if sc_delta >= config.ADJUST_DELTA and not pos.get("call_adjusted"):
        log.info("  [%s] CALL delta %.3f >= %.2f — rolling", symbol, sc_delta, config.ADJUST_DELTA)
        _roll_side(symbol, state, pos, "call", price)
        return

    cost_to_close = _current_cost_to_close(pos)
    pct_profit    = 1 - (cost_to_close / pos["net_credit"]) if pos["net_credit"] > 0 else 0

    log.info("  [%s] Cost=$%.2f  profit=%.0f%%  (target=%.0f%%)",
             symbol, cost_to_close, pct_profit * 100, config.PROFIT_TARGET_PCT * 100)

    if pct_profit >= config.PROFIT_TARGET_PCT:
        log.info("  [%s] PROFIT TARGET HIT", symbol)
        _close_condor(symbol, state, pos,
                      f"Profit target {config.PROFIT_TARGET_PCT*100:.0f}% reached")
        return

    loss_ratio = cost_to_close / pos["net_credit"] if pos["net_credit"] > 0 else 0
    if loss_ratio >= config.MAX_LOSS_RATIO:
        log.info("  [%s] STOP-LOSS: cost=%.1f× credit", symbol, loss_ratio)
        _close_condor(symbol, state, pos, f"Stop-loss: cost {loss_ratio:.1f}x credit")
        return

    log.info("  [%s] Holding — no action needed", symbol)


# ── Main ─────────────────────────────────────────────────────────────────────

def run() -> None:
    log.info("=" * 62)
    log.info("  IRON CONDOR BOT — %s", date.today().isoformat())
    log.info("  Symbols: %s", ", ".join(config.SYMBOLS))
    log.info("=" * 62)

    if not market_is_open():
        log.info("Market closed — exiting.")
        return

    state = sm.load(config.STATE_FILE)

    for symbol in config.SYMBOLS:
        sym_cfg = config.SYMBOL_CONFIGS.get(symbol, {})
        log.info("")
        if symbol in state["active"]:
            log.info("── Monitoring %s ──", symbol)
            monitor_condor(symbol, state)
        else:
            log.info("── Scanning %s for entry ──", symbol)
            try_open_condor(symbol, state, sym_cfg)

    sm.save(config.STATE_FILE, state)
    active_count = len(state["active"])
    log.info("")
    log.info("State saved. Active condors: %d / %d", active_count, len(config.SYMBOLS))
    log.info("=" * 62)


if __name__ == "__main__":
    run()
