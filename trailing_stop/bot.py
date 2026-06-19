"""
bot.py  --  Trailing Stop Strategy Monitor
==========================================
Runs every 30 minutes via Windows Task Scheduler (or manually).

Rules implemented
-----------------
Rule 1  STOP LOSS     : If price drops 10% from entry -> sell everything
Rule 2  TRAILING STOP : Once up 10%, stop = 5% below highest seen (only rises)
Rule 3  LADDER IN     : If price drops 20% from entry -> buy 10 more shares
Rule 4  BALANCE GUARD : Never buy if cash < $10,000. Alert user.
Rule 5  PHARMA SCAN   : Each morning scan Finviz + FDA RSS for biotech/pharma
                        stocks with catalyst events (FDA approval, Phase 3
                        results, PDUFA dates). Auto-add matching stocks to the
                        trailing stop + ladder strategy for that day.
"""

import logging
import os
import sys
from datetime import datetime, timezone

# Allow import of config from same folder and shared notifier from parent
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import (
    ALPACA_API_KEY, ALPACA_SECRET_KEY, ALPACA_BASE_URL, ALPACA_DATA_URL,
    WATCHED_STOCKS, INITIAL_QTY, LADDER_QTY,
    STOP_LOSS_PCT, TRAIL_TRIGGER_PCT, TRAIL_STOP_PCT, LADDER_IN_DROP_PCT,
    MIN_CASH_BALANCE, STATE_FILE, LOG_DIR, NOTIFY_EMAIL,
    PHARMA_SCAN_ENABLED, PHARMA_MAX_STOCKS, PHARMA_SKIP_EVENTS,
    CATALYST_CACHE, SECTOR_CACHE,
)
from state_manager import StateManager
import notifier
import config as cfg
import pharma_catalyst

import requests

