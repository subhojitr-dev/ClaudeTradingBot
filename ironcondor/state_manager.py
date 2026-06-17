"""
state_manager.py  --  Iron Condor position state machine

States:
  OPEN        Both spreads are open, monitoring for profit target / adjustment trigger
  ADJUSTING   One side has been rolled (adjustment in progress)
  CLOSED      Position fully exited (profit target, stop-loss, expiry, or manual)

State file (ironcondor_state.json):
{
  "active": {
    "SPY": {
      "status":             "OPEN" | "ADJUSTING" | "CLOSED",
      "entry_date":         "2026-06-13",
      "expiry":             "2026-06-27",
      "spy_price_at_entry": 540.12,

      "short_put":          "SPY260627P00515000",
      "short_put_strike":   515.0,
      "short_put_credit":   1.45,

      "long_put":           "SPY260627P00510000",
      "long_put_strike":    510.0,
      "long_put_debit":     0.55,

      "short_call":         "SPY260627C00565000",
      "short_call_strike":  565.0,
      "short_call_credit":  1.30,

      "long_call":          "SPY260627C00570000",
      "long_call_strike":   570.0,
      "long_call_debit":    0.50,

      "net_credit":         1.70,   # per share — max profit per condor = 170
      "max_risk":           3.30,   # per share — max loss = 330

      "put_adjusted":       false,  # true once put side has been rolled
      "call_adjusted":      false,
      "adjustment_log":     [],     # record of any rolls made

      "close_credit":       null,   # filled in when position is closed
      "net_pnl":            null
    }
  },
  "history": []
}
"""

import json
import logging
import os
from datetime import date

log = logging.getLogger(__name__)


def load(state_file: str) -> dict:
    if os.path.exists(state_file):
        try:
            with open(state_file) as f:
                data = json.load(f)
                data.setdefault("active", {})
                data.setdefault("history", [])
                return data
        except Exception as e:
            log.error("State load failed: %s", e)
    return {"active": {}, "history": []}


def save(state_file: str, state: dict) -> None:
    with open(state_file, "w") as f:
        json.dump(state, f, indent=2, default=str)


def open_condor(state: dict, symbol: str, legs: dict) -> None:
    state["active"][symbol] = {
        "status":             "OPEN",
        "entry_date":         date.today().isoformat(),
        "expiry":             legs["expiry"],
        "spy_price_at_entry": legs.get("spy_price", 0),

        "short_put":          legs["short_put"],
        "short_put_strike":   legs["short_put_strike"],
        "short_put_credit":   legs["short_put_credit"],

        "long_put":           legs["long_put"],
        "long_put_strike":    legs["long_put_strike"],
        "long_put_debit":     legs["long_put_debit"],

        "short_call":         legs["short_call"],
        "short_call_strike":  legs["short_call_strike"],
        "short_call_credit":  legs["short_call_credit"],

        "long_call":          legs["long_call"],
        "long_call_strike":   legs["long_call_strike"],
        "long_call_debit":    legs["long_call_debit"],

        "net_credit":         legs["net_credit"],
        "max_risk":           legs["max_risk"],
        "credit_ratio":       legs["credit_ratio"],
        "put_spread_width":   legs.get("put_spread_width", 5),
        "call_spread_width":  legs.get("call_spread_width", 5),

        "put_adjusted":       False,
        "call_adjusted":      False,
        "adjustment_log":     [],

        "close_credit":       None,
        "net_pnl":            None,
    }
    log.info("State: condor opened on %s  credit=$%.2f  expiry=%s",
             symbol, legs["net_credit"], legs["expiry"])


def record_adjustment(
    state: dict,
    symbol: str,
    side: str,   # "put" or "call"
    old_short: str,
    new_short: str,
    new_long: str,
    new_short_strike: float,
    new_long_strike: float,
    roll_credit: float,
) -> None:
    pos = state["active"].get(symbol)
    if not pos:
        return
    entry = {
        "date":              date.today().isoformat(),
        "side":              side,
        "old_short":         old_short,
        "new_short":         new_short,
        "new_long":          new_long,
        "new_short_strike":  new_short_strike,
        "new_long_strike":   new_long_strike,
        "roll_credit":       roll_credit,
    }
    pos["adjustment_log"].append(entry)
    if side == "put":
        pos["short_put"]        = new_short
        pos["short_put_strike"] = new_short_strike
        pos["long_put"]         = new_long
        pos["long_put_strike"]  = new_long_strike
        pos["put_adjusted"]     = True
    else:
        pos["short_call"]        = new_short
        pos["short_call_strike"] = new_short_strike
        pos["long_call"]         = new_long
        pos["long_call_strike"]  = new_long_strike
        pos["call_adjusted"]     = True
    # Net credit grows by roll credit (or shrinks if we paid a debit to roll)
    pos["net_credit"] = round(pos["net_credit"] + roll_credit, 4)
    log.info("State: %s side adjusted on %s  new_short=%.2f  roll_credit=$%.2f",
             side, symbol, new_short_strike, roll_credit)


def close_condor(
    state: dict,
    symbol: str,
    cost_to_close: float,
    reason: str,
) -> None:
    pos = state["active"].get(symbol)
    if not pos:
        return
    net_pnl = round((pos["net_credit"] - cost_to_close) * 100, 2)
    pos["close_credit"] = cost_to_close
    pos["net_pnl"]      = net_pnl
    pos["status"]       = "CLOSED"
    pos["close_reason"] = reason
    pos["close_date"]   = date.today().isoformat()
    log.info("State: condor closed on %s  cost_to_close=$%.2f  net_pnl=$%.2f  reason=%s",
             symbol, cost_to_close, net_pnl, reason)
    state["history"].append(state["active"].pop(symbol))
