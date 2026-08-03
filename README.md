# Subhojit's Automated Trading Bot System

> **Paper Trading on Alpaca** — No real money is at risk.
> All strategies run automatically via Windows Task Scheduler.

---

## What is SETUP_PROMPT.md?

The file `copytrade/SETUP_PROMPT.md` is a **rebuild blueprint**. If this conversation with Claude is ever lost or a new session is needed, that file contains every credential, file path, lesson learned, and quick-reference command needed to recreate the entire copy-trading bot from scratch in one paste. Think of it as the "if this machine burns down" recovery document.

---

## System Overview

Five independent bots run on two separate Alpaca paper trading accounts:

```
┌──────────────────────────────────────────────────────────────────────────┐
│                        WINDOWS TASK SCHEDULER                            │
│                                                                          │
│  Every 30 min (9:30–4 PM)    Every 30 min (9:30–4 PM)       9:25 AM   │
│  ┌──────────────────────┐   ┌──────────────────────┐       ┌────────┐  │
│  │  Trailing Stop Bot   │   │  Copy Trading Bot    │       │ Daily  │  │
│  │  + Pharma Scanner    │   │  (Pelosi / McCaul)   │       │ Top-Up │  │
│  └──────────────────────┘   └──────────────────────┘       └────────┘  │
│                                                                          │
│  Every 30 min (9:30–4 PM)        4:00 PM daily                         │
│  ┌──────────────────────┐   ┌──────────────────────┐                   │
│  │  Wheel Strategy Bot  │   │  Wheel Daily Report  │                   │
│  │  (Options Flywheel)  │   │  (emailed to you)    │                   │
│  └──────────────────────┘   └──────────────────────┘                   │
│                                                                          │
│  Every 2 hours (market hours)                                           │
│  ┌──────────────────────────────────────────────────┐                  │
│  │  Strangle Bot (Bi-Directional Earnings Plays)    │                  │
│  │  • Monitors open strangles (sell legs at target) │                  │
│  │  • Scans for new entries only if earnings are    │                  │
│  │    14–21 days away — otherwise does nothing      │                  │
│  └──────────────────────────────────────────────────┘                  │
│                                                                          │
│  Every 30 min (market hours)                                            │
│  ┌──────────────────────────────────────────────────┐                  │
│  │  Iron Condor Bot (SPY — sell premium both sides) │                  │
│  │  • Bull put spread + bear call spread on SPY     │                  │
│  │  • Strikes placed at S/R levels, delta ≤ 0.20   │                  │
│  │  • 14 DTE entry, 50% profit target               │                  │
│  │  • Rolls threatened side if short delta → 0.45  │                  │
│  └──────────────────────────────────────────────────┘                  │
└──────────────────────────────────────────────────────────────────────────┘
         │                                    │
         ▼                                    ▼
  Account PA31HKOPMG4M               Account PA34EFPV3B80
  (Stocks only)                      (Stocks + Options)
  Trailing Stop + Copy Trade         Flywheel + Strangle + Iron Condor
```

---

## Two Alpaca Paper Accounts

| Account | ID | Used For | API Keys |
|---------|-----|----------|----------|
| Claude Trading | PA31HKOPMG4M | Trailing Stop + Copy Trades | PKMQDKH... |
| Paper Trading  | PA34EFPV3B80 | Wheel Strategy + Strangle + Iron Condor (Options) | PK5QNID... |

---

## Bot 1: Trailing Stop + Ladder Strategy

### What It Does
Buys 10 shares of each of 15 stocks and protects them with a trailing stop
while aggressively adding shares on dips (laddering in).

### The 15 Stocks
```
Trailing Stop Portfolio:   GOOGL  COHR  MU  AVGO  NBIS
                           KTOS   RKLB  GLW  NVDA  AMD

Pelosi Copy Trades:        PANW  AAPL  MSFT  VST  TEM
```

### The 4 Rules

| Rule | Trigger | Action |
|------|---------|--------|
| **Stop Loss** | Price drops 10% from entry | Sell ALL shares immediately |
| **Trailing Stop** | Price rises 10% from entry | Stop floor = 5% below highest price ever (never moves down) |
| **Ladder In** | Price drops 20% from entry | Buy 10 more shares (repeats every 5% further drop) |
| **Cash Guard** | Cash < $10,000 | Skip all buys, send alert email |

