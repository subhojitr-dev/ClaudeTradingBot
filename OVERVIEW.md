# Trading Bot System — Plain-English Overview

> **Important:** All trading is done on **Alpaca Paper Trading** accounts.
> No real money is involved. This is a simulation and learning environment.

---

## What Does This System Do?

This system is a collection of four automated trading strategies that run on your
Windows PC without you having to do anything day-to-day. Each strategy watches
the stock market, makes decisions based on pre-set rules, and places trades
automatically. You get an email whenever something important happens.

Think of it as four "trading robots" running in the background while you go about
your day.

---

## The Four Robots (Strategies)

---

### Robot 1 — Trailing Stop Bot
**What it does in plain English:**

It buys a fixed number of shares in 15 hand-picked stocks and then protects those
positions automatically using three rules:

- **Stop-Loss:** If a stock falls 10% from what you paid for it, it sells everything
  immediately to prevent a bigger loss.
- **Trailing Stop:** If a stock rises 10% or more, it starts "following" the price
  upward. If the stock then drops 5% from its highest point, it sells — locking in
  most of the gain.
- **Ladder In:** If a stock drops 20% from your purchase price, instead of panicking,
  it buys more shares at the lower price (averaging down).

It also runs a morning scan of biotech/pharma news (FDA announcements, clinical trial
results) and automatically adds promising stocks to the watch list that day.

**The 15 stocks it watches:**
```
GOOGL  COHR  MU    AVGO  NBIS
KTOS   RKLB  GLW   NVDA  AMD
PANW   AAPL  MSFT  VST   TEM
```

**Emails you when:** Stop-loss triggered, ladder-in triggered, pharma stock added.

---

### Robot 2 — Copy Trade Bot
**What it does in plain English:**

It watches the publicly disclosed stock trades of two US politicians on a website
called Capitol Trades, and whenever they buy a stock, it copies that trade
automatically. The idea is that politicians often have an information edge.

**Politicians it follows:**
1. **Nancy Pelosi** — known for high-conviction tech bets
2. **Michael McCaul** — tech and defense focused

It will never copy more than 10 positions at a time, and it skips sales (only copies
buys). The first time it runs, it ignores all historical trades so it doesn't flood
the account with months of old orders.

**Emails you when:** A politician's trade is copied.

---

### Robot 3 — Options Wheel Bot (Flywheel)
**What it does in plain English:**

This one generates income by repeatedly selling options contracts on four stocks.
It works like a cycle (a "wheel"):

1. **Sell a Put:** Agree to buy 100 shares of a stock at a lower price, in exchange
   for receiving a cash premium upfront. You only get assigned if the stock falls to
   that lower price.
2. **If assigned (stock drops to your price):** You now own 100 shares. Immediately
   move to step 3.
3. **Sell a Call:** Agree to sell your 100 shares at a higher price, receiving
   another premium. You give up the shares if the stock rises to that price.
4. **Repeat:** Whether the options expire worthless (you keep the premium and go
   again) or you get assigned in either direction, the wheel keeps spinning and
   collecting premium.

It also closes positions early if they've already captured 70% of the maximum
possible profit — no need to hold to expiry if most of the money has been made.

**The 4 stocks it runs on:** AVGO, COHR, NBIS, GLW

**Emails you when:** Put sold, call sold, shares assigned, shares called away,
70% profit close. Also emails a daily P&L summary at 4 PM every trading day.

---

### Robot 4 — Strangle Bot (Earnings Plays)
**What it does in plain English:**

2–3 weeks before a company reports its earnings, this bot checks whether the stock
is a good candidate for an "earnings strangle" — a bet that the stock will move
significantly in either direction after the announcement.

It buys both a Call option (profits if stock goes up) and a Put option (profits if
stock goes down) at the same time. This way, it doesn't matter which direction the
stock moves — as long as it moves enough, one of the two options makes money.

The entry rules are strict:
- The stock must have a history of moving sharply on earnings (at least 4% move
  after at least 4 of the last 8 reports)
- The current option pricing (IV) must be average or below — if options are already
  expensive, the edge is gone
- Options chosen are about 30% out-of-the-money and expire in about 90 days

**Exit plan:**
- Judges the Call and Put **together** as one position, not one leg at a time — the
  two always move in opposite directions on the same stock move, so watching only
  one leg (e.g. "sell the Call once it's up 15%") can lock in a small win on that
  leg while leaving the other leg's growing loss with no exit plan at all.
- This combined check runs at all times, before and after earnings alike.
- **If the combined position is up 20% or more** — close both legs, take the profit.
- **If the combined position is down 20% or more** — close both legs, cut the loss.

**The stocks it scans:** NVDA, AAPL, MSFT, GOOGL, AVGO, AMD, TSLA, META, AMZN, MU,
PANW, COHR, MRVL, RKLB, NBIS

**Emails you when:** Strangle opened, whole position closed (profit target or
stop-loss), IV too high (skipped).

---

### Robot 5 — Iron Condor Bot (SPY)
**What it does in plain English:**

This strategy makes money when the market does *nothing dramatic* — it profits from
time passing and SPY staying in a range. You collect cash upfront by agreeing to
absorb losses only if SPY moves a very large amount in either direction.

It simultaneously places two credit spreads on SPY:
- **Bull Put Spread:** Sell a put at a lower price (you agree to buy SPY if it
  falls to that level), and buy an even lower put as insurance. You collect a
  credit. You keep it all if SPY stays above your short put.
- **Bear Call Spread:** Same idea on the upside. You sell a call above the market
  and buy a higher call as insurance. You keep the credit if SPY stays below your
  short call.

Combined, this creates a "profit zone" — a range within which SPY can move freely
and you make money. Only if SPY breaks outside both strikes do you lose.

