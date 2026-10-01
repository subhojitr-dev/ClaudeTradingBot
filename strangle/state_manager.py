"""
state_manager.py  --  Persist strangle positions across bot runs

State machine per symbol:

  SCANNING      → criteria not yet met, keep checking each run
  OPEN          → both legs bought, monitoring pre-earnings
  CALL_SOLD     → call taken off pre-earnings, holding put through event
  CLOSED        → both legs exited; record moved to history

State file format (strangle_state.json):
{
  "active": {
    "NVDA": {
      "status":            "OPEN" | "CALL_SOLD" | "CLOSED",
      "phase":             "PRE_EARNINGS" | "POST_EARNINGS",
      "earnings_date":     "2025-07-23",
      "entry_date":        "2025-07-01",
      "expiry":            "2025-10-03",

      "call_contract":     "NVDA251003C00160000",
      "call_strike":       160.0,
      "call_delta":        0.29,
      "call_entry_price":  5.50,
      "call_sold_price":   null | 6.33,
      "call_sold_date":    null | "2025-07-10",

      "put_contract":      "NVDA251003P00120000",
      "put_strike":        120.0,
      "put_delta":         0.31,
      "put_entry_price":   4.20,
      "put_sold_price":    null | 4.65,
      "put_sold_date":     null | "2025-07-25",

      "total_cost":        970.0,       # (call_ask + put_ask) × 100
      "total_proceeds":    0.0,         # filled in as legs are sold
      "net_pnl":           0.0          # proceeds - cost (filled on close)
    }
  },
  "history": [...]        ← closed trades archived here
}
"""

import json
import logging
import os
from datetime import date

log = logging.getLogger(__name__)

_DIR = os.path.dirname(os.path.abspath(__file__))


def _abs(path: str) -> str:
    return path if os.path.isabs(path) else os.path.join(_DIR, path)


def load(state_file: str) -> dict:
    state_file = _abs(state_file)
    if os.path.exists(state_file):
        try:
            with open(state_file) as f:
                data = json.load(f)
                data.setdefault("active", {})
                data.setdefault("history", [])
                return data
        except Exception as e:
            log.error("Failed to load state file: %s", e)
    return {"active": {}, "history": []}


def save(state_file: str, state: dict) -> None:
    with open(_abs(state_file), "w") as f:
        json.dump(state, f, indent=2, default=str)


def open_strangle(state: dict, symbol: str, legs: dict, earnings_date: str,
                  stock_price: float | None = None) -> None:
    """Record a newly opened strangle position."""
    total_cost = (legs["call_ask"] + legs["put_ask"]) * 100
    state["active"][symbol] = {
        "status":           "OPEN",
        "phase":            "PRE_EARNINGS",
        "earnings_date":    earnings_date,
        "entry_date":       date.today().isoformat(),
        "expiry":           legs["expiry"],
        "entry_stock_price": round(stock_price, 2) if stock_price else None,

        "call_contract":    legs["call_contract"],
        "call_strike":      legs["call_strike"],
        "call_delta":       legs["call_delta"],
        "call_entry_price": legs["call_ask"],
        "call_sold_price":  None,
        "call_sold_date":   None,

        "put_contract":     legs["put_contract"],
        "put_strike":       legs["put_strike"],
        "put_delta":        legs["put_delta"],
        "put_entry_price":  legs["put_ask"],
        "put_sold_price":   None,
        "put_sold_date":    None,

        "total_cost":       round(total_cost, 2),
        "total_proceeds":   0.0,
        "net_pnl":          0.0,
    }
    log.info("State: opened strangle on %s (cost $%.2f)", symbol, total_cost)


def record_call_sold(state: dict, symbol: str, sell_price: float) -> None:
    pos = state["active"].get(symbol)
    if not pos:
        return
    pos["call_sold_price"] = round(sell_price, 4)
    pos["call_sold_date"]  = date.today().isoformat()
    pos["status"]          = "CALL_SOLD"
    proceeds               = sell_price * 100
    pos["total_proceeds"]  = round(pos["total_proceeds"] + proceeds, 2)
    log.info("State: call sold on %s @ $%.2f (proceeds $%.2f)", symbol, sell_price, proceeds)


def record_put_sold(state: dict, symbol: str, sell_price: float) -> None:
    pos = state["active"].get(symbol)
    if not pos:
        return
    pos["put_sold_price"]  = round(sell_price, 4)
    pos["put_sold_date"]   = date.today().isoformat()
    proceeds               = sell_price * 100
    pos["total_proceeds"]  = round(pos["total_proceeds"] + proceeds, 2)
    pos["net_pnl"]         = round(pos["total_proceeds"] - pos["total_cost"], 2)
    pos["status"]          = "CLOSED"
    log.info("State: put sold on %s @ $%.2f  Net P&L = $%.2f", symbol, sell_price, pos["net_pnl"])
    _archive(state, symbol)


def switch_to_post_earnings(state: dict, symbol: str) -> None:
    pos = state["active"].get(symbol)
    if pos:
        pos["phase"] = "POST_EARNINGS"
        log.info("State: %s switched to POST_EARNINGS phase", symbol)


def _archive(state: dict, symbol: str) -> None:
    """Move a closed position from active to history."""
    pos = state["active"].pop(symbol, None)
    if pos:
        state["history"].append(pos)
        log.info("State: %s archived to history", symbol)


def abandon(state: dict, symbol: str, reason: str) -> None:
    """Remove a position without recording proceeds (e.g. expiry with no exit)."""
    pos = state["active"].pop(symbol, None)
    if pos:
        pos["status"]  = "ABANDONED"
        pos["abandon_reason"] = reason
        state["history"].append(pos)
        log.info("State: %s abandoned (%s)", symbol, reason)