---

### Trailing Stop Strategy — Flow Diagram

```
┌─────────────────────────────────────────────────────────┐
│               BOT STARTS (every 30 min)                 │
└────────────────────────┬────────────────────────────────┘
                         │
                         ▼
              ┌──────────────────┐
              │  Market Open?    │──── NO ──→ Exit (no action)
              └────────┬─────────┘
                       │ YES
                       ▼
              ┌──────────────────┐
              │ Load State File  │
              │ Sync Positions   │
              └────────┬─────────┘
                       │
                       ▼
              ┌──────────────────────────┐
              │  Pharma Catalyst Scan    │
              │  (once per day, cached)  │
              │  Finviz + FDA RSS        │──→ Add pharma stocks to list
              └────────┬─────────────────┘
                       │
                       ▼
         ┌─────────────────────────────┐
         │  For Each Watched Stock...  │
         └─────────────┬───────────────┘
                       │
                       ▼
              ┌─────────────────┐
              │  Get Price Now  │
              └────────┬────────┘
                       │
          ┌────────────┼────────────────────┐
          │            │                    │
          ▼            ▼                    ▼
   ┌─────────────┐  ┌──────────────┐  ┌──────────────┐
   │ Price ≤     │  │ Price ≥      │  │ Price ≤      │
   │ Stop Price? │  │ Entry+10%?   │  │ Entry-20%?   │
   └──────┬──────┘  └──────┬───────┘  └──────┬───────┘
          │ YES             │ YES              │ YES
          ▼                 ▼                  ▼
   ┌─────────────┐  ┌──────────────┐  ┌──────────────┐
   │ SELL ALL    │  │ Activate     │  │ Cash ≥       │
   │ shares      │  │ Trailing     │  │ $10,000?     │
   │ Send email  │  │ Stop         │  └──────┬───────┘
   └─────────────┘  │              │         │ YES
                    │ Stop = Price │         ▼
                    │ × 0.95       │  ┌──────────────┐
                    │ (never down) │  │ BUY 10 more  │
                    └──────────────┘  │ shares       │
                                      │ Send email   │
                                      └──────────────┘
```

---

### Trailing Stop — Worked Example (NVDA)

**Starting position:** Buy 10 shares of NVDA at **$200.00**

```
Date       Price    Event                              Stop Floor    Shares
─────────────────────────────────────────────────────────────────────────────
Day 1      $200     Initial buy (10 shares)            $180.00       10
           ──── Stop loss set at 10% below entry ($200 × 0.90) ────
Day 5      $195     Normal fluctuation                 $180.00       10
Day 8      $210     Nothing yet (need 10% up first)    $180.00       10
Day 12     $220     +10% from entry → Trailing STARTS  $209.00       10
           ──── Stop now follows: $220 × 0.95 = $209 ────────────────
Day 15     $245     New high → stop raises             $232.75       10
           ──── $245 × 0.95 = $232.75 ──────────────────────────────
Day 18     $270     New high → stop raises             $256.50       10
           ──── $270 × 0.95 = $256.50 ──────────────────────────────
Day 20     $255     Price dips — stop does NOT move    $256.50       10
           ──── $255 < $256.50 → STOP TRIGGERED ────────────────────
Day 20     $255     SELL ALL 10 shares                 —             0

RESULT:  Bought at $200, sold at $255 = +$550 profit (+27.5%)
         Stop protected $1,350 of gains (vs $270 peak)
```

**What if NVDA had dropped instead?**
```
Day 1      $200     Initial buy                        $180.00       10
Day 5      $175     Down 12.5% — STOP HIT at $180!     —             —
           ──── SELL ALL at ~$180 ──────────────────────────────────
RESULT:  Max loss = -$200 (-10%)  ✓ Loss contained
```

**What if NVDA laddered in?**
```
Day 1      $200     Buy 10 shares                      $180.00       10
Day 10     $160     Down 20% → LADDER IN: Buy 10 more             20
           ──── New avg entry = ($200×10 + $160×10) / 20 = $180 ──
           ──── New stop = $180 × 0.90 = $162 ──────────────────────
Day 15     $152     Down another 5% from last ladder → Buy 10 more  30
           ──── Avg entry recalculated again ───────────────────────
Day 30     $210     Strong recovery — all 30 shares profitable ✓
```

