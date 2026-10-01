"""
daily_report.py  --  Consolidated end-of-day trade ledger across all 6 strategies
===================================================================================
Run once per day after market close (Task Scheduler, 4:05 PM ET). Builds one row
per trade across Trailing Stop, Pharma Scan, Copy Trade, Flywheel, Strangle, and Iron Condor,
reading each bot's own state JSON (read-only -- never touches a bot's state) plus
live prices from Alpaca.

Behaviour:
  - A trade still open gets its current price / gain $ / gain % / last_updated
    overwritten every run.
  - Once a trade is detected closed, its row is written ONE final time (frozen
    values, closed_at set) and is never touched again on subsequent runs.
  - Closed trades older than RETENTION_DAYS (365) are dropped from the ledger
    entirely on the next run -- open trades are never pruned regardless of age.

Outputs (this folder):
  trade_ledger.json  -- canonical store (source of truth for the next run)
  trade_ledger.csv   -- flattened export, Excel-openable
  dashboard.html     -- local static snapshot for quick viewing

Credentials are hardcoded (not imported from each bot's config.py) to avoid
importing multiple same-named `config`/`alpaca_client` modules from different
folders -- the same reason sell_all.py hardcodes them.
"""

import csv
import json
import logging
import os
import re
import sys
from datetime import datetime, timezone, date, timedelta

import requests

REPORTS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(REPORTS_DIR)  # tradingbot/

LEDGER_JSON = os.path.join(REPORTS_DIR, "trade_ledger.json")
LEDGER_CSV = os.path.join(REPORTS_DIR, "trade_ledger.csv")
LEDGER_HTML = os.path.join(REPORTS_DIR, "dashboard.html")
LOG_DIR = os.path.join(REPORTS_DIR, "logs")

