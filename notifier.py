"""
notifier.py  --  Shared HTML email notification utility
========================================================
Used by the copy-trade bot and the trailing-stop bot.

Functions:
  notify_copy_trade        -- politician trade copied
  notify_stop_loss         -- trailing stop triggered, full position sold
  notify_ladder_in         -- price dropped, adding shares (Rule 3)
  notify_pharma_catalyst   -- pharma stock added to watch list
  send_email               -- low-level plain/HTML send (kept for compatibility)
"""

import re
import smtplib
import logging
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import email_archive
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

log = logging.getLogger(__name__)

_CSS = """
  body { font-family: Arial, sans-serif; background: #f4f4f4; margin: 0; padding: 20px; }
  .card { background: #ffffff; border-radius: 8px; max-width: 640px; margin: 0 auto;
          padding: 24px; box-shadow: 0 2px 8px rgba(0,0,0,.12); }
  h2   { margin: 0 0 4px 0; font-size: 20px; }
  .sub { color: #666; font-size: 13px; margin-bottom: 20px; }
  .section { margin-top: 18px; }
  .section-title { font-weight: bold; font-size: 13px; color: #444;
                   text-transform: uppercase; letter-spacing: .5px;
                   border-bottom: 1px solid #e0e0e0; padding-bottom: 4px; margin-bottom: 10px; }
  table  { width: 100%; border-collapse: collapse; font-size: 14px; }
  th     { text-align: left; background: #f0f0f0; padding: 6px 8px; font-size: 12px; color: #555; }
  td     { padding: 6px 8px; border-bottom: 1px solid #f0f0f0; }
  .mono  { font-family: monospace; font-size: 13px; }
  .green { color: #1a7a1a; font-weight: bold; }
  .red   { color: #c0392b; font-weight: bold; }
  .amber { color: #d68910; font-weight: bold; }
  .pill  { display: inline-block; padding: 2px 10px; border-radius: 12px;
            font-size: 12px; font-weight: bold; }
  .pill-green  { background: #d4edda; color: #155724; }
  .pill-red    { background: #f8d7da; color: #721c24; }
  .pill-blue   { background: #cce5ff; color: #004085; }
  .pill-amber  { background: #fff3cd; color: #856404; }
  .pill-purple { background: #e2d9f3; color: #4a1e9e; }
  .kv    { display: flex; justify-content: space-between; padding: 4px 0;
           font-size: 14px; border-bottom: 1px solid #f5f5f5; }
  .kv .k { color: #555; }
  .kv .v { font-weight: bold; }
  .highlight { background: #d4edda; border-radius: 6px; padding: 10px;
               font-size: 14px; color: #155724; margin-top: 10px; }
  .warn-box  { background: #f8d7da; border-radius: 6px; padding: 10px;
               font-size: 14px; color: #721c24; margin-top: 10px; }
  .footer { margin-top: 20px; font-size: 11px; color: #aaa; text-align: center; }
"""


def _wrap(title: str, badge_html: str, body_html: str, footer: str = "Trading Bot") -> str:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<style>{_CSS}</style></head><body>
<div class="card">
  <h2>{title}</h2>
  <div class="sub">{badge_html} &nbsp; {ts}</div>
  {body_html}
  <div class="footer">{footer} &mdash; Paper Trading</div>
