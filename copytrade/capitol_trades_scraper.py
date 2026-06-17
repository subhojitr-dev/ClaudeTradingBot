"""
capitol_trades_scraper.py
=========================
Fetches recent trades for a politician from:

    https://www.capitoltrades.com/trades?politician=P000197&pageSize=20&page=1

Capitol Trades is a Next.js / React app — all trade data is injected into
the DOM by client-side JavaScript AFTER the initial HTML loads.  A plain
requests() call therefore gets an empty shell.

Strategy
--------
Primary  : Playwright headless Chromium — renders the full page, then
           extracts rows from the trades table.
Fallback : requests + BeautifulSoup on the raw HTML (works if CT ever
           switches to SSR, or if Playwright is unavailable).

Playwright install (one-time, run in your venv):
    pip install playwright
    playwright install chromium
"""

import json
import logging
import re
import time
from typing import Any, Dict, List

log = logging.getLogger(__name__)

# ── URL used to fetch trades ───────────────────────────────────────────────────
#
#   Base  : https://www.capitoltrades.com/trades
#   Param : politician=<CT_POLITICIAN_ID>   (Nancy Pelosi = P000197)
#   Param : pageSize=20                     (trades per page)
#   Param : page=1
#   Param : sortBy=txDate&order=desc        (newest first)
#
CT_TRADES_URL_TEMPLATE = (
    "https://www.capitoltrades.com/trades"
    "?politician={politician_id}"
    "&pageSize={page_size}"
    "&page={page}"
    "&sortBy=txDate&order=desc"
)

# ── Table column indices (0-based) on the Capitol Trades trade table ──────────
# Confirmed live layout (May 2026) — 10 cells per row:
#   [0] Politician name + party/state
#   [1] Company name + "TICKER:US"
#   [2] Filed / Published date
#   [3] Traded / Transaction date
#   [4] Days to report
#   [5] Owner (Spouse / Joint / Self)
#   [6] BUY or SELL
#   [7] Amount range  e.g. "500K–1M"
#   [8] Price per share or N/A
#   [9] Link label
COL_POLITICIAN = 0
COL_COMPANY    = 1
COL_FILED      = 2
COL_TRADED     = 3
COL_ACTION     = 6
COL_AMOUNT     = 7


# ══════════════════════════════════════════════════════════════════════════════
#  Public entry point
# ══════════════════════════════════════════════════════════════════════════════

def fetch_politician_trades(
    politician_id: str,
    politician_name: str = "Unknown",
    page_size: int = 20,
    max_pages: int = 1,
) -> List[Dict[str, Any]]:
    """
    Fetch recent trades for a politician from Capitol Trades.
    Returns a list of normalised trade dicts.

    Data source URL (example for Nancy Pelosi):
        https://www.capitoltrades.com/trades?politician=P000197&pageSize=20&page=1&sortBy=txDate&order=desc
    """
    all_trades: List[Dict] = []

    for page in range(1, max_pages + 1):
        url = CT_TRADES_URL_TEMPLATE.format(
            politician_id=politician_id,
            page_size=page_size,
            page=page,
        )
        log.info("Fetching page %d for %s: %s", page, politician_name, url)

        raw_trades = _fetch_with_playwright(url, politician_name)
        if not raw_trades:
            log.warning("Playwright returned no trades – trying requests fallback...")
            raw_trades = _fetch_with_requests(url, politician_name)

        if not raw_trades:
            log.warning("No trades found on page %d – stopping pagination", page)
            break

        all_trades.extend(raw_trades)

        if len(raw_trades) < page_size:
            break   # Last page reached

    log.info("Total trades fetched for %s: %d", politician_name, len(all_trades))
    return all_trades


# ══════════════════════════════════════════════════════════════════════════════
#  Playwright renderer (primary)
# ══════════════════════════════════════════════════════════════════════════════

def _fetch_with_playwright(url: str, politician_name: str = "Unknown") -> List[Dict[str, Any]]:
    """
    Use a headless Chromium browser to render the Capitol Trades page and
    extract trade rows from the DOM table.
    """
    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
    except ImportError:
        log.warning("Playwright not installed. Run: pip install playwright && playwright install chromium")
        return []

    trades: List[Dict] = []
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                viewport={"width": 1280, "height": 900},
            )
            page = context.new_page()

            log.info("Browser navigating to: %s", url)
            page.goto(url, wait_until="domcontentloaded", timeout=30_000)

            # Wait for the trade table rows to appear
            try:
                page.wait_for_selector("table tbody tr", timeout=20_000)
            except PWTimeout:
                log.warning("Timed out waiting for trade table rows")
                # Try to get whatever is on the page
                pass

            # Give JS a moment to finish rendering
            time.sleep(2)

            # ── Extract rows via JavaScript in the browser context ──────────
            rows_data = page.evaluate("""
                () => {
                    const rows = document.querySelectorAll('table tbody tr');
                    const result = [];
                    rows.forEach(row => {
                        const cells = row.querySelectorAll('td');
                        if (cells.length < 5) return;
                        const cellTexts = [];
                        cells.forEach(cell => cellTexts.push(cell.innerText.trim()));
                        // Also grab data attributes if present
                        const attrs = {};
                        for (const attr of row.attributes) {
                            attrs[attr.name] = attr.value;
                        }
                        result.push({ cells: cellTexts, attrs: attrs });
                    });
                    return result;
                }
            """)

            browser.close()

            log.info("Playwright extracted %d raw rows", len(rows_data or []))
            for row in (rows_data or []):
                trade = _parse_table_row(row.get("cells", []), politician_name)
                if trade:
                    trades.append(trade)

    except Exception as e:
        log.error("Playwright error: %s", e)

    return trades


