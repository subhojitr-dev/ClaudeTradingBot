# FILES.md — Complete File Reference
## Trading Bot System — All Files, Paths & Descriptions

---

## Directory Structure

```
C:\Users\subho\tradingbot\
│
├── notifier.py                          ← Shared email utility
├── README.md                            ← System documentation & strategy guide
├── FILES.md                             ← This file
│
├── trailing_stop\
│   ├── config.py                        ← Strategy parameters & credentials
│   ├── bot.py                           ← Main trailing stop engine
│   ├── pharma_catalyst.py               ← FDA/Finviz pharma scanner
│   ├── trailing_stop_state.json         ← Live position state (auto-generated)
│   ├── pharma_catalyst_cache.json       ← Daily pharma scan cache (auto-generated)
│   ├── sector_cache.json                ← Finviz sector lookup cache (auto-generated)
│   └── run_trailing.bat                 ← Windows launcher script
├── sell_all.py                              ← Emergency liquidation (one-time use)
│
├── copytrade\
│   ├── config.py                        ← Politician list & trade settings
│   ├── bot.py                           ← Main copy-trade engine
│   ├── alpaca_client.py                 ← Alpaca REST API wrapper
│   ├── capitol_trades_scraper.py        ← Capitol Trades website scraper
│   ├── trade_tracker.py                 ← Seen-trade deduplication store
│   ├── option_resolver.py               ← Maps option descriptions → OCC symbols
│   ├── dashboard.py                     ← Terminal P&L dashboard
│   ├── seen_trades.json                 ← Already-processed trade IDs (auto-generated)
│   ├── run_bot.bat                      ← Windows launcher script
│   └── SETUP_PROMPT.md                  ← AI session bootstrap instructions
│
├── flywheel\
│   ├── config.py                        ← Wheel strategy parameters & credentials
│   ├── bot.py                           ← Main wheel options engine
│   ├── alpaca_client.py                 ← Options-aware Alpaca API wrapper
│   ├── option_selector.py               ← Finds optimal CSP / CC contracts
│   ├── state_manager.py                 ← Wheel state machine persistence
│   ├── report.py                        ← Daily 4 PM P&L email report
│   ├── wheel_state.json                 ← Live wheel positions (auto-generated)
│   ├── run_flywheel.bat                 ← Windows launcher (main bot)
│   └── run_report.bat                   ← Windows launcher (report only)
│
├── daily_topup\
│   ├── topup_check.py                   ← Cash top-up monitor
│   └── run_topup.bat                    ← Windows launcher script
│
├── strangle\
│   ├── config.py                        ← Strategy parameters & credentials
    ├── bot.py                           ← Main engine (monitor + scan, every 2 hours)
    ├── earnings_scanner.py              ← yfinance earnings dates + historical move check
    ├── iv_checker.py                    ← Rolling IV percentile filter (local JSON cache)
    ├── option_selector.py               ← Finds ~0.30 delta, ~90 DTE call + put via Alpaca
    ├── state_manager.py                 ← Persists OPEN / CALL_SOLD / CLOSED states
    ├── alpaca_client.py                 ← Options-aware Alpaca API wrapper
    ├── notifier.py                      ← Email alerts (open, combined close, IV skip)
    ├── dashboard.py                     ← Terminal P&L view (run manually)
    ├── strangle_state.json              ← Live strangle positions (auto-generated)
    ├── iv_history.json                  ← Rolling IV observations per symbol (auto-generated)
│   └── run_strangle.bat                 ← Windows launcher (every 2 hours via Task Scheduler)
│
└── ironcondor\
    ├── config.py                        ← Strategy parameters (SPY, deltas, DTE, credit threshold)
    ├── bot.py                           ← Main engine (open / monitor / adjust / close)
    ├── support_resistance.py            ← SPY S/R levels from swing highs/lows + MAs + round numbers
    ├── option_selector.py               ← Selects all 4 legs: put spread + call spread
    ├── state_manager.py                 ← Persists OPEN / ADJUSTING / CLOSED condor state
    ├── alpaca_client.py                 ← Alpaca options API wrapper (account PA34EFPV3B80)
    ├── notifier.py                      ← Email alerts (opened, adjusted, closed)
    ├── dashboard.py                     ← Live terminal view with Greeks and P&L per leg
    ├── ironcondor_state.json            ← Live condor state (auto-generated)
    └── run_ironcondor.bat               ← Windows launcher (every 30 min via Task Scheduler)

reports\
├── daily_report.py                      ← Consolidated trade ledger across all 5 strategies
├── run_daily_report.bat                 ← Windows launcher (daily at 4:05 PM via Task Scheduler)
├── trade_ledger.json                    ← Canonical ledger store (auto-generated, gitignored)
├── trade_ledger.csv                     ← Flattened export, Excel-openable (auto-generated, gitignored)
└── dashboard.html                       ← Local static snapshot (auto-generated, gitignored)
```

---

## Root Level Files

---

### `C:\Users\subho\tradingbot\notifier.py`

**Purpose:** Shared email notification utility used by the trailing stop, copy trade, and flywheel bots. Centralises all Gmail SMTP logic in one place so no bot duplicates email code. (The strangle bot has its own `strangle/notifier.py` since it uses a different Alpaca account and subject prefix.)

**Key Functions:**

| Function | What it does |
|---|---|
| `send_email(subject, body, ...)` | Core SMTP sender — connects to Gmail port 587, strips spaces from App Password, sends plain-text email |
| `notify_copy_trade(symbol, qty, price, politician, action)` | Sends alert when a politician's trade is copied |
| `notify_ladder_in(symbol, qty, price, drop_pct)` | Sends alert when ladder-in buy is triggered (stock dropped 20%) |
| `notify_stop_loss(symbol, qty, price, loss_pct)` | Sends alert when stop-loss is triggered (stock dropped 10%) |
| `notify_pharma_add(symbols)` | Sends alert listing pharma stocks added to the watch list that morning |
| `notify_csp_opened(symbol, contract, premium, expiry)` | Sends alert when a new cash-secured put is sold |
| `notify_option_event(event_type, symbol, ...)` | Generic option event alert (assignment, early close, roll, called away) |