---

## Bot 2: Wheel Strategy (Options Flywheel)

### What It Does
Generates income by selling options premium on 4 stocks:
**AVGO, COHR, NBIS, GLW** — running on account PA34EFPV3B80.

The "Wheel" cycles between two stages: selling puts → getting assigned → selling covered calls → shares called away → repeat.

### Delta Rules
Both legs use **delta < 0.25** — less than 25% probability of the option finishing in-the-money:

| Leg | Delta | Meaning |
|-----|-------|---------|
| Sell Put | \|delta\| < 0.25 | < 25% chance you get assigned the stock |
| Sell Call | delta < 0.25 | < 25% chance your shares get called away |

---

### Wheel Strategy — State Machine Diagram

```
                    ┌─────────────────────────────────┐
                    │              IDLE               │
                    │   Looking for a new trade       │◄──────────────────┐
                    └──────────────────┬──────────────┘                   │
                                       │                                   │
                    ┌──────────────────▼──────────────┐                   │
                    │         SELL PUT (CSP)           │                   │
                    │  Strike: 20% below stock price   │                   │
                    │  Delta:  < 0.25                  │                   │
                    │  Expiry: 2–4 weeks out           │                   │
                    │  Cash reserved as collateral     │                   │
                    └──────────────────┬──────────────┘                   │
                                       │                                   │
            ┌──────────────────────────┼──────────────────┐               │
            │                          │                  │               │
            ▼                          ▼                  ▼               │
   ┌──────────────────┐    ┌──────────────────┐  ┌──────────────┐         │
   │  70% PROFIT HIT  │    │  PUT EXPIRES     │  │  ASSIGNED    │         │
   │  Close early     │    │  WORTHLESS       │  │  Stock at    │         │
   │  +$420 example   │    │  Keep full prem  │  │  strike price│         │
   └────────┬─────────┘    └────────┬─────────┘  └──────┬───────┘         │
            │                       │                   │                 │
            └──────────┬────────────┘                   │                 │
                       │                                ▼                 │
                       │                   ┌─────────────────────────┐    │
                    Back to                │      SELL CALL (CC)      │    │
                    IDLE →                 │  Strike: 10% above price │    │
                    sell                   │  Delta:  < 0.25          │    │
                    new put                │  Expiry: 2–4 weeks       │    │
                                           └────────────┬────────────┘    │
                                                        │                 │
                           ┌────────────────────────────┼──────────┐      │
                           │                            │          │      │
                           ▼                            ▼          ▼      │
                  ┌──────────────────┐    ┌──────────────────┐  ┌──────┐  │
                  │  70% PROFIT HIT  │    │  CALL EXPIRES    │  │CALLED│  │
                  │  Close early     │    │  WORTHLESS       │  │ AWAY │  │
                  │  Keep stock      │    │  Keep stock      │  │Stock │  │
                  │  Sell new call   │    │  Sell new call   │  │ sold │  │
                  └──────────────────┘    └──────────────────┘  └──┬───┘  │
                           │                       │               │      │
                           └───────────────────────┘               └──────┘
                                  Stay in CC Stage              Back to IDLE
```

---

### Wheel Strategy — Worked Example (AVGO at $430)

**--- STAGE 1: Sell Cash-Secured Put ---**

```
Stock price today: $430.00
Target strike: $430 × 0.80 = $344.00  (20% below, delta ~0.22 ✓)
Expiry: 3 weeks out (21 days)

ACTION: Sell 1 AVGO Put @ $344 strike for $6.00 premium
Cash received:    $6.00 × 100 shares = $600
Cash reserved:    $344 × 100 shares  = $34,400 collateral
```

**Outcome A — Put Expires Worthless (most common, ~75% probability):**
```
3 weeks later: AVGO is at $418 (above $344 strike)
Put expires worthless — we keep $600 premium
Return: $600 / $34,400 = 1.7% in 3 weeks = ~30% annualised
→ Sell another put next week. Repeat.
```

