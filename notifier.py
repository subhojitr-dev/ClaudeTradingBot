"""
notifier.py  --  Shared email notification utility
===================================================
Used by both the copy-trading bot and the trailing-stop bot.

Gmail setup (one-time):
  1. Go to https://myaccount.google.com/apppasswords
  2. Create an App Password for "Mail / Windows Computer"
  3. Paste the 16-char password into SMTP_PASSWORD in each config.py
"""

import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timezone

log = logging.getLogger(__name__)


def send_email(
    subject: str,
    body: str,
    to: str,
    smtp_host: str,
    smtp_port: int,
    smtp_user: str,
    smtp_password: str,
) -> bool:
    """
    Send a plain-text email via SMTP (TLS).
    Returns True on success, False on failure.
    If smtp_password is empty the call is silently skipped.
    """
    # Strip spaces — Gmail app passwords are displayed with spaces for readability
    smtp_password = smtp_password.replace(" ", "")
    if not smtp_password:
        log.warning("Email skipped -- SMTP_PASSWORD not configured in config.py")
        return False
    try:
        msg = MIMEMultipart()
        msg["From"]    = smtp_user
        msg["To"]      = to
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))

        with smtplib.SMTP(smtp_host, smtp_port, timeout=15) as server:
            server.ehlo()
            server.starttls()
            server.login(smtp_user, smtp_password)
            server.send_message(msg)

        log.info("Email sent >> %s", subject)
        return True
    except Exception as e:
        log.error("Email send failed: %s", e)
        return False


# ── Pre-formatted email builders ──────────────────────────────────────────────

def notify_copy_trade(
    politician: str, action: str, symbol: str, qty: int,
    price_ref: float, order_id: str, cfg: object,
) -> None:
    """Send notification when a politician copy trade is placed."""
    subject = f"[TradingBot] COPY TRADE: {action.upper()} {symbol} x{qty} ({politician})"
    body = f"""
Trading Bot — Copy Trade Alert
===============================
Time (UTC) : {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')}
Politician : {politician}
Action     : {action.upper()}
Symbol     : {symbol}
Qty        : {qty} shares
Price ref  : ${price_ref:.2f}  (market order)
Order ID   : {order_id}

This trade was automatically copied from {politician}'s Capitol Trades filing.
"""
    send_email(
        subject, body.strip(), cfg.NOTIFY_EMAIL,
        cfg.SMTP_HOST, cfg.SMTP_PORT, cfg.SMTP_USER, cfg.SMTP_PASSWORD,
    )


def notify_ladder_in(
    symbol: str, qty: int, price: float, drop_pct: float,
    ladder_num: int, new_stop: float, new_entry: float, order_id: str, cfg: object,
) -> None:
    """Send notification when trailing-stop bot ladders into a position."""
    subject = f"[TradingBot] LADDER IN: BUY {symbol} x{qty}  (down {drop_pct:.1f}%)"
    body = f"""
Trading Bot — Ladder-In Alert
==============================
Time (UTC)   : {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')}
Symbol       : {symbol}
Action       : BUY {qty} more shares (Ladder #{ladder_num})
Price ref    : ${price:.2f}
Drop from entry: {drop_pct:.1f}%
New avg entry: ${new_entry:.2f}
New stop loss: ${new_stop:.2f}
Order ID     : {order_id}

Rule 3 triggered: price dropped >{drop_pct:.1f}% from entry -- adding shares.
"""
    send_email(
        subject, body.strip(), cfg.NOTIFY_EMAIL,
        cfg.SMTP_HOST, cfg.SMTP_PORT, cfg.SMTP_USER, cfg.SMTP_PASSWORD,
    )


def notify_stop_loss(
    symbol: str, qty: int, price: float, stop: float,
    pct_from_entry: float, order_id: str, cfg: object,
) -> None:
    """Send notification when trailing-stop bot hits a stop loss."""
    subject = f"[TradingBot] STOP LOSS HIT: SELL ALL {symbol}  ({pct_from_entry:+.1f}%)"
    body = f"""
Trading Bot — Stop Loss Alert
==============================
Time (UTC)   : {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')}
Symbol       : {symbol}
Action       : SELL ALL {qty} shares
Current price: ${price:.2f}
Stop level   : ${stop:.2f}
P&L vs entry : {pct_from_entry:+.1f}%
Order ID     : {order_id}

Rule 1 triggered: price fell to/below stop loss -- full position sold.
"""
    send_email(
        subject, body.strip(), cfg.NOTIFY_EMAIL,
        cfg.SMTP_HOST, cfg.SMTP_PORT, cfg.SMTP_USER, cfg.SMTP_PASSWORD,
    )