**Design Notes:**
- Strips spaces from SMTP password before login (`password.replace(" ", "")`) — Gmail App Passwords are displayed with spaces but must be submitted without
- Uses `smtplib.SMTP` with `starttls()` — standard Gmail port 587 TLS
- All bots import this via `sys.path.insert(0, parent_dir)` so it can live at the root

---

### `C:\Users\subho\tradingbot\README.md`

**Purpose:** Comprehensive human-readable documentation of the entire trading bot system. Intended as the primary reference for understanding what the system does, how each strategy works, and how to configure it.

**Contents:**
- Explanation of SETUP_PROMPT.md and how it is used
- System overview ASCII diagram showing all four bots and their accounts
- Two-account structure table (trailing stop account vs. options account)
- Trailing stop strategy flow diagram with detailed rules
- Worked example: NVDA trade from entry through ladder-in through trailing stop exit
- Wheel strategy state machine diagram (IDLE → CSP → CC → IDLE)
- Full AVGO wheel cycle worked example showing all 5 possible outcomes
- Copy trading bot explanation and Capitol Trades data flow (Pelosi + McCaul only)
- Pharma catalyst scanner pipeline diagram
- Strangle strategy entry criteria, exit rules, and state machine
- Complete email notifications reference table
- Schedules table showing when each bot/task runs
- Configuration parameter reference for all four strategies

---

### `C:\Users\subho\tradingbot\sell_all.py`

**Purpose:** One-time emergency liquidation script. Sells ALL open positions and cancels all pending orders across BOTH Alpaca paper accounts (PA31HKOPMG4M and PA34EFPV3B80) in a single run. Used on 2026-06-16 to clear the slate before a fresh start.

**How to run:**
```cmd
cd C:\Users\subho\tradingbot
python sell_all.py
```

**What it does:**
1. Fetches all open positions in each account and prints them with current P&L
2. Cancels any pending orders
3. Calls the Alpaca bulk-close endpoint (`DELETE /v2/positions`) — all positions sold at market
4. Prints a summary and the dashboard URL to verify fills

**Design Notes:**
- Uses both accounts' API keys hardcoded directly (not importing from sub-configs) so it works standalone without `cd`-ing into a subfolder
- Paper trading only — no real money at risk

---

### `C:\Users\subho\tradingbot\FILES.md`

**Purpose:** This file. A complete catalogue of every file in the system with its full path and a detailed description of what it does, why it exists, and how it relates to other files.

---

## Trailing Stop Strategy

### `C:\Users\subho\tradingbot\trailing_stop\config.py`

**Purpose:** Single source of truth for all trailing stop strategy parameters. Every number that controls trade behaviour lives here so changes can be made without touching bot logic.

**Key Settings:**

| Parameter | Value | Meaning |
|---|---|---|
| `ALPACA_API_KEY` | PKMQDKH... | Account PA31HKOPMG4M credentials |
| `WATCHED_STOCKS` | 15 tickers | Core portfolio: tech + Pelosi top-5 |
| `INITIAL_QTY` | 10 | Shares bought on first entry |
| `LADDER_QTY` | 10 | Additional shares bought on ladder-in |
| `STOP_LOSS_PCT` | 0.10 | Sell all if price drops 10% from entry |
| `TRAIL_TRIGGER_PCT` | 0.10 | Start trailing when up 10% |
| `TRAIL_STOP_PCT` | 0.05 | Trail 5% below peak price |
| `LADDER_IN_DROP_PCT` | 0.20 | Buy more if down 20% from entry |
| `MIN_CASH_BALANCE` | $10,000 | Never buy if cash would drop below this |
| `PHARMA_SCAN_ENABLED` | True | Run morning pharma scanner |
| `PHARMA_MAX_STOCKS` | 3 | Max new pharma stocks to add per day |
| `PHARMA_SKIP_EVENTS` | FDA_REJECTION | Do not buy stocks with rejection news |
| `POLL_INTERVAL` | 1800 | 30 minutes between price checks |
| `NOTIFY_EMAIL` | subhojitr@... | Destination for all alert emails |
| `SMTP_PASSWORD` | ioyx jwsd... | Gmail App Password |

---

### `C:\Users\subho\tradingbot\trailing_stop\bot.py`

**Purpose:** Main engine for the trailing stop + ladder strategy. Runs every 30 minutes via Windows Task Scheduler. Manages the full position lifecycle for all watched stocks.

**Execution Flow:**
1. **Market check** — calls Alpaca clock API; exits immediately if market is closed
2. **Pharma scan** (Rule 5) — calls `pharma_catalyst.scan_today()`; any new biotech stocks with FDA/trial events are appended to the active watch list and an email is sent
3. **State load** — reads `trailing_stop_state.json` from disk; initialises state for any new symbols
4. **Position sync** — fetches current Alpaca positions; updates `current_qty` in state for each symbol
5. **Entry check** — for any symbol with no position, buys `INITIAL_QTY` shares if cash allows
6. **Rule evaluation loop** — for each held symbol:
   - Fetches current price
   - Updates `peak_price` if new high
   - **Rule 1 (Stop Loss):** if `price < entry_price * (1 - 0.10)` → sell all, email alert
   - **Rule 2 (Trailing Stop):** if up ≥ 10% AND price falls 5% from peak → sell all, email alert
   - **Rule 3 (Ladder In):** if `price < entry_price * (1 - 0.20)` AND not yet laddered → buy 10 more shares, email alert
7. **State save** — writes updated state back to JSON