**Outcome B — 70% Profit Close (before expiry):**
```
After 10 days: AVGO rose, put now worth $1.80 (was $6.00)
Profit so far: ($6.00 - $1.80) / $6.00 = 70% ✓  TARGET HIT
Buy to close at $1.80  →  profit = $4.20 × 100 = $420
Sell new put immediately at a fresh strike
```

**Outcome C — Assigned (AVGO dropped to $344):**
```
Expiry: AVGO closed at $342 (below $344 strike)
We are ASSIGNED: must buy 100 shares at $344

Cash paid:        $344 × 100 = $34,400
Premium received: $600 (already collected)
Effective cost:   $344 - $6.00 = $338/share  ← lower break-even!

→ Move to STAGE 2
```

**--- STAGE 2: Sell Covered Call ---**

```
We now hold 100 AVGO shares at effective cost $338/share
Current price: $344

Target strike: $344 × 1.10 = $378.40  (10% above, delta ~0.22 ✓)
Expiry: 3 weeks out

ACTION: Sell 1 AVGO Call @ $378.40 strike for $4.50 premium
Cash received:  $4.50 × 100 = $450
```

**Outcome D — Call Expires Worthless:**
```
3 weeks later: AVGO at $360 (below $378.40 strike)
Call expires worthless — keep $450 premium
Still hold 100 shares. Sell another covered call.
→ Stay in Stage 2, repeat.
```

**Outcome E — Shares Called Away (completing the wheel):**
```
Expiry: AVGO closed at $385 (above $378.40 strike)
Shares CALLED AWAY at $378.40

Stock profit:       ($378.40 - $338.00) × 100 =  $4,040
Put premium:                                    +   $600
Call premium:                                   +   $450
─────────────────────────────────────────────────────────
TOTAL CYCLE PROFIT:                              $5,090

→ Back to STAGE 1. Sell a new put. The Wheel turns again.
```

**Full Cycle Summary:**
```
┌─────────────────────────────────────────────────────────┐
│  AVGO Wheel Cycle — 6 weeks total                       │
│                                                         │
│  Stage 1: Sold put @ $344  →  +$600                    │
│  Stage 2: Sold call @ $378 →  +$450                    │
│  Stock gain (assigned → called away): +$4,040          │
│  ─────────────────────────────────────────────────────  │
│  Total profit: $5,090 on $34,400 collateral = 14.8%    │
│  Annualised: ~128% (paper trading — no real risk)      │
└─────────────────────────────────────────────────────────┘
```

---

## Bot 3: Copy Trading Bot (Politician Trades)

### What It Does
Monitors Capitol Trades every 30 minutes for new filings from 2 politicians
and automatically copies their trades (10 shares per stock, 1 contract per option).

### Politicians Monitored (in priority order)

| Rank | Politician | CT ID | Style |
|------|-----------|-------|-------|
| 1 | Nancy Pelosi (D-CA) | P000197 | High-conviction mega-cap tech |
| 2 | Michael McCaul (R-TX) | M001157 | Tech + defense |

> Ro Khanna was removed 2026-06-16 — reduced to the 2 highest-conviction sources.

### Rules
- **Max 10 copy positions** at any time
- **No short selling** — if a politician sells a stock you don't own, skip it
- **First run**: marks all historical trades as "seen" without ordering (prevents buying months of old history)
- **Wash trade guard**: skip sell if open buy order exists and no position held yet

---

## Bot 4: Bi-Directional Strangle Strategy (Earnings Plays)

### What It Does
2–3 weeks before a stock's earnings announcement, buys one OTM call and one OTM put
(a strangle) if the stock historically moves big on earnings and current IV is average or below.
Runs every **2 hours** (not 30 min — it only needs to check a few times per day).

### Entry Criteria (all must pass)
| Check | Rule |
|---|---|
| Earnings window | Earnings must be **14–21 days** away |
| Move history | Moved ≥ 4% on at least **4 of the last 8** earnings reports |
| IV filter | Current IV is at or below the **50th percentile** of own 60-day history |
| Contract | OTM call + put, delta ≈ **0.30**, expiry **~90 DTE** |

