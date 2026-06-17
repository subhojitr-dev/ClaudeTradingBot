"""
option_resolver.py
Attempts to build or find a valid OCC options symbol for a Capitol Trades
option record, using Alpaca's option snapshot API.

OCC Format:  SYMBOL + YYMMDD + C/P + 8-digit strike (price * 1000, zero-padded)
Example:     NVDA251219C00120000  = NVDA $120 Call expiring 2025-12-19
"""

import logging
import re
import requests
from datetime import datetime, date, timedelta
from typing import Optional, Dict, Any

from config import ALPACA_API_KEY, ALPACA_SECRET_KEY

log = logging.getLogger(__name__)

DATA_URL = "https://data.alpaca.markets/v2"
HEADERS = {
    "APCA-API-KEY-ID":     ALPACA_API_KEY,
    "APCA-API-SECRET-KEY": ALPACA_SECRET_KEY,
}


def resolve_option_symbol(trade: Dict[str, Any]) -> Optional[str]:
    """
    Given a normalised Capitol Trades option record, return the best
    OCC symbol we can find on Alpaca.

    Strategy:
    1. If the raw trade already contains a full OCC symbol, use it.
    2. If we have strike + expiry + option_type, construct the OCC symbol.
    3. Otherwise, search Alpaca's option chain for the nearest ATM contract.
    """
    ticker      = trade.get("ticker", "")
    option_type = (trade.get("option_type") or "").lower()  # 'call' or 'put'
    strike      = trade.get("strike")
    expiry      = trade.get("expiry")

    if not ticker:
        return None

    # ── 1. Check raw for pre-formed OCC symbol ──────────────────────────────
    raw = trade.get("raw", {})
    for field in ("occSymbol", "occ_symbol", "contractSymbol", "optionSymbol"):
        val = raw.get(field) or (raw.get("option") or {}).get(field)
        if val and re.match(r"^[A-Z]+\d{6}[CP]\d{8}$", val):
            log.info("Found pre-formed OCC symbol: %s", val)
            return val

    # ── 2. Construct from known strike + expiry + type ──────────────────────
    if strike and expiry and option_type in ("call", "put"):
        try:
            occ = _build_occ(ticker, option_type, strike, expiry)
            # Verify it exists on Alpaca
            if _verify_option(occ):
                log.info("Constructed + verified OCC symbol: %s", occ)
                return occ
            else:
                log.warning("Constructed OCC symbol %s not found on Alpaca", occ)
        except Exception as e:
            log.warning("Could not build OCC from trade data: %s", e)

    # ── 3. Search Alpaca option chain for nearest ATM contract ───────────────
    log.info("Searching Alpaca option chain for %s %s...", ticker, option_type or "call")
    occ = _find_atm_option(ticker, option_type or "call")
    if occ:
        log.info("Found ATM option via chain search: %s", occ)
    return occ


# ── Helpers ──────────────────────────────────────────────────────────────────

def _build_occ(ticker: str, option_type: str, strike, expiry: str) -> str:
    """Build an OCC symbol string."""
    # Parse expiry – Capitol Trades uses ISO dates: 2025-12-19
    if isinstance(expiry, str):
        for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%Y%m%d"):
            try:
                exp_date = datetime.strptime(expiry, fmt).date()
                break
            except ValueError:
                continue
        else:
            raise ValueError(f"Cannot parse expiry: {expiry}")
    else:
        exp_date = expiry

    cp      = "C" if option_type == "call" else "P"
    yy      = exp_date.strftime("%y")
    mm      = exp_date.strftime("%m")
    dd      = exp_date.strftime("%d")
    strike_int = int(float(strike) * 1000)
    return f"{ticker}{yy}{mm}{dd}{cp}{strike_int:08d}"


def _verify_option(occ_symbol: str) -> bool:
    """Return True if Alpaca knows about this option contract."""
    try:
        r = requests.get(
            f"{DATA_URL}/options/snapshots/{occ_symbol}",
            headers=HEADERS,
            timeout=10,
        )
        return r.ok
    except Exception:
        return False


def _find_atm_option(ticker: str, option_type: str) -> Optional[str]:
    """
    Search Alpaca's options chain for the nearest at-the-money contract
    expiring in the next 30–90 days.
    """
    today     = date.today()
    exp_from  = today + timedelta(days=30)
    exp_to    = today + timedelta(days=90)
    cp        = "call" if option_type == "call" else "put"

    try:
        # Get current stock price first
        r = requests.get(
            f"{DATA_URL}/stocks/{ticker}/quotes/latest",
            headers=HEADERS,
            timeout=10,
        )
        if not r.ok:
            log.warning("Could not get quote for %s", ticker)
            return None
        quote_data = r.json().get("quote", {})
        mid_price  = (quote_data.get("ap", 0) + quote_data.get("bp", 0)) / 2
        if mid_price <= 0:
            return None

        # Query option snapshots
        params = {
            "type":            cp,
            "expiration_date_gte": exp_from.isoformat(),
            "expiration_date_lte": exp_to.isoformat(),
            "limit":           20,
        }
        r2 = requests.get(
            f"{DATA_URL}/options/snapshots/{ticker}",
            headers=HEADERS,
            params=params,
            timeout=15,
        )
        if not r2.ok:
            log.warning("Option chain lookup failed for %s: %s", ticker, r2.text[:200])
            return None

        snapshots = r2.json().get("snapshots", {})
        if not snapshots:
            return None

        # Pick the contract whose strike is closest to current price
        best_symbol = None
        best_delta  = float("inf")
        for sym, snap in snapshots.items():
            details = snap.get("greeks") or snap.get("details") or {}
            strike_val = details.get("strike_price") or details.get("strikePrice", 0)
            if strike_val:
                delta = abs(float(strike_val) - mid_price)
                if delta < best_delta:
                    best_delta  = delta
                    best_symbol = sym

        return best_symbol

    except Exception as e:
        log.warning("Error searching option chain for %s: %s", ticker, e)
        return None