**State File Structure (per symbol):**
```json
{
  "NVDA": {
    "entry_price": 120.00,
    "current_qty": 20,
    "peak_price": 138.00,
    "trailing_active": true,
    "laddered_in": true,
    "entry_date": "2025-01-15"
  }
}
```

---

### `C:\Users\subho\tradingbot\trailing_stop\pharma_catalyst.py`

**Purpose:** Morning scanner that identifies pharmaceutical and biotech stocks with significant FDA/clinical trial events happening that day. Called once per day by `bot.py` and results are cached to avoid repeated scraping during 30-min polls.

**Data Sources** (rewritten 2026-08-03 -- see `issues_log.md`-style note below):
1. **Alpaca Big Movers Screener** (`/v1beta1/screener/stocks/movers`) — today's biggest % gainers market-wide, no watchlist needed. Filtered to plain tickers, price ≥ `MOVERS_MIN_PRICE`, gain ≥ `MOVERS_MIN_PCT_CHANGE`. Each surviving candidate is checked against its own Finviz quote page (`finviz.com/quote.ashx?t=TICKER`) for pharma/biotech sector + a classifiable catalyst headline.
2. **FDA Press Release RSS** (`fda.gov/.../press-releases/rss.xml`) — official FDA announcements

> **Why it changed:** the original sources were Finviz's general news page and its biotech screener page, scraped directly. Both had been silently broken since the bot's first run (confirmed via logs going back to 2026-07-21) — Finviz redesigned `news.ashx` to no longer tag headlines with a ticker at all, and the screener's results table is now client-side rendered with its CSV export fallback paywalled behind Finviz Elite. The FDA RSS URL had also moved (`fda-press-releases` → `press-releases`). The per-ticker Finviz quote page was confirmed still working, so the new design leans on that instead of the two broken wide-scan pages.

**Keyword Detection (`_classify_event`):**

| Keyword Match | Event Type |
|---|---|
| "fda approv", "nda approv", "bla approv" | FDA_APPROVAL |
| "pdufa", "adcom", "advisory committee" | FDA_DECISION |
| "phase 3", "phase iii", "top-line results", "pivotal" | TRIAL_RESULTS |
| "nda submitted", "bla submitted", "marketing application" | REGULATORY_FILING |
| "breakthrough therapy", "fast track", "orphan drug" | FDA_DESIGNATION |
| "complete response letter", "crl", "fda reject" | FDA_REJECTION |
| "fda", "clinical", "catalyst", "data readout" | CATALYST_EVENT |

**Sector Verification (`_is_pharma_stock`):**
- Fetches Finviz quote page for the ticker
- Looks for sector keywords: "biotech", "pharmaceut", "drug", "biolog", "therapeut", "genomic", "medtech"
- Caches result in `sector_cache.json` permanently — avoids repeated HTTP requests for the same ticker

**Caching:**
- `pharma_catalyst_cache.json` stores results keyed by today's date (YYYY-MM-DD)
- On subsequent 30-min bot runs, cached results are returned immediately
- Cache expires automatically the next day when the date key changes

**Output:**
```python
[
  {"ticker": "MRNA", "event": "TRIAL_RESULTS", "headline": "Moderna Phase 3 top-line results..."},
  {"ticker": "BIIB", "event": "FDA_APPROVAL",  "headline": "FDA approves Biogen..."}
]
```

---

### `C:\Users\subho\tradingbot\trailing_stop\trailing_stop_state.json`

**Purpose:** Auto-generated runtime file. Persists the position state for every watched stock across bot restarts. Without this file the bot would lose track of entry prices, peak prices, and whether ladder-in has already occurred.

**Auto-generated:** Created on first run; updated after every poll cycle. Do not edit manually unless resetting a position.

---

### `C:\Users\subho\tradingbot\trailing_stop\pharma_catalyst_cache.json`

**Purpose:** Auto-generated cache file. Stores the result of the day's pharma scan keyed by date. Prevents the bot from re-scraping Finviz and FDA RSS on every 30-minute poll.

**Format:**
```json
{
  "2025-05-29": [
    {"ticker": "MRNA", "event": "TRIAL_RESULTS", "headline": "..."}
  ]
}
```

---

### `C:\Users\subho\tradingbot\trailing_stop\sector_cache.json`

**Purpose:** Auto-generated permanent cache for Finviz sector lookups. Once a ticker's sector is confirmed as pharma/biotech (or not), the result is stored here indefinitely. Prevents repeated HTTP calls for the same tickers across days.

---

### `C:\Users\subho\tradingbot\trailing_stop\run_trailing.bat`

**Purpose:** Windows batch file that launches the trailing stop bot. Called by Windows Task Scheduler every 30 minutes.

**Contents:**
```bat
@echo off
cd /d C:\Users\subho\tradingbot\trailing_stop
C:\Users\subho\AppData\Local\Python\bin\python3.14.exe bot.py >> logs\trailing.log 2>&1
```

---

## Copy Trade Strategy

### `C:\Users\subho\tradingbot\copytrade\SETUP_PROMPT.md`

**Purpose:** A special markdown file used to "bootstrap" an AI assistant (like Claude) into understanding the full context of the copy-trade system instantly. When you start a new chat session and paste the contents of this file in as your first message, the AI immediately knows all the file paths, API credentials, strategy rules, and system architecture — without needing lengthy re-explanation.

**How it works:**
- Contains a complete system description: what each file does, what the strategy is, account credentials, edge cases
- Written in first-person from the perspective of the developer ("My trading bot monitors Capitol Trades...")
- Acts as a compressed memory — the AI can then make code changes, debug issues, or add features with full context

**Why it exists:**
- AI chat sessions have limited memory — they forget everything between sessions
- Manually re-explaining the whole system each time would take 10-15 minutes
- Pasting this file restores full context in seconds

**This is NOT executable code** — it is purely a human/AI communication aid.

---

### `C:\Users\subho\tradingbot\copytrade\config.py`

