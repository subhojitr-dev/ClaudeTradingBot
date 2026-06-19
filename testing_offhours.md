# Off-Hours Notification Testing

## When and Why

The live bots cannot be tested during market hours without real capital at risk, and during
off-hours (evenings, weekends, holidays) the bots exit immediately after the market-open
check — no trading logic runs, no emails are sent.

To verify the full email pipeline (SMTP delivery, HTML rendering, local archive) without
waiting for the market, a standalone test script was created that calls every notifier
function directly with realistic synthetic data.

---

## What Was Run

**Script:** `C:\Users\subho\tradingbot\test_notifications.py`  
**Run date:** 2026-06-19 (Juneteenth — US market holiday)  
**Run by:** Manual execution from PowerShell:
```
cd C:\Users\subho\tradingbot
python test_notifications.py
```

**Result:** 23 HTML emails sent to subhojitr@gmail.com with zero errors.  
**Archive:** 23 HTML files saved to `email_archive\2026-W25\`

---

## How the Data Was Generated

The script bypasses all Alpaca API calls, market-open checks, and state files.
It imports each strategy's notifier module directly and calls every notification
function with hardcoded realistic values. No orders are placed, no positions are
opened or closed.

| Strategy | Notifications tested | Sample data basis |
|----------|---------------------|-------------------|
| Iron Condor | Opened, Adjustment, Closed, Daily Report | SPY @ $547, IWM condor, realistic strikes/credits |
| Strangle | Opened, Call Sold, Put Sold, IV Skip | NVDA earnings play, AMZN IV skip |
| Flywheel | CSP Opened/Expired/Assigned/Rolled/Closed Early, CC Opened/Called Away/Expired/Closed Early, Skipped | AAPL and MSFT wheel cycles, TSLA cash skip |
| Copy Trade | Buy, Sell | Nancy Pelosi NVDA buy, McCaul MSFT sell |
| Trailing Stop | Stop Loss, Ladder In, Pharma Catalyst | AMGN stop + ladder, MRNA FDA approval |

---

## What the Test Verified

- SMTP login and delivery via Gmail app password
- `MIMEMultipart("alternative")` plain + HTML parts render correctly in Gmail
- All subject lines carry the `TradingBot:` prefix for Gmail filter compatibility
- `email_archive.save()` writes correctly named HTML files to the ISO-week folder
- Module isolation (`sys.path` manipulation) correctly loads each strategy's own
  `notifier.py` rather than the shared root `tradingbot/notifier.py`

---

## What the Test Did NOT Verify

- Actual trade logic (strike selection, delta checks, profit/loss calculations)
- Alpaca order placement or position management
- State file reads/writes (open positions, premium tracking)
- The market-open clock check
- Real option prices or Greeks — all values are synthetic

These can only be verified during live market hours when Task Scheduler fires the real bots.

---

## Re-running the Test

The script is safe to run at any time — it sends real emails but makes no API calls
and modifies no state. Each run adds ~23 files to the current week's archive folder.

```
cd C:\Users\subho\tradingbot
python test_notifications.py
```