**How strikes are chosen:**
- Short strikes must have a delta of 0.20 or less (only 20% probability of being
  breached, statistically)
- The bot identifies real support and resistance levels from 60 days of SPY price
  history (swing highs/lows, 20/50/200-day moving averages, round-number levels
  like $530, $535, $540) and places short strikes just beyond those structural
  levels — adding a second layer of protection beyond just delta
- Opened at exactly 14 days to expiry on SPY weekly options

**Exit and adjustment rules:**
- **Profit target:** Close the whole condor when 50% of the collected premium has
  been captured — no need to hold for the remaining 50%
- **Stop-loss:** Close if the cost to buy back the position reaches 2× the
  original credit collected
- **Adjustment at 0.45 delta:** If either short strike's delta rises from 0.20
  to 0.45 (meaning SPY has moved significantly toward it), the threatened spread
  is "rolled" — bought back and re-sold at a safer strike 7.50 points further away.
  This resets the risk without closing the whole trade

**Emails you when:** Condor opened (with full details of all 4 legs), adjustment
triggered (which side and what happened), condor closed (reason + final P&L).

---

## How It All Runs Automatically (Windows Task Scheduler)

Your PC runs all of this automatically using Windows Task Scheduler — the same
built-in tool Windows uses to run antivirus scans and updates. The bots are
registered as scheduled tasks and Windows wakes them up on a timer.

**You do not need to do anything** for the bots to run. As long as your PC is on
and connected to the internet during market hours, everything happens automatically.

### The Schedule

| What runs | When | How often |
|-----------|------|-----------|
| **Daily Cash Check** | 9:25 AM, Mon–Fri | Once (before market opens) |
| **Trailing Stop Bot** | 9:30 AM – 4:00 PM, Mon–Fri | Every 30 minutes |
| **Copy Trade Bot** | 9:30 AM – 4:00 PM, Mon–Fri | Every 30 minutes |
| **Flywheel (Wheel) Bot** | 9:30 AM – 4:00 PM, Mon–Fri | Every 30 minutes |
| **Flywheel Daily Report** | 4:00 PM, Mon–Fri | Once (after market closes) |
| **Strangle Bot** | Market hours, Mon–Fri | Every 2 hours |
| **Iron Condor Bot** | Market hours, Mon–Fri | Every 30 minutes |

> **Why every 30 minutes?** Stock prices and politician disclosures don't need
> to be checked every second. 30 minutes is frequent enough to act on signals
> without hammering the APIs. The strangle bot runs every 2 hours because
> earnings windows and IV levels change slowly — checking more often adds nothing.

### Viewing the Scheduled Tasks

To see all registered tasks in a Command Prompt or PowerShell:
```powershell
schtasks /query /fo TABLE | findstr "trailing copytrade flywheel report topup strangle"
```

---

## Two Trading Accounts

The system uses two separate Alpaca paper trading accounts so that stock trades
and options trades are kept cleanly separated:

| Account | ID | What uses it |
|---|---|---|
| Claude Trading | PA31HKOPMG4M | Trailing Stop Bot + Copy Trade Bot |
| Paper Trading | PA34EFPV3B80 | Flywheel Bot + Strangle Bot |

---

## Pre-Requisites to Run Anything Manually

Before you can run any bot manually from a terminal, the following must be in place:

### 1. Python 3.14 is installed
The bots use Python. Verify it is installed:
```powershell
C:\Users\subho\AppData\Local\Python\bin\python3.14.exe --version
```
You should see: `Python 3.14.x`

### 2. Required Python packages are installed
Each strategy uses third-party libraries. Install them all at once:
```powershell
C:\Users\subho\AppData\Local\Python\bin\python3.14.exe -m pip install requests yfinance
```

| Package | Used by |
|---|---|
| `requests` | All bots (Alpaca API calls) |
| `yfinance` | Strangle bot (earnings dates + price history) |
| `playwright` | Copy Trade bot (fallback scraper for Capitol Trades) |
| `beautifulsoup4` | Copy Trade bot (primary HTML scraper) |

To install everything including the copy trade scraper dependencies:
```powershell
C:\Users\subho\AppData\Local\Python\bin\python3.14.exe -m pip install requests yfinance playwright beautifulsoup4
C:\Users\subho\AppData\Local\Python\bin\python3.14.exe -m playwright install chromium
```

### 3. Internet connection
All bots call Alpaca's API over HTTPS. No special network setup needed beyond
a normal internet connection.

### 4. Market must be open (for most bots)
Every bot checks whether the US stock market is open at the start of each run.
If the market is closed (weekends, holidays, outside 9:30 AM–4:00 PM ET), the
bot prints "Market closed — exiting" and stops. This is by design.

> **Exception:** You can run `topup_check.py` and `dashboard.py` any time —
> they only read data, they don't place trades.

### 5. The correct working directory
Each bot imports its own `config.py` using a relative path. You **must** `cd`
into the bot's folder before running it, or it will fail to find config.

---

## Manual Run Commands

Open PowerShell or Command Prompt, then use the commands below.

---

### Trailing Stop Bot — one poll cycle
```powershell
cd C:\Users\subho\tradingbot\trailing_stop
C:\Users\subho\AppData\Local\Python\bin\python3.14.exe bot.py
```
**What happens:** Checks market open → runs pharma scan → evaluates all 15
stocks → applies stop/trail/ladder rules → saves state → exits.

---

### Copy Trade Bot — one scrape cycle
```powershell
cd C:\Users\subho\tradingbot\copytrade
C:\Users\subho\AppData\Local\Python\bin\python3.14.exe bot.py
```
**What happens:** Checks market open → scrapes Capitol Trades for Pelosi and
McCaul → places buy orders for any new trades → saves seen-trade IDs → exits.

