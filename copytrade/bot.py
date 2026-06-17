"""
bot.py  --  Copy-Trading Bot  (Multi-Politician -> Alpaca Paper Trading)
========================================================================
Run manually:    python bot.py
Scheduled:       every 30 minutes via Windows Task Scheduler

Logic
-----
1. Check if the US market is open (still queue orders when closed).
2. For each monitored politician (Pelosi, McCaul, Ro Khanna):
   a. Fetch latest N trades from Capitol Trades.
   b. For each trade not yet seen:
      - If it's a stock  -> place market order for STOCK_QTY shares.
      - If it's an option-> place market order for 1 contract.
      - Mark trade as seen so we never duplicate.
3. Enforce MAX_COPY_POSITIONS cap: never hold more than 10 copy positions.
4. Send email notification for every new trade placed.
5. On FIRST EVER run: mark all historical trades as seen without ordering.
"""

import logging
import os
import sys
from datetime import datetime, timezone

# ── Path setup: allow importing shared notifier from parent folder ─────────────
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import (
    POLITICIANS,
    MAX_COPY_POSITIONS,
    STOCK_QTY,
    OPTION_CONTRACTS,
    TRACKER_FILE,
    LOG_DIR,
)
from alpaca_client import (
    get_account,
    get_positions,
    get_open_orders,
    place_stock_order,
    place_option_order,
    is_market_open,
)
from capitol_trades_scraper import fetch_politician_trades
from trade_tracker import TradeTracker
from option_resolver import resolve_option_symbol
import notifier
import config as cfg