# ══════════════════════════════════════════════════════════════════════════════
#  Requests fallback (plain HTTP – works only if site has SSR content)
# ══════════════════════════════════════════════════════════════════════════════

def _fetch_with_requests(url: str, politician_name: str = "Unknown") -> List[Dict[str, Any]]:
    """
    Plain HTTP fallback. Attempts to find trade data embedded in the raw HTML
    (Next.js __NEXT_DATA__ or server-rendered table rows).
    """
    import requests
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        log.warning("beautifulsoup4 not installed – skipping HTML fallback")
        return []

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,*/*;q=0.9",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.capitoltrades.com/",
    }

    try:
        resp = requests.get(url, headers=headers, timeout=30)
        resp.raise_for_status()
    except Exception as e:
        log.error("HTTP request failed: %s", e)
        return []

    soup = BeautifulSoup(resp.text, "html.parser")

    # ── Try __NEXT_DATA__ first ──────────────────────────────────────────────
    next_data_tag = soup.find("script", id="__NEXT_DATA__")
    if next_data_tag:
        try:
            nd = json.loads(next_data_tag.string)
            props = nd.get("props", {}).get("pageProps", {})
            for key in ("trades", "data", "initialData", "tradeData"):
                val = props.get(key)
                if isinstance(val, list) and val:
                    log.info("Found %d trades in __NEXT_DATA__[%s]", len(val), key)
                    return [_normalise_api(t) for t in val]
                if isinstance(val, dict):
                    inner = val.get("trades") or val.get("data") or []
                    if inner:
                        return [_normalise_api(t) for t in inner]
        except Exception as e:
            log.warning("Could not parse __NEXT_DATA__: %s", e)

    # ── Try HTML table rows ──────────────────────────────────────────────────
    trades = []
    for row in soup.select("table tbody tr"):
        cells = [td.get_text(separator=" ", strip=True) for td in row.find_all("td")]
        trade = _parse_table_row(cells, politician_name)
        if trade:
            trades.append(trade)

    if trades:
        log.info("Extracted %d trades from HTML table", len(trades))
    else:
        log.warning("No trade data found in raw HTML (site likely requires JS rendering)")

    return trades


# ══════════════════════════════════════════════════════════════════════════════
#  Parsers
# ══════════════════════════════════════════════════════════════════════════════

def _parse_table_row(cells: List[str], politician_name: str = "Unknown") -> Dict[str, Any]:
    """
    Convert a list of cell text values from the Capitol Trades trades table
    into a normalised trade dict.

    Confirmed live layout (May 2026) — 10 cells per row:
        [0] Politician        e.g. "Nancy Pelosi\\nDemocratHouseCA"
        [1] Company+Ticker    e.g. "Microsoft Corp\\nMSFT:US"
        [2] Filed date        e.g. "23 Jun\\n2023"
        [3] Traded date       e.g. "14 Jun\\n2023"
        [4] Days to report    e.g. "days\\n7"
        [5] Owner             e.g. "Spouse"
        [6] Action            e.g. "BUY" / "SELL"
        [7] Amount            e.g. "500K–1M"
        [8] Price             e.g. "$180.00" / "N/A"
        [9] Link label
    """
    if not cells or len(cells) < 7:
        return {}

    # ── Ticker: extracted from cell[1] which looks like "Company Name\nTICKER:US" ──
    company_cell = cells[COL_COMPANY] if len(cells) > COL_COMPANY else ""
    ticker = ""
    # Ticker is after the last newline, formatted as "TICK:US"
    ticker_match = re.search(r"([A-Z]{1,6}(?:\.[A-Z]{1,2})?):US", company_cell)
    if ticker_match:
        ticker = ticker_match.group(1)
    else:
        # Fallback: first all-caps word
        m2 = re.match(r"^([A-Z]{1,6})", company_cell.strip())
        if m2:
            ticker = m2.group(1)

    if not ticker:
        return {}

    # ── Asset type: Capitol Trades currently shows stocks (options would say "Call"/"Put") ──
    # Cell [1] may say "Call Option" or "Put Option" for options
    asset_raw = company_cell.lower()
    if "call" in asset_raw:
        asset_type  = "option"
        option_type = "call"
    elif "put" in asset_raw:
        asset_type  = "option"
        option_type = "put"
    else:
        asset_type  = "stock"
        option_type = None

    # ── Action ──────────────────────────────────────────────────────────────
    action_raw = (cells[COL_ACTION] if len(cells) > COL_ACTION else "").upper()
    if "BUY" in action_raw or "PURCHASE" in action_raw:
        action = "buy"
    elif "SELL" in action_raw or "SALE" in action_raw:
        action = "sell"
    elif "EXCHANGE" in action_raw or "RECEIVE" in action_raw:
        action = "buy"
    else:
        action = "buy"

    # ── Amount ───────────────────────────────────────────────────────────────
    amount_raw  = cells[COL_AMOUNT] if len(cells) > COL_AMOUNT else ""
    size_low, size_high = _parse_amount(amount_raw)

    # ── Dates ────────────────────────────────────────────────────────────────
    filed_date  = cells[COL_FILED].replace("\n", " ")  if len(cells) > COL_FILED  else ""
    traded_date = cells[COL_TRADED].replace("\n", " ") if len(cells) > COL_TRADED else ""

    # ── Deterministic trade ID ────────────────────────────────────────────────
    trade_id = f"{traded_date}|{ticker}|{action}|{amount_raw}".replace(" ", "_")

    return {
        "trade_id":    trade_id,
        "politician":  politician_name,
        "ticker":      ticker,
        "asset_type":  asset_type,
        "action":      action,
        "tx_date":     traded_date,
        "filed_date":  filed_date,
        "size_low":    size_low,
        "size_high":   size_high,
        "option_type": option_type,
        "strike":      None,
        "expiry":      None,
        "raw":         {"cells": cells},
    }


def _normalise_api(raw: Dict) -> Dict[str, Any]:
    """Normalise a raw API response dict (fallback path)."""
    def safe(key, default=None):
        return raw.get(key, default)

    ticker = (
        safe("ticker") or safe("symbol")
        or (safe("issuer") or {}).get("ticker", "")
        or ""
    ).upper().strip()

    asset = (safe("assetType") or safe("asset_type") or "stock").lower()
    if "option" in asset:
        asset_type = "option"
    elif asset in ("stock", "equity", "common stock"):
        asset_type = "stock"
    else:
        asset_type = "other"

    action = (safe("type") or safe("txType") or safe("action") or "buy").lower()
    action = "buy" if action in ("purchase", "buy") else ("sell" if "sell" in action or "sale" in action else action)

    size_raw = safe("size") or safe("amount") or {}
    if isinstance(size_raw, dict):
        size_low  = int(size_raw.get("lower", 0))
        size_high = int(size_raw.get("upper", 0))
    else:
        size_low = size_high = int(size_raw or 0)

    option_info = safe("option") or {}
    option_type = (option_info.get("type") or "").lower() or None if asset_type == "option" else None

    trade_id = str(safe("id") or safe("tradeId") or "")
    if not trade_id:
        tx = safe("txDate") or ""
        trade_id = f"{tx}|{ticker}|{action}"

    return {
        "trade_id":    trade_id,
        "politician":  safe("politician") or "Nancy Pelosi",
        "ticker":      ticker,
        "asset_type":  asset_type,
        "action":      action,
        "tx_date":     safe("txDate") or safe("tradeDate") or "",
        "filed_date":  safe("filedDate") or "",
        "size_low":    size_low,
        "size_high":   size_high,
        "option_type": option_type,
        "strike":      (option_info.get("strike")) if asset_type == "option" else None,
        "expiry":      (option_info.get("expiry")) if asset_type == "option" else None,
        "raw":         raw,
    }


def _parse_amount(amount_str: str):
    """
    Parse Capitol Trades amount strings like '$250K–$500K' or '$1M–5M'.
    Returns (low_int, high_int) in whole dollars.
    """
    def to_int(s: str) -> int:
        s = s.strip().lstrip("$").replace(",", "").upper()
        if not s:
            return 0
        try:
            if s.endswith("M"):
                return int(float(s[:-1]) * 1_000_000)
            elif s.endswith("K"):
                return int(float(s[:-1]) * 1_000)
            else:
                return int(float(s))
        except ValueError:
            return 0

    parts = re.split(r"[–\-—]", amount_str)
    if len(parts) == 2:
        return to_int(parts[0]), to_int(parts[1])
    elif len(parts) == 1:
        v = to_int(parts[0])
        return v, v
    return 0, 0