### Exit Rules
Judges the call + put **together** against total cost, never one leg alone — the
two legs move opposite each other on the same stock move, so watching only one
leg (e.g. "sell the call once it's up 15%") misrepresents the position's real
P&L and can lock in a leg's small gain while leaving the other leg's growing
loss with no exit plan at all. This check runs at all times, pre- and
post-earnings alike.
```
Combined value = call leg value + put leg value (locked-in proceeds for any
                 leg already sold, live mid price for any leg still open)

  Combined value ≥ +20% of total cost → close both legs, take the profit
  Combined value ≤ -20% of total cost → close both legs, cut the loss
```

### Stocks Watched
```
NVDA  AAPL  MSFT  GOOGL  AVGO  AMD  TSLA  META  AMZN  MU
PANW  COHR  MRVL  RKLB   NBIS
```

### State Machine
```
  ┌──────────────────────────────────────────────────────────┐
  │  Every 2-hour run                                        │
  ├──────────────────────────────────────────────────────────┤
  │  Phase 1 — Monitor open strangles:                       │
  │    Judge call + put TOGETHER vs. total cost, always      │
  │    ≥ +20% combined → close both, take profit             │
  │    ≤ -20% combined → close both, cut loss                │
  │                                                          │
  │  Phase 2 — Scan for new entries:                         │
  │    For each untraded stock:                              │
  │      earnings NOT in 14-21 day window? → skip, do nothing│
  │      earnings IN window?               → run all 3 checks│
  │        all pass → buy strangle                           │
  │        any fail → skip this cycle, recheck in 2 hours   │
  └──────────────────────────────────────────────────────────┘
```

### Files
```
strangle\
  config.py           ← all parameters
  bot.py              ← main engine (two-phase: monitor then scan)
  earnings_scanner.py ← yfinance earnings dates + historical move check
  iv_checker.py       ← rolling IV percentile filter (local JSON cache)
  option_selector.py  ← finds ~0.30 delta, ~90 DTE call + put via Alpaca
  state_manager.py    ← persists OPEN / CALL_SOLD / CLOSED states
  alpaca_client.py    ← Alpaca options API wrapper
  notifier.py         ← email alerts (open, combined close, IV skip)
  dashboard.py        ← terminal P&L view (run manually)
  strangle_state.json ← auto-generated live position state
  iv_history.json     ← auto-generated rolling IV history per symbol
  run_strangle.bat    ← launcher (called every 2 hours by Task Scheduler)
```

---

## Pharma Catalyst Scanner (Rule 5 of Trailing Stop)

Each morning at market open, the trailing stop bot scans 3 sources for biotech/pharma stocks with high-impact catalyst events:

```
┌─────────────────────────────────────────────────────────┐
│              PHARMA CATALYST SCANNER                    │
│              (runs once per day, cached)                │
├─────────────┬─────────────────┬────────────────────────┤
│ Finviz News │ Finviz Screener │ FDA Official RSS        │
│ finviz.com  │ Top biotech     │ fda.gov press releases  │
│ /news.ashx  │ movers today    │                        │
└──────┬──────┴────────┬────────┴────────────┬───────────┘
       │               │                     │
       └───────────────┴─────────────────────┘
                               │
                    ┌──────────▼──────────┐
                    │  Filter for events: │
                    │  ✅ FDA Approval    │
                    │  ✅ FDA Decision    │
                    │  ✅ Phase 3 Results │
                    │  ✅ Trial Readouts  │
                    │  ✅ Breakthrough    │
                    │  ❌ FDA Rejection   │ ← SKIPPED
                    └──────────┬──────────┘
                               │
                    ┌──────────▼──────────┐
                    │ Verify pharma sector│
                    │ (Finviz sector check│
                    └──────────┬──────────┘
                               │
                    ┌──────────▼──────────┐
                    │  Add to watch list  │
                    │  Buy 10 shares      │
                    │  Apply trailing     │
                    │  stop + ladder-in   │
                    │  Send email alert   │
                    └─────────────────────┘
```

---

## Daily Top-Up Checker

Runs at **9:25 AM** (5 minutes before market open) every weekday.

- Checks if cash balance < $100,000
- If below: calculates shortfall, opens Alpaca dashboard in browser, shows Windows toast notification, emails alert
- Note: Alpaca retail API has no cash injection endpoint — top-up must be done manually via the dashboard

---