# ── Logging ────────────────────────────────────────────────────────────────────
os.makedirs(LOG_DIR, exist_ok=True)
log_file = os.path.join(LOG_DIR, f"trailing_{datetime.now().strftime('%Y%m%d')}.log")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    handlers=[
        logging.FileHandler(log_file, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)

HEADERS = {
    "APCA-API-KEY-ID":     ALPACA_API_KEY,
    "APCA-API-SECRET-KEY": ALPACA_SECRET_KEY,
    "Content-Type":        "application/json",
}


# ── Alpaca helpers ─────────────────────────────────────────────────────────────

def get_account():
    r = requests.get(f"{ALPACA_BASE_URL}/account", headers=HEADERS)
    r.raise_for_status()
    return r.json()


def get_positions():
    r = requests.get(f"{ALPACA_BASE_URL}/positions", headers=HEADERS)
    r.raise_for_status()
    return {p["symbol"]: p for p in r.json()}


def get_clock():
    r = requests.get(f"{ALPACA_BASE_URL}/clock", headers=HEADERS)
    r.raise_for_status()
    return r.json()


def get_latest_price(symbol: str) -> float:
    """Returns mid-point of latest bid/ask. Falls back to last trade price."""
    try:
        r = requests.get(
            f"{ALPACA_DATA_URL}/stocks/{symbol}/quotes/latest",
            headers=HEADERS, timeout=10
        )
        if r.ok:
            q = r.json().get("quote", {})
            ask, bid = float(q.get("ap", 0)), float(q.get("bp", 0))
            if ask > 0 and bid > 0:
                return (ask + bid) / 2
    except Exception:
        pass
    # Fallback: last trade
    try:
        r = requests.get(
            f"{ALPACA_DATA_URL}/stocks/{symbol}/trades/latest",
            headers=HEADERS, timeout=10
        )
        if r.ok:
            return float(r.json().get("trade", {}).get("p", 0))
    except Exception:
        pass
    return 0.0


def place_order(symbol: str, qty: int, side: str, reason: str) -> dict:
    payload = {
        "symbol":        symbol,
        "qty":           qty,
        "side":          side,
        "type":          "market",
        "time_in_force": "day",
    }
    r = requests.post(f"{ALPACA_BASE_URL}/orders", headers=HEADERS, json=payload)
    if not r.ok:
        log.error("Order FAILED %s %s x%d [%s]: %s", side, symbol, qty, reason, r.text[:200])
        r.raise_for_status()
    order = r.json()
    log.info("Order PLACED >> %s %s x%d [%s] | ID=%s Status=%s",
             side.upper(), symbol, qty, reason, order["id"], order["status"])
    return order


def print_order_summary(symbol: str, side: str, qty: int, price: float,
                        reason: str, order: dict, state: dict):
    """Print a clear, formatted confirmation block after every order."""
    bar = "=" * 58
    print(f"\n{bar}")
    print(f"  ORDER CONFIRMATION")
    print(f"{bar}")
    print(f"  Symbol    : {symbol}")
    print(f"  Side      : {side.upper()}")
    print(f"  Qty       : {qty} shares")
    print(f"  Price ref : ${price:.2f}  (market order, fills at best price)")
    print(f"  Reason    : {reason}")
    print(f"  Order ID  : {order.get('id')}")
    print(f"  Status    : {order.get('status')}")
    print(f"  Time (UTC): {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')}")
    if state:
        print(f"  --- Strategy State After Order ---")
        print(f"  Entry price : ${state.get('entry_price', 0):.2f}")
        print(f"  Stop loss   : ${state.get('stop_price', 0):.2f}")
        print(f"  Total shares: {state.get('total_shares', 0)}")
        print(f"  Trailing on : {'YES' if state.get('trailing_active') else 'NO'}")
        print(f"  Ladder count: {state.get('ladder_count', 0)}")
    print(f"{bar}\n")


def alert_low_balance(cash: float):
    msg = (
        f"\n{'!'*58}\n"
        f"  LOW BALANCE ALERT\n"
        f"  Cash: ${cash:,.2f}  --  Below minimum ${MIN_CASH_BALANCE:,}\n"
        f"  ACTION REQUIRED: Please add funds to {NOTIFY_EMAIL}\n"
        f"  No new BUY orders will be placed until balance is restored.\n"
        f"{'!'*58}\n"
    )
    log.warning(msg)
    print(msg)


# ── Main strategy logic ────────────────────────────────────────────────────────

def run():
    log.info("=" * 58)
    log.info("Trailing Stop Bot -- %s", datetime.now(timezone.utc).isoformat())
    log.info("=" * 58)

    # ── 1. Account check ─────────────────────────────────────────────────────
    try:
        acct  = get_account()
        cash  = float(acct["cash"])
        bp    = float(acct["buying_power"])
        pv    = float(acct["portfolio_value"])
        log.info("Account PA31HKOPMG4M | Cash=$%.2f | Buying Power=$%.2f | Portfolio=$%.2f",
                 cash, bp, pv)
    except Exception as e:
        log.error("Cannot reach Alpaca: %s", e)
        sys.exit(1)

    # ── 2. Market clock ──────────────────────────────────────────────────────
    clock      = get_clock()
    mkt_open   = clock.get("is_open", False)
    next_open  = clock.get("next_open", "")
    log.info("Market: %s  (next open: %s)", "OPEN" if mkt_open else "CLOSED", next_open)

    # ── 3. Load state ────────────────────────────────────────────────────────
    sm = StateManager(STATE_FILE)

    # ── 3b. Pharma Catalyst Scan (Rule 5) ────────────────────────────────────
    # Runs once per day; cached results reused on subsequent 30-min ticks.
    active_symbols = list(WATCHED_STOCKS)   # start with base list
    if PHARMA_SCAN_ENABLED and mkt_open:
        try:
            catalysts = pharma_catalyst.scan_today(
                max_stocks=PHARMA_MAX_STOCKS,
                skip_event_types=PHARMA_SKIP_EVENTS,
                cache_file=CATALYST_CACHE,
                sector_cache_file=SECTOR_CACHE,
            )
            for cat in catalysts:
                ticker     = cat["ticker"]
                event_type = cat["event_type"]
                headline   = cat["headline"]

                if ticker in active_symbols:
                    log.info("Pharma catalyst %s (%s) already in watch list", ticker, event_type)
                    continue

                # Only add if this is a POSITIVE catalyst
                if event_type in PHARMA_SKIP_EVENTS:
                    log.info("Skipping %s -- event type %s is in skip list", ticker, event_type)
                    continue

                log.info(
                    "PHARMA CATALYST >> Adding %s to watch list | %s | %s",
                    ticker, event_type, headline[:80],
                )
                active_symbols.append(ticker)

                # Email alert
                notifier.notify_pharma_catalyst(
                    ticker=ticker, event_type=event_type,
                    headline=headline, source=cat.get("source", "N/A"),
                    initial_qty=INITIAL_QTY, cfg=cfg,
                )

        except Exception as e:
            log.error("Pharma catalyst scan error (non-fatal): %s", e)

    log.info("Active watch list (%d symbols): %s", len(active_symbols), active_symbols)

    # ── 4. Sync positions from Alpaca (in case state is stale after restart) ─
    positions = get_positions()
    for sym in active_symbols:
        s = sm.get(sym)
        if sym in positions and not s:
            # Position exists in Alpaca but not in our state -- initialise
            pos       = positions[sym]
            avg_entry = float(pos["avg_entry_price"])
            qty       = int(float(pos["qty"]))
            log.info("Syncing %s from Alpaca positions: qty=%d entry=%.4f", sym, qty, avg_entry)
            sm.init_symbol(sym, avg_entry, qty)

    # ── 5. Initialise state for any stock not yet tracked ────────────────────
    for sym in active_symbols:
        if not sm.get(sym):
            # No position and no state -- buy it now (initial entry)
            if cash < MIN_CASH_BALANCE + 500:  # keep buffer
                alert_low_balance(cash)
                log.warning("Skipping initial buy of %s -- low balance", sym)
                continue
            cur_price = get_latest_price(sym)
            log.info("No state for %s -- placing initial buy @ ~$%.2f", sym, cur_price)
            try:
                order = place_order(sym, INITIAL_QTY, "buy", "INITIAL ENTRY")
                sm.init_symbol(sym, cur_price, INITIAL_QTY)
                sm.record_order(sym, {"type": "initial_buy", "price_ref": cur_price,
                                      "qty": INITIAL_QTY, "order_id": order["id"]})
                print_order_summary(sym, "buy", INITIAL_QTY, cur_price,
                                    "INITIAL ENTRY", order, sm.get(sym))
                cash -= cur_price * INITIAL_QTY
            except Exception as e:
                log.error("Initial buy failed for %s: %s", sym, e)

    # ── 6. Price-check and apply rules for every active symbol ───────────────
    prices = {}
    for sym in sm.active_symbols() or active_symbols:
        cur = get_latest_price(sym)
        if cur <= 0:
            log.warning("%s -- could not get price, skipping this tick", sym)
            continue
        prices[sym] = cur
        s           = sm.get(sym)
        entry       = s["entry_price"]
        stop        = s["stop_price"]
        total_shares = s["total_shares"]

        log.info("%s  cur=$%.2f  entry=$%.2f  stop=$%.2f  shares=%d",
                 sym, cur, entry, stop, total_shares)

        # -- Update trailing state (raises stop if price is higher) -----------
        sm.update_price(sym, cur, TRAIL_TRIGGER_PCT, TRAIL_STOP_PCT)
        s = sm.get(sym)  # re-read after update

        # ====================================================================
        # RULE 1: Stop loss hit -- sell everything
        # ====================================================================
        if cur <= s["stop_price"]:
            pct_from_entry = (cur - entry) / entry * 100
            reason = (
                f"STOP LOSS HIT  cur=${cur:.2f} <= stop=${s['stop_price']:.2f} "
                f"({pct_from_entry:+.1f}% from entry)"
            )
            log.warning("RULE 1 TRIGGERED: %s -- %s", sym, reason)
            if sym in positions:
                try:
                    order = place_order(sym, total_shares, "sell", reason)
                    sm.record_order(sym, {"type": "stop_loss_sell", "price_ref": cur,
                                          "qty": total_shares, "order_id": order["id"]})
                    print_order_summary(sym, "sell", total_shares, cur, reason, order, s)
                    sm.mark_sold(sym)
                    notifier.notify_stop_loss(
                        symbol=sym, qty=total_shares, price=cur,
                        stop=s["stop_price"], pct_from_entry=pct_from_entry,
                        order_id=order["id"], cfg=cfg,
                    )
                except Exception as e:
                    log.error("Stop loss sell failed for %s: %s", sym, e)
            else:
                log.info("%s stop triggered but no Alpaca position found -- marking sold", sym)
                sm.mark_sold(sym)
            continue  # no further rules for this symbol

        # ====================================================================
        # RULE 3: Ladder in -- price dropped 20%+ from entry
        # ====================================================================
        drop_from_entry = (entry - cur) / entry
        last_ladder     = s.get("last_ladder_price", entry)
        # Only trigger if price is >= 20% below entry AND
        # has dropped at least 5% more since last ladder (avoid same-tick repeat)
        drop_since_last = (last_ladder - cur) / last_ladder if last_ladder > 0 else 0

        if drop_from_entry >= LADDER_IN_DROP_PCT and drop_since_last >= 0.05:
            if cash < MIN_CASH_BALANCE:
                alert_low_balance(cash)
                log.warning("RULE 3: Would ladder into %s but balance too low", sym)
            else:
                reason = (
                    f"LADDER IN  price down {drop_from_entry*100:.1f}% from entry "
                    f"(ladder #{s['ladder_count']+1})"
                )
                log.info("RULE 3 TRIGGERED: %s -- %s", sym, reason)
                try:
                    order = place_order(sym, LADDER_QTY, "buy", reason)
                    sm.ladder_in(sym, cur, LADDER_QTY)
                    s = sm.get(sym)
                    sm.record_order(sym, {"type": "ladder_buy", "price_ref": cur,
                                          "qty": LADDER_QTY, "order_id": order["id"]})
                    print_order_summary(sym, "buy", LADDER_QTY, cur, reason, order, s)
                    cash -= cur * LADDER_QTY
                    notifier.notify_ladder_in(
                        symbol=sym, qty=LADDER_QTY, price=cur,
                        drop_pct=drop_from_entry * 100,
                        ladder_num=s["ladder_count"],
                        new_stop=s["stop_price"],
                        new_entry=s["entry_price"],
                        order_id=order["id"],
                        cfg=cfg,
                    )
                except Exception as e:
                    log.error("Ladder-in failed for %s: %s", sym, e)

        # ====================================================================
        # RULE 2 status log (trailing already updated above)
        # ====================================================================
        s = sm.get(sym)
        if s.get("trailing_active"):
            log.info("%s trailing stop ACTIVE | stop=$%.2f | high=$%.2f",
                     sym, s["stop_price"], s["highest_price"])

    # ── 7. Portfolio summary table ───────────────────────────────────────────
    print("\n" + "=" * 78)
    print("  TRAILING STOP STRATEGY -- PORTFOLIO SNAPSHOT")
    print(f"  {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print("=" * 78)
    print(sm.summary_table(prices))
    print("=" * 78)
    print(f"  Cash: ${cash:,.2f}  |  Buying Power: ${bp:,.2f}  |  Portfolio: ${pv:,.2f}")
    print("=" * 78 + "\n")

    log.info("Bot run complete.")


if __name__ == "__main__":
    run()
