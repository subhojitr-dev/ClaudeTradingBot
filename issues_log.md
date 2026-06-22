# TradingBot — Issues Log

All issues found during pre-production review on 2026-06-22.
Status column: FIXED / OPEN / WONTFIX

---

## Issue 001 — Flywheel options snapshot 404 (FIXED 2026-06-22)

| Field | Detail |
|-------|--------|
| **Severity** | Critical |
| **File** | `flywheel/alpaca_client.py:143` |
| **Discovered** | Live log error on first market open (Mon 2026-06-22) |
| **Status** | FIXED — commit c0ab4f0 |

**Root cause:** Alpaca options snapshot data lives under `/v1beta1`, not `/v2`.  
The `ALPACA_DATA_URL` constant pointed at `https://data.alpaca.markets/v2`, so  
`/v2/options/snapshots` returned HTTP 404 on every call. The Flywheel bot could  
not price any CSP or CC candidates — no trades would ever be placed.

**Fix:** Added `ALPACA_OPTIONS_DATA_URL = "https://data.alpaca.markets/v1beta1"`  
to `flywheel/config.py` and switched the snapshot call to use it.

---

## Issue 002 — Iron Condor options snapshot 404 (FIXED 2026-06-22)

| Field | Detail |
|-------|--------|
| **Severity** | Critical |
| **File** | `ironcondor/alpaca_client.py:125` |
| **Discovered** | Pre-production code review |
| **Status** | FIXED — this commit |

**Root cause:** Same v2/v1beta1 mismatch as Issue 001. Iron Condor would fail to  
fetch option Greeks/pricing for all 4 legs of every condor — no entry or exit  
decisions could be made.

**Fix:** Added `_OPTIONS_DATA_URL = "https://data.alpaca.markets/v1beta1"` directly  
in `ironcondor/alpaca_client.py` and switched the snapshot call to use it.

---

## Issue 003 — Strangle options snapshot 404 (FIXED 2026-06-22)

| Field | Detail |
|-------|--------|
| **Severity** | Critical |
| **File** | `strangle/alpaca_client.py:114` |
| **Discovered** | Pre-production code review |
| **Status** | FIXED — this commit |

**Root cause:** Same v2/v1beta1 mismatch as Issue 001. Strangle bot could not  
fetch option prices for call/put legs — entry and exit decisions would fail silently.

**Fix:** Added `_OPTIONS_DATA_URL = "https://data.alpaca.markets/v1beta1"` in  
`strangle/alpaca_client.py` and switched the snapshot call to use it.

---

## Issue 004 — State files created in wrong directory under Task Scheduler (FIXED 2026-06-22)

| Field | Detail |
|-------|--------|
| **Severity** | Critical |
| **Files** | `ironcondor/state_manager.py`, `strangle/state_manager.py`, `flywheel/state_manager.py`, `trailing_stop/state_manager.py`, `copytrade/trade_tracker.py` |
| **Discovered** | Pre-production code review |
| **Status** | FIXED — this commit |

**Root cause:** All config files set `STATE_FILE = "ironcondor_state.json"` as a  
relative path. When Task Scheduler fires a bot with a working directory different  
from the bot's folder, `open(STATE_FILE)` creates/reads the JSON in the wrong  
location. On every subsequent run the bot would start with empty state — treating  
every open position as if it didn't exist, potentially double-entering trades.

**Fix:** Each state manager now resolves relative paths against its own `__file__`  
directory at startup using `os.path.join(_DIR, filepath)`. Absolute paths pass  
through unchanged. No config changes needed.

---

## Issue 005 — Strangle history IndexError on empty history (OPEN)

| Field | Detail |
|-------|--------|
| **Severity** | Low |
| **File** | `strangle/bot.py` — any line referencing `state["history"][-1]` |
| **Discovered** | Pre-production code review |
| **Status** | OPEN — only occurs if code tries to read last history entry before any trade has ever closed |

**Root cause:** `state["history"][-1]` raises `IndexError` if the history list is  
empty (i.e., the very first run before any strangle has ever been closed).

**Impact:** Low — only a risk on the very first run and only if code explicitly  
accesses history[-1]. Current strangle bot does not appear to call this path on  
a fresh state, but worth fixing defensively.

**Recommended fix:**
```python
last = state["history"][-1] if state["history"] else {}
```

---

## Summary

| # | Issue | Severity | Status |
|---|-------|----------|--------|
| 001 | Flywheel options snapshot 404 (v2 vs v1beta1) | Critical | FIXED |
| 002 | Iron Condor options snapshot 404 (v2 vs v1beta1) | Critical | FIXED |
| 003 | Strangle options snapshot 404 (v2 vs v1beta1) | Critical | FIXED |
| 004 | State files in wrong directory under Task Scheduler | Critical | FIXED |
| 005 | Strangle history IndexError on empty history | Low | OPEN |
