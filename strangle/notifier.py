"""notifier.py  --  Rich HTML email alerts for the Strangle bot

Three notification types:
  notify_strangle_opened  -- entry with call + put legs and earnings context
  notify_combined_close   -- whole position closed (profit target or stop-loss),
                              judged on call + put together, not either leg alone
  notify_iv_skip          -- skipped entry due to elevated IV
"""

import smtplib
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import email_archive
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from config import NOTIFY_EMAIL, SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD

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
  .pill-gray   { background: #e2e3e5; color: #383d41; }
  .kv    { display: flex; justify-content: space-between; padding: 4px 0;
           font-size: 14px; border-bottom: 1px solid #f5f5f5; }
  .kv .k { color: #555; }
  .kv .v { font-weight: bold; }
  .footer { margin-top: 20px; font-size: 11px; color: #aaa; text-align: center; }
"""


def _wrap(title: str, badge_html: str, body_html: str) -> str:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<style>{_CSS}</style></head><body>
<div class="card">
  <h2>{title}</h2>
  <div class="sub">{badge_html} &nbsp; {ts}</div>
  {body_html}
  <div class="footer">Strangle Bot &mdash; Earnings Play Paper Trading</div>
</div></body></html>"""


def _kv(label: str, value: str) -> str:
    return f'<div class="kv"><span class="k">{label}</span><span class="v">{value}</span></div>'


def _send(subject: str, html: str) -> None:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = SMTP_USER
    msg["To"]      = NOTIFY_EMAIL
    import re
    plain = re.sub(r"<[^>]+>", "", html).strip()
    msg.attach(MIMEText(plain, "plain"))
    msg.attach(MIMEText(html,  "html"))
    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as s:
            s.starttls()
            s.login(SMTP_USER, SMTP_PASSWORD.replace(" ", ""))
            s.send_message(msg)
    except Exception as e:
        print(f"[notifier] Email failed: {e}", file=sys.stderr)
    email_archive.save(subject, html)


# ── 1. STRANGLE OPENED ────────────────────────────────────────────────────────

def notify_strangle_opened(
    symbol: str,
    earnings_date: str,
    call: str,
    put: str,
    call_price: float,
    put_price: float,
    total_cost: float,
) -> None:
    legs_html = f"""
    <table>
      <tr><th>Leg</th><th>Contract</th><th>Type</th><th>Cost</th></tr>
      <tr>
        <td>Buy Call</td>
        <td class="mono">{call}</td>
        <td><span class="pill pill-green">CALL</span></td>
        <td class="mono green">${call_price:.2f}</td>
      </tr>
      <tr>
        <td>Buy Put</td>
        <td class="mono">{put}</td>
        <td><span class="pill pill-blue">PUT</span></td>
        <td class="mono green">${put_price:.2f}</td>
      </tr>
    </table>"""

    body = f"""
    <div class="section">
      <div class="section-title">Trade Setup</div>
      {_kv("Symbol", f"<span class='mono'>{symbol}</span>")}
      {_kv("Earnings date", f"<span class='amber'>{earnings_date}</span>")}
      {_kv("Strategy", "Long strangle — profit if stock moves sharply either direction")}
      {_kv("Total cost", f"<span class='red'>${total_cost:.2f}  (max loss if both expire worthless)</span>")}
    </div>

    <div class="section">
      <div class="section-title">Legs Purchased</div>
      {legs_html}
    </div>

    <div class="section">
      <div class="section-title">Monitoring Plan</div>
      {_kv("Rule", "Judge call + put TOGETHER against total cost, not either leg alone")}
      {_kv("Exit", "Close both legs once combined value is +/-15% of total cost")}
      {_kv("Check frequency", "Every 2 hours during market hours")}
    </div>"""

    _send(
        f"TradingBot: [Strangle] OPENED {symbol} — earnings {earnings_date}",
        _wrap(f"Strangle — {symbol} Trade Opened",
              '<span class="pill pill-blue">TRADE OPENED</span>', body),
    )


# ── 2. COMBINED CLOSE (whole position, either direction) ──────────────────────

def notify_combined_close(
    symbol: str,
    reason: str,
    call_sold_price,
    put_sold_price,
    total_cost: float,
    total_proceeds: float,
    net_pnl: float,
) -> None:
    result     = "PROFIT" if net_pnl >= 0 else "LOSS"
    pnl_class  = "green"    if net_pnl >= 0 else "red"
    pill_class = "pill-green" if net_pnl >= 0 else "pill-red"
    pnl_sign   = "+" if net_pnl >= 0 else ""

    legs_html = f"""
    <table>
      <tr><th>Leg</th><th>Exit price</th></tr>
      <tr><td>Call</td><td class="mono">{f"${call_sold_price:.2f}" if call_sold_price is not None else "—"}</td></tr>
      <tr><td>Put</td><td class="mono">{f"${put_sold_price:.2f}" if put_sold_price is not None else "—"}</td></tr>
    </table>"""

    body = f"""
    <div class="section">
      <div class="section-title">Whole Position Closed</div>
      {_kv("Symbol", f"<span class='mono'>{symbol}</span>")}
      {_kv("Reason", reason)}
    </div>

    <div class="section">
      <div class="section-title">Legs</div>
      {legs_html}
    </div>

    <div class="section">
      <div class="section-title">Final Trade Result</div>
      {_kv("Total cost", f"${total_cost:.2f}")}
      {_kv("Total proceeds", f"${total_proceeds:.2f}")}
      {_kv("Net P&amp;L (both legs together)",
           f"<span class='{pnl_class}'>{pnl_sign}${abs(net_pnl):.2f}</span>")}
      {_kv("Outcome", f"<span class='{pnl_class}'>{result}</span>")}
      {_kv("Status", "Strangle fully closed — no open legs remaining")}
    </div>"""

    _send(
        f"TradingBot: [Strangle] CLOSED {symbol} — {result}  {pnl_sign}${abs(net_pnl):.0f}",
        _wrap(f"Strangle — {symbol} Trade Closed ({result})",
              f'<span class="pill {pill_class}">CLOSED · {result}</span>', body),
    )


# ── 4. IV SKIP ────────────────────────────────────────────────────────────────

def notify_iv_skip(
    symbol: str,
    iv: float,
    pct: float,
    threshold: float,
) -> None:
    body = f"""
    <div class="section">
      <div class="section-title">Entry Skipped — IV Too High</div>
      {_kv("Symbol", f"<span class='mono'>{symbol}</span>")}
      {_kv("Current IV", f"<span class='red'>{iv:.1%}</span>")}
      {_kv("IV percentile rank", f"<span class='red'>{pct:.0f}th percentile</span>")}
      {_kv("Maximum allowed", f"{threshold:.0f}th percentile")}
    </div>

    <div class="section">
      <div class="section-title">Why This Matters</div>
      <p style="font-size:14px; color:#444; margin:0;">
        Elevated IV means options are expensive — the market is already pricing in a big move.
        Buying a strangle when IV is high means overpaying for both legs, which reduces the
        probability of profit even if the stock moves significantly.
        The bot will recheck on the next run.
      </p>
    </div>"""

    _send(
        f"TradingBot: [Strangle] SKIP {symbol} — IV too high ({pct:.0f}th percentile)",
        _wrap(f"Strangle — {symbol} Entry Skipped",
              '<span class="pill pill-amber">SKIP · HIGH IV</span>', body),
    )