**Purpose:** Configuration for the copy-trade bot. Defines which politicians to monitor, trading limits, and credentials.

**Key Settings:**

| Parameter | Value | Meaning |
|---|---|---|
| `POLITICIANS` | List of 2 | Nancy Pelosi, Michael McCaul |
| `MAX_COPY_POSITIONS` | 10 | Never hold more than 10 copy-trade positions |
| `INITIAL_QTY` | 5 | Shares to buy when copying a trade |
| `ALPACA_API_KEY` | PKMQDKH... | Same account as trailing stop (PA31HKOPMG4M) |

> Ro Khanna was removed 2026-06-16 — reduced to 2 highest-conviction politicians.

**Politicians list structure:**
```python
POLITICIANS = [
    {"name": "Nancy Pelosi",   "ct_id": "P000197"},
    {"name": "Michael McCaul", "ct_id": "M001157"},
]
```

The `ct_id` is the Capitol Trades URL identifier for each politician's trade disclosure page.

---

### `C:\Users\subho\tradingbot\copytrade\bot.py`

**Purpose:** Main engine for the copy-trade strategy. Runs every 30 minutes. Monitors 2 politicians' Capitol Trades pages (Pelosi, McCaul) and places buy orders when new stock purchases are disclosed.

**Execution Flow:**
1. **Market check** — exits if market is closed
2. **Load seen trades** — reads `seen_trades.json` to know which disclosures were already processed
3. **First-run guard** — if no seen trades exist yet, marks ALL current trades as seen without ordering (prevents buying months of historical trades on first launch)
4. **For each politician:**
   - Scrapes their Capitol Trades page using `capitol_trades_scraper.py`
   - Finds trades not in `seen_trades.json`
   - Skips if it's a Sale or Option trade
   - Checks `MAX_COPY_POSITIONS` cap — stops if already at limit
   - Checks if already holding this ticker — skips if yes
   - Checks if another politician already triggered this ticker this run (`ordered_this_run` set)
   - Places market buy order via Alpaca
   - Sends email notification
   - Marks trade as seen
5. **Save seen trades** — writes updated `seen_trades.json`

---

### `C:\Users\subho\tradingbot\copytrade\alpaca_client.py`

**Purpose:** Thin wrapper around the Alpaca REST API v2 for stock trading. Used exclusively by the copy-trade bot.

**Key Functions:**

| Function | Description |
|---|---|
| `get_account()` | Returns account info including cash balance and buying power |
| `get_positions()` | Returns all current open positions |
| `get_position(symbol)` | Returns position for a specific symbol |
| `place_market_order(symbol, qty, side)` | Places a market buy or sell order |
| `get_clock()` | Returns market open/closed status |
| `get_bars(symbol, timeframe, limit)` | Returns OHLCV price bars |

---

### `C:\Users\subho\tradingbot\copytrade\capitol_trades_scraper.py`

**Purpose:** Scrapes the Capitol Trades website to extract stock trade disclosures for politicians. Capitol Trades aggregates congressional stock trading disclosures filed with the House and Senate STOCK Act.

**Two scraping strategies (tried in order):**
1. **Requests + BeautifulSoup** — fast, lightweight HTTP scraping for static HTML
2. **Playwright headless Chromium** — used as fallback when Capitol Trades serves JavaScript-rendered content that BeautifulSoup cannot parse

**Key Function:**
```python
fetch_politician_trades(ct_id, politician_name) → list[dict]
```

**Output per trade:**
```python
{
  "politician": "Nancy Pelosi",
  "trade_id":   "abc123",
  "ticker":     "NVDA",
  "action":     "Purchase",
  "amount":     "$1,001 - $15,000",
  "date":       "2025-05-15"
}
```

**Why Playwright is needed:**
- Capitol Trades uses React/Next.js — on some requests the table is rendered client-side
- Playwright launches a real (headless) browser, waits for the JavaScript to execute, then reads the DOM

---

### `C:\Users\subho\tradingbot\copytrade\trade_tracker.py`

**Purpose:** Manages the `seen_trades.json` file. Provides clean load/save/check/mark functions so `bot.py` doesn't need to handle raw JSON file I/O.

**Key Functions:**

| Function | Description |
|---|---|
| `load_seen()` | Reads seen_trades.json, returns set of trade IDs |
| `save_seen(seen_set)` | Writes set back to JSON file |
| `is_seen(trade_id, seen_set)` | Returns True if trade was already processed |
| `mark_seen(trade_id, seen_set)` | Adds trade ID to the set |

---

### `C:\Users\subho\tradingbot\copytrade\option_resolver.py`

**Purpose:** Translates human-readable option descriptions from Capitol Trades into OCC option contract symbols that Alpaca can process. Used when a politician's disclosure describes an option trade rather than a stock trade.

**Example:**
- Input: `"Call Option, NVDA, Strike $120, Exp Dec 2025"`
- Output: `"NVDA251219C00120000"` (OCC format)

**Note:** The copy-trade bot currently skips option trades (buys stock equivalents only), but this resolver exists for future enhancement.

---

### `C:\Users\subho\tradingbot\copytrade\dashboard.py`

**Purpose:** Prints a live terminal dashboard showing all copy-trade positions, their current P&L, and which politician triggered each position.

**Output format (terminal table):**
```
SYMBOL   QTY   ENTRY    NOW      P&L$     P&L%    POLITICIAN
NVDA     5     $120.50  $138.20  +$88.50  +7.3%   Nancy Pelosi
AAPL     5     $195.00  $210.00  +$75.00  +7.7%   Michael McCaul
```

Run manually: `python dashboard.py`

---

### `C:\Users\subho\tradingbot\copytrade\seen_trades.json`

**Purpose:** Auto-generated deduplication store. Saves the set of Capitol Trades disclosure IDs that have already been processed. Prevents the bot from re-buying the same trade on every 30-minute run.

