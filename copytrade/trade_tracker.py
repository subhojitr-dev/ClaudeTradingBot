"""
trade_tracker.py
Persists which Capitol Trades trade IDs have already been acted on,
so we never duplicate an order across bot runs.
"""

import json
import os
import logging
from datetime import datetime, timezone

log = logging.getLogger(__name__)

_DIR = os.path.dirname(os.path.abspath(__file__))


class TradeTracker:
    def __init__(self, filepath: str = "trades_tracker.json"):
        self.filepath = filepath if os.path.isabs(filepath) else os.path.join(_DIR, filepath)
        self._data = self._load()

    # ------------------------------------------------------------------
    def _load(self) -> dict:
        if os.path.exists(self.filepath):
            try:
                with open(self.filepath, "r") as f:
                    return json.load(f)
            except Exception as e:
                log.warning("Could not load tracker file: %s – starting fresh", e)
        return {"seen_trade_ids": [], "orders_placed": []}

    def _save(self):
        with open(self.filepath, "w") as f:
            json.dump(self._data, f, indent=2, default=str)

    # ------------------------------------------------------------------
    def is_seen(self, trade_id: str) -> bool:
        return trade_id in self._data["seen_trade_ids"]

    def mark_seen(self, trade_id: str):
        if trade_id not in self._data["seen_trade_ids"]:
            self._data["seen_trade_ids"].append(trade_id)
            self._save()

    # ------------------------------------------------------------------
    def record_order(self, ct_trade: dict, alpaca_order: dict):
        """Log a successfully placed Alpaca order linked to the CT trade."""
        record = {
            "timestamp":        datetime.now(timezone.utc).isoformat(),
            "ct_trade_id":      ct_trade.get("trade_id"),
            "ct_politician":    ct_trade.get("politician"),
            "ct_ticker":        ct_trade.get("ticker"),
            "ct_asset_type":    ct_trade.get("asset_type"),
            "ct_action":        ct_trade.get("action"),
            "ct_tx_date":       ct_trade.get("tx_date"),
            "alpaca_order_id":  alpaca_order.get("id"),
            "alpaca_symbol":    alpaca_order.get("symbol"),
            "alpaca_qty":       alpaca_order.get("qty"),
            "alpaca_side":      alpaca_order.get("side"),
            "alpaca_status":    alpaca_order.get("status"),
        }
        self._data["orders_placed"].append(record)
        self._save()
        log.info("Recorded order: %s", record)

    # ------------------------------------------------------------------
    def summary(self) -> str:
        n_seen   = len(self._data["seen_trade_ids"])
        n_orders = len(self._data["orders_placed"])
        return f"TradeTracker: {n_seen} CT trades seen, {n_orders} Alpaca orders placed"