## Email Notifications

All emails sent to **subhojitr@gmail.com** via Gmail SMTP.

| Bot | Event | Subject Format |
|-----|-------|---------------|
| Trailing Stop | Stop loss hit | `[TradingBot] STOP LOSS HIT: SELL ALL AMD (-10.1%)` |
| Trailing Stop | Ladder-in | `[TradingBot] LADDER IN: BUY MU x10 (down 22.3%)` |
| Trailing Stop | Pharma catalyst | `[TradingBot] PHARMA CATALYST: MRNA added (FDA_APPROVAL)` |
| Copy Trade | New trade copied | `[TradingBot] COPY TRADE: BUY NVDA x10 (Nancy Pelosi)` |
| Wheel Bot | New put sold | `[Flywheel] NEW CSP: SELL AVGO PUT $344` |
| Wheel Bot | New call sold | `[Flywheel] NEW CC: SELL AVGO CALL $378` |
| Wheel Bot | Assigned | `[Flywheel] ASSIGNED: AVGO – now hold 100 shares` |
| Wheel Bot | Called away | `[Flywheel] CALLED AWAY: AVGO shares sold at $378` |
| Wheel Bot | 70% profit | `[Flywheel] 70% PROFIT – Closed AVGO PUT early` |
| Wheel Bot | Daily report | `[Flywheel] Daily Report – 2026-05-29` |
| Strangle Bot | Strangle opened | `[Strangle] OPENED NVDA — earnings 2026-07-23` |
| Strangle Bot | Whole position closed | `[Strangle] CLOSED NVDA — combined profit target hit (+21.4%)` |
| Strangle Bot | IV too high, skipped | `[Strangle] SKIP NVDA — IV too high (73rd pct)` |
| Daily Top-Up | Low cash | `LOW CASH ALERT – add $X to reach $100,000` |

---

## Bot 5: Iron Condor (SPY — Sell Premium Both Sides)

### What It Does
Sells a bull-put spread and a bear-call spread simultaneously on SPY, collecting
a net credit upfront.  Profits if SPY stays inside the range between the two short
strikes through expiry (14 DTE).

### Structure
```
  Long Put          Short Put       [SPY price]     Short Call        Long Call
  (protection)      (sell, credit)                  (sell, credit)    (protection)
      |_________________|_______________|_______________|________________|
  lp_strike       sp_strike       ~$540          sc_strike         lc_strike
  (sp - $5)      (delta ≤ 0.20)                (delta ≤ 0.20)    (sc + $5)

  ← Max loss →  ← collect credit here: profit zone →             ← Max loss →
```

### Entry Rules (all must pass)
| Rule | Value |
|---|---|
| Underlying | SPY only |
| DTE at entry | 14 days (±2 days tolerance) |
| Short strike delta | ≤ 0.20 on both sides |
| S/R alignment | Short put placed just below nearest support; short call just above nearest resistance |
| Trend bias | If SPY above MA50, allow call delta up to 0.23; if below MA50, tighten to 0.17 |
| Minimum credit | ≥ 33% of wing width (e.g. ≥ $1.65 on a $5-wide condor) |
| Wing width | $5 on each side |

### How S/R Levels Are Found
The bot analyses 60 days of SPY daily candles and identifies three types of levels:
1. **Swing highs/lows** — price points where the high/low is the highest/lowest
   in a ±5 candle window (structural pivots)
2. **Moving averages** — 20-day, 50-day, and 200-day SMAs (dynamic S/R)
3. **Psychological levels** — every $5 increment near the current price (round numbers
   attract orders and act as magnets)

Nearby levels are clustered (merged if within $1.50) to avoid treating the same
zone as multiple levels.

### Management Rules
| Event | Action |
|---|---|
| Either short strike delta reaches **0.45** | Roll that spread ~$7.50 further OTM, same expiry |
| Roll costs more than $0.75/share debit | Close the whole condor instead |
| DTE < 4 when adjustment triggered | Close instead of rolling |
| Net profit reaches **50%** of original credit | Close — take the win |
| Cost to close = 2× original credit | Stop-loss — close to cap the loss |
| Expires worthless | Maximum profit — no close needed |