**Format:**
```json
["trade_id_abc123", "trade_id_def456", "trade_id_ghi789"]
```

---

### `C:\Users\subho\tradingbot\copytrade\run_bot.bat`

**Purpose:** Windows batch launcher for the copy-trade bot. Called by Windows Task Scheduler every 30 minutes.

```bat
@echo off
cd /d C:\Users\subho\tradingbot\copytrade
C:\Users\subho\AppData\Local\Python\bin\python3.14.exe bot.py >> logs\copytrade.log 2>&1
```

---

## Flywheel (Options Wheel) Strategy

### `C:\Users\subho\tradingbot\flywheel\config.py`

**Purpose:** Configuration for the options wheel strategy. Uses the second paper trading account (PA34EFPV3B80) with its own separate API keys.

**Key Settings:**

| Parameter | Value | Meaning |
|---|---|---|
| `ALPACA_API_KEY` | PK5QNIDGKGVA2QEAQKYVSAPFV4 | Second account credentials |
| `WHEEL_STOCKS` | AVGO, COHR, NBIS, GLW | Stocks to run the wheel on |
| `CSP_STRIKE_DISCOUNT` | 0.20 | Sell put 20% below current price |
| `CSP_MAX_DELTA` | 0.25 | Never sell put with delta > 0.25 |
| `CSP_MIN_DTE` | 14 | Minimum days-to-expiry for put |
| `CSP_MAX_DTE` | 28 | Maximum days-to-expiry for put |
| `CC_STRIKE_PREMIUM` | 0.10 | Sell call 10% above cost basis |
| `CC_MAX_DELTA` | 0.25 | Never sell call with delta > 0.25 |
| `CC_MIN_DTE` | 14 | Minimum days-to-expiry for call |
| `CC_MAX_DTE` | 28 | Maximum days-to-expiry for call |
| `EARLY_CLOSE_PROFIT_PCT` | 0.70 | Buy back option when 70% of premium captured |
| `ROLL_TRIGGER_PCT` | 0.80 | Roll put up when it has lost 80% of value (ITM risk) |
| `ROLL_MIN_NET_CREDIT` | 0.10 | Only roll if net credit is at least $0.10 |

**Delta Rule Explained:**
- `CSP_MAX_DELTA = 0.25` means the put's |delta| must be below 0.25 — less than 25% probability of assignment
- `CC_MAX_DELTA = 0.25` means the call's delta must be below 0.25 — less than 25% probability of being called away

---

### `C:\Users\subho\tradingbot\flywheel\alpaca_client.py`

**Purpose:** Options-aware Alpaca API wrapper. Handles both stock and options endpoints. Used exclusively by the flywheel bot.

**Key Functions:**

| Function | Description |
|---|---|
| `get_option_contracts(symbol, exp_gte, exp_lte, type, strike_gte, strike_lte)` | Queries `/v2/options/contracts` to find available contracts |
| `get_option_snapshots(symbols_list)` | Fetches real-time quotes + Greeks for a list of OCC symbols |
| `get_option_snapshot(occ_symbol)` | Single contract real-time quote + Greeks |
| `get_mid_price(occ_symbol)` | Returns (bid + ask) / 2 |
| `get_bid_price(occ_symbol)` | Returns best bid (used for realistic sell fills) |
| `get_ask_price(occ_symbol)` | Returns best ask |
| `get_delta(occ_symbol)` | Returns absolute value of delta (handles negative put deltas) |
| `get_iv(occ_symbol)` | Returns implied volatility |
| `place_option_order(occ_symbol, qty, side, order_type, limit_price)` | Places option order with `asset_class: "us_option"` |
| `get_positions()` | Returns all open positions (stocks + options) |
| `get_account()` | Returns cash balance and buying power |

**Options Data Endpoint:** `https://data.alpaca.markets/v2/options/snapshots` with `feed=indicative` for paper trading

---

### `C:\Users\subho\tradingbot\flywheel\option_selector.py`

**Purpose:** Finds the optimal option contract to sell for each wheel stage. Applies delta filtering, DTE filtering, and strike selection logic.

**Key Functions:**

**`find_csp_contract(symbol, current_price, strike_discount, max_delta, min_dte, max_dte)`**
- Target strike = `current_price * (1 - strike_discount)` — 20% OTM put
- Fetches all put contracts in the DTE window
- Filters out any contract with `|delta| >= max_delta`
- Picks the contract closest to target strike with sufficient premium
- Returns OCC symbol string

**`find_cc_contract(symbol, current_price, strike_premium, max_delta, min_dte, max_dte)`**
- Target strike = `current_price * (1 + strike_premium)` — 10% OTM call
- Searches up to `current_price * 1.35` to find a call with delta < 0.25
- Returns OCC symbol string

**`find_roll_up_contract(symbol, current_symbol, current_strike, current_expiry, min_net_credit, max_delta)`**
- Must use same expiry date as current contract
- New strike must be higher than current strike
- Net credit (new premium - buyback cost) must be >= `min_net_credit`
- New put must still have delta < max_delta
- Returns OCC symbol or None if no valid roll exists

**`_pick_best_contract(candidates, target_strike, max_delta, price_fn)`**
- Scores each contract by `abs(strike - target_strike)`
- Filters any with delta >= max_delta
- Returns the one with lowest score (closest to target)

---

### `C:\Users\subho\tradingbot\flywheel\state_manager.py`

**Purpose:** Manages the wheel strategy state machine. Tracks what stage each symbol is in (IDLE, CSP, CC), which contract is open, and accumulated premium collected.

**Stages:**

| Stage | Meaning |
|---|---|
| `IDLE` | No position. Bot will sell a cash-secured put next run. |
| `CSP` | Short put is open. Monitoring for expiry, assignment, early close, or roll. |
| `CC` | Assigned (hold stock). Short call is open. Monitoring for called-away or early close. |

