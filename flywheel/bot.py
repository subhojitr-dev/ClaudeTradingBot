"""
bot.py  --  Wheel Strategy Bot
================================
Scheduled every 30 minutes Mon-Fri 9:30 AM - 4:00 PM ET.

STAGE 1 -- Cash-Secured Put:
  - Sell put at 20% below stock price, 2-4 weeks DTE
  - Collect premium.  Expires worthless -> sell another.
  - 70% profit before expiry -> close and reopen.
  - Stock rises a lot (put worth <20% of entry) -> roll up to higher strike.
  - Assigned -> buy stock, move to Stage 2.

STAGE 2 -- Covered Call:
  - Sell call at 10% above stock price, 2-4 weeks DTE, delta >= 0.30.
  - Collect premium.  Expires worthless -> sell another.
  - 70% profit before expiry -> close and reopen.
  - Shares called away -> back to Stage 1.

Rules:
  - Never sell PUT unless cash >= strike * 100 (fully cash-secured).
  - Track total premium collected across all symbols and cycles.
  - Email notification on every significant event.
"""

import logging
import os
import sys
from datetime import date, datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import (
    WHEEL_STOCKS,
    CSP_STRIKE_DISCOUNT, CSP_MAX_DELTA, CSP_MIN_DTE, CSP_MAX_DTE,
    CC_STRIKE_PREMIUM, CC_MAX_DELTA, CC_MIN_DTE, CC_MAX_DTE,
    EARLY_CLOSE_PROFIT_PCT, ROLL_TRIGGER_PCT, ROLL_MIN_NET_CREDIT,
    STATE_FILE, LOG_DIR,
    NOTIFY_EMAIL, SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD,
)
import alpaca_client as ac
from option_selector import find_csp_contract, find_cc_contract, find_roll_up_contract
from state_manager import WheelState
import notifier