os.makedirs(LOG_DIR, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    handlers=[
        logging.FileHandler(
            os.path.join(LOG_DIR, f"daily_report_{datetime.now().strftime('%Y%m%d')}.log"),
            encoding="utf-8",
        ),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)

# ── Account A -- PA31HKOPMG4M (Trailing Stop + Copy Trade) ─────────────────────
A_KEY = "PKMQDKH257J3XSHRQLOHC63SIW"
A_SECRET = "2UPCu2hsjcqQ6XDQQurzpoDYKvX6qkWMVhD8bMZwrfWd"
A_BASE = "https://paper-api.alpaca.markets/v2"
A_DATA = "https://data.alpaca.markets/v2"
A_HEADERS = {"APCA-API-KEY-ID": A_KEY, "APCA-API-SECRET-KEY": A_SECRET}

# ── Account B -- PA34EFPV3B80 (Flywheel + Strangle + Iron Condor) ──────────────
B_KEY = "PK5QNIDGKGVA2QEAQKYVSAPFV4"
B_SECRET = "HezMftTuve3Lbhj4G5uEqzxuFDTzHjACeH8iH4k2LbuZ"
B_BASE = "https://paper-api.alpaca.markets/v2"
B_DATA = "https://data.alpaca.markets/v2"
B_OPT = "https://data.alpaca.markets/v1beta1"
B_HEADERS = {"APCA-API-KEY-ID": B_KEY, "APCA-API-SECRET-KEY": B_SECRET}

RETENTION_DAYS = 365  # closed trades older than this are dropped from the ledger

TRAILING_STOP_WATCHLIST = {
    "GOOGL", "COHR", "MU", "AVGO", "NBIS", "KTOS", "RKLB", "GLW", "NVDA", "AMD",
    "PANW", "AAPL", "MSFT", "VST", "TEM",
}

OCC_RE = re.compile(r"^([A-Z]+)\d{6}[CP]\d{8}$")


def occ_underlying(occ_symbol: str) -> str:
    m = OCC_RE.match(occ_symbol or "")
    return m.group(1) if m else (occ_symbol or "?")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def today() -> str:
    return date.today().isoformat()


def load_json(path: str, default):
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            log.warning("Could not load %s: %s", path, e)
    return default


# ── Alpaca helpers ──────────────────────────────────────────────────────────────

def get_positions(base: str, headers: dict) -> dict:
    r = requests.get(f"{base}/positions", headers=headers, timeout=10)
    r.raise_for_status()
    return {p["symbol"]: p for p in r.json()}


def get_stock_price(data_url: str, headers: dict, symbol: str) -> float:
    try:
        r = requests.get(f"{data_url}/stocks/{symbol}/quotes/latest", headers=headers, timeout=10)
        if r.ok:
            q = r.json().get("quote", {})
            ask, bid = float(q.get("ap") or 0), float(q.get("bp") or 0)
            if ask > 0 and bid > 0:
                return (ask + bid) / 2
    except Exception:
        pass
    try:
        r = requests.get(f"{data_url}/stocks/{symbol}/trades/latest", headers=headers, timeout=10)
        if r.ok:
            return float(r.json().get("trade", {}).get("p") or 0)
    except Exception:
        pass
    return 0.0


def get_option_mids(options_data_url: str, headers: dict, occ_symbols: list) -> dict:
    occ_symbols = [s for s in occ_symbols if s]
    if not occ_symbols:
        return {}
    try:
        r = requests.get(
            f"{options_data_url}/options/snapshots",
            headers=headers,
            params={"symbols": ",".join(occ_symbols[:100]), "feed": "indicative"},
            timeout=15,
        )
        if r.ok:
            snaps = r.json().get("snapshots", {})
            out = {}
            for sym in occ_symbols:
                snap = snaps.get(sym, {})
                q = snap.get("latestQuote", {})
                ask, bid = float(q.get("ap") or 0), float(q.get("bp") or 0)
                if ask > 0 and bid > 0:
                    out[sym] = round((ask + bid) / 2, 4)
                elif ask > 0:
                    out[sym] = ask
                else:
                    out[sym] = float(snap.get("latestTrade", {}).get("p") or 0)
            return out
    except Exception as e:
        log.warning("get_option_mids failed: %s", e)
    return {s: 0.0 for s in occ_symbols}


def get_option_mid(options_data_url: str, headers: dict, occ_symbol: str) -> float:
    return get_option_mids(options_data_url, headers, [occ_symbol]).get(occ_symbol, 0.0)


# ── Row builder ──────────────────────────────────────────────────────────────────

def make_row(strategy, symbol, trade_type, status, opened_at, qty, entry_price,
             current_price, gain_dollars, gain_pct, closed_at=None, close_reason=None, notes="", legs=None, risk_metrics=None):
    return {
        "strategy": strategy,
        "symbol": symbol,
        "trade_type": trade_type,
        "status": status,
        "opened_at": opened_at,
        "qty": qty,
        "entry_price": round(entry_price, 4) if entry_price is not None else None,
        "current_price": round(current_price, 4) if current_price is not None else None,
        "gain_dollars": round(gain_dollars, 2),
        "gain_pct": round(gain_pct, 2),
        "last_updated": now_iso(),
        "closed_at": closed_at,
        "close_reason": close_reason,
        "notes": notes,
        **({"legs": legs} if legs is not None else {}),
        **({"risk_metrics": risk_metrics} if risk_metrics is not None else {}),
    }


# ── Pharma Scan registry ─────────────────────────────────────────────────────────
# The pharma/FDA catalyst scanner (trailing_stop/pharma_catalyst.py) feeds tickers into
# the Trailing Stop bot's watch list, so those positions live in trailing_stop_state.json
# alongside the 15 hand-picked stocks. To report them as their own "PharmaScan" strategy
# we remember every ticker the scanner ever added -- parsed from the Trailing Stop logs
# and the archived alert emails, and persisted so log/email cleanup never loses it.

PHARMA_REGISTRY = os.path.join(REPORTS_DIR, "pharma_registry.json")
_PHARMA_LOG_RE = re.compile(r"PHARMA CATALYST >> Adding ([A-Z.]+) to watch list")
_PHARMA_MAIL_RE = re.compile(r"TradingBot_TrailingStop_PHARMA_CATALYST_([A-Z.]+)_added")


def load_pharma_symbols() -> set:
    found = set(load_json(PHARMA_REGISTRY, []))
    log_dir = os.path.join(ROOT, "trailing_stop", "logs")
    if os.path.isdir(log_dir):
        for name in os.listdir(log_dir):
            if name.endswith(".log"):
                with open(os.path.join(log_dir, name), encoding="utf-8", errors="ignore") as f:
                    found.update(_PHARMA_LOG_RE.findall(f.read()))
    mail_dir = os.path.join(ROOT, "email_archive")
    if os.path.isdir(mail_dir):
        for week in os.listdir(mail_dir):
            wdir = os.path.join(mail_dir, week)
            if os.path.isdir(wdir):
                for name in os.listdir(wdir):
                    m = _PHARMA_MAIL_RE.search(name)
                    if m:
                        found.add(m.group(1))
    with open(PHARMA_REGISTRY, "w", encoding="utf-8") as f:
        json.dump(sorted(found), f)
    return found


# ── Strategy 1: Trailing Stop ─────────────────────────────────────────────────────

def build_trailing_stop_rows() -> dict:
    rows = {}
    pharma = load_pharma_symbols()
    state = load_json(os.path.join(ROOT, "trailing_stop", "trailing_stop_state.json"), {})
    for symbol, s in state.items():
        entry = s.get("entry_price")
        if entry is None:
            continue
        qty = s.get("total_shares", 0)
        is_pharma = symbol in pharma
        strat = "PharmaScan" if is_pharma else "TrailingStop"
        note = ("Pharma/FDA catalyst scan -> trailing stop" if is_pharma
                else "Trailing stop + ladder-in strategy")
        trade_id = f"{'PH' if is_pharma else 'TS'}-{symbol}"
        if s.get("status") == "active":
            cur = get_stock_price(A_DATA, A_HEADERS, symbol)
            gain_d = (cur - entry) * qty
            gain_p = (cur - entry) / entry * 100 if entry else 0
            stop_price = s.get("stop_price") or round(entry * 0.90, 4)
            ts_risk = {
                "stop_loss_pct": 10.0,
                "stop_loss_price": round(stop_price, 4),
                "stop_loss_dollars": round((stop_price - entry) * qty, 2),
                "trailing_trigger_pct": 10.0,
                "trailing_stop_pct": 5.0,
                "trailing_active": bool(s.get("trailing_active")),
                "highest_price": s.get("highest_price"),
            }
            rows[trade_id] = make_row(
                strat, symbol, "stock", "OPEN", None, qty, entry, cur, gain_d, gain_p,
                notes=note,
                risk_metrics=ts_risk,
            )
        else:
            sell_orders = [o for o in s.get("orders", []) if o.get("type") == "stop_loss_sell"]
            exit_order = min(sell_orders, key=lambda o: o.get("timestamp", "")) if sell_orders else None
            exit_price = exit_order["price_ref"] if exit_order else entry
            closed_at = exit_order["timestamp"][:10] if exit_order else None
            gain_d = (exit_price - entry) * qty
            gain_p = (exit_price - entry) / entry * 100 if entry else 0
            rows[trade_id] = make_row(
                strat, symbol, "stock", "CLOSED", None, qty, entry, exit_price, gain_d, gain_p,
                closed_at=closed_at, close_reason="Stop-loss hit",
                notes=note,
            )
    return rows


# ── Strategy 2: Copy Trade ────────────────────────────────────────────────────────

def build_copytrade_rows(existing_ledger: dict) -> dict:
    rows = {}
    tracker = load_json(os.path.join(ROOT, "copytrade", "trades_tracker.json"), {})
    orders = tracker.get("orders_placed", [])

    by_symbol = {}
    for o in orders:
        sym = o.get("alpaca_symbol")
        if sym:
            by_symbol[sym] = o  # last order per symbol wins

    try:
        positions = get_positions(A_BASE, A_HEADERS)
    except Exception as e:
        log.warning("Copytrade: could not fetch positions: %s", e)
        positions = {}

    for sym, o in by_symbol.items():
        trade_id = f"CT-{sym}"
        pol = o.get("ct_politician", "?")
        if sym in positions:
            p = positions[sym]
            qty = float(p.get("qty", 0))
            entry = float(p.get("avg_entry_price", 0))
            cur = float(p.get("current_price", 0)) or entry
            gain_d = float(p.get("unrealized_pl", 0))
            gain_p = float(p.get("unrealized_plpc", 0)) * 100
            note = f"Copied from {pol}"
            if sym in TRAILING_STOP_WATCHLIST:
                note += " -- shared account: this position may also include Trailing Stop shares in this symbol"
            rows[trade_id] = make_row(
                "CopyTrade", sym, "stock", "OPEN", o.get("ct_tx_date"), qty, entry, cur, gain_d, gain_p,
                notes=note,
            )
        else:
            prev = existing_ledger.get(trade_id)
            if prev and prev.get("status") == "OPEN":
                rows[trade_id] = {
                    **prev,
                    "status": "CLOSED",
                    "closed_at": today(),
                    "close_reason": "Position no longer held (closed outside the bot -- manual sell or sell_all.py)",
                }
            # else: never seen open -- nothing meaningful to show, skip
    return rows


# ── Strategy 3: Flywheel ──────────────────────────────────────────────────────────

def build_flywheel_rows() -> dict:
    rows = {}
    state = load_json(os.path.join(ROOT, "flywheel", "wheel_state.json"), {})
    for symbol, s in state.items():
        if symbol.startswith("_"):
            continue
        history = s.get("history", [])
        pending_contract = None
        pending_stock = None

        for ev in history:
            etype = ev.get("type")
            if etype in ("sell_put", "sell_call"):
                premium_per_share = ev.get("premium_per_share", 0)
                qty = round(ev["total_premium"] / (premium_per_share * 100)) if premium_per_share else 1
                pending_contract = {
                    "contract": ev["contract"],
                    "entry_premium": premium_per_share,
                    "qty": qty,
                    "type": "put" if etype == "sell_put" else "call",
                    "expiry": ev.get("expiry"),
                    "date": ev.get("date"),
                }
            elif etype == "expired_worthless" and pending_contract:
                c = pending_contract
                gain_d = c["entry_premium"] * 100 * c["qty"]
                rows[c["contract"]] = make_row(
                    "Flywheel", symbol, f"option_short_{c['type']}", "CLOSED", c["date"], c["qty"],
                    c["entry_premium"], 0.0, gain_d, 100.0,
                    closed_at=ev.get("date"), close_reason="Expired worthless (kept full premium)",
                    notes=f"{c['contract']}  exp {c['expiry']}",
                )
                pending_contract = None
            elif etype == "closed_early" and pending_contract:
                c = pending_contract
                close_price = ev.get("close_price", 0)
                gain_d = ev.get("profit", (c["entry_premium"] - close_price) * 100 * c["qty"])
                gain_p = (c["entry_premium"] - close_price) / c["entry_premium"] * 100 if c["entry_premium"] else 0
                rows[c["contract"]] = make_row(
                    "Flywheel", symbol, f"option_short_{c['type']}", "CLOSED", c["date"], c["qty"],
                    c["entry_premium"], close_price, gain_d, gain_p,
                    closed_at=ev.get("date"), close_reason=f"Closed early ({ev.get('reason', '70% profit')})",
                    notes=f"{c['contract']}  exp {c['expiry']}",
                )
                pending_contract = None
            elif etype == "assigned":
                if pending_contract and pending_contract["type"] == "put":
                    c = pending_contract
                    prem = ev.get("premium_received", c["entry_premium"] * 100 * c["qty"])
                    rows[c["contract"]] = make_row(
                        "Flywheel", symbol, "option_short_put", "CLOSED", c["date"], c["qty"],
                        c["entry_premium"], 0.0, prem, 100.0,
                        closed_at=ev.get("date"),
                        close_reason=f"Assigned {ev.get('shares')} shares @ ${ev.get('strike')}",
                        notes=f"{c['contract']}",
                    )
                    pending_contract = None
                pending_stock = {
                    "date": ev.get("date"),
                    "effective_cost": ev.get("effective_cost"),
                    "shares": ev.get("shares"),
                }
            elif etype == "called_away" and pending_stock:
                st = pending_stock
                strike = ev.get("strike")
                shares = ev.get("shares_sold", st["shares"])
                cost = st["effective_cost"] or 0
                gain_d = (strike - cost) * shares
                gain_p = (strike - cost) / cost * 100 if cost else 0
                stock_id = f"{symbol}-STOCK-{st['date']}"
                rows[stock_id] = make_row(
                    "Flywheel", symbol, "stock_assigned", "CLOSED", st["date"], shares,
                    cost, strike, gain_d, gain_p,
                    closed_at=ev.get("date"), close_reason=f"Called away @ ${strike}",
                    notes="Shares from put assignment",
                )
                pending_stock = None

        # Currently open contract (top-level state, authoritative over the reconstructed pending_contract)
        contract_sym = s.get("contract_symbol")
        if contract_sym:
            entry_prem = s.get("entry_premium", 0)
            qty = s.get("contracts", 1)
            leg_type = s.get("contract_type", "put")
            mid = get_option_mid(B_OPT, B_HEADERS, contract_sym)
            gain_d = (entry_prem - mid) * 100 * qty
            gain_p = (entry_prem - mid) / entry_prem * 100 if entry_prem else 0
            rows[contract_sym] = make_row(
                "Flywheel", symbol, f"option_short_{leg_type}", "OPEN", s.get("entry_date"), qty,
                entry_prem, mid, gain_d, gain_p,
                notes=f"{contract_sym}  exp {s.get('contract_expiry')}",
            )

        # Currently open stock lot (top-level state, authoritative over pending_stock)
        if s.get("stock_qty", 0) > 0:
            assigned_date = pending_stock["date"] if pending_stock else None
            stock_id = f"{symbol}-STOCK-{assigned_date or 'open'}"
            cost = s.get("stock_avg_cost", 0)
            qty = s.get("stock_qty", 0)
            cur = get_stock_price(B_DATA, B_HEADERS, symbol)
            gain_d = (cur - cost) * qty
            gain_p = (cur - cost) / cost * 100 if cost else 0
            rows[stock_id] = make_row(
                "Flywheel", symbol, "stock_assigned", "OPEN", assigned_date, qty,
                cost, cur, gain_d, gain_p, notes="Shares held from put assignment",
            )
    return rows


# ── Strategy 4: Strangle ──────────────────────────────────────────────────────────

def build_strangle_rows() -> dict:
    rows = {}
    state = load_json(os.path.join(ROOT, "strangle", "strangle_state.json"), {"active": {}, "history": []})

    for symbol, pos in state.get("active", {}).items():
        trade_id = f"STR-{symbol}-{pos.get('entry_date')}"
        need_mids = []
        if pos.get("call_sold_price") is None:
            need_mids.append(pos.get("call_contract"))
        if pos.get("put_sold_price") is None:
            need_mids.append(pos.get("put_contract"))
        mids = get_option_mids(B_OPT, B_HEADERS, need_mids)

        call_val = pos["call_sold_price"] * 100 if pos.get("call_sold_price") is not None else \
            mids.get(pos.get("call_contract"), 0.0) * 100
        put_val = pos["put_sold_price"] * 100 if pos.get("put_sold_price") is not None else \
            mids.get(pos.get("put_contract"), 0.0) * 100

        current_value = call_val + put_val
        total_cost = pos.get("total_cost", 0)
        gain_d = current_value - total_cost
        gain_p = gain_d / total_cost * 100 if total_cost else 0
        str_legs = [
            {"role": "Long Call", "side": "long", "type": "CALL", "strike": pos.get("call_strike"), "premium": pos.get("call_entry_price"), "current": mids.get(pos.get("call_contract"), 0) if pos.get("call_sold_price") is None else pos.get("call_sold_price")},
            {"role": "Long Put",  "side": "long", "type": "PUT",  "strike": pos.get("put_strike"),  "premium": pos.get("put_entry_price"),  "current": mids.get(pos.get("put_contract"),  0) if pos.get("put_sold_price")  is None else pos.get("put_sold_price")},
        ]
        str_risk = {
            "total_cost": round(total_cost / 100, 4),
            "profit_target_pct": 20.0,
            "profit_target_dollars": round(total_cost * 0.20 / 100, 2),
            "stop_loss_pct": 20.0,
            "stop_loss_dollars": round(total_cost * 0.20 / 100, 2),
        }
        rows[trade_id] = make_row(
            "Strangle", symbol, "strangle", "OPEN", pos.get("entry_date"), 1,
            total_cost / 100, current_value / 100, gain_d, gain_p,
            notes=f"phase={pos.get('phase')} status={pos.get('status')} earnings={pos.get('earnings_date')}",
            legs=str_legs,
            risk_metrics=str_risk,
        )

    for pos in state.get("history", []):
        sym = occ_underlying(pos.get("call_contract", ""))
        trade_id = f"STR-{sym}-{pos.get('entry_date')}"
        net_pnl = pos.get("net_pnl", 0) or 0
        cost = pos.get("total_cost", 0) or 0
        gain_p = net_pnl / cost * 100 if cost else 0
        closed_str_legs = [
            {"role": "Long Call", "side": "long", "type": "CALL", "strike": pos.get("call_strike"), "premium": pos.get("call_entry_price"), "current": pos.get("call_sold_price")},
            {"role": "Long Put",  "side": "long", "type": "PUT",  "strike": pos.get("put_strike"),  "premium": pos.get("put_entry_price"),  "current": pos.get("put_sold_price")},
        ]
        rows[trade_id] = make_row(
            "Strangle", sym, "strangle", "CLOSED", pos.get("entry_date"), 1,
            cost / 100, (cost + net_pnl) / 100, net_pnl, gain_p,
            closed_at=pos.get("put_sold_date") or pos.get("call_sold_date"),
            close_reason=pos.get("abandon_reason") or pos.get("close_reason") or "Both legs closed",
            notes=f"earnings={pos.get('earnings_date')}"
                  + (f" stock_entry={pos['entry_stock_price']}" if pos.get("entry_stock_price") else "")
                  + (f" stock_exit={pos['exit_stock_price']}" if pos.get("exit_stock_price") else ""),
            legs=closed_str_legs,
        )
    return rows


# ── Strategy 5: Iron Condor ───────────────────────────────────────────────────────

def build_ironcondor_rows() -> dict:
    rows = {}
    state = load_json(os.path.join(ROOT, "ironcondor", "ironcondor_state.json"), {"active": {}, "history": []})

    for symbol, pos in state.get("active", {}).items():
        trade_id = f"IC-{symbol}-{pos.get('entry_date')}"
        legs = [pos.get("short_put"), pos.get("long_put"), pos.get("short_call"), pos.get("long_call")]
        mids = get_option_mids(B_OPT, B_HEADERS, legs)
        cost_to_close = (
            (mids.get(pos.get("short_put"), 0) - mids.get(pos.get("long_put"), 0))
            + (mids.get(pos.get("short_call"), 0) - mids.get(pos.get("long_call"), 0))
        )
        net_credit = pos.get("net_credit", 0)
        pnl_per_share = net_credit - cost_to_close
        gain_d = pnl_per_share * 100
        gain_p = pnl_per_share / net_credit * 100 if net_credit else 0
        ic_legs = [
            {"role": "Short Put",  "side": "short", "type": "PUT",  "strike": pos.get("short_put_strike"),  "premium": pos.get("short_put_credit"),  "current": mids.get(pos.get("short_put"),  0)},
            {"role": "Long Put",   "side": "long",  "type": "PUT",  "strike": pos.get("long_put_strike"),   "premium": pos.get("long_put_debit"),    "current": mids.get(pos.get("long_put"),   0)},
            {"role": "Short Call", "side": "short", "type": "CALL", "strike": pos.get("short_call_strike"), "premium": pos.get("short_call_credit"), "current": mids.get(pos.get("short_call"), 0)},
            {"role": "Long Call",  "side": "long",  "type": "CALL", "strike": pos.get("long_call_strike"),  "premium": pos.get("long_call_debit"),   "current": mids.get(pos.get("long_call"),  0)},
        ]
        put_spread_width = abs((pos.get("short_put_strike") or 0) - (pos.get("long_put_strike") or 0))
        call_spread_width = abs((pos.get("long_call_strike") or 0) - (pos.get("short_call_strike") or 0))
        wing_width = max(put_spread_width, call_spread_width) or 5
        max_loss_per_share = round(wing_width - net_credit, 4) if net_credit else None
        profit_target_credit = round(net_credit * 0.50, 4)
        stop_loss_credit = round(net_credit * 2.0, 4)
        expiry = pos.get("expiry")
        days_to_expiry = None
        if expiry:
            try:
                days_to_expiry = (date.fromisoformat(expiry) - date.today()).days
            except ValueError:
                pass
        ic_risk = {
            "net_credit": round(net_credit, 4),
            "profit_target_credit": profit_target_credit,
            "profit_target_dollars": round(profit_target_credit * 100, 2),
            "stop_loss_credit": stop_loss_credit,
            "stop_loss_dollars": round(stop_loss_credit * 100, 2),
            "max_loss_per_share": max_loss_per_share,
            "max_loss_dollars": round(max_loss_per_share * 100, 2) if max_loss_per_share is not None else None,
            "wing_width": wing_width,
            "short_put_strike": pos.get("short_put_strike"),
            "short_call_strike": pos.get("short_call_strike"),
            "expiry": expiry,
            "days_to_expiry": days_to_expiry,
        }
        rows[trade_id] = make_row(
            "IronCondor", symbol, "iron_condor", "OPEN", pos.get("entry_date"), 1,
            net_credit, cost_to_close, gain_d, gain_p,
            notes=f"short {pos.get('short_put_strike')}P/{pos.get('short_call_strike')}C exp {pos.get('expiry')}",
            legs=ic_legs,
            risk_metrics=ic_risk,
        )

    for pos in state.get("history", []):
        symbol = pos.get("symbol", "SPY")
        trade_id = f"IC-{symbol}-{pos.get('entry_date')}"
        net_credit = pos.get("net_credit", 0)
        net_pnl = pos.get("net_pnl", 0) or 0
        gain_p = net_pnl / (net_credit * 100) * 100 if net_credit else 0
        closed_ic_legs = [
            {"role": "Short Put",  "side": "short", "type": "PUT",  "strike": pos.get("short_put_strike"),  "premium": pos.get("short_put_credit")},
            {"role": "Long Put",   "side": "long",  "type": "PUT",  "strike": pos.get("long_put_strike"),   "premium": pos.get("long_put_debit")},
            {"role": "Short Call", "side": "short", "type": "CALL", "strike": pos.get("short_call_strike"), "premium": pos.get("short_call_credit")},
            {"role": "Long Call",  "side": "long",  "type": "CALL", "strike": pos.get("long_call_strike"),  "premium": pos.get("long_call_debit")},
        ] if pos.get("short_put_strike") else None
        rows[trade_id] = make_row(
            "IronCondor", symbol, "iron_condor", "CLOSED", pos.get("entry_date"), 1,
            net_credit, pos.get("close_credit", 0), net_pnl, gain_p,
            closed_at=pos.get("close_date"), close_reason=pos.get("close_reason"),
            notes=f"exp {pos.get('expiry')}",
            legs=closed_ic_legs,
        )
    return rows


# ── Merge / persist ────────────────────────────────────────────────────────────────

def merge_rows(existing: dict, new_rows: dict) -> dict:
    merged = dict(existing)
    for trade_id, row in new_rows.items():
        prev = merged.get(trade_id)
        if prev and prev.get("status") == "CLOSED":
            continue  # frozen -- never touch a closed trade again
        merged[trade_id] = row
    return merged


def prune_old_closed(trades: dict) -> dict:
    """Drop closed trades whose closed_at is older than RETENTION_DAYS.
    Open trades and closed trades with no recorded closed_at (can't safely
    judge their age) are always kept."""
    cutoff = date.today() - timedelta(days=RETENTION_DAYS)
    pruned = {}
    dropped = 0
    for trade_id, row in trades.items():
        closed_at = row.get("closed_at") if row.get("status") == "CLOSED" else None
        if closed_at:
            try:
                if date.fromisoformat(closed_at) < cutoff:
                    dropped += 1
                    continue
            except ValueError:
                pass
        pruned[trade_id] = row
    if dropped:
        log.info("Pruned %d closed trade(s) older than %d days", dropped, RETENTION_DAYS)
    return pruned


CSV_FIELDS = [
    "trade_id", "strategy", "symbol", "trade_type", "status", "opened_at", "qty",
    "entry_price", "current_price", "gain_dollars", "gain_pct", "last_updated",
    "closed_at", "close_reason", "notes",
]


def sort_key(item):
    trade_id, row = item
    return (row.get("status") != "OPEN", row.get("strategy", ""), row.get("symbol", ""))


def write_csv(trades: dict):
    with open(LEDGER_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        w.writeheader()
        for trade_id, row in sorted(trades.items(), key=sort_key):
            csv_row = {k: v for k, v in row.items() if k not in ("legs", "risk_metrics")}
            w.writerow({"trade_id": trade_id, **csv_row})


def write_html(trades: dict):
    ordered = sorted(trades.items(), key=sort_key)
    rows_html = []
    for trade_id, r in ordered:
        cls = "pos" if r["gain_dollars"] >= 0 else "neg"
        row_cls = "open" if r["status"] == "OPEN" else "closed"
        rows_html.append(
            f"<tr class='{row_cls}'>"
            f"<td>{r['strategy']}</td><td>{r['symbol']}</td><td>{r['trade_type']}</td>"
            f"<td>{r['status']}</td><td>{r.get('opened_at') or ''}</td><td>{r['qty']}</td>"
            f"<td>{r['entry_price']}</td><td>{r['current_price']}</td>"
            f"<td class='{cls}'>{r['gain_dollars']:+.2f}</td><td class='{cls}'>{r['gain_pct']:+.2f}%</td>"
            f"<td>{r.get('closed_at') or ''}</td><td>{r.get('close_reason') or ''}</td>"
            f"<td class='meta'>{(r.get('last_updated') or '')[:19].replace('T', ' ')}</td>"
            f"<td class='meta'>{r.get('notes') or ''}</td></tr>"
        )
    html = f"""<!DOCTYPE html><html><head><meta charset="utf-8"><title>Trading Bot -- Trade Ledger</title>
<style>
 body{{font-family:Arial,sans-serif;background:#0b0d10;color:#e6e6e6;padding:20px}}
 h1{{font-size:20px;margin-bottom:2px}}
 table{{width:100%;border-collapse:collapse;font-size:13px;margin-top:12px}}
 th{{text-align:left;background:#1c1f24;padding:6px 8px;position:sticky;top:0}}
 td{{padding:6px 8px;border-bottom:1px solid #22252b;white-space:nowrap}}
 tr.closed{{opacity:.6}}
 .pos{{color:#4ade80;font-weight:bold}} .neg{{color:#f87171;font-weight:bold}}
 .meta{{color:#888;font-size:11px;white-space:normal;max-width:260px}}
</style></head><body>
<h1>Trading Bot -- Consolidated Trade Ledger</h1>
<p style="color:#888">Generated {now_iso()}</p>
<table>
<tr><th>Strategy</th><th>Symbol</th><th>Type</th><th>Status</th><th>Opened</th><th>Qty</th>
<th>Entry</th><th>Current</th><th>Gain $</th><th>Gain %</th><th>Closed</th><th>Close Reason</th>
<th>Last Updated</th><th>Notes</th></tr>
{''.join(rows_html)}
</table>
</body></html>"""
    with open(LEDGER_HTML, "w", encoding="utf-8") as f:
        f.write(html)


def main():
    os.makedirs(REPORTS_DIR, exist_ok=True)
    ledger = load_json(LEDGER_JSON, {})
    existing_trades = ledger.get("trades", {})

    # One-time/idempotent migration: frozen Trailing Stop rows that came from the pharma
    # scanner are re-labelled PharmaScan (TS-XXX -> PH-XXX).
    pharma = load_pharma_symbols()
    for tid in [t for t in existing_trades if t.startswith("TS-") and t[3:] in pharma]:
        row = existing_trades.pop(tid)
        row["strategy"] = "PharmaScan"
        row["notes"] = "Pharma/FDA catalyst scan -> trailing stop"
        existing_trades["PH-" + tid[3:]] = row

    all_new = {}
    for name, builder, args in [
        ("TrailingStop", build_trailing_stop_rows, ()),
        ("CopyTrade", build_copytrade_rows, (existing_trades,)),
        ("Flywheel", build_flywheel_rows, ()),
        ("Strangle", build_strangle_rows, ()),
        ("IronCondor", build_ironcondor_rows, ()),
    ]:
        try:
            new_rows = builder(*args)
            log.info("%s: %d row(s) computed", name, len(new_rows))
            all_new.update(new_rows)
        except Exception as e:
            log.error("%s: failed to build rows (%s) -- skipping this strategy this run", name, e, exc_info=True)

    merged = merge_rows(existing_trades, all_new)
    merged = prune_old_closed(merged)

    ledger = {"generated_at": now_iso(), "trades": merged}
    with open(LEDGER_JSON, "w", encoding="utf-8") as f:
        json.dump(ledger, f, indent=2, default=str)

    write_csv(merged)
    write_html(merged)

    open_count = sum(1 for r in merged.values() if r.get("status") == "OPEN")
    closed_count = sum(1 for r in merged.values() if r.get("status") == "CLOSED")
    log.info("Trade ledger updated: %d total (%d open, %d closed)", len(merged), open_count, closed_count)
    log.info("  JSON: %s", LEDGER_JSON)
    log.info("  CSV:  %s", LEDGER_CSV)
    log.info("  HTML: %s", LEDGER_HTML)


if __name__ == "__main__":
    main()