</div></body></html>"""


def _kv(label: str, value: str) -> str:
    return f'<div class="kv"><span class="k">{label}</span><span class="v">{value}</span></div>'


def send_email(
    subject: str,
    body: str,
    to: str,
    smtp_host: str,
    smtp_port: int,
    smtp_user: str,
    smtp_password: str,
    html: str = None,
) -> bool:
    """
    Send an email via SMTP (TLS).
    If `html` is provided it is sent as the HTML part with `body` as plain-text fallback.
    Returns True on success, False on failure.
    """
    smtp_password = smtp_password.replace(" ", "")
    if not smtp_password:
        log.warning("Email skipped -- SMTP_PASSWORD not configured in config.py")
        return False
    try:
        msg = MIMEMultipart("alternative")
        msg["From"]    = smtp_user
        msg["To"]      = to
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))
        if html:
            msg.attach(MIMEText(html, "html"))
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


def _send_html(subject: str, html: str, cfg) -> None:
    plain = re.sub(r"<[^>]+>", "", html).strip()
    send_email(
        subject=subject, body=plain, html=html,
        to=cfg.NOTIFY_EMAIL,
        smtp_host=cfg.SMTP_HOST, smtp_port=cfg.SMTP_PORT,
        smtp_user=cfg.SMTP_USER, smtp_password=cfg.SMTP_PASSWORD,
    )
    email_archive.save(subject, html)


# ── Copy Trade ────────────────────────────────────────────────────────────────

def notify_copy_trade(
    politician: str,
    action: str,
    symbol: str,
    qty: int,
    price_ref: float,
    order_id: str,
    cfg,
) -> None:
    action_upper = action.upper()
    action_class = "green" if action_upper == "BUY" else "red"
    pill_class   = "pill-green" if action_upper == "BUY" else "pill-red"
    ts_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    body = f"""
    <div class="section">
      <div class="section-title">Trade Details</div>
      {_kv("Politician", f"<span class='amber'>{politician}</span>")}
      {_kv("Action", f"<span class='{action_class}'>{action_upper}</span>")}
      {_kv("Symbol", f"<span class='mono'>{symbol}</span>")}
      {_kv("Quantity", str(qty))}
      {_kv("Order type", "Market order")}
      {_kv("Time (UTC)", ts_utc)}
      {_kv("Order ID", f"<span class='mono'>{order_id}</span>")}
    </div>

    <div class="section">
      <div class="section-title">Why This Trade</div>
      <p style="font-size:14px; color:#444; margin:0;">
        {politician} filed a new trade disclosure on Capitol Trades.
        This trade was automatically copied within minutes of the filing being detected.
      </p>
    </div>"""

    subject = f"TradingBot: [CopyTrade] {action_upper} {symbol} x{qty} — {politician}"
    badge   = f'<span class="pill {pill_class}">COPY TRADE · {action_upper}</span>'
    html    = _wrap(f"Copy Trade — {action_upper} {symbol}", badge, body, "Copy Trade Bot")
    _send_html(subject, html, cfg)


# ── Stop Loss ─────────────────────────────────────────────────────────────────

def notify_stop_loss(
    symbol: str,
    qty: int,
    price: float,
    stop: float,
    pct_from_entry: float,
    order_id: str,
    cfg,
) -> None:
    pnl_class = "green" if pct_from_entry >= 0 else "red"
    ts_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    body = f"""
    <div class="section">
      <div class="section-title">Stop Loss Triggered</div>
      {_kv("Symbol", f"<span class='mono'>{symbol}</span>")}
      {_kv("Shares sold", str(qty))}
      {_kv("Current price", f"${price:.2f}")}
      {_kv("Stop level", f"${stop:.2f}")}
      {_kv("P&amp;L vs entry", f"<span class='{pnl_class}'>{pct_from_entry:+.1f}%</span>")}
      {_kv("Time (UTC)", ts_utc)}
      {_kv("Order ID", f"<span class='mono'>{order_id}</span>")}
    </div>
    <div class="warn-box">
      Rule 1 triggered: price fell to or below the trailing stop level.
      The full position has been sold. The symbol will be removed from the active watch list.
    </div>"""

    subject = f"TradingBot: [TrailingStop] STOP LOSS HIT — SELL ALL {symbol}  ({pct_from_entry:+.1f}%)"
    badge   = '<span class="pill pill-red">STOP LOSS · SOLD</span>'
    html    = _wrap(f"Trailing Stop — {symbol} Stop Loss Hit", badge, body, "Trailing Stop Bot")
    _send_html(subject, html, cfg)


# ── Ladder In ─────────────────────────────────────────────────────────────────

def notify_ladder_in(
    symbol: str,
    qty: int,
    price: float,
    drop_pct: float,
    ladder_num: int,
    new_stop: float,
    new_entry: float,
    order_id: str,
    cfg,
) -> None:
    ts_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    body = f"""
    <div class="section">
      <div class="section-title">Ladder-In Purchase</div>
      {_kv("Symbol", f"<span class='mono'>{symbol}</span>")}
      {_kv("Shares bought", str(qty))}
      {_kv("Purchase price", f"${price:.2f}")}
      {_kv("Drop from entry", f"<span class='amber'>{drop_pct:.1f}% below entry</span>")}
      {_kv("Ladder number", f"#{ladder_num}")}
      {_kv("New avg entry", f"${new_entry:.2f}")}
      {_kv("New stop loss", f"${new_stop:.2f}")}
      {_kv("Time (UTC)", ts_utc)}
      {_kv("Order ID", f"<span class='mono'>{order_id}</span>")}
    </div>

    <div class="section">
      <div class="section-title">Why This Happened</div>
      <p style="font-size:14px; color:#444; margin:0;">
        Rule 3 triggered: {symbol} dropped {drop_pct:.1f}% from entry price,
        indicating a potential buying opportunity. Adding {qty} more shares lowers
        the average cost basis to ${new_entry:.2f}. The stop loss has been
        recalculated to ${new_stop:.2f}.
      </p>
    </div>"""

    subject = f"TradingBot: [TrailingStop] LADDER IN — BUY {symbol} x{qty}  (down {drop_pct:.1f}%)"
    badge   = '<span class="pill pill-amber">LADDER IN · BUY</span>'
    html    = _wrap(f"Trailing Stop — {symbol} Ladder In #{ladder_num}", badge, body, "Trailing Stop Bot")
    _send_html(subject, html, cfg)


# ── Pharma Catalyst ───────────────────────────────────────────────────────────

def notify_pharma_catalyst(
    ticker: str,
    event_type: str,
    headline: str,
    source: str,
    initial_qty: int,
    cfg,
) -> None:
    body = f"""
    <div class="section">
      <div class="section-title">Catalyst Detected</div>
      {_kv("Ticker", f"<span class='mono'>{ticker}</span>")}
      {_kv("Event type", f"<span class='green'>{event_type}</span>")}
      {_kv("Headline", f"<em>{headline}</em>")}
      {_kv("Source", source or "N/A")}
      {_kv("Time (UTC)", datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"))}
    </div>

    <div class="section">
      <div class="section-title">Action Taken</div>
      <p style="font-size:14px; color:#444; margin:0;">
        {ticker} has been added to the active watch list.
        The bot will buy {initial_qty} shares and apply the standard
        trailing stop + ladder-in strategy.
      </p>
    </div>"""

    subject = f"TradingBot: [TrailingStop] PHARMA CATALYST — {ticker} added ({event_type})"
    badge   = '<span class="pill pill-purple">PHARMA CATALYST</span>'
    html    = _wrap(f"Pharma Catalyst — {ticker}", badge, body, "Trailing Stop Bot")
    _send_html(subject, html, cfg)
