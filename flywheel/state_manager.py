"""
state_manager.py  --  Wheel Strategy State Persistence
=======================================================
Tracks per-symbol wheel state across runs.

Stage Machine:
  IDLE  -> sell CSP  -> CSP
  CSP   -> expires worthless  -> IDLE  (collect full premium)
  CSP   -> 70% profit         -> IDLE  (close early, reopen)
  CSP   -> roll up            -> CSP   (same expiry, higher strike)
  CSP   -> assigned           -> CC    (now hold stock)
  CC    -> sell covered call  -> CC    (still in CC stage)
  CC    -> expires worthless  -> CC    (keep stock, sell new call)
  CC    -> 70% profit         -> CC    (close early, sell new call)
  CC    -> called away        -> IDLE  (stock sold, restart wheel)
"""

import json
import logging
import os
from datetime import datetime, timezone

log = logging.getLogger(__name__)

_DIR = os.path.dirname(os.path.abspath(__file__))


class WheelState:

    def __init__(self, filepath: str):
        self.filepath = filepath if os.path.isabs(filepath) else os.path.join(_DIR, filepath)
        self._data    = self._load()

    # ── Persistence ────────────────────────────────────────────────────────────

    def _load(self) -> dict:
        if os.path.exists(self.filepath):
            try:
                with open(self.filepath, encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                log.error("State load failed: %s", e)
        return {
            "_summary": {
                "total_premium_all":  0.0,
                "last_report_date":   None,
            }
        }

    def save(self):
        try:
            with open(self.filepath, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2, default=str)
        except Exception as e:
            log.error("State save failed: %s", e)

    # ── Symbol accessors ───────────────────────────────────────────────────────

    def get(self, symbol: str) -> dict:
        return self._data.get(symbol, {})

    def symbols(self) -> list:
        return [k for k in self._data if not k.startswith("_")]

    def total_premium(self) -> float:
        return self._data.get("_summary", {}).get("total_premium_all", 0.0)

    # ── Initialise ─────────────────────────────────────────────────────────────

    def init_symbol(self, symbol: str):
        """Create a blank IDLE entry for a symbol if it doesn't exist."""
        if symbol not in self._data:
            self._data[symbol] = {
                "stage":                   "IDLE",
                "contract_symbol":         None,
                "contract_expiry":         None,
                "contract_strike":         None,
                "contract_type":           None,
                "entry_premium":           0.0,
                "entry_date":              None,
                "contracts":               1,
                "stock_qty":               0,
                "stock_avg_cost":          0.0,
                "total_premium_collected": 0.0,
                "cycle_count":             0,
                "history":                 [],
            }
            self.save()

    # ── Stage 1: CSP ───────────────────────────────────────────────────────────

    def open_csp(self, symbol: str, contract: dict, premium: float, qty: int, order_id: str):
        """Record opening a cash-secured put."""
        s = self._data[symbol]
        s.update({
            "stage":           "CSP",
            "contract_symbol": contract["symbol"],
            "contract_expiry": contract.get("expiration_date"),
            "contract_strike": float(contract.get("strike_price", 0)),
            "contract_type":   "put",
            "entry_premium":   round(premium, 4),
            "entry_date":      _today(),
            "contracts":       qty,
        })
        s["history"].append({
            "type":             "sell_put",
            "contract":         contract["symbol"],
            "strike":           float(contract.get("strike_price", 0)),
            "expiry":           contract.get("expiration_date"),
            "premium_per_share": round(premium, 4),
            "total_premium":    round(premium * 100 * qty, 2),
            "date":             _today(),
            "order_id":         order_id,
        })
        self.save()
        log.info("State: %s -> CSP @ $%.2f  contract=%s", symbol, premium, contract["symbol"])

    def csp_expired_worthless(self, symbol: str):
        """Put expired worthless -- collect full premium, return to IDLE."""
        s = self._data[symbol]
        premium_total = round(s["entry_premium"] * 100 * s["contracts"], 2)
        self._add_premium(symbol, premium_total)
        s["history"].append({
            "type":          "expired_worthless",
            "contract":      s["contract_symbol"],
            "premium_total": premium_total,
            "date":          _today(),
        })
        self._reset_contract(symbol, new_stage="IDLE")
        log.info("State: %s CSP expired worthless, +$%.2f premium", symbol, premium_total)

    def csp_closed_early(self, symbol: str, close_price: float, reason: str):
        """Put closed early (70% profit or roll-up buy side)."""
        s = self._data[symbol]
        profit = round((s["entry_premium"] - close_price) * 100 * s["contracts"], 2)
        self._add_premium(symbol, profit)
        s["history"].append({
            "type":         "closed_early",
            "contract":     s["contract_symbol"],
            "entry_premium": s["entry_premium"],
            "close_price":  close_price,
            "profit":       profit,
            "reason":       reason,
            "date":         _today(),
        })
        self._reset_contract(symbol, new_stage="IDLE")
        log.info("State: %s CSP closed early (%s), profit=$%.2f", symbol, reason, profit)

    def csp_assigned(self, symbol: str, shares: int):
        """Put assigned -- we now hold stock at the strike price."""
        s = self._data[symbol]
        strike      = s["contract_strike"]
        premium     = s["entry_premium"]
        premium_ttl = round(premium * 100 * s["contracts"], 2)
        self._add_premium(symbol, premium_ttl)
        # Effective cost = strike - premium received (lower break-even)
        effective_cost = round(strike - premium, 2)
        s.update({
            "stage":          "CC",
            "stock_qty":      shares,
            "stock_avg_cost": effective_cost,
        })
        s["history"].append({
            "type":             "assigned",
            "strike":           strike,
            "shares":           shares,
            "premium_received": premium_ttl,
            "effective_cost":   effective_cost,
            "date":             _today(),
        })
        self._reset_contract(symbol, new_stage="CC")
        log.info("State: %s ASSIGNED %d shares @ $%.2f (eff. $%.2f after premium)",
                 symbol, shares, strike, effective_cost)

    # ── Stage 2: Covered Call ──────────────────────────────────────────────────

    def open_cc(self, symbol: str, contract: dict, premium: float, qty: int, order_id: str):
        """Record opening a covered call."""
        s = self._data[symbol]
        s.update({
            "stage":           "CC",
            "contract_symbol": contract["symbol"],
            "contract_expiry": contract.get("expiration_date"),
            "contract_strike": float(contract.get("strike_price", 0)),
            "contract_type":   "call",
            "entry_premium":   round(premium, 4),
            "entry_date":      _today(),
            "contracts":       qty,
        })
        s["history"].append({
            "type":             "sell_call",
            "contract":         contract["symbol"],
            "strike":           float(contract.get("strike_price", 0)),
            "expiry":           contract.get("expiration_date"),
            "premium_per_share": round(premium, 4),
            "total_premium":    round(premium * 100 * qty, 2),
            "date":             _today(),
            "order_id":         order_id,
        })
        self.save()
        log.info("State: %s -> CC @ $%.2f  contract=%s", symbol, premium, contract["symbol"])

    def cc_expired_worthless(self, symbol: str):
        """Call expired worthless -- keep stock, collect premium, sell new call next run."""
        s = self._data[symbol]
        premium_total = round(s["entry_premium"] * 100 * s["contracts"], 2)
        self._add_premium(symbol, premium_total)
        s["history"].append({
            "type":          "expired_worthless",
            "contract":      s["contract_symbol"],
            "premium_total": premium_total,
            "date":          _today(),
        })
        # Stay in CC stage, keep stock, clear contract (sell new one next run)
        self._reset_contract(symbol, new_stage="CC")
        log.info("State: %s CC expired worthless, +$%.2f premium (still hold stock)",
                 symbol, premium_total)

    def cc_closed_early(self, symbol: str, close_price: float):
        """Call closed early (70% profit) -- keep stock, sell new call next run."""
        s = self._data[symbol]
        profit = round((s["entry_premium"] - close_price) * 100 * s["contracts"], 2)
        self._add_premium(symbol, profit)
        s["history"].append({
            "type":        "closed_early",
            "contract":    s["contract_symbol"],
            "entry_premium": s["entry_premium"],
            "close_price": close_price,
            "profit":      profit,
            "reason":      "70pct_profit",
            "date":        _today(),
        })
        self._reset_contract(symbol, new_stage="CC")
        log.info("State: %s CC closed early (70%% profit), +$%.2f (still hold stock)",
                 symbol, profit)

    def cc_called_away(self, symbol: str):
        """Shares called away -- back to Stage 1 (IDLE)."""
        s   = self._data[symbol]
        prem = round(s["entry_premium"] * 100 * s["contracts"], 2)
        self._add_premium(symbol, prem)
        # Stock P&L tracked separately in report
        s["history"].append({
            "type":              "called_away",
            "contract":          s["contract_symbol"],
            "strike":            s["contract_strike"],
            "shares_sold":       s["stock_qty"],
            "premium_collected": prem,
            "date":              _today(),
        })
        s["stock_qty"]      = 0
        s["stock_avg_cost"] = 0.0
        self._reset_contract(symbol, new_stage="IDLE")
        s["cycle_count"] = s.get("cycle_count", 0) + 1
        self.save()
        log.info("State: %s shares CALLED AWAY, back to IDLE", symbol)

    # ── Helpers ────────────────────────────────────────────────────────────────

    def _add_premium(self, symbol: str, amount: float):
        s = self._data[symbol]
        s["total_premium_collected"] = round(
            s.get("total_premium_collected", 0) + amount, 2
        )
        summ = self._data.setdefault("_summary", {})
        summ["total_premium_all"] = round(
            summ.get("total_premium_all", 0) + amount, 2
        )

    def _reset_contract(self, symbol: str, new_stage: str):
        s = self._data[symbol]
        s["stage"]            = new_stage
        s["contract_symbol"]  = None
        s["contract_expiry"]  = None
        s["contract_strike"]  = None
        s["contract_type"]    = None
        s["entry_premium"]    = 0.0
        s["entry_date"]       = None
        self.save()


def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()
