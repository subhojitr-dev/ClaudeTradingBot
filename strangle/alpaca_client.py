"""
alpaca_client.py  --  Alpaca REST API wrapper for the strangle bot
Account: PA34EFPV3B80 (Options Paper Account)
"""

import logging
import requests
from datetime import date, timedelta
from config import (
    ALPACA_API_KEY, ALPACA_SECRET_KEY,
    ALPACA_BASE_URL, ALPACA_DATA_URL,
)

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


def get_stock_price(symbol: str) -> float:
    """Mid-price from latest quote; falls back to latest trade."""
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


def get_option_contracts(
    underlying: str,
    option_type: str,
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
        log.error("get_option_contracts(%s %s) failed: %s", underlying, option_type, e)
        return []


def get_option_snapshots(symbols: list) -> dict:
    if not symbols:
        return {}
    params = {"symbols": ",".join(symbols[:100]), "feed": "indicative"}
    try:
        r = requests.get(
            f"{ALPACA_DATA_URL}/options/snapshots",
            headers=DATA_HEADERS, params=params, timeout=15,
        )
        r.raise_for_status()
        return r.json().get("snapshots", {})
    except Exception as e:
        log.error("get_option_snapshots failed: %s", e)
        return {}


def get_option_snapshot(symbol: str) -> dict:
    return get_option_snapshots([symbol]).get(symbol, {})


def extract_mid(snapshot: dict) -> float:
    q   = snapshot.get("latestQuote", {})
    ask = float(q.get("ap") or 0)
    bid = float(q.get("bp") or 0)
    if ask > 0 and bid > 0:
        return round((ask + bid) / 2, 4)
    if ask > 0:
        return ask
    t = snapshot.get("latestTrade", {})
    return float(t.get("p") or 0)


def extract_ask(snapshot: dict) -> float:
    return float(snapshot.get("latestQuote", {}).get("ap") or 0)


def extract_delta(snapshot: dict) -> float:
    return abs(float(snapshot.get("greeks", {}).get("delta") or 0))


def extract_iv(snapshot: dict) -> float:
    return float(snapshot.get("impliedVolatility") or 0)


def place_option_order(
    contract_symbol: str,
    side: str,          # "buy" (buy to open) or "sell" (sell to close)
    qty: int,
    limit_price: float,
) -> dict:
    payload = {
        "symbol":        contract_symbol,
        "qty":           qty,
        "side":          side,
        "type":          "limit",
        "time_in_force": "day",
        "limit_price":   round(max(limit_price, 0.01), 2),
        "asset_class":   "us_option",
    }
    log.info("Option order: %s %s x%d @ $%.2f", side.upper(), contract_symbol, qty, limit_price)
    r = requests.post(f"{ALPACA_BASE_URL}/orders", headers=HEADERS, json=payload, timeout=10)
    if not r.ok:
        log.error("Order FAILED %s: %s", r.status_code, r.text[:300])
        r.raise_for_status()
    return r.json()