### Adjustment Detail (0.45 Delta Roll)
When a short strike's delta climbs from 0.20 → 0.45, it means SPY has moved
strongly toward that wing and the option is now at higher risk of going in-the-money.

```
BEFORE adjustment (put side example):
  Short put at $510  Δ=0.45  ← breached trigger
  Long  put at $505

AFTER roll ($7.50 lower):
  Old spread bought back  (pay market price)
  Short put at $502.50  Δ≈0.20  ← back to safe zone
  Long  put at $497.50

Net result: if the roll produces a credit → win.
            If it costs a small debit (≤$0.75) → still reduces max loss.
```

---

## Schedules at a Glance

| Task Name | Schedule | Window | Bot |
|-----------|----------|--------|-----|
| `TrailingStopBot` | Every 30 min | Mon–Fri 9:30–4 PM ET | Trailing Stop |
| `CopyTradingBot_Politicians` | Every 30 min | Mon–Fri 9:30–4 PM ET | Copy Trade (Pelosi + McCaul) |
| `WheelStrategyBot` | Every 30 min | Mon–Fri 9:30–4 PM ET | Wheel Options |
| `WheelStrategyReport` | Once at 4:00 PM | Mon–Fri | Daily Report |
| `DailyTopUpCheck` | Once at 9:25 AM | Mon–Fri | Balance Check |
| `StrangleBot` | Every 2 hours | Mon–Fri (market hours) | Strangle (Earnings Plays) |
| `StrangleReport` | Once at 4:00 PM | Mon–Fri | Strangle End-of-Day Report |
| `IronCondorBot` | Every 30 min | Mon–Fri (market hours) | Iron Condor on SPY |
| `IronCondorReport` | Once at 4:00 PM | Mon–Fri | Iron Condor End-of-Day Report |

---

## Configuration Files

| Setting | File | Key |
|---------|------|-----|
| Trailing stop % | `trailing_stop/config.py` | `STOP_LOSS_PCT` |
| Trail trigger % | `trailing_stop/config.py` | `TRAIL_TRIGGER_PCT` |
| Ladder-in drop % | `trailing_stop/config.py` | `LADDER_IN_DROP_PCT` |
| Watched stocks | `trailing_stop/config.py` | `WATCHED_STOCKS` |
| Max copy positions | `copytrade/config.py` | `MAX_COPY_POSITIONS` |
| Politicians to copy | `copytrade/config.py` | `POLITICIANS` |
| CSP strike discount | `flywheel/config.py` | `CSP_STRIKE_DISCOUNT` |
| CC strike premium | `flywheel/config.py` | `CC_STRIKE_PREMIUM` |
| Delta limit (both) | `flywheel/config.py` | `CSP_MAX_DELTA / CC_MAX_DELTA` |
| Early close % | `flywheel/config.py` | `EARLY_CLOSE_PROFIT_PCT` |
| Max pharma stocks | `trailing_stop/config.py` | `PHARMA_MAX_STOCKS` |
| Strangle stocks | `strangle/config.py` | `WATCHED_STOCKS` |
| Strangle earnings window | `strangle/config.py` | `EARNINGS_MIN_DAYS / EARNINGS_MAX_DAYS` |
| Strangle IV threshold | `strangle/config.py` | `IV_PERCENTILE_THRESHOLD` |
| Strangle combined profit target | `strangle/config.py` | `COMBINED_PROFIT_TARGET_PCT` |
| Strangle combined stop-loss | `strangle/config.py` | `COMBINED_STOP_LOSS_PCT` |
| Strangle delta target | `strangle/config.py` | `TARGET_DELTA` |
| Strangle DTE target | `strangle/config.py` | `TARGET_DTE` |
| Iron Condor DTE | `ironcondor/config.py` | `TARGET_DTE` |
| Iron Condor max delta | `ironcondor/config.py` | `MAX_SHORT_DELTA` |
| Iron Condor wing width | `ironcondor/config.py` | `WING_WIDTH` |
| Iron Condor adjust trigger | `ironcondor/config.py` | `ADJUST_DELTA` |
| Iron Condor profit target | `ironcondor/config.py` | `PROFIT_TARGET_PCT` |
| Iron Condor S/R on/off | `ironcondor/config.py` | `USE_SR_LEVELS` |
