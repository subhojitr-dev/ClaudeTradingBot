"""
pharma_catalyst.py  --  Daily Pharma/Biotech Catalyst Scanner
==============================================================
Scans each morning for pharmaceutical stocks with high-impact catalyst
events:

  - FDA drug approvals (PDUFA decisions, NDAs, BLAs)
  - Phase 2 / Phase 3 clinical trial results
  - Breakthrough therapy / Priority review designations
  - Advisory committee (AdCom) votes
  - Complete Response Letters (CRL) -- SKIPPED by default

Sources:
  1. Alpaca market-movers screener -- today's biggest % gainers market-wide
     (no watchlist needed), filtered to penny-stock/warrant noise removed,
     then each surviving candidate is checked against its own Finviz quote
     page for pharma/biotech sector + a classifiable news headline.
  2. FDA RSS Feed -- FDA press releases (official approvals)

  (Two earlier sources -- Finviz's general news.ashx page and its biotech
  screener page -- were removed 2026-08-03. Finviz redesigned news.ashx to
  no longer tag headlines with a ticker at all, and the screener's results
  table is now client-side rendered with CSV export paywalled behind
  Finviz Elite, so neither could reliably be scraped anymore. The
  still-working piece -- per-ticker quote.ashx pages -- is what source 1
  above now leans on instead.)

Results are cached per day so the scan only runs once regardless of
how many times the trailing-stop bot fires during the day.

Each found stock is returned as:
  {
    "ticker":     "MRNA",
    "headline":   "Moderna Phase 3 trial shows 94% efficacy...",
    "event_type": "TRIAL_RESULTS",
    "source":     "alpaca_movers",
  }
"""

import json
import logging
import os
import re
import time
from datetime import date
from typing import Dict, List

import requests
from bs4 import BeautifulSoup

log = logging.getLogger(__name__)

# ── Keyword sets ──────────────────────────────────────────────────────────────

CATALYST_KEYWORDS = [
    "fda approv", "fda clears", "fda grants", "fda accepts",
    "fda approves", "approved by fda", "receives fda",
    "pdufa", "advisory committee", "adcom",
    "nda submission", "nda accepted", "bla submission", "bla accepted",
    "phase 3 ", "phase iii ", "phase 2/3", "phase 2b",
    "top-line results", "topline results", "top line data",
    "trial results", "clinical data", "data readout", "interim data",
    "complete response letter", " crl ", "refuse to file",
    "breakthrough therapy", "priority review", "fast track designation",
    "accelerated approval", "orphan drug designation",
    "positive results", "meets primary endpoint", "primary endpoint met",
    "fails primary", "misses primary",
]

# Event classification mapping
EVENT_MAP = [
    (["fda approv", "fda clears", "fda grants", "approved by fda",
      "receives fda approval", "accelerated approval"],           "FDA_APPROVAL"),
    (["pdufa", "advisory committee", "adcom", "fda decision"],   "FDA_DECISION"),
    (["complete response letter", " crl ", "refuse to file",
      "fails primary", "misses primary endpoint"],                "FDA_REJECTION"),
    (["phase 3", "phase iii", "phase 2/3", "phase 2b",
      "top-line", "topline", "trial results", "data readout",
      "interim data", "primary endpoint met", "positive results"], "TRIAL_RESULTS"),
    (["nda submission", "bla submission", "nda accepted",
      "bla accepted"],                                            "REGULATORY_FILING"),
    (["breakthrough therapy", "priority review", "fast track"],   "FDA_DESIGNATION"),
]

# Known pharma/biotech keywords that appear on Finviz quote pages
PHARMA_INDUSTRIES = {
    "biotechnology", "drug manufacturers", "pharmaceutical",
    "specialty pharmaceutical", "biopharmaceutical", "biologics",
    "drug manufacturer", "healthcare",
}

