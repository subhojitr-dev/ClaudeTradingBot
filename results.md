# TradingBot — Email Output & Error Log Reference

All emails use the subject prefix **`TradingBot:`** so a single Gmail filter catches everything.  
All emails are also saved locally to `email_archive/YYYY-WW/` and deleted every Monday at 8 AM.

---

## Local Email Archive

| Item | Detail |
|------|--------|
| Location | `C:\Users\subho\tradingbot\email_archive\YYYY-WW\` |
| File naming | `YYYYMMDD_HHMMSS_<subject-slug>.html` |
| Retention | Current week only — previous weeks deleted every Monday at 08:00 |
| Cleanup task | `WeeklyEmailCleanup` in Windows Task Scheduler |
| Cleanup log | `C:\Users\subho\tradingbot\logs\weekly_cleanup.log` |

Example archive path:
```
email_archive/
  2026-W25/
    20260619_093012_TradingBot_IronCondor_OPENED_SPY.html
    20260619_160001_TradingBot_IronCondor_Daily_Report.html
  2026-W26/          ← current week (kept)
    ...
```

---

## Strategy 1 — Iron Condor (SPY · IWM · GLD)

**Bot runs:** Every 30 minutes, Mon–Fri 9:30 AM – 4:00 PM ET  
**Report runs:** 4:00 PM ET, Mon–Fri  
**Log file:** `ironcondor/logs/ironcondor_YYYYMMDD.log`  
**Error log:** `ironcondor/logs/errors_YYYYMMDD.log`

| Trigger | Subject | When sent |
|---------|---------|-----------|
| New condor opened | `TradingBot: [IronCondor] OPENED SPY $530/525P · $565/570C exp 2026-07-03 credit=$1.70` | When 4-leg order is placed for SPY, IWM, or GLD |
| Short strike hit 0.45 delta | `TradingBot: [IronCondor] ADJUSTMENT — SPY PUT side rolled $530 → $520 (11 DTE)` | When a threatened spread is rolled further OTM |
| Profit target or stop-loss | `TradingBot: [IronCondor] CLOSED SPY — PROFIT +$85 \| 50% profit target` | When position exits for any reason |
| Daily report | `TradingBot: [IronCondor] Daily Report — 2026-06-19 SPY · IWM · GLD` | 4:00 PM every trading day |

**What goes in the error log:**
- `Clock check failed` — Alpaca API unreachable at startup
- `Price fetch failed for SPY` — cannot get current stock price
- `Order placement failed` — Alpaca rejected a 4-leg entry order
- `Close orders failed` — could not buy back the condor to close
- `Roll orders failed` — could not execute the roll to new strikes

---

## Strategy 2 — Strangle (Earnings Play)

**Bot runs:** Every 2 hours, Mon–Fri 9:30 AM – 4:00 PM ET  
**Report runs:** 4:00 PM ET, Mon–Fri  
**Log file:** `strangle/logs/strangle_YYYYMMDD.log`  
**Error log:** `strangle/logs/errors_YYYYMMDD.log`

| Trigger | Subject | When sent |
|---------|---------|-----------|
| New strangle entered | `TradingBot: [Strangle] OPENED NVDA — earnings 2026-07-01` | When call + put are purchased 14–21 days before earnings |
| Call rose 15%+ pre-earnings | `TradingBot: [Strangle] CALL SOLD NVDA — +16.2% pre-earnings` | When call leg hits profit target |
| Put rose 10%+ post-earnings | `TradingBot: [Strangle] CLOSED NVDA — PROFIT +$312` | When put leg is sold and trade is fully closed |
| IV too high to enter | `TradingBot: [Strangle] SKIP NVDA — IV too high (72nd percentile)` | When earnings window is right but IV is elevated |
| Daily report | `TradingBot: [Strangle] Daily Report — 2026-06-19` | 4:00 PM every trading day |

**What goes in the error log:**
- `Clock check failed` — Alpaca API unreachable at startup
- `order placement failed` — could not buy the call or put
- `sell call failed` — could not close the call leg
- `sell put failed` — could not close the put leg
- `Cannot fetch positions` — Alpaca positions endpoint failed

---

## Strategy 3 — Flywheel / Wheel Strategy

**Bot runs:** Every 30 minutes, Mon–Fri 9:30 AM – 4:00 PM ET  
**Report runs:** 4:00 PM ET, Mon–Fri  
**Log file:** `flywheel/logs/flywheel_YYYYMMDD.log`  
**Error log:** *(errors logged to same daily file — see ERROR lines)*

| Trigger | Subject | When sent |
|---------|---------|-----------|
| Cash-secured put sold | `TradingBot: [Flywheel] CSP OPENED — SELL AAPL PUT $185 premium $112.00` | Stage 1 entry |
| Put expired worthless | `TradingBot: [Flywheel] PUT EXPIRED WORTHLESS — AAPL +$112.00` | Best case: keep full premium |
| Put assigned | `TradingBot: [Flywheel] ASSIGNED — AAPL 100 shares at $185 cost basis $183.88` | Moving to Stage 2 |
| Put rolled to higher strike | `TradingBot: [Flywheel] PUT ROLLED UP — AAPL $185 → $190 +$45.00` | Stock rose, roll for more premium |
| Put closed at 70% profit | `TradingBot: [Flywheel] CSP CLOSED EARLY — AAPL +$78.00 (70% profit)` | Early exit to free capital |
| Covered call sold | `TradingBot: [Flywheel] CC OPENED — SELL AAPL CALL $200 premium $95.00` | Stage 2 entry |
| Shares called away | `TradingBot: [Flywheel] CALLED AWAY — AAPL 100 shares sold at $200 P&L +$1,612` | Back to Stage 1 |
| Call expired worthless | `TradingBot: [Flywheel] CALL EXPIRED WORTHLESS — AAPL +$95.00` | Keep stock, sell new call |
| Call closed at 70% profit | `TradingBot: [Flywheel] CC CLOSED EARLY — AAPL +$66.50 (70% profit)` | Early exit, sell new call sooner |
| Insufficient cash for CSP | `TradingBot: [Flywheel] SKIPPED AAPL — insufficient cash (need $18,500, have $12,000)` | Only when cash is genuinely too low |
| Daily report | `TradingBot: [Flywheel] Daily Report — 2026-06-19` | 4:00 PM every trading day |

**What goes in the error log:**
- `Cannot reach Alpaca` — API unreachable, bot exits
- `CSP order failed` — could not place the put sell order
- `buy-to-close failed` — could not close the put at 70% profit
- `roll-up failed` — could not execute the roll to higher strike
- `CC order failed` — could not place the covered call sell order
- `CC buy-to-close failed` — could not close the call at 70% profit

---

## Strategy 4 — Copy Trade (Politician Trades)

**Bot runs:** Every 30 minutes, Mon–Fri 9:30 AM – 4:00 PM ET  
**Log file:** `copytrade/logs/bot_YYYYMMDD.log`  
**Politicians tracked:** Nancy Pelosi, Michael McCaul

| Trigger | Subject | When sent |
|---------|---------|-----------|
| New politician trade filed | `TradingBot: [CopyTrade] BUY NVDA x5 — Nancy Pelosi` | When Capitol Trades shows a new filing |

**What goes in the error log:**
- API or scraper failures are logged as ERROR in the daily bot log

---

## Strategy 5 — Trailing Stop (Stocks + Pharma)

**Bot runs:** Every 30 minutes, Mon–Fri 9:30 AM – 4:00 PM ET  
**Log file:** `trailing_stop/logs/trailing_YYYYMMDD.log`

| Trigger | Subject | When sent |
|---------|---------|-----------|
| Pharma catalyst detected | `TradingBot: [TrailingStop] PHARMA CATALYST — MRNA added (FDA Approval)` | When FDA approval, Phase 3 result, or breakthrough designation is found |
| Stop loss triggered | `TradingBot: [TrailingStop] STOP LOSS HIT — SELL ALL AAPL (+2.1%)` | Rule 1: price fell to or below trailing stop level |
| Ladder in triggered | `TradingBot: [TrailingStop] LADDER IN — BUY MSFT x10 (down 22.4%)` | Rule 3: price dropped 20%+ from entry, adding shares |

**What goes in the error log:**
- `Cannot reach Alpaca` — API unreachable at startup
- `Initial buy failed` — could not place the first buy order
- `Stop loss sell failed` — could not execute the stop-loss sell
- `Ladder-in failed` — could not place the ladder-in buy order
- `Pharma catalyst scan error` — scraper or network failure (non-fatal, bot continues)

---

## Daily Report Schedule (All Strategies)

| Time | Email |
|------|-------|
| 4:00 PM ET | `TradingBot: [IronCondor] Daily Report` |
| 4:00 PM ET | `TradingBot: [Strangle] Daily Report` |
| 4:00 PM ET | `TradingBot: [Flywheel] Daily Report` |

Copy Trade and Trailing Stop do not have daily reports — they only email on real events.

---

## Error Log Summary

| Log file | What triggers an ERROR entry |
|----------|------------------------------|
| `ironcondor/logs/errors_YYYYMMDD.log` | API unreachable, order placement failure, price fetch failure, close/roll order failure |
| `strangle/logs/errors_YYYYMMDD.log` | API unreachable, order placement failure, position fetch failure |
| `copytrade/logs/bot_YYYYMMDD.log` | Scraper failures, API failures (ERROR lines within the combined log) |
| `trailing_stop/logs/trailing_YYYYMMDD.log` | API failures, buy/sell order failures (ERROR lines within the combined log) |
| `flywheel/logs/flywheel_YYYYMMDD.log` | API failures, order failures (ERROR lines within the combined log) |

> Iron Condor and Strangle have a **dedicated** `errors_YYYYMMDD.log` containing only ERROR-level
> messages — easy to check at a glance each morning. The other three bots write errors into their
> main daily log; search for the word `ERROR` to find them.

---

## Gmail Filter

Create one filter to label everything:

| Field | Value |
|-------|-------|
| **From** | `subhojitr@gmail.com` |
| **Subject contains** | `TradingBot:` |
| **Apply label** | `Trading Bot` |
| **Skip inbox** | Optional — uncheck if you want alerts to appear |