**State per symbol:**
```python
{
  "AVGO": {
    "stage": "CC",
    "contract_symbol": "AVGO250620P00160000",
    "contract_expiry": "2025-06-20",
    "contract_strike": 160.0,
    "contract_type": "put",
    "entry_premium": 3.20,
    "stock_qty": 100,
    "stock_avg_cost": 162.50,
    "total_premium_collected": 8.45,
    "cycle_count": 2,
    "history": [...]
  }
}
```

**Key Methods:**

| Method | Triggered when |
|---|---|
| `open_csp(symbol, contract, premium, expiry, strike)` | New put sold — stage → CSP |
| `csp_expired_worthless(symbol)` | Put expired, kept full premium — stage → IDLE |
| `csp_closed_early(symbol, close_price)` | Bought back at 70% profit — stage → IDLE |
| `csp_assigned(symbol, stock_qty, avg_cost)` | Put exercised, now own shares — stage → CC |
| `open_cc(symbol, contract, premium, expiry, strike)` | New covered call sold — stays in CC |
| `cc_expired_worthless(symbol)` | Call expired, kept premium, still own shares — stays CC, sell new call |
| `cc_closed_early(symbol, close_price)` | Call bought back at 70% profit — stays CC, sell new call |
| `cc_called_away(symbol, sale_price)` | Shares sold at strike — stage → IDLE |

---

### `C:\Users\subho\tradingbot\flywheel\bot.py`

**Purpose:** Main engine for the options wheel strategy. Runs every 30 minutes. Manages the full state machine for each of the four wheel stocks.

**Execution Flow:**
1. **Market check** — exits if market closed or within 15 min of close (avoid last-minute fills)
2. **Load wheel state** from `wheel_state.json`
3. **Sync positions** — reconciles Alpaca positions with state (detects assignments, expirations)
4. **For each symbol:**
   - `handle_idle()` — sells a new CSP if cash available and valid contract found
   - `handle_csp()` — checks for expiry/assignment/70% profit/roll trigger
   - `handle_cc()` — checks for called-away/70% profit/need to sell new call
5. **Save wheel state**

**`handle_idle(symbol)`:**
- Checks cash >= strike × 100 (collateral requirement)
- Finds contract via `option_selector.find_csp_contract()`
- Places sell-to-open order at bid price
- Updates state to CSP stage
- Sends email: "New CSP opened on AVGO"

**`handle_csp(symbol)`:**
- If option position gone AND stock position appeared → `csp_assigned()`, then immediately sell CC
- If option position gone AND no stock → `csp_expired_worthless()`, cycle back to IDLE
- If current mid price ≤ entry_premium × 0.30 → early close (kept 70%) → `csp_closed_early()`
- If current mid price ≥ entry_premium × ROLL_TRIGGER_PCT → attempt roll up

**`handle_cc(symbol)`:**
- If stock position gone → `cc_called_away()`, back to IDLE
- If option position gone (expired worthless) → `cc_expired_worthless()`, sell new CC
- If current mid price ≤ entry_premium × 0.30 → early close → `cc_closed_early()`, sell new CC

---

### `C:\Users\subho\tradingbot\flywheel\report.py`

**Purpose:** Generates and emails a daily P&L report at 4 PM. Summarises all wheel positions, premium collected, and unrealised gains/losses.

**Email Contents:**

**Table 1 — Options Positions:**
```
SYM    STAGE  CONTRACT              ENTRY  NOW    P&L$    P&L%   EXPIRY     COLLECTED
AVGO   CC     AVGO250620C00200000   3.20   0.95   +2.25   +70%   Jun 20     $845
COHR   CSP    COHR250613P00060000   1.10   0.45   +0.65   +59%   Jun 13     $220
```

**Table 2 — Stock Positions (assigned shares):**
```
SYM    QTY    AVG COST   NOW       P&L$      P&L%
AVGO   100    $162.50    $178.00   +$1,550   +9.5%
```

**Table 3 — Summary:**
- Total premium collected all-time
- Total unrealised stock P&L
- Combined return

Run via `run_report.bat` scheduled at 4 PM daily.

---

### `C:\Users\subho\tradingbot\flywheel\wheel_state.json`

**Purpose:** Auto-generated runtime file. Persists the wheel state machine for all four stocks. Without this file the bot would lose track of open contracts, assignment status, and accumulated premium.

---

### `C:\Users\subho\tradingbot\flywheel\run_flywheel.bat`

**Purpose:** Windows batch launcher for the flywheel main bot. Called every 30 minutes by Task Scheduler.

```bat
@echo off
cd /d C:\Users\subho\tradingbot\flywheel
C:\Users\subho\AppData\Local\Python\bin\python3.14.exe bot.py >> logs\flywheel.log 2>&1
```

---

### `C:\Users\subho\tradingbot\flywheel\run_report.bat`

**Purpose:** Windows batch launcher for the 4 PM daily P&L report email. Scheduled separately from the main bot — runs once per trading day at 4:00 PM.

```bat
@echo off
cd /d C:\Users\subho\tradingbot\flywheel
C:\Users\subho\AppData\Local\Python\bin\python3.14.exe report.py >> logs\report.log 2>&1
```

---

## Daily Top-Up

### `C:\Users\subho\tradingbot\daily_topup\topup_check.py`

**Purpose:** Monitors cash balance in both paper accounts and sends an email alert if either falls below a threshold. Useful when the wheel strategy ties up large amounts of cash as collateral and the trailing stop bot might be unable to buy new entries.

**Logic:**
- Checks account PA31HKOPMG4M cash balance — alerts if below `MIN_CASH_BALANCE` ($10,000)
- Checks account PA34EFPV3B80 cash balance — alerts if below `FLYWHEEL_MIN_CASH` ($20,000)
- No action taken — alert only (you top up manually in Alpaca paper dashboard)

---

### `C:\Users\subho\tradingbot\daily_topup\run_topup.bat`