# Common non-ticker uppercase words to ignore when extracting tickers from FDA text
FDA_SKIP_WORDS = {
    "FDA", "NDA", "BLA", "IND", "NME", "CRL", "PDUFA", "US", "NEW",
    "THE", "AND", "FOR", "INC", "LLC", "LTD", "PLC", "AG", "SA",
    "CEO", "COO", "CFO", "MD", "DR", "MR", "MS", "PH", "TO", "OF",
    "IN", "ON", "AT", "BY", "OR", "WITH", "FROM", "AN",
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept":          "text/html,application/xhtml+xml,*/*;q=0.9",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer":         "https://www.google.com/",
}


# ══════════════════════════════════════════════════════════════════════════════
#  Public entry point
# ══════════════════════════════════════════════════════════════════════════════

def scan_today(
    max_stocks: int = 3,
    skip_event_types: list = None,
    cache_file: str = "pharma_catalyst_cache.json",
    sector_cache_file: str = "sector_cache.json",
    alpaca_api_key: str = None,
    alpaca_secret_key: str = None,
    alpaca_data_url: str = "https://data.alpaca.markets/v1beta1",
    movers_min_pct: float = 8.0,
    movers_min_price: float = 5.0,
    movers_max_candidates: int = 25,
) -> List[Dict]:
    """
    Scan all sources for pharma/biotech catalyst events today.

    Returns list of dicts: {ticker, headline, event_type, source}
    Results are cached -- calling this multiple times in one day
    returns the cached list without re-scanning.

    Args:
        max_stocks           : maximum number of stocks to return
        skip_event_types     : event types to exclude (e.g. ["FDA_REJECTION"])
        cache_file            : path to daily results cache
        sector_cache_file    : path to persistent sector classification cache
        alpaca_api_key/secret: credentials for the Alpaca movers screener
                                (big-movers source is skipped if not provided)
        alpaca_data_url       : base URL for Alpaca's screener endpoint
        movers_min_pct        : minimum % gain today to be worth checking
        movers_min_price      : minimum price to filter out penny stocks
        movers_max_candidates : cap on how many movers get checked against Finviz
    """
    skip_event_types = skip_event_types or []
    today_str        = date.today().isoformat()

    # Return cached results if already scanned today
    cache = _load_json(cache_file)
    if cache.get("date") == today_str:
        cached = cache.get("results", [])
        log.info("Pharma catalyst: using cached results from %s (%d stocks)",
                 today_str, len(cached))
        return [r for r in cached if r.get("event_type") not in skip_event_types]

    log.info("Pharma catalyst: scanning sources for %s...", today_str)
    results: List[Dict] = []
    seen_tickers: set   = set()

    # ── Source 1: Today's biggest movers (Alpaca), filtered to pharma/biotech ──
    if alpaca_api_key and alpaca_secret_key:
        try:
            movers = _scan_big_movers(
                sector_cache_file, alpaca_api_key, alpaca_secret_key, alpaca_data_url,
                movers_min_pct, movers_min_price, movers_max_candidates,
            )
            for item in movers:
                if item["ticker"] not in seen_tickers:
                    results.append(item)
                    seen_tickers.add(item["ticker"])
            log.info("Big movers: %d pharma/biotech catalyst stock(s) found", len(movers))
        except Exception as e:
            log.error("Big movers scan failed: %s", e)
    else:
        log.warning("Alpaca credentials not provided -- skipping big-movers scan")

    # ── Source 2: FDA official RSS feed ────────────────────────────────────
    try:
        before = len(seen_tickers)
        for item in _scan_fda_rss(sector_cache_file):
            if item["ticker"] not in seen_tickers:
                results.append(item)
                seen_tickers.add(item["ticker"])
        log.info("FDA RSS: %d additional event(s)", len(seen_tickers) - before)
    except Exception as e:
        log.error("FDA RSS scan failed: %s", e)

    # Cap results
    results = results[:max_stocks]

    # Cache for rest of day
    _save_json(cache_file, {"date": today_str, "results": results})

    if results:
        log.info("Pharma catalyst: found %d stock(s) with events today: %s",
                 len(results), [r["ticker"] for r in results])
    else:
        log.info("Pharma catalyst: no catalyst events found today")

    return [r for r in results if r.get("event_type") not in skip_event_types]


# ══════════════════════════════════════════════════════════════════════════════
#  Source 1: Today's Biggest Movers (Alpaca) -> Finviz sector + news check
# ══════════════════════════════════════════════════════════════════════════════

# Warrants, units, and other odd tickers (e.g. "ADACW", "MDCXW") tend to
# dominate the raw movers list with huge, meaningless % swings on thin
# volume -- filter to plain 1-5 letter ticker symbols only.
_PLAIN_TICKER_RE = re.compile(r"^[A-Z]{1,5}$")


def _scan_big_movers(
    sector_cache_file: str,
    api_key: str,
    secret_key: str,
    data_url: str,
    min_pct: float,
    min_price: float,
    max_candidates: int,
) -> List[Dict]:
    """
    Find today's biggest % gainers market-wide via Alpaca's screener API --
    no watchlist needed. Filters out penny stocks and warrants/units, then
    checks each surviving candidate's Finviz quote page for pharma/biotech
    sector membership and a classifiable catalyst headline in its own news
    feed (both of which still work server-side, unlike Finviz's general
    news page and screener page).
    """
    headers = {"APCA-API-KEY-ID": api_key, "APCA-API-SECRET-KEY": secret_key}
    try:
        r = requests.get(
            f"{data_url}/screener/stocks/movers",
            headers=headers, params={"top": 50}, timeout=15,
        )
        r.raise_for_status()
        gainers = r.json().get("gainers", [])
    except Exception as e:
        log.warning("Alpaca movers fetch failed: %s", e)
        return []

    results = []
    checked = 0

    for g in gainers:
        symbol = g.get("symbol", "")
        price  = g.get("price", 0) or 0
        pct    = g.get("percent_change", 0) or 0

        if not _PLAIN_TICKER_RE.match(symbol):
            continue
        if price < min_price or pct < min_pct:
            continue
        if checked >= max_candidates:
            break
        checked += 1

        if not _is_pharma_stock(symbol, sector_cache_file):
            continue

        headline, event_type = _fetch_stock_news_headline(symbol)
        if not event_type:
            continue

        results.append({
            "ticker":     symbol,
            "headline":   headline,
            "event_type": event_type,
            "source":     "alpaca_movers",
            "pct_change": pct,
        })
        log.info("  [movers] %s | +%.1f%% | %-20s | %s", symbol, pct, event_type, headline[:70])

        time.sleep(0.3)   # be polite to Finviz between per-ticker checks

    log.info("Big movers: checked %d candidate(s) (>= %.0f%% gain, >= $%.2f)",
              checked, min_pct, min_price)
    return results


def _fetch_stock_news_headline(ticker: str):
    """
    Fetch latest news headline for a ticker from Finviz quote page.
    Returns (headline, event_type) or ("", None).
    """
    try:
        r = requests.get(
            f"https://finviz.com/quote.ashx?t={ticker}",
            headers=HEADERS, timeout=10,
        )
        if not r.ok:
            return "", None

        soup  = BeautifulSoup(r.text, "html.parser")
        table = soup.find("table", id="news-table")
        if not table:
            return "", None

        for row in table.find_all("tr")[:5]:   # check first 5 news items
            for a in row.find_all("a"):
                text = a.get_text(strip=True)
                if len(text) > 20:
                    event = _classify_event(text.lower())
                    if event:
                        return text[:200], event
    except Exception:
        pass
    return "", None


# ══════════════════════════════════════════════════════════════════════════════
#  Source 2: FDA Official RSS Feed
# ══════════════════════════════════════════════════════════════════════════════

def _scan_fda_rss(sector_cache_file: str) -> List[Dict]:
    """
    Scan the FDA's official press release RSS feed for drug approvals.
    Tries to match company names in headlines to stock tickers via Finviz.
    """
    rss_url = (
        "https://www.fda.gov/about-fda/contact-fda/stay-informed/"
        "rss-feeds/press-releases/rss.xml"
    )
    try:
        r = requests.get(rss_url, headers=HEADERS, timeout=15)
        r.raise_for_status()
    except Exception as e:
        log.warning("FDA RSS fetch failed: %s", e)
        return []

    soup    = BeautifulSoup(r.text, "xml")
    results = []
    seen    = set()

    for item in soup.find_all("item"):
        title_tag = item.find("title")
        desc_tag  = item.find("description")
        title = title_tag.get_text(strip=True) if title_tag else ""
        desc  = desc_tag.get_text(strip=True)  if desc_tag  else ""
        full  = (title + " " + desc).lower()

        event_type = _classify_event(full)
        if not event_type:
            continue

        # Extract potential ticker symbols from the title (all-caps 2-6 char words)
        # FDA headlines rarely include tickers, but sometimes do
        raw_caps = re.findall(r'\b([A-Z]{2,6})\b', title + " " + desc)
        candidates = [t for t in raw_caps if t not in FDA_SKIP_WORDS]

        for ticker in candidates:
            if ticker in seen:
                continue
            if _is_pharma_stock(ticker, sector_cache_file):
                seen.add(ticker)
                results.append({
                    "ticker":     ticker,
                    "headline":   title[:200],
                    "event_type": event_type,
                    "source":     "fda_rss",
                })
                log.info("  [fda_rss] %s | %-20s | %s", ticker, event_type, title[:70])

    return results


# ══════════════════════════════════════════════════════════════════════════════
#  Helpers
# ══════════════════════════════════════════════════════════════════════════════

def _classify_event(text: str) -> str:
    """Classify catalyst type from lowercase text. Returns event string or ''."""
    for keywords, event_type in EVENT_MAP:
        if any(kw in text for kw in keywords):
            return event_type
    # Broad fallback: any catalyst keyword at all
    if any(kw in text for kw in CATALYST_KEYWORDS):
        return "CATALYST_EVENT"
    return ""


def _is_pharma_stock(ticker: str, sector_cache_file: str = "sector_cache.json") -> bool:
    """
    Check if ticker is in pharma/biotech sector by scraping Finviz quote page.
    Result is cached persistently in sector_cache.json.
    """
    cache = _load_json(sector_cache_file)

    if ticker in cache:
        return cache[ticker]

    try:
        r = requests.get(
            f"https://finviz.com/quote.ashx?t={ticker}",
            headers=HEADERS, timeout=10,
        )
        if not r.ok:
            cache[ticker] = False
            _save_json(sector_cache_file, cache)
            return False

        page_text = r.text.lower()
        is_pharma = any(ind in page_text for ind in PHARMA_INDUSTRIES)

        cache[ticker] = is_pharma
        _save_json(sector_cache_file, cache)

        if is_pharma:
            log.debug("  Sector check %s: pharma/biotech CONFIRMED", ticker)
        return is_pharma

    except Exception as e:
        log.debug("Sector check %s failed: %s", ticker, e)
        return False


def _load_json(path: str) -> dict:
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _save_json(path: str, data: dict):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        log.error("JSON save failed (%s): %s", path, e)
