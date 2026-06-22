"""
alpaca_client.py  --  Alpaca REST API wrapper for the Iron Condor bot
Account: PA34EFPV3B80 (Options Paper Account)
"""

import logging
import requests
from datetime import date, timedelta
from config import (
    ALPACA_API_KEY, ALPACA_SECRET_KEY,
    ALPACA_BASE_URL, ALPACA_DATA_URL,
)

_OPTIONS_DATA_URL = "https://data.alpaca.markets/v1beta1"

log = logging.getLogger(__name__)

HEADERS = {
    "APCA-API-KEY-ID":     ALPACA_API_KEY,
    "APCA-API-SECRET-KEY": ALPACA_SECRET_KEY,
    "Content-Type":        "application/json",
}
DATA_HEADERS = {
    "APCA-API-KEY-ID":     ALPACA_API_KEY,
    "APCA-API-SECRET-KEY": ALPACA_SECRET_KEY,
}


# ── Market & Account ──────────────────────────────────────────────────────────

def get_clock() -> dict:
    r = requests.get(f"{ALPACA_BASE_URL}/clock", headers=HEADERS, timeout=10)
    r.raise_for_status()
    return r.json()


def get_account() -> dict:
    r = requests.get(f"{ALPACA_BASE_URL}/account", headers=HEADERS, timeout=10)
    r.raise_for_status()
    return r.json()


def get_positions() -> dict:
    """Return all open positions keyed by OCC symbol."""
    r = requests.get(f"{ALPACA_BASE_URL}/positions", headers=HEADERS, timeout=10)
    r.raise_for_status()
    return {p["symbol"]: p for p in r.json()}


# ── SPY Price ─────────────────────────────────────────────────────────────────

def get_spy_price(symbol: str = "SPY") -> float:
    """Current mid-price of SPY from latest quote."""
    try:
        r = requests.get(
            f"{ALPACA_DATA_URL}/stocks/{symbol}/quotes/latest",
            headers=DATA_HEADERS, timeout=10,
        )
        if r.ok:
            q = r.json().get("quote", {})
            ask = float(q.get("ap") or 0)
            bid = float(q.get("bp") or 0)
            if ask > 0 and bid > 0:
                return (ask + bid) / 2
    except Exception:
        pass
    # Fallback: last trade price
    try:
        r = requests.get(
            f"{ALPACA_DATA_URL}/stocks/{symbol}/trades/latest",
            headers=DATA_HEADERS, timeout=10,
        )
        if r.ok:
            return float(r.json().get("trade", {}).get("p") or 0)
    except Exception:
        pass
    return 0.0


# ── Option Contracts ──────────────────────────────────────────────────────────

def get_option_contracts(
    underlying: str,
    option_type: str,       # "call" or "put"
    min_dte: int,
    max_dte: int,
    strike_gte: float = None,
    strike_lte: float = None,
) -> list:
    today   = date.today()
    exp_gte = (today + timedelta(days=min_dte)).isoformat()
    exp_lte = (today + timedelta(days=max_dte)).isoformat()
    params  = {
        "underlying_symbols":  underlying,
        "expiration_date_gte": exp_gte,
        "expiration_date_lte": exp_lte,
        "type":   option_type,
        "status": "active",
        "limit":  250,
    }
    if strike_gte is not None:
        params["strike_price_gte"] = round(strike_gte, 2)
    if strike_lte is not None:
        params["strike_price_lte"] = round(strike_lte, 2)
    try:
        r = requests.get(
            f"{ALPACA_BASE_URL}/options/contracts",
            headers=HEADERS, params=params, timeout=15,
        )
        r.raise_for_status()
        return r.json().get("option_contracts", [])
    except Exception as e:
        log.error("get_option_contracts(%s %s): %s", underlying, option_type, e)
        return []


# ── Option Snapshots (Greeks + Pricing) ──────────────────────────────────────

def get_option_snapshots(symbols: list) -> dict:
    if not symbols:
        return {}
    params = {"symbols": ",".join(symbols[:100]), "feed": "indicative"}
    try:
        r = requests.get(
            f"{_OPTIONS_DATA_URL}/options/snapshots",
            headers=DATA_HEADERS, params=params, timeout=15,
        )
        r.raise_for_status()
        return r.json().get("snapshots", {})
    except Exception as e:
        log.error("get_option_snapshots: %s", e)
        return {}


def get_option_snapshot(symbol: str) -> dict:
    return get_option_snapshots([symbol]).get(symbol, {})


# ── Price / Greek Extractors ──────────────────────────────────────────────────

def mid(snap: dict) -> float:
    q   = snap.get("latestQuote", {})
    ask = float(q.get("ap") or 0)
    bid = float(q.get("bp") or 0)
    if ask > 0 and bid > 0:
        return round((ask + bid) / 2, 4)
    return float(snap.get("latestTrade", {}).get("p") or 0)


def ask(snap: dict) -> float:
    return float(snap.get("latestQuote", {}).get("ap") or 0)


def bid_price(snap: dict) -> float:
    return float(snap.get("latestQuote", {}).get("bp") or 0)


def delta(snap: dict) -> float:
    """Absolute value of delta."""
    return abs(float(snap.get("greeks", {}).get("delta") or 0))


def raw_delta(snap: dict) -> float:
    """Signed delta (negative for puts)."""
    return float(snap.get("greeks", {}).get("delta") or 0)


def iv(snap: dict) -> float:
    return float(snap.get("impliedVolatility") or 0)


def theta(snap: dict) -> float:
    return float(snap.get("greeks", {}).get("theta") or 0)


# ── Order Placement ───────────────────────────────────────────────────────────

def place_option_order(
    occ_symbol: str,
    side: str,           # "buy" (buy to open / buy to close)
                         # "sell" (sell to open / sell to close)
    qty: int,
    limit_price: float,
) -> dict:
    payload = {
        "symbol":        occ_symbol,
        "qty":           qty,
        "side":          side,
        "type":          "limit",
        "time_in_force": "day",
        "limit_price":   round(max(limit_price, 0.01), 2),
        "asset_class":   "us_option",
    }
    log.info("  ORDER  %s %s x%d @ $%.2f", side.upper(), occ_symbol, qty, limit_price)
    r = requests.post(f"{ALPACA_BASE_URL}/orders", headers=HEADERS, json=payload, timeout=10)
    if not r.ok:
        log.error("  Order FAILED %s: %s", r.status_code, r.text[:300])
        r.raise_for_status()
    return r.json()