# ── Logging ────────────────────────────────────────────────────────────────────
os.makedirs(LOG_DIR, exist_ok=True)
_log_file = os.path.join(LOG_DIR, f"flywheel_{datetime.now().strftime('%Y%m%d')}.log")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    handlers=[
        logging.FileHandler(_log_file, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)




# ══════════════════════════════════════════════════════════════════════════════
#  STAGE 1 handler
# ══════════════════════════════════════════════════════════════════════════════

def handle_idle(symbol: str, sm: WheelState, positions: dict, cash: float) -> float:
    """IDLE: look to open a new cash-secured put."""
    price = ac.get_stock_price(symbol)
    if price <= 0:
        log.warning("%s: cannot get stock price, skipping", symbol)
        return cash

    result = find_csp_contract(
        symbol=symbol, current_price=price,
        strike_discount=CSP_STRIKE_DISCOUNT,
        max_delta=CSP_MAX_DELTA,
        min_dte=CSP_MIN_DTE, max_dte=CSP_MAX_DTE,
    )
    if not result:
        log.info("%s: no suitable CSP contract found", symbol)
        return cash

    contract, snapshot, sell_price = result
    strike        = float(contract.get("strike_price", 0))
    cash_required = strike * 100   # 1 contract = 100 shares

    # RULE: Never sell put unless cash covers full assignment
    if cash < cash_required:
        msg = (
            f"Insufficient cash for {symbol} CSP.\n"
            f"Need ${cash_required:,.0f} (strike ${strike:.2f} x 100 shares)\n"
            f"Available: ${cash:,.0f}\n"
            f"Please add funds to account PA34EFPV3B80."
        )
        log.warning(msg)
        notifier.notify_skipped(symbol, cash, cash_required, strike)
        return cash

    log.info("%s: SELL PUT  %s  strike=$%.2f  sell=$%.2f  cash_needed=$%.0f",
             symbol, contract["symbol"], strike, sell_price, cash_required)

    try:
        order = ac.place_option_order(contract["symbol"], "sell", 1, sell_price)
        sm.open_csp(symbol, contract, sell_price, 1, order["id"])
        notifier.notify_csp_opened(
            symbol=symbol, contract_sym=contract["symbol"],
            strike=strike, sell_price=sell_price,
            expiry=contract.get("expiration_date", ""),
            stock_price=price, cash_required=cash_required,
            csp_strike_discount=CSP_STRIKE_DISCOUNT, order_id=order["id"],
        )
        return cash - cash_required   # reserve collateral

    except Exception as e:
        log.error("%s: CSP order failed: %s", symbol, e)
        return cash


# ══════════════════════════════════════════════════════════════════════════════
#  STAGE 1 monitor (active CSP)
# ══════════════════════════════════════════════════════════════════════════════

def handle_csp(symbol: str, sm: WheelState, positions: dict, cash: float) -> float:
    """Monitor an open cash-secured put."""
    s            = sm.get(symbol)
    contract_sym = s.get("contract_symbol")
    entry_prem   = s.get("entry_premium", 0)
    expiry_str   = s.get("contract_expiry")
    strike       = s.get("contract_strike", 0)
    entry_date   = s.get("entry_date")

    opt_in_pos   = contract_sym in positions
    stock_in_pos = symbol in positions
    today        = date.today()
    is_expired   = expiry_str and today > date.fromisoformat(expiry_str)

    # ── Order placed today but not yet filled ────────────────────────────────
    if entry_date == today.isoformat() and not opt_in_pos:
        log.info("%s: CSP order placed today, waiting for fill", symbol)
        return cash

    # ── Expiry handling ──────────────────────────────────────────────────────
    if is_expired:
        if not opt_in_pos and not stock_in_pos:
            # Expired worthless -- full premium kept
            log.info("%s: CSP expired WORTHLESS -- collecting $%.2f", symbol, entry_prem * 100)
            sm.csp_expired_worthless(symbol)
            notifier.notify_csp_expired(
                symbol=symbol, entry_prem=entry_prem,
                total_premium=sm.get(symbol).get("total_premium_collected", 0),
                grand_total=sm.total_premium(),
            )
            return cash + strike * 100   # release collateral

        if not opt_in_pos and stock_in_pos:
            # Assigned -- stock delivered at strike price
            pos    = positions[symbol]
            shares = int(float(pos.get("qty") or 100))
            log.info("%s: PUT ASSIGNED -- received %d shares at $%.2f", symbol, shares, strike)
            sm.csp_assigned(symbol, shares)
            eff_cost = round(strike - entry_prem, 2)
            notifier.notify_assigned(
                symbol=symbol, shares=shares, strike=strike,
                entry_prem=entry_prem, eff_cost=eff_cost,
            )
            return cash   # cash used to pay for stock

    # ── Position disappeared before expiry ───────────────────────────────────
    if not opt_in_pos and not is_expired:
        if stock_in_pos:
            # Early assignment (rare)
            pos    = positions[symbol]
            shares = int(float(pos.get("qty") or 100))
            log.info("%s: Early assignment detected", symbol)
            sm.csp_assigned(symbol, shares)
            return cash
        else:
            # Order probably not filled yet or position data lag
            log.warning("%s: CSP not found in positions -- will check next run", symbol)
            return cash

    if not opt_in_pos:
        return cash

    # ── Get current option price ─────────────────────────────────────────────
    snap          = ac.get_option_snapshot(contract_sym)
    current_val   = ac.get_mid_price(snap)

    if current_val <= 0:
        log.warning("%s: could not get current put price", symbol)
        return cash

    profit_pct = (entry_prem - current_val) / entry_prem if entry_prem > 0 else 0
    log.info("%s CSP | entry=$%.4f  now=$%.4f  profit=%.1f%%  strike=$%.2f  exp=%s",
             symbol, entry_prem, current_val, profit_pct * 100, strike, expiry_str)

    # ── Rule: Close at 70% profit ────────────────────────────────────────────
    if profit_pct >= EARLY_CLOSE_PROFIT_PCT:
        buy_price = round(ac.get_ask_price(snap) or current_val * 1.05, 2)
        log.info("%s: 70%% profit target hit ($%.4f)! Buying to close.", symbol, current_val)
        try:
            ac.place_option_order(contract_sym, "buy", 1, buy_price)
            sm.csp_closed_early(symbol, current_val, "70pct_profit")
            notifier.notify_csp_closed_early(
                symbol=symbol, entry_prem=entry_prem, current_val=current_val,
            )
            return cash + strike * 100   # release collateral
        except Exception as e:
            log.error("%s: buy-to-close failed: %s", symbol, e)
        return cash

    # ── Rule: Roll up if put is nearly worthless (stock rose) ────────────────
    if profit_pct >= ROLL_TRIGGER_PCT:
        stock_price = ac.get_stock_price(symbol)
        log.info("%s: put at %.1f%% profit, checking roll-up (stock=$%.2f)",
                 symbol, profit_pct * 100, stock_price)
        roll = find_roll_up_contract(
            symbol=symbol,
            current_price=stock_price,
            current_strike=strike,
            expiry_date=expiry_str,
            min_net_credit=ROLL_MIN_NET_CREDIT,
            current_put_value=current_val,
        )
        if roll:
            new_c, new_snap, new_mid = roll
            new_strike   = float(new_c.get("strike_price", 0))
            net_credit   = new_mid - current_val
            buy_price    = round(ac.get_ask_price(snap) or current_val * 1.05, 2)
            sell_price   = round(new_mid * 0.98, 2)
            log.info("%s: rolling put $%.2f -> $%.2f, net credit $%.2f",
                     symbol, strike, new_strike, net_credit * 100)
            try:
                ac.place_option_order(contract_sym, "buy", 1, buy_price)
                ac.place_option_order(new_c["symbol"], "sell", 1, sell_price)
                # Record close of old put then open of new put
                sm.csp_closed_early(symbol, current_val, f"roll_up_to_{new_strike:.0f}")
                sm.open_csp(symbol, new_c, sell_price, 1, "roll_order")
                extra_collateral = (new_strike - strike) * 100
                notifier.notify_rolled_up(
                    symbol=symbol, old_strike=strike, new_strike=new_strike,
                    net_credit=net_credit, expiry=expiry_str,
                )
                return cash - extra_collateral
            except Exception as e:
                log.error("%s: roll-up failed: %s", symbol, e)

    return cash


# ══════════════════════════════════════════════════════════════════════════════
#  STAGE 2 handler
# ══════════════════════════════════════════════════════════════════════════════

def handle_cc(symbol: str, sm: WheelState, positions: dict, cash: float) -> float:
    """Stage 2: manage stock + optional open covered call."""
    s            = sm.get(symbol)
    contract_sym = s.get("contract_symbol")
    entry_prem   = s.get("entry_premium", 0)
    expiry_str   = s.get("contract_expiry")
    call_strike  = s.get("contract_strike", 0)
    entry_date   = s.get("entry_date")
    stock_qty    = s.get("stock_qty", 100)
    stock_cost   = s.get("stock_avg_cost", 0)

    stock_in_pos = symbol in positions
    opt_in_pos   = contract_sym and (contract_sym in positions)
    today        = date.today()
    is_expired   = expiry_str and today > date.fromisoformat(expiry_str)

    # ── Shares were called away ──────────────────────────────────────────────
    if not stock_in_pos:
        if call_strike and is_expired:
            stock_price = call_strike
            stock_pnl   = (call_strike - stock_cost) * stock_qty
            log.info("%s: shares CALLED AWAY at $%.2f (P&L $%+.2f)", symbol, call_strike, stock_pnl)
            sm.cc_called_away(symbol)
            notifier.notify_called_away(
                symbol=symbol, stock_qty=stock_qty, call_strike=call_strike,
                stock_pnl=stock_pnl, stock_cost=stock_cost, entry_prem=entry_prem,
            )
        else:
            log.warning("%s: stock not in positions (unexpected) -- resetting to IDLE", symbol)
            sm._data[symbol]["stage"] = "IDLE"
            sm._data[symbol]["stock_qty"] = 0
            sm.save()
        return cash

    # ── No open call yet (or call order placed today) ────────────────────────
    if not contract_sym or (entry_date == today.isoformat() and not opt_in_pos):
        if entry_date == today.isoformat() and not opt_in_pos:
            log.info("%s: CC order placed today, waiting for fill", symbol)
            return cash

        # Sell a new covered call
        price = ac.get_stock_price(symbol)
        if price <= 0:
            return cash

        result = find_cc_contract(
            symbol=symbol, current_price=price,
            strike_premium=CC_STRIKE_PREMIUM,
            max_delta=CC_MAX_DELTA,
            min_dte=CC_MIN_DTE, max_dte=CC_MAX_DTE,
        )
        if not result:
            log.info("%s: no suitable CC contract found", symbol)
            return cash

        contract, snapshot, sell_price = result
        c_strike = float(contract.get("strike_price", 0))
        delta    = ac.get_delta(snapshot)

        log.info("%s: SELL CALL  %s  strike=$%.2f  sell=$%.2f  delta=%.3f",
                 symbol, contract["symbol"], c_strike, sell_price, delta)
        try:
            order = ac.place_option_order(contract["symbol"], "sell", 1, sell_price)
            sm.open_cc(symbol, contract, sell_price, 1, order["id"])
            notifier.notify_cc_opened(
                symbol=symbol, contract_sym=contract["symbol"],
                c_strike=c_strike, sell_price=sell_price,
                expiry=contract.get("expiration_date", ""),
                stock_price=price, delta=delta, stock_cost=stock_cost,
                cc_strike_premium=CC_STRIKE_PREMIUM, order_id=order["id"],
            )
        except Exception as e:
            log.error("%s: CC order failed: %s", symbol, e)
        return cash

    # ── Monitor existing covered call ────────────────────────────────────────
    if not opt_in_pos:
        # Call expired or was exercised
        if is_expired and stock_in_pos:
            log.info("%s: CC expired worthless -- keeping stock, collect $%.2f",
                     symbol, entry_prem * 100)
            sm.cc_expired_worthless(symbol)
            notifier.notify_cc_expired(
                symbol=symbol, entry_prem=entry_prem, stock_qty=stock_qty,
                total_premium=sm.get(symbol).get("total_premium_collected", 0),
            )
        return cash

    snap        = ac.get_option_snapshot(contract_sym)
    current_val = ac.get_mid_price(snap)

    if current_val <= 0:
        log.warning("%s: could not get current call price", symbol)
        return cash

    profit_pct = (entry_prem - current_val) / entry_prem if entry_prem > 0 else 0
    log.info("%s CC | entry=$%.4f  now=$%.4f  profit=%.1f%%  strike=$%.2f  exp=%s",
             symbol, entry_prem, current_val, profit_pct * 100, call_strike, expiry_str)

    # Rule: Close at 70% profit
    if profit_pct >= EARLY_CLOSE_PROFIT_PCT:
        buy_price = round(ac.get_ask_price(snap) or current_val * 1.05, 2)
        log.info("%s: CC 70%% profit hit! Buying to close.", symbol)
        try:
            ac.place_option_order(contract_sym, "buy", 1, buy_price)
            sm.cc_closed_early(symbol, current_val)
            notifier.notify_cc_closed_early(
                symbol=symbol, entry_prem=entry_prem, current_val=current_val,
                stock_qty=stock_qty,
            )
        except Exception as e:
            log.error("%s: CC buy-to-close failed: %s", symbol, e)

    return cash


# ══════════════════════════════════════════════════════════════════════════════
#  Main runner
# ══════════════════════════════════════════════════════════════════════════════

def run():
    log.info("=" * 62)
    log.info("Wheel Strategy Bot  --  %s", datetime.now(timezone.utc).isoformat())
    log.info("Account: PA34EFPV3B80")
    log.info("=" * 62)

    # Account
    try:
        acct = ac.get_account()
        cash = float(acct.get("cash", 0))
        bp   = float(acct.get("buying_power", 0))
        pv   = float(acct.get("portfolio_value", 0))
        log.info("Cash=$%.2f  BP=$%.2f  Portfolio=$%.2f", cash, bp, pv)
    except Exception as e:
        log.error("Cannot reach Alpaca: %s", e)
        sys.exit(1)

    # Market check
    clock    = ac.get_clock()
    is_open  = clock.get("is_open", False)
    next_open = clock.get("next_open", "")
    log.info("Market: %s  (next open: %s)", "OPEN" if is_open else "CLOSED", next_open)

    if not is_open:
        log.info("Market closed -- no action taken. Daily report runs at 4 PM ET.")
        return

    # Load state + positions
    sm        = WheelState(STATE_FILE)
    positions = ac.get_positions()
    log.info("Open positions: %s", list(positions.keys()))

    # Ensure all wheel symbols are initialised
    for sym in WHEEL_STOCKS:
        sm.init_symbol(sym)

    # Process each symbol
    for sym in WHEEL_STOCKS:
        log.info("-" * 50)
        s     = sm.get(sym)
        stage = s.get("stage", "IDLE")
        total = s.get("total_premium_collected", 0)
        log.info("%s | Stage: %-5s | Total premium: $%.2f", sym, stage, total)

        try:
            if stage == "IDLE":
                cash = handle_idle(sym, sm, positions, cash)
            elif stage == "CSP":
                cash = handle_csp(sym, sm, positions, cash)
            elif stage == "CC":
                cash = handle_cc(sym, sm, positions, cash)
        except Exception as e:
            log.error("Unhandled error for %s: %s", sym, e, exc_info=True)

    log.info("=" * 62)
    log.info("Run complete | Grand total premium: $%.2f", sm.total_premium())
    log.info("=" * 62)


if __name__ == "__main__":
    run()