### Copy Trade Dashboard — live P&L table (read-only, any time)
```powershell
cd C:\Users\subho\tradingbot\copytrade
C:\Users\subho\AppData\Local\Python\bin\python3.14.exe dashboard.py
```

---

### Flywheel (Wheel) Bot — one management cycle
```powershell
cd C:\Users\subho\tradingbot\flywheel
C:\Users\subho\AppData\Local\Python\bin\python3.14.exe bot.py
```
**What happens:** Checks market open → syncs Alpaca positions with wheel state
→ handles each of the 4 wheel stocks (sells puts, monitors assignments, sells
calls, handles early closes) → saves state → exits.

### Flywheel Report — email P&L summary now (any time)
```powershell
cd C:\Users\subho\tradingbot\flywheel
C:\Users\subho\AppData\Local\Python\bin\python3.14.exe report.py
```

---

### Strangle Bot — one scan + monitor cycle
```powershell
cd C:\Users\subho\tradingbot\strangle
C:\Users\subho\AppData\Local\Python\bin\python3.14.exe bot.py
```
**What happens:** Checks market open → monitors any open strangles (sells legs
at profit targets) → scans watched stocks for earnings in the 14–21 day window
→ if found, checks IV and move history → opens strangle if all criteria pass
→ saves state → exits.

### Strangle Dashboard — live P&L (read-only, any time)
```powershell
cd C:\Users\subho\tradingbot\strangle
C:\Users\subho\AppData\Local\Python\bin\python3.14.exe dashboard.py
```

---

### Daily Cash Check — run now (any time)
```powershell
cd C:\Users\subho\tradingbot\daily_topup
C:\Users\subho\AppData\Local\Python\bin\python3.14.exe topup_check.py
```
**What happens:** Pulls cash balance from Alpaca → if below $100,000, prints
alert with exact steps to top up and opens the Alpaca dashboard in your browser.

---

### Iron Condor Bot — one monitoring/entry cycle
```powershell
cd C:\Users\subho\tradingbot\ironcondor
C:\Users\subho\AppData\Local\Python\bin\python3.14.exe bot.py
```
**What happens:** Checks market open → if a condor is open, fetches live Greeks
for both short strikes and checks profit target (50%), stop-loss (2× credit), and
adjustment trigger (delta 0.45) → if no condor is open, analyses SPY S/R levels,
finds the 14-DTE expiry, selects 4 legs at delta ≤ 0.20 just beyond S/R,
verifies the credit is ≥ 33% of max risk, and places orders → saves state.

### Iron Condor Dashboard — live legs view (read-only, any time)
```powershell
cd C:\Users\subho\tradingbot\ironcondor
C:\Users\subho\AppData\Local\Python\bin\python3.14.exe dashboard.py
```

---

### Emergency: Sell Everything
```powershell
cd C:\Users\subho\tradingbot
C:\Users\subho\AppData\Local\Python\bin\python3.14.exe sell_all.py
```
**What happens:** Lists all open positions in both accounts, cancels all pending
orders, then market-sells every position. Used to clear the slate for a fresh
start. Paper trading only — no real money.

---

## Where to Find Logs

Every bot writes a log file that records exactly what it did each run.

| Bot | Log file |
|---|---|
| Trailing Stop | `trailing_stop\logs\trailing.log` |
| Copy Trade | `copytrade\logs\copytrade.log` |
| Flywheel | `flywheel\logs\flywheel.log` |
| Flywheel Report | `flywheel\logs\report.log` |
| Strangle | `strangle\logs\strangle.log` |
| Iron Condor | `ironcondor\logs\ironcondor.log` |
| Daily Top-Up | `daily_topup\logs\topup_YYYY-MM-DD.log` |

To watch a log file update in real time (PowerShell):
```powershell
Get-Content C:\Users\subho\tradingbot\trailing_stop\logs\trailing.log -Wait -Tail 30
```

---

## Where to See the Positions (Alpaca Dashboard)

Paper trading account overview:
```
https://app.alpaca.markets/paper/dashboard/overview
```

Switch between the two accounts using the dropdown in the top-left corner of the
Alpaca dashboard.

---

## What to Do If Something Goes Wrong

| Problem | What to check |
|---|---|
| Bot didn't run at scheduled time | Open Task Scheduler (search "Task Scheduler" in Start Menu) → find the task → check "Last Run Result" |
| Bot ran but placed no trades | Check the log file — most likely the market was closed or no criteria were met |
| Email not received | Check spam folder. Verify Gmail App Password in the relevant `config.py` |
| Alpaca API error | Check internet connection. Alpaca paper API occasionally has brief outages |
| Want to reset a strategy's state | Delete the relevant `.json` state file — bot will reinitialise cleanly on next run |
| Need to stop a bot temporarily | Open Task Scheduler → right-click the task → Disable |
| Need to sell everything immediately | Run `sell_all.py` (see Emergency section above) |

---

## File Map (Where Everything Lives)

```
C:\Users\subho\tradingbot\
│
├── OVERVIEW.md          ← This file — plain-English guide
├── README.md            ← Full technical documentation
├── FILES.md             ← Complete file-by-file reference
├── notifier.py          ← Shared email utility (trailing stop, copy trade, flywheel)
├── sell_all.py          ← Emergency: liquidate all positions in both accounts
│
├── trailing_stop\       ← Robot 1
├── copytrade\           ← Robot 2
├── flywheel\            ← Robot 3
├── strangle\            ← Robot 4
├── ironcondor\          ← Robot 5
└── daily_topup\         ← Morning cash balance checker
```

