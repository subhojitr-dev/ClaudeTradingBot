"""
state_manager.py
Persists per-symbol strategy state to JSON so the bot survives restarts.

State schema per symbol:
{
  "GOOGL": {
    "status":          "active" | "sold",
    "entry_price":     float,       # avg cost basis
    "total_shares":    int,         # current shares held
    "stop_price":      float,       # current stop-loss level
    "highest_price":   float,       # highest seen since entry
    "trailing_active": bool,        # True once 10% gain triggered
    "ladder_count":    int,         # how many times we've laddered in
    "last_ladder_price": float,     # price at last ladder-in (avoid double-buy)
    "orders": []                    # history of all orders placed
  }
}
"""

import json
import os
import logging
from datetime import datetime, timezone
from typing import Dict, Any

log = logging.getLogger(__name__)


class StateManager:
    def __init__(self, filepath: str):
        self.filepath = filepath
        self._state: Dict[str, Any] = self._load()

    def _load(self) -> Dict:
        if os.path.exists(self.filepath):
            try:
                with open(self.filepath) as f:
                    return json.load(f)
            except Exception as e:
                log.warning("Could not load state file: %s", e)
        return {}

    def _save(self):
        with open(self.filepath, "w") as f:
            json.dump(self._state, f, indent=2, default=str)

    # ── Symbol state ────────────────────────────────────────────────────────

    def get(self, symbol: str) -> Dict:
        return self._state.get(symbol, {})

    def init_symbol(self, symbol: str, entry_price: float, qty: int):
        """Initialise state after the first buy fills."""
        stop = round(entry_price * 0.90, 4)   # 10% initial stop
        self._state[symbol] = {
            "status":            "active",
            "entry_price":       entry_price,
            "total_shares":      qty,
            "stop_price":        stop,
            "highest_price":     entry_price,
            "trailing_active":   False,
            "ladder_count":      0,
            "last_ladder_price": entry_price,
            "orders":            [],
        }
        self._save()
        log.info("Initialised %s | entry=%.4f | stop=%.4f", symbol, entry_price, stop)

    def update_price(self, symbol: str, current_price: float,
                     trail_trigger_pct: float, trail_stop_pct: float):
        """
        Called on every price tick. Updates highest_price, trailing_active,
        and stop_price.  The stop price NEVER goes down.
        """
        s = self._state.get(symbol)
        if not s or s["status"] != "active":
            return

        changed = False

        # Track highest price
        if current_price > s["highest_price"]:
            s["highest_price"] = current_price
            changed = True

        entry = s["entry_price"]

        # Activate trailing once we're up trail_trigger_pct (10%) from entry
        if not s["trailing_active"] and current_price >= entry * (1 + trail_trigger_pct):
            s["trailing_active"] = True
            log.info("%s trailing stop ACTIVATED at price %.4f", symbol, current_price)
            changed = True

        # While trailing is active, raise the stop to trail_stop_pct (5%) below
        # the HIGHEST price seen. The stop only moves UP.
        if s["trailing_active"]:
            new_stop = round(s["highest_price"] * (1 - trail_stop_pct), 4)
            if new_stop > s["stop_price"]:
                old_stop = s["stop_price"]
                s["stop_price"] = new_stop
                log.info("%s stop raised  %.4f -> %.4f  (high=%.4f)",
                         symbol, old_stop, new_stop, s["highest_price"])
                changed = True

        if changed:
            self._save()

    def record_order(self, symbol: str, order_dict: dict):
        s = self._state.setdefault(symbol, {})
        s.setdefault("orders", []).append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **order_dict,
        })
        self._save()

    def ladder_in(self, symbol: str, price: float, qty: int):
        s = self._state[symbol]
        old_shares = s["total_shares"]
        old_entry  = s["entry_price"]
        # Recalculate average entry
        new_total   = old_shares + qty
        new_entry   = (old_shares * old_entry + qty * price) / new_total
        # Raise stop relative to new entry (10% below)
        new_stop    = round(new_entry * 0.90, 4)
        s["total_shares"]      = new_total
        s["entry_price"]       = round(new_entry, 4)
        s["stop_price"]        = max(s["stop_price"], new_stop)  # never lower stop
        s["last_ladder_price"] = price
        s["ladder_count"]     += 1
        self._save()
        log.info("%s ladder-in x%d at %.4f | new_entry=%.4f new_stop=%.4f",
                 symbol, qty, price, new_entry, s["stop_price"])

    def mark_sold(self, symbol: str):
        if symbol in self._state:
            self._state[symbol]["status"] = "sold"
            self._save()

    def all_symbols(self):
        return list(self._state.keys())

    def active_symbols(self):
        return [s for s, v in self._state.items() if v.get("status") == "active"]

    def summary_table(self, prices: Dict[str, float]) -> str:
        lines = []
        header = f"{'Symbol':<6}  {'Shares':>6}  {'Entry':>8}  {'Stop':>8}  {'Current':>8}  {'P&L%':>7}  {'Trailing':>9}  {'Ladders':>7}  {'Status'}"
        lines.append(header)
        lines.append("-" * len(header))
        for sym, v in self._state.items():
            cur = prices.get(sym, 0.0)
            pnl = (cur - v["entry_price"]) / v["entry_price"] * 100 if v["entry_price"] else 0
            trailing = "YES" if v.get("trailing_active") else "no"
            lines.append(
                f"{sym:<6}  {v['total_shares']:>6}  "
                f"${v['entry_price']:>7.2f}  "
                f"${v['stop_price']:>7.2f}  "
                f"${cur:>7.2f}  "
                f"{pnl:>+6.1f}%  "
                f"{trailing:>9}  "
                f"{v.get('ladder_count',0):>7}  "
                f"{v.get('status','?')}"
            )
        return "\n".join(lines)
