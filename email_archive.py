"""
email_archive.py  --  Local HTML email archive for all TradingBot notifications

Every email sent by any bot is also saved to:
  tradingbot/email_archive/YYYY-WW/YYYYMMDD_HHMMSS_<slug>.html

Weekly cleanup: call cleanup() on Monday morning to delete all folders
except the current week. Registered in Task Scheduler as WeeklyEmailCleanup.
"""

import os
import re
import shutil
import logging
from datetime import date, datetime

log = logging.getLogger(__name__)

# Root of the archive — always relative to this file so it works from any cwd
_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "email_archive")


def _week_folder() -> str:
    """Return path for the current ISO week folder, creating it if needed."""
    today = date.today()
    folder = os.path.join(_ROOT, f"{today.year}-W{today.isocalendar()[1]:02d}")
    os.makedirs(folder, exist_ok=True)
    return folder


def _slug(subject: str) -> str:
    """Turn an email subject into a safe filename segment (max 60 chars)."""
    s = re.sub(r"[^\w\s-]", "", subject)
    s = re.sub(r"\s+", "_", s.strip())
    return s[:60]


def save(subject: str, html: str) -> None:
    """Save an email to the current week's archive folder."""
    try:
        folder    = _week_folder()
        ts        = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename  = f"{ts}_{_slug(subject)}.html"
        filepath  = os.path.join(folder, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(f"<!-- Subject: {subject} -->\n")
            f.write(html)
        log.info("Email archived: %s", filepath)
    except Exception as e:
        log.warning("Email archive save failed (non-fatal): %s", e)


def cleanup() -> None:
    """
    Delete all weekly archive folders except the current week.
    Called every Monday morning by the WeeklyEmailCleanup scheduled task.
    """
    if not os.path.isdir(_ROOT):
        log.info("Email archive folder does not exist yet — nothing to clean.")
        return

    today       = date.today()
    current_wk  = f"{today.year}-W{today.isocalendar()[1]:02d}"
    deleted     = []
    kept        = []

    for entry in os.listdir(_ROOT):
        full = os.path.join(_ROOT, entry)
        if not os.path.isdir(full):
            continue
        if entry == current_wk:
            kept.append(entry)
        else:
            try:
                shutil.rmtree(full)
                deleted.append(entry)
                log.info("Deleted old email archive folder: %s", entry)
            except Exception as e:
                log.warning("Could not delete %s: %s", entry, e)

    log.info("Email archive cleanup done. Deleted: %s  Kept: %s",
             deleted or "none", kept or "none")
    print(f"[WeeklyCleanup] Deleted {len(deleted)} old week(s): {deleted}")
    print(f"[WeeklyCleanup] Kept current week: {kept}")


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s  %(levelname)s  %(message)s")
    cleanup()
    sys.exit(0)