**Purpose:** Windows batch launcher for the daily cash check. Typically scheduled to run once each morning before market open.

---

## Consolidated Trade Ledger (`reports\`)

### `C:\Users\subho\tradingbot\reports\daily_report.py`

**Purpose:** Builds one row per trade across all 5 strategies, read-only against each bot's own state JSON (never modifies a bot's state) plus live Alpaca prices. Added 2026-08-02.

**Behaviour:**
- A trade still open gets its current price / gain $ / gain % / `last_updated` overwritten every run.
- Once a trade is detected closed, its row is written one final time (frozen values, `closed_at` set) and never touched again.
- Closed trades older than `RETENTION_DAYS` (60) are dropped entirely on the next run; open trades are never pruned regardless of age.
- Credentials are hardcoded directly (not imported from each bot's `config.py`) to avoid importing multiple same-named `config`/`alpaca_client` modules from different folders — same reason `sell_all.py` hardcodes them.

**Per-strategy row logic:**
- **Trailing Stop:** one row per symbol (state file key) — open while `status == "active"`, closed using the earliest `stop_loss_sell` order once sold.
- **Copy Trade:** one row per symbol traded via `trades_tracker.json`, using Alpaca's own `unrealized_pl`/`unrealized_plpc` directly. Since Copy Trade shares an account with Trailing Stop, a shared symbol's position may reflect both bots combined (noted in the row). The bot itself never sells, so a row is only marked closed if a previously-open position disappears from Alpaca (closed outside the bot — manual sell or `sell_all.py`).
- **Flywheel:** walks each symbol's `history` list to reconstruct past option-leg and stock-lot trades (pairing `sell_put`/`sell_call` with the matching close event), plus the currently open contract and/or stock lot from the top-level state fields.
- **Strangle / Iron Condor:** both already separate `active` vs `history` in their own state files — active positions get live-priced (option mid or 4-leg cost-to-close), closed trades use their already-recorded `net_pnl`.

**Outputs (this folder, all gitignored):**
- `trade_ledger.json` — canonical store, read back in on the next run
- `trade_ledger.csv` — flattened export, Excel-openable
- `dashboard.html` — local static snapshot for quick viewing

**Feeds:** the Trade Results tab on `trading-analytics-hub.vercel.app`, via `trading_analytics_hub/scripts/sync.mjs` uploading this JSON to Vercel Blob.

---

### `C:\Users\subho\tradingbot\reports\run_daily_report.bat`

**Purpose:** Windows batch launcher for the daily ledger report. Scheduled task `TradeLedgerReport`, weekdays at 4:05 PM — 5 minutes after the other 4:00 PM reports, so all state files have settled first.

---

## Strangle Strategy (Bi-Directional Earnings Plays)

### `C:\Users\subho\tradingbot\strangle\config.py`

**Purpose:** All parameters for the strangle strategy.

**Key Settings:**

| Parameter | Value | Meaning |
|---|---|---|
| `ALPACA_API_KEY` | PK5QNID... | Options account PA34EFPV3B80 |
| `WATCHED_STOCKS` | 15 tickers | Liquid names to scan for earnings |
| `EARNINGS_MIN_DAYS` | 14 | Earnings must be at least 2 weeks out |
| `EARNINGS_MAX_DAYS` | 21 | Earnings must be at most 3 weeks out |
| `IV_PERCENTILE_THRESHOLD` | 50 | Only enter if current IV ≤ 50th pct of own history |
| `IV_HISTORY_DAYS` | 60 | Days of IV observations to retain per symbol |
| `LOOK_BACK_EARNINGS` | 8 | Number of past earnings reports to check |
| `MIN_QUALIFYING_EARNINGS` | 4 | Must have moved sharply on at least this many |
| `MIN_EARNINGS_MOVE_PCT` | 4.0 | "Sharp move" defined as ≥ 4% the day after earnings |
| `TARGET_DTE` | 90 | Buy options with ~90 days to expiry |
| `DTE_TOLERANCE` | 14 | Accept expiries within ±14 days of target |
| `TARGET_DELTA` | 0.30 | Target OTM delta for both call and put |
| `DELTA_TOLERANCE` | 0.07 | Accept delta between 0.23 and 0.37 |
| `COMBINED_PROFIT_TARGET_PCT` | 0.20 | Close both legs once combined value is +20% of cost |
| `COMBINED_STOP_LOSS_PCT` | 0.20 | Close both legs once combined value is -20% of cost |
| `MAX_OPEN_STRANGLES` | 5 | Max simultaneous open strangles |
| `POLL_HOURS` | 2 | Bot runs every 2 hours (not 30 min) |

---

### `C:\Users\subho\tradingbot\strangle\bot.py`

**Purpose:** Main engine. Runs every 2 hours. Two phases per run:

**Phase 1 — Monitor open strangles** (only stocks already in `strangle_state.json`):
- Judges the call + put **together** against total cost, at all times (pre- or
  post-earnings alike) — never one leg's price in isolation
- Combined value ≥ +20% of cost → close whatever legs are still open, trade closed (profit)
- Combined value ≤ -20% of cost → close whatever legs are still open, trade closed (stop-loss)

**Phase 2 — Scan for new entries** (all watched stocks not already in an open strangle):
- Calls `earnings_scanner.scan_for_entries()` — stocks with no earnings in the 14–21 day window are **silently skipped**
- For stocks in the window: runs IV filter + historical move check
- If all pass → buys 1 call + 1 put via Alpaca, records in state, sends email

---

### `C:\Users\subho\tradingbot\strangle\earnings_scanner.py`

**Purpose:** Uses yfinance to (1) find the next earnings date per symbol and (2) check historical price moves the day after each of the last N earnings reports. Only stocks in the 14–21 day earnings window AND with a history of big post-earnings moves pass to the next filter.

---

### `C:\Users\subho\tradingbot\strangle\iv_checker.py`

**Purpose:** Maintains a rolling local JSON cache (`iv_history.json`) of daily ATM IV observations per symbol. On each entry evaluation, records the current IV and computes its percentile rank vs history. Entry is only allowed if IV ≤ 50th percentile ("average or below"). If fewer than 5 observations exist, the filter is skipped (benefit of the doubt on early runs).

---

### `C:\Users\subho\tradingbot\strangle\option_selector.py`

**Purpose:** Finds the best OTM call and OTM put for a given symbol using Alpaca's options contracts API. Targets delta ≈ 0.30 ± 0.07 and expiry ≈ 90 DTE ± 14 days. Returns both contract OCC symbols, their strikes, deltas, IVs, and ask prices.

---

### `C:\Users\subho\tradingbot\strangle\state_manager.py`

**Purpose:** Persists the strangle state machine to `strangle_state.json`. Tracks each position through: `OPEN` → `CALL_SOLD` → `CLOSED`. Closed trades are archived in a `history` array in the same file for P&L review.

**State fields per symbol:** status, phase (PRE_EARNINGS/POST_EARNINGS), earnings_date, entry_date, expiry, call/put contract symbols, entry prices, sold prices and dates, total_cost, total_proceeds, net_pnl.

---

### `C:\Users\subho\tradingbot\strangle\alpaca_client.py`

**Purpose:** Alpaca REST API wrapper for the strangle bot (account PA34EFPV3B80). Provides: stock price lookup, option contract search, option snapshot (Greeks + pricing), bid/ask/mid/delta/IV extraction, and buy/sell option order placement.

---

### `C:\Users\subho\tradingbot\strangle\notifier.py`

**Purpose:** Email alerts specific to the strangle bot. Three alert types:

| Function | Trigger |
|---|---|
| `notify_strangle_opened` | New strangle entered (both legs bought) |
| `notify_combined_close` | Whole position closed — combined profit target or stop-loss hit, judged on call + put together, includes final net P&L |
| `notify_iv_skip` | Stock met earnings criteria but IV was too high — skipped |

---

### `C:\Users\subho\tradingbot\strangle\dashboard.py`

**Purpose:** Terminal P&L dashboard for active strangles. Fetches live option prices from Alpaca and shows each leg's current gain/loss vs entry. Run manually anytime: `python dashboard.py`

---

### `C:\Users\subho\tradingbot\strangle\strangle_state.json`

**Auto-generated.** Created on first strangle entry. Tracks all active and historical strangle positions. Delete only to reset all state (bot will reinitialise with no open positions).

---

### `C:\Users\subho\tradingbot\strangle\iv_history.json`

**Auto-generated.** Rolling log of daily IV observations per symbol. Grows over the first 60 days then stays at a fixed window. Deleting it resets the IV percentile filter — the bot will skip IV filtering until 5+ observations accumulate again.

---

### `C:\Users\subho\tradingbot\strangle\run_strangle.bat`

**Purpose:** Windows batch launcher called every 2 hours by Task Scheduler.

```bat
@echo off
cd /d C:\Users\subho\tradingbot\strangle
C:\Users\subho\AppData\Local\Python\bin\python3.14.exe bot.py >> logs\strangle.log 2>&1
```

---

## Auto-Generated Runtime Files (Summary)

These files are created and maintained automatically by the bots. You do not need to create or edit them. Delete them only if you want to reset the corresponding bot's state (it will reinitialise on next run).

| File | Created by | Reset effect |
|---|---|---|
| `trailing_stop/trailing_stop_state.json` | trailing_stop/bot.py | Forgets all entry prices, re-enters all positions fresh |
| `trailing_stop/pharma_catalyst_cache.json` | trailing_stop/pharma_catalyst.py | Forces a fresh pharma scan on next run |
| `trailing_stop/sector_cache.json` | trailing_stop/pharma_catalyst.py | Forces re-verification of all tickers' sectors |
| `copytrade/seen_trades.json` | copytrade/bot.py | **CAUTION** — bot will treat all historical trades as new and may place large orders |
| `flywheel/wheel_state.json` | flywheel/bot.py | Forgets all open option positions — bot will try to open new ones |
| `strangle/strangle_state.json` | strangle/bot.py | Forgets all open strangles — bot starts fresh with no active positions |
| `strangle/iv_history.json` | strangle/iv_checker.py | Resets IV percentile history — filter skipped until 5+ new observations accumulate |
| `ironcondor/ironcondor_state.json` | ironcondor/bot.py | Forgets open condor — bot will look for a new entry on next run |
| `reports/trade_ledger.json` | reports/daily_report.py | Forgets all ledger rows (open and closed) — rebuilt fresh from each bot's current state on next run |

---

## Task Scheduler Summary

All bots are registered with Windows Task Scheduler. To view:

```
schtasks /query /fo TABLE | findstr "trailing\|copytrade\|flywheel\|report\|topup\|strangle"
```

| Task Name | Script | Frequency | Time |
|---|---|---|---|
| TrailingStopBot | trailing_stop\run_trailing.bat | Every 30 min | Market hours |
| CopyTradeBot | copytrade\run_bot.bat | Every 30 min | Market hours |
| FlywheelBot | flywheel\run_flywheel.bat | Every 30 min | Market hours |
| FlywheelReport | flywheel\run_report.bat | Daily | 4:00 PM |
| DailyTopup | daily_topup\run_topup.bat | Daily | 9:25 AM |
| StrangleBot | strangle\run_strangle.bat | Every 2 hours | Market hours |
| StrangleReport | strangle\run_report.bat | Daily | 4:00 PM |
| IronCondorBot | ironcondor\run_ironcondor.bat | Every 30 min | Market hours |
| IronCondorReport | ironcondor\run_report.bat | Daily | 4:00 PM |
| TradeLedgerReport | reports\run_daily_report.bat | Daily | 4:05 PM |