# ── Logging setup ──────────────────────────────────────────────────────────────
os.makedirs(LOG_DIR, exist_ok=True)
log_filename = os.path.join(
    LOG_DIR,
    f"bot_{datetime.now().strftime('%Y%m%d')}.log",
)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    handlers=[
        logging.FileHandler(log_filename, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)


# ── Helpers ────────────────────────────────────────────────────────────────────

def count_copy_positions(positions: list, tracker: TradeTracker) -> int:
    """
    Count how many copy-trade positions we currently hold.
    A position is a 'copy position' if its symbol appears in our orders_placed history.
    """
    copied_symbols = {
        o["symbol"].upper()
        for o in tracker._data.get("orders_placed", [])
        if o.get("symbol")
    }
    held_symbols = {p["symbol"].upper() for p in positions}
    return len(copied_symbols & held_symbols)


# ── Main ───────────────────────────────────────────────────────────────────────
def run():
    log.info("=" * 60)
    log.info("Copy-Trading Bot starting -- %d politicians monitored",
             len(POLITICIANS))
    log.info("Run time (UTC): %s", datetime.now(timezone.utc).isoformat())
    log.info("=" * 60)

    # 1. Account check
    try:
        acct = get_account()
        log.info(
            "Account: %s  |  Buying power: $%s  |  Portfolio: $%s",
            acct.get("account_number"),
            acct.get("buying_power"),
            acct.get("portfolio_value"),
        )
    except Exception as e:
        log.error("Cannot reach Alpaca API: %s", e)
        sys.exit(1)

    # 2. Market open check
    market_open = is_market_open()
    log.info("Market is %s", "OPEN" if market_open else "CLOSED / PRE-MARKET")

    # 3. Load tracker, positions, open orders
    tracker = TradeTracker(TRACKER_FILE)
    log.info(tracker.summary())

    positions    = get_positions()
    open_orders  = get_open_orders()
    open_buy_syms = {
        o["symbol"].upper() for o in open_orders if o.get("side") == "buy"
    }
    held_symbols = {p["symbol"].upper() for p in positions}

    # Current copy-position count (before this run places any orders)
    copy_pos_count = count_copy_positions(positions, tracker)
    log.info("Current copy positions held: %d / %d max",
             copy_pos_count, MAX_COPY_POSITIONS)

    # 4. First-run detection across ALL politicians
    is_first_run = len(tracker._data.get("seen_trade_ids", [])) == 0

    # 5. Fetch and process trades for each politician
    total_new_trades = 0
    # Track tickers already ordered THIS run to avoid cross-politician duplication
    ordered_this_run: set = set()

    for pol in POLITICIANS:
        pol_name = pol["name"]
        pol_id   = pol["ct_id"]

        log.info("-" * 60)
        log.info("Fetching trades for: %s  (ID: %s)", pol_name, pol_id)

        try:
            trades = fetch_politician_trades(
                politician_id=pol_id,
                politician_name=pol_name,
                page_size=20,
            )
        except Exception as e:
            log.error("Failed to fetch Capitol Trades for %s: %s", pol_name, e)
            continue   # Try next politician

        log.info("Fetched %d trades from Capitol Trades for %s",
                 len(trades), pol_name)

        if not trades:
            log.warning("No trades returned for %s -- scraper may need updating.", pol_name)
            continue

        # First-run: mark all historical trades as seen (no orders)
        if is_first_run:
            log.info("FIRST RUN -- marking all %d %s historical trades as seen (no orders).",
                     len(trades), pol_name)
            for trade in trades:
                tracker.mark_seen(trade["trade_id"])
            continue   # Process next politician; orders start from next run

        # Process new trades
        for trade in trades:
            trade_id   = trade["trade_id"]
            ticker     = trade["ticker"]
            asset_type = trade["asset_type"]
            action     = trade["action"]
            tx_date    = trade["tx_date"]

            # Already seen
            if tracker.is_seen(trade_id):
                continue

            # Skip sells on stocks we don't hold (no shorts)
            if action == "sell" and ticker not in held_symbols:
                log.info("Skipping SELL %s (%s) -- not held", ticker, pol_name)
                tracker.mark_seen(trade_id)
                continue

            # Skip missing ticker or non-stock/option
            if not ticker:
                log.info("Trade %s has no ticker -- skipping", trade_id)
                tracker.mark_seen(trade_id)
                continue
            if asset_type not in ("stock", "option"):
                log.info("Trade %s is type '%s' -- skipping", trade_id, asset_type)
                tracker.mark_seen(trade_id)
                continue

            # Enforce position cap (only for buys)
            if action == "buy":
                # Re-count live after any orders placed this run
                live_count = copy_pos_count + len(
                    ordered_this_run - held_symbols  # new symbols not previously held
                )
                if live_count >= MAX_COPY_POSITIONS:
                    log.warning(
                        "POSITION CAP REACHED (%d/%d) -- skipping BUY %s (%s)",
                        live_count, MAX_COPY_POSITIONS, ticker, pol_name,
                    )
                    tracker.mark_seen(trade_id)
                    continue

            # Skip if this ticker was already ordered this run (another politician)
            if action == "buy" and ticker in ordered_this_run:
                log.info("Already ordered %s this run -- skipping duplicate from %s",
                         ticker, pol_name)
                tracker.mark_seen(trade_id)
                continue

            total_new_trades += 1
            log.info(
                "NEW TRADE >> %s %s %s  (tx: %s  by %s)",
                action.upper(), ticker, asset_type, tx_date, pol_name,
            )

            # Place the order
            try:
                order = None

                if asset_type == "stock":
                    # Wash-trade guard
                    if action == "sell" and ticker in open_buy_syms and ticker not in held_symbols:
                        log.warning(
                            "Skipping SELL %s -- open BUY order exists, no position (wash trade guard)",
                            ticker,
                        )
                        tracker.mark_seen(trade_id)
                        continue

                    order = place_stock_order(symbol=ticker, qty=STOCK_QTY, side=action)
                    tracker.record_order(trade, order)
                    tracker.mark_seen(trade_id)

                elif asset_type == "option":
                    occ_symbol = resolve_option_symbol(trade)
                    if occ_symbol:
                        order = place_option_order(option_symbol=occ_symbol, side=action)
                    else:
                        log.warning(
                            "Could not resolve OCC symbol for %s -- placing stock order instead",
                            trade_id,
                        )
                        order = place_stock_order(symbol=ticker, qty=STOCK_QTY, side=action)
                    tracker.record_order(trade, order)
                    tracker.mark_seen(trade_id)

                # Email notification
                if order:
                    ordered_this_run.add(ticker)
                    notifier.notify_copy_trade(
                        politician=pol_name,
                        action=action,
                        symbol=ticker,
                        qty=STOCK_QTY if asset_type == "stock" else OPTION_CONTRACTS,
                        price_ref=0.0,   # market order; actual fill price unknown until filled
                        order_id=order.get("id", "N/A"),
                        cfg=cfg,
                    )

            except Exception as e:
                log.error("Order failed for trade %s (%s %s by %s): %s",
                          trade_id, action, ticker, pol_name, e)
                # Do NOT mark as seen -- retry next run
                continue

    if is_first_run:
        log.info("=" * 60)
        log.info("FIRST RUN complete. All historical trades marked as seen.")
        log.info("From the NEXT run, only genuinely new trades will be copied.")
        log.info("=" * 60)
    elif total_new_trades == 0:
        log.info("No new trades found across all %d politicians this run.", len(POLITICIANS))
    else:
        log.info("Processed %d new trade(s) this run.", total_new_trades)

    log.info(tracker.summary())
    log.info("Bot run complete.")


if __name__ == "__main__":
    run()
