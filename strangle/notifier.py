"""
notifier.py  --  Email alerts for the strangle bot
"""

import smtplib
import sys
import os
from email.mime.text import MIMEText
from config import NOTIFY_EMAIL, SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD


def send_email(subject: str, body: str) -> None:
    msg            = MIMEText(body)
    msg["Subject"] = subject
    msg["From"]    = SMTP_USER
    msg["To"]      = NOTIFY_EMAIL
    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as s:
            s.starttls()
            s.login(SMTP_USER, SMTP_PASSWORD.replace(" ", ""))
            s.send_message(msg)
    except Exception as e:
        print(f"[notifier] Email send failed: {e}", file=sys.stderr)


def notify_strangle_opened(symbol: str, earnings_date: str, call: str, put: str,
                            call_price: float, put_price: float, total_cost: float) -> None:
    send_email(
        f"[Strangle] OPENED {symbol} — earnings {earnings_date}",
        f"Strangle opened on {symbol}\n\n"
        f"  Earnings date : {earnings_date}\n"
        f"  CALL contract : {call}  @ ${call_price:.2f}\n"
        f"  PUT  contract : {put}   @ ${put_price:.2f}\n"
        f"  Total cost    : ${total_cost:.2f}\n\n"
        f"Monitoring: sell CALL if +15%, sell PUT after earnings if +10%.",
    )


def notify_call_sold(symbol: str, contract: str, entry: float, exit_price: float,
                     gain_pct: float) -> None:
    pnl = (exit_price - entry) * 100
    send_email(
        f"[Strangle] CALL SOLD {symbol} — +{gain_pct:.1%} pre-earnings",
        f"Call leg sold on {symbol} before earnings.\n\n"
        f"  Contract   : {contract}\n"
        f"  Entry      : ${entry:.2f}\n"
        f"  Exit       : ${exit_price:.2f}\n"
        f"  Gain       : +{gain_pct:.1%}  (${pnl:.2f})\n\n"
        f"Holding PUT through earnings. Will sell if PUT rises 10%.",
    )


def notify_put_sold(symbol: str, contract: str, entry: float, exit_price: float,
                    gain_pct: float, net_pnl: float) -> None:
    send_email(
        f"[Strangle] PUT SOLD {symbol} — +{gain_pct:.1%} post-earnings",
        f"Put leg sold on {symbol} after earnings.\n\n"
        f"  Contract   : {contract}\n"
        f"  Entry      : ${entry:.2f}\n"
        f"  Exit       : ${exit_price:.2f}\n"
        f"  Gain       : +{gain_pct:.1%}\n"
        f"  Net P&L    : ${net_pnl:.2f}  (both legs combined)\n\n"
        f"Strangle is now fully closed.",
    )


def notify_iv_skip(symbol: str, iv: float, pct: float, threshold: float) -> None:
    send_email(
        f"[Strangle] SKIP {symbol} — IV too high ({pct:.0f}th pct)",
        f"{symbol} meets earnings criteria but IV is elevated — skipping entry.\n\n"
        f"  Current IV         : {iv:.1%}\n"
        f"  IV percentile rank : {pct:.0f}th\n"
        f"  Threshold          : ≤ {threshold:.0f}th percentile\n\n"
        f"Will recheck on next run.",
    )