For the full file-by-file breakdown, see `FILES.md`.
For detailed strategy explanations with worked examples, see `README.md`.

---

## All Python Source Files — What Each One Does and How

30 Python scripts in total across 5 folders. Grouped by strategy below.

---

### Root Level (shared utilities)

---

#### `notifier.py`
**What it does:** Sends alert emails via Gmail. Every other bot imports this file
to avoid duplicating email logic.

**How it works:**
- Uses Python's built-in `smtplib` library to connect to Gmail on port 587
- Authenticates with a Gmail App Password (not your real password — a special
  16-character key generated in Google Account settings)
- Strips spaces from the App Password before sending (Gmail displays it with
  spaces but requires it without)
- Contains one named function per alert type (stop-loss, ladder-in, pharma add,
  copy trade, CSP opened, etc.) so the calling bot just passes values and doesn't
  need to know anything about email

**Called by:** `trailing_stop/bot.py`, `copytrade/bot.py`, `flywheel/bot.py`

---

#### `sell_all.py`
**What it does:** Emergency one-shot script. Sells every open position and cancels
every pending order across both Alpaca paper accounts in about 5 seconds.

**How it works:**
- Calls Alpaca's `DELETE /v2/orders` endpoint — cancels all open orders in bulk
- Then calls `DELETE /v2/positions` endpoint — market-sells every open position
  in one API call (Alpaca's "close all positions" endpoint)
- Loops over both accounts (PA31HKOPMG4M and PA34EFPV3B80) sequentially
- Prints a table of every position and its P&L before closing, so you can see
  what you had
- Not scheduled — run manually only

---

### Trailing Stop Bot (`trailing_stop\`)

---

#### `trailing_stop/config.py`
**What it does:** The single file where all strategy settings live. Nothing is
hard-coded in the bot logic — all numbers come from here.

**How it works:** Pure Python constants (no functions). The bot does
`from config import *` to pull every setting into scope. Change a number here
and the bot picks it up on its very next run — no code changes needed.

**Key things defined here:** The 15 watched stocks, stop-loss %, trailing trigger %,
trailing stop %, ladder-in drop %, minimum cash balance, pharma scan toggle,
Alpaca API keys, email credentials.

---

#### `trailing_stop/bot.py`
**What it does:** The main brain of the trailing stop strategy. Runs every 30
minutes via Task Scheduler. Makes all buy and sell decisions for the 15 watched
stocks.

**How it works — step by step each run:**
1. Calls Alpaca clock API → if market closed, exits immediately (no action)
2. Loads `trailing_stop_state.json` (memory of entry prices, stops, etc.)
3. Calls `pharma_catalyst.scan_today()` — once per day only (cached); adds any
   qualifying biotech stocks to the watch list and emails you
4. Fetches all current positions from Alpaca to sync share counts
5. For every stock with no position yet → places a market buy order for 10 shares
6. For every held stock → fetches current price, then checks three rules in order:
   - **Stop-loss:** price < entry × 0.90 → sell all, email
   - **Trailing stop:** if trailing is active and price < peak × 0.95 → sell all, email
   - **Ladder-in:** price < entry × 0.80 and not already laddered → buy 10 more, email
   - **Activate trailing:** price > entry × 1.10 → start trailing, update peak
7. Saves updated state back to JSON

---

#### `trailing_stop/state_manager.py`
**What it does:** Manages the memory file (`trailing_stop_state.json`) that lets
the bot remember entry prices, stop prices, and ladder counts across restarts.

**How it works:**
- Implemented as a Python class (`StateManager`) with methods for each state
  change event: `init_symbol`, `update_price`, `ladder_in`, `mark_sold`
- Every method that changes state immediately saves the JSON file, so even if
  the bot crashes mid-run, the state is consistent
- `update_price` is the core method: it raises the trailing stop if a new peak
  is set, and activates trailing if the 10% gain trigger is crossed. The stop
  price is guaranteed to never go down (uses `max()` when updating)
- Also provides `summary_table()` which renders a formatted text table of all
  positions — used in log output

---

#### `trailing_stop/pharma_catalyst.py`
**What it does:** Morning scanner that finds biotech/pharma stocks with a major
FDA or clinical trial event happening today and returns them to the bot for entry.

**How it works:**
- Runs once per day (result cached in `pharma_catalyst_cache.json` keyed by
  today's date — subsequent 30-min runs return the cached result instantly)
- Scrapes three data sources in parallel:
  - **Finviz News** (`finviz.com/news.ashx`) — latest headlines
  - **Finviz Biotech Screener** — top-moving biotech tickers today
  - **FDA Press Release RSS Feed** — official FDA announcements
- For each headline/ticker found, `_classify_event()` checks for keywords like
  "FDA approved", "phase 3 results", "PDUFA", "breakthrough therapy". Rejection
  news ("complete response letter", "CRL") is flagged and skipped
- `_is_pharma_stock()` verifies the ticker is actually in biotech/pharma by
  checking its Finviz sector page (cached permanently in `sector_cache.json`)
- Returns a list of qualifying stocks with their event type and headline

---

### Copy Trade Bot (`copytrade\`)

---

#### `copytrade/config.py`
**What it does:** All settings for the copy trade bot — which politicians to
follow, position limits, trade sizing, and credentials.

**How it works:** Same pattern as trailing stop — pure constants, imported by
the bot at startup. The `POLITICIANS` list is the key setting: each entry has
a `name` and `ct_id` (the politician's unique ID on the Capitol Trades website).
Remove an entry from this list to stop following that politician.

---

#### `copytrade/bot.py`
**What it does:** The main engine. Runs every 30 minutes. Checks if Pelosi or
McCaul have filed any new stock purchase disclosures, and copies them.

**How it works — step by step each run:**
1. Market open check → exit if closed
2. Loads `seen_trades.json` (the list of trade IDs already processed)
3. **First-run guard:** if the seen-trades file is empty, marks all current
   disclosures as "already seen" without ordering anything. This prevents
   buying months of historical trades on the very first run
4. For each politician in the list:
   - Calls `capitol_trades_scraper.fetch_politician_trades()` to get their
     latest disclosures
   - Filters out any trade ID already in `seen_trades.json`
   - Skips Sales (only copies Purchases)
   - Skips Options trades (only copies stock buys)
   - Checks: already at 10-position cap? already hold this ticker? already
     ordered this ticker this run? → skips if any of these
   - Places a market buy order via Alpaca for 10 shares
   - Sends email notification
   - Adds trade ID to the seen set
5. Saves updated `seen_trades.json`

---

#### `copytrade/alpaca_client.py`
**What it does:** Thin wrapper around Alpaca's REST API specifically for the
copy trade bot (stocks only, no options).

**How it works:** Each function makes one HTTPS request to Alpaca using the
`requests` library and returns the parsed JSON. Functions: `get_account`,
`get_positions`, `get_position`, `place_market_order`, `get_clock`, `get_bars`.
Authentication is done via two HTTP headers (`APCA-API-KEY-ID` and
`APCA-API-SECRET-KEY`) on every request.

---

#### `copytrade/capitol_trades_scraper.py`
**What it does:** Fetches the trade disclosure list for a politician from the
Capitol Trades website and parses it into a list of structured trade records.

**How it works — two-strategy approach:**
1. **Fast path (requests + BeautifulSoup):** Makes an HTTP GET request and
   parses the HTML table directly. Works when Capitol Trades serves static HTML.
2. **Fallback (Playwright headless browser):** If the fast path returns an empty
   table (Capitol Trades sometimes renders its table in JavaScript), Playwright
   launches a real headless Chromium browser, navigates to the page, waits for
   the JavaScript table to render, then reads the DOM. Slower but always works.

Each row in the table is parsed into: `{politician, trade_id, ticker, action,
amount, date}`.

---

#### `copytrade/trade_tracker.py`
**What it does:** Handles reading and writing the `seen_trades.json` file —
the de-duplication store that prevents ordering the same disclosure twice.

**How it works:** Four simple functions — `load_seen()` reads the JSON file
into a Python set, `save_seen()` writes it back, `is_seen()` checks membership,
`mark_seen()` adds an ID. Using a set means lookups are instant even with
thousands of entries.

---

#### `copytrade/option_resolver.py`
**What it does:** Converts human-readable option descriptions from Capitol Trades
("Call Option, NVDA, Strike $120, Exp Dec 2025") into the OCC contract symbol
format that Alpaca understands ("NVDA251219C00120000").

**How it works:** Parses the description string using regular expressions to
extract symbol, type (call/put), strike price, and expiry date, then formats
them into the 21-character OCC standard. Currently the bot skips option trades
entirely, but this module exists for future use.

---

#### `copytrade/dashboard.py`
**What it does:** Prints a live terminal table showing all copy-trade positions
with their current P&L and which politician triggered each one. Read-only —
makes no trades.

**How it works:** Calls Alpaca's positions API to get current prices and P&L,
then formats each position into a table row. Run manually any time with
`python dashboard.py`.

---

#### `copytrade/debug_scraper.py`
**What it does:** One-off diagnostic script. Launches a headless browser,
navigates to Pelosi's Capitol Trades page, and prints the raw text content of
every table row and cell. Used during development to inspect the HTML structure
when the scraper needed updating.

**How it works:** Playwright opens Chromium, waits for the table to load,
then runs JavaScript on the page (`document.querySelectorAll`) to extract cell
text. Not scheduled — run manually only when the scraper breaks.

---

### Flywheel (Options Wheel) Bot (`flywheel\`)

---

#### `flywheel/config.py`
**What it does:** All settings for the wheel strategy on account PA34EFPV3B80.

**How it works:** Same constant-file pattern. Key settings: the 4 wheel stocks,
CSP strike discount (20% OTM), covered call premium (10% OTM), delta limits
(never sell option with delta > 0.25), DTE window (14–28 days), early-close
threshold (70% profit), roll trigger, minimum net credit for a roll.

---

#### `flywheel/bot.py`
**What it does:** The wheel strategy engine. Runs every 30 minutes. Manages the
full put→assignment→call cycle for all 4 wheel stocks simultaneously.

**How it works — step by step each run:**
1. Market check → exits if closed or within 15 minutes of close (avoids
   last-minute fills at wide spreads)
2. Loads `wheel_state.json`
3. Syncs Alpaca positions with state (detects assignments and expirations by
   comparing what Alpaca says is open vs what the state says should be there)
4. For each of the 4 stocks, calls the right handler based on current stage:
   - `handle_idle()` — no position; finds a CSP contract and sells it
   - `handle_csp()` — short put open; checks for expiry, assignment, 70%
     profit close, or roll-up trigger
   - `handle_cc()` — holding stock + short call; checks for called-away,
     70% profit close, or expired call (sell new one)
5. Saves updated state

---

#### `flywheel/option_selector.py`
**What it does:** Finds the best specific option contract to sell for each wheel
stage, applying all delta and DTE filters.

**How it works:**
- For a CSP: queries Alpaca for all put contracts on the symbol within the DTE
  window, filters out any with delta > 0.25, then picks the one whose strike
  is closest to 20% below the current stock price
- For a covered call: same logic but for calls, targeting 10% above current price
- For a roll: must use the same expiry, new strike must be higher, net credit
  (new premium minus buyback cost) must be positive and above the minimum
- Uses Alpaca's `GET /v2/options/contracts` to list available contracts, then
  `GET /v2/options/snapshots` to get live Greeks (delta) and pricing for each

---

#### `flywheel/state_manager.py`
**What it does:** Persists the wheel state machine for all 4 stocks to
`wheel_state.json`. Each stock moves through stages: IDLE → CSP → CC → IDLE.

**How it works:** Each stage transition is a named method (`open_csp`,
`csp_assigned`, `open_cc`, `cc_called_away`, etc.). Each method updates the
in-memory state dict and saves to JSON. Also accumulates a `history` list of
all past contracts so you can see the full premium collection record. The total
premium collected for each symbol grows monotonically — it's never reset.

---

#### `flywheel/alpaca_client.py`
**What it does:** Options-aware Alpaca API wrapper for the flywheel bot. Handles
both stock and options endpoints from account PA34EFPV3B80.

**How it works:** Same structure as the copy trade client but extended with
options-specific functions: `get_option_contracts`, `get_option_snapshots`,
`get_option_snapshot`, `get_mid_price`, `get_bid_price`, `get_delta`, `get_iv`,
`place_option_order`. Option orders include `"asset_class": "us_option"` in the
payload, which is required by Alpaca to distinguish them from stock orders.

---

#### `flywheel/report.py`
**What it does:** Generates and emails the daily 4 PM P&L summary for the wheel
strategy. Runs once per day via its own Task Scheduler entry.

**How it works:**
- Loads `wheel_state.json` for current stage and contract details per symbol
- Calls Alpaca to get current option mid-prices and stock prices
- Builds three tables: open option positions, stock positions (assigned shares),
  and a summary of total premium collected vs unrealised stock P&L
- Formats everything as plain text and sends via Gmail SMTP

---

### Strangle Bot (`strangle\`)

---

#### `strangle/config.py`
**What it does:** All settings for the strangle strategy on account PA34EFPV3B80.

**How it works:** Same constant-file pattern. Key settings: the 15 stocks to
scan, earnings entry window (14–21 days), IV percentile threshold (50th),
IV history retention (60 days), historical move filter (≥4% on ≥4 of last 8
reports), target delta (0.30), target DTE (90), combined profit target (20%),
combined stop-loss (20%), max simultaneous strangles (5), polling interval (2 hrs).

---

#### `strangle/bot.py`
**What it does:** Main engine for the strangle strategy. Runs every 2 hours.
Two phases per run: monitor open strangles, then scan for new entries.

**How it works — step by step each run:**
1. Market check → exits if closed
2. Loads `strangle_state.json`
3. Fetches all current Alpaca option positions
4. **Phase 1 — Monitor:** For every stock in the active state:
   - If today is past the earnings date, switches it to POST_EARNINGS phase
     (bookkeeping only — doesn't change the exit check below)
   - Judges the call + put **together** against total cost (using locked-in
     proceeds for any leg already sold) — never one leg's price alone
   - If combined value is ≥ +20% or ≤ -20% of cost, places sell-to-close
     order(s) for whatever legs are still open, records in state, emails,
     archives the trade
5. **Phase 2 — Scan:** For each watched stock not already in an open strangle:
   - Calls `earnings_scanner.scan_for_entries()` — if earnings are not 14–21
     days away, the stock is silently skipped (this is the most common outcome)
   - If in the window: calls `iv_checker.passes_iv_filter()` — records today's
     IV and checks if it's at or below the 50th percentile
   - If IV passes: calls `option_selector.find_strangle_legs()` to find the
     contracts
   - If contracts found: places buy orders for both legs, records in state,
     sends opening email
6. Saves state

---

#### `strangle/earnings_scanner.py`
**What it does:** Determines whether a stock has earnings coming up in the
14–21 day window AND has historically moved big on earnings day.

**How it works:**
- Uses the `yfinance` library (Yahoo Finance) to get earnings data
- `get_next_earnings_date(symbol)` calls `yf.Ticker(symbol).calendar` which
  returns the next scheduled earnings date as a Python date object
- `historical_earnings_moves(symbol)` fetches 2 years of daily price history
  via `yf.Ticker(symbol).history()`, then for each of the last N earnings
  dates, calculates the absolute percentage move from the close before earnings
  to the close the day after. Returns a list like `[8.2, 3.1, 12.4, ...]`
- `scan_for_entries()` combines both: filters by date window first (fast, no
  price data needed), then checks move history only for stocks that pass

---

#### `strangle/iv_checker.py`
**What it does:** Tracks implied volatility (IV) over time per stock and answers
"is today's IV cheap or expensive relative to recent history?"

**How it works:**
- Maintains `iv_history.json`: a dict of `{symbol: [{date, iv}, ...]}` entries,
  one record per bot run per symbol
- Every time the bot evaluates a stock for entry, it calls `record_iv()` which
  appends today's observation and prunes records older than 60 days
- `iv_percentile()` sorts all stored IV values and calculates what percentage
  of historical observations were below today's IV — a value of 30 means "IV is
  cheaper than 70% of past readings"
- If fewer than 5 observations exist (early in the bot's life), the filter is
  skipped and entry is allowed — not enough data to be selective yet
- ATM IV is estimated by averaging the call and put leg IVs returned by the
  Alpaca options snapshot

---

#### `strangle/option_selector.py`
**What it does:** Finds the specific call and put contracts to buy for a new
strangle — targeting delta ≈ 0.30 and DTE ≈ 90 days.

**How it works:**
- Calls `alpaca_client.get_option_contracts()` twice — once for calls (strikes
  above current price) and once for puts (strikes below current price) — within
  the DTE window (76–104 days out)
- Fetches live snapshots (Greeks + pricing) for all candidates in a single
  batch API call
- `_best_contract()` filters to only contracts with delta between 0.23 and 0.37,
  then picks the one whose delta is closest to 0.30
- Returns both legs as a dict including OCC symbols, strikes, deltas, IVs, and
  ask prices. Returns None if no valid pair is found (e.g. options market is thin)

---

#### `strangle/state_manager.py`
**What it does:** Persists strangle positions through their lifecycle:
OPEN → CALL_SOLD → CLOSED.

**How it works:**
- State file has two top-level keys: `active` (open trades) and `history`
  (closed trades)
- `open_strangle()` adds a new entry to `active` with all entry details and
  calculates total cost (call ask + put ask) × 100 shares per contract
- `record_call_sold()` updates the active entry with the call exit price and
  adds the proceeds to the running total
- `record_put_sold()` does the same for the put, computes net P&L
  (total proceeds − total cost), sets status to CLOSED, then moves the entry
  from `active` to `history`
- All saves are immediate (no buffering) so crashes leave consistent state

---

#### `strangle/alpaca_client.py`
**What it does:** Options-aware Alpaca API wrapper for the strangle bot (same
account PA34EFPV3B80 as flywheel). Nearly identical to flywheel's client but
kept separate so each bot is fully self-contained.

**How it works:** Identical pattern to flywheel's client. Helper functions
`extract_mid`, `extract_ask`, `extract_delta`, `extract_iv` parse the nested
Alpaca snapshot JSON into simple floats. Option buy orders use `side: "buy"`
(buy to open); sell orders use `side: "sell"` (sell to close).

---

#### `strangle/notifier.py`
**What it does:** Strangle-specific email alerts. Separate from the root-level
`notifier.py` because the strangle bot uses a different account and different
subject-line prefix (`[Strangle]`).

**How it works:** Same Gmail SMTP mechanics as the root notifier. Three alert
functions: `notify_strangle_opened` (both legs entered), `notify_combined_close`
(whole position closed — profit target or stop-loss, judged on call + put
together, includes final net P&L), `notify_iv_skip` (criteria met but IV was
elevated — skipped).

---

#### `strangle/dashboard.py`
**What it does:** Prints a terminal table of all active strangles with live
prices and current gain/loss on each leg. Read-only.

**How it works:** Loads `strangle_state.json`, then for each active position
calls Alpaca's option snapshot API to get the current mid price of each leg.
Computes gain/loss vs entry price and formats into a table. Also shows the last
10 closed trades from the history section with their net P&L. Run manually any
time: `python dashboard.py`.

---

### Iron Condor Bot (`ironcondor\`)

---

#### `ironcondor/config.py`
**What it does:** All settings for the iron condor strategy. The one file to edit if you want to change any parameter without touching bot logic.

**Key things defined here:** SPY as the underlying, `TARGET_DTE=14`, `MAX_SHORT_DELTA=0.20`, `WING_WIDTH=5` (dollars between short and long strike on each side), `ADJUST_DELTA=0.45` (roll trigger), `PROFIT_TARGET_PCT=0.50` (close at 50% profit), `MAX_LOSS_RATIO=2.0` (stop-loss at 2× premium), `USE_SR_LEVELS=True` (use support/resistance for strike placement), `USE_TREND_BIAS=True` (tighten the call side when SPY is trending up), minimum credit ratio of 33%.

---

#### `ironcondor/bot.py`
**What it does:** The main engine. Runs every 30 minutes. Either monitors an open condor or scans for a new entry — never both in the same run.

**How it works — step by step each run:**
1. Market open check → exit if closed
2. Load `ironcondor_state.json`
3. If a condor is already open:
   - Calculate days to expiry — if expired, record as max profit and close
   - Fetch live delta for both short strikes
   - If either short delta ≥ 0.45 → call `_roll_side()` to adjust that spread
   - Calculate current cost-to-close across all 4 legs
   - If profit captured ≥ 50% → close for profit
   - If cost-to-close ≥ 2× original credit → stop-loss close
4. If no condor is open:
   - Get SPY price
   - Call `support_resistance.analyse()` to find S/R levels and trend
   - Call `option_selector.find_iron_condor()` to select all 4 legs
   - If valid condor found (meets all criteria) → place 4 orders and record
5. Save state

---

#### `ironcondor/support_resistance.py`
**What it does:** Analyses 60 days of SPY daily candles (via yfinance) to find support and resistance levels, and determines the current trend relative to the 50-day moving average.

**How it works:**
- **Swing highs/lows:** Scans the price history with a sliding window (±5 candles). A swing high is a candle whose High is the highest in its window; a swing low whose Low is the lowest. These are pivot points other traders will also be watching.
- **Moving averages:** Calculates the 20, 50, and 200-day SMA. When price is near a major MA, that level often acts as support or resistance.
- **Round numbers:** Every $5 increment near SPY's current price (e.g. $530, $535, $540...) is included because options traders cluster orders around round numbers.
- **Clustering:** Levels within $1.50 of each other are merged into one (averaged) so the same price zone doesn't appear as five separate levels.
- Returns separate `support` (sorted nearest-first below price) and `resistance` (sorted nearest-first above price) lists, plus trend = "above_ma50", "below_ma50", or "neutral".

---

#### `ironcondor/option_selector.py`
**What it does:** Selects the specific OCC contract symbols for all four legs of the iron condor — short put, long put, short call, long call.

**How it works:**
- `find_target_expiry()`: queries Alpaca for all SPY call contracts in the 12–16 DTE window, extracts the unique expiry dates, and picks the one closest to 14 days out (SPY has weekly options every Friday).
- `_pick_short_put()`: queries Alpaca for SPY puts 3–15% below current price at the target expiry, fetches their Greeks, filters to delta ≤ 0.20, then if S/R is enabled picks the strike closest to "one tick below the nearest support level". Falls back to highest-premium qualifying strike if no S/R guidance.
- `_pick_short_call()`: same logic for calls above the price, plus applies the trend bias (allows up to 0.23 delta if SPY is above MA50).
- `_find_wing()`: queries for the contract exactly WING_WIDTH ($5) further OTM than the short strike on each side — this is the long leg that caps the maximum loss.
- Checks the credit quality: `(short_put_credit − long_put_debit) + (short_call_credit − long_call_debit)` must be ≥ 33% of the wing width. If not, returns None and no trade is placed.

---

#### `ironcondor/state_manager.py`
**What it does:** Persists the condor position (all 4 leg symbols, strikes, entry prices, adjustment history) to `ironcondor_state.json`. Manages state transitions.

**How it works:**
- `open_condor()`: records all leg details, calculates max risk and credit ratio, initialises `put_adjusted=False` and `call_adjusted=False` flags
- `record_adjustment()`: when a side is rolled, updates the relevant short/long contract symbols and strikes, appends to `adjustment_log` (date, old strike, new strike, roll credit/debit), and adds the roll credit to the cumulative `net_credit`
- `close_condor()`: calculates final net P&L = (net_credit − cost_to_close) × 100, records reason and close date, moves from `active` to `history`

---

#### `ironcondor/alpaca_client.py`
**What it does:** Alpaca REST API wrapper for the iron condor bot (account PA34EFPV3B80).

**How it works:** Same structure as the other option clients. Key extra functions: `raw_delta()` returns the signed delta (negative for puts, used to detect which direction risk is growing), `theta()` returns the daily time decay value (informational, shown in logs), `bid_price()` used when selling (get filled at bid), `ask()` used when buying (get filled at ask).

---

#### `ironcondor/notifier.py`
**What it does:** Sends rich HTML email alerts for every significant Iron Condor event — styled tables, colour-coded P&L, and full trade history in every close notification.

**Alert types:**
- `notify_condor_opened`: Full 4-leg table (strike, delta, credit/debit per leg), net credit and max risk in dollars, profit target, stop-loss level, adjustment trigger, trend bias label, nearest support and resistance levels from S/R scan
- `notify_adjustment`: Triggered side (PUT or CALL), old vs new strikes in a comparison table, direction moved (higher/lower), roll credit or debit, cumulative net credit after roll, SPY price at time of adjustment, days remaining to expiry
- `notify_closed`: Full trade summary including entry date, close date, duration, final 4-leg strikes (with "rolled" tags if adjusted), full adjustment history table, original credit vs cost to close vs net P&L — plus a special "expired worthless" note when max profit is achieved at expiry
- `notify_no_entry`: Daily scan summary listing which criterion was not met

---

#### `ironcondor/dashboard.py`
**What it does:** Prints a live terminal table of the open condor with real-time Greeks and P&L breakdown per spread leg. Read-only — makes no trades.

**How it works:** Loads state, fetches live option snapshots for all 4 legs, computes: current mid price and delta for each short strike, cost-to-close per spread, percentage of max profit captured on each side, overall combined P&L. Warns visually if either short delta is approaching 0.35 (a heads-up before the 0.45 adjustment trigger fires). Also shows a full adjustment history and the last 10 closed trades.

---

### Daily Top-Up Checker (`daily_topup\`)

---

#### `daily_topup/topup_check.py`
**What it does:** Every weekday at 9:25 AM (5 minutes before market open),
checks whether either paper account has fallen below its target cash level.
If it has, alerts you with the exact amount to add and opens the Alpaca
dashboard in your browser automatically.

**How it works:**
- Calls Alpaca's `GET /v2/account` endpoint for account PA31HKOPMG4M
- Compares `cash` field to `TARGET_CASH` ($100,000)
- If below: prints a large visible warning with step-by-step instructions for
  topping up via the Alpaca web dashboard (there is no API endpoint for adding
  paper money — it must be done manually), calls `webbrowser.open()` to launch
  the dashboard URL, and fires a Windows toast notification using PowerShell
- Logs each check to `topup_log.json` and to a dated log file
- Skips if already run today (guards against Task Scheduler running it twice)

---

## Quick Reference: Which File to Edit for Common Changes

| What you want to change | File to edit |
|---|---|
| Add or remove a stock from trailing stop | `trailing_stop/config.py` → `WATCHED_STOCKS` |
| Change stop-loss or trailing stop % | `trailing_stop/config.py` → `STOP_LOSS_PCT`, `TRAIL_STOP_PCT` |
| Add or remove a politician | `copytrade/config.py` → `POLITICIANS` |
| Change how many copy-trade positions max | `copytrade/config.py` → `MAX_COPY_POSITIONS` |
| Change wheel option delta target | `flywheel/config.py` → `CSP_MAX_DELTA`, `CC_MAX_DELTA` |
| Change wheel early-close % | `flywheel/config.py` → `EARLY_CLOSE_PROFIT_PCT` |
| Add or remove a strangle stock | `strangle/config.py` → `WATCHED_STOCKS` |
| Change strangle earnings window | `strangle/config.py` → `EARNINGS_MIN_DAYS`, `EARNINGS_MAX_DAYS` |
| Change strangle profit/stop-loss target | `strangle/config.py` → `COMBINED_PROFIT_TARGET_PCT`, `COMBINED_STOP_LOSS_PCT` |
| Change notification email address | `config.py` in each strategy folder → `NOTIFY_EMAIL` |
