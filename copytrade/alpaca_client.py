"""
alpaca_client.py
Thin wrapper around the Alpaca REST v2 API (paper trading).
"""

import requests
import logging
from config import ALPACA_API_KEY, ALPACA_SECRET_KEY, ALPACA_BASE_URL

log = logging.getLogger(__name__)

HEADERS = {
    "APCA-API-KEY-ID":     ALPACA_API_KEY,
    "APCA-API-SECRET-KEY": ALPACA_SECRET_KEY,
    "Content-Type":        "application/json",
}


def get_account():
    """Return account info dict."""
    r = requests.get(f"{ALPACA_BASE_URL}/account", headers=HEADERS)
    r.raise_for_status()
    return r.json()


def get_positions():
    """Return list of current positions."""
    r = requests.get(f"{ALPACA_BASE_URL}/positions", headers=HEADERS)
    r.raise_for_status()
    return r.json()


def get_open_orders():
    """Return list of open orders."""
    r = requests.get(f"{ALPACA_BASE_URL}/orders?status=open", headers=HEADERS)
    r.raise_for_status()
    return r.json()


def place_stock_order(symbol: str, qty: int, side: str) -> dict:
    """
    Place a market order for a stock.
    side: 'buy' | 'sell'
    """
    payload = {
        "symbol":        symbol,
        "qty":           qty,
        "side":          side,
        "type":          "market",
        "time_in_force": "day",
    }
    log.info("Placing stock order: %s %s x%d", side.upper(), symbol, qty)
    r = requests.post(f"{ALPACA_BASE_URL}/orders", headers=HEADERS, json=payload)
    if not r.ok:
        log.error("Order failed: %s – %s", r.status_code, r.text)
        r.raise_for_status()
    result = r.json()
    log.info("Order accepted – ID: %s  Status: %s", result["id"], result["status"])
    return result


def place_option_order(option_symbol: str, side: str) -> dict:
    """
    Place a market order for 1 options contract.
    option_symbol must be an OCC-formatted symbol,
    e.g. 'NVDA251219C00120000'
    side: 'buy' | 'sell'
    """
    payload = {
        "symbol":        option_symbol,
        "qty":           1,
        "side":          side,
        "type":          "market",
        "time_in_force": "day",
        "asset_class":   "us_option",
    }
    log.info("Placing option order: %s %s x1", side.upper(), option_symbol)
    r = requests.post(f"{ALPACA_BASE_URL}/orders", headers=HEADERS, json=payload)
    if not r.ok:
        log.error("Option order failed: %s – %s", r.status_code, r.text)
        r.raise_for_status()
    result = r.json()
    log.info("Option order accepted – ID: %s  Status: %s", result["id"], result["status"])
    return result


def is_market_open() -> bool:
    """Check if the US market is currently open."""
    r = requests.get(f"{ALPACA_BASE_URL}/clock", headers=HEADERS)
    r.raise_for_status()
    return r.json().get("is_open", False)


def get_latest_quote(symbol: str) -> dict:
    """Get latest quote for a symbol (data API)."""
    data_url = "https://data.alpaca.markets/v2"
    r = requests.get(
        f"{data_url}/stocks/{symbol}/quotes/latest",
        headers=HEADERS,
    )
    r.raise_for_status()
    return r.json()
