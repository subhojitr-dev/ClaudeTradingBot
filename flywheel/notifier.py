"""notifier.py  --  Rich HTML email alerts for the Flywheel (Wheel Strategy) bot

Event types:
  notify_csp_opened          -- new cash-secured put sold (Stage 1 entry)
  notify_csp_expired         -- put expired worthless, full premium kept
  notify_assigned            -- put assigned, stock delivered at strike
  notify_rolled_up           -- CSP rolled to higher strike
  notify_csp_closed_early    -- CSP bought back at 70% profit
  notify_cc_opened           -- new covered call sold (Stage 2 entry)
  notify_called_away         -- shares called away, back to Stage 1
  notify_cc_expired          -- covered call expired worthless, keep stock
  notify_cc_closed_early     -- CC bought back at 70% profit
  notify_skipped             -- insufficient cash for CSP
  send_report                -- daily HTML report
"""

import re
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
  .highlight { background: #d4edda; border-radius: 6px; padding: 10px;
               font-size: 14px; color: #155724; margin-top: 10px; }
  .warn-box  { background: #fff3cd; border-radius: 6px; padding: 10px;
               font-size: 14px; color: #856404; margin-top: 10px; }
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
  <div class="footer">Flywheel Bot &mdash; Wheel Strategy Paper Trading</div>
</div></body></html>"""


def _kv(label: str, value: str) -> str:
    return f'<div class="kv"><span class="k">{label}</span><span class="v">{value}</span></div>'


def _send(subject: str, html: str) -> None:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = SMTP_USER
    msg["To"]      = NOTIFY_EMAIL
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


# ── 1. CSP OPENED ─────────────────────────────────────────────────────────────

def notify_csp_opened(
    symbol: str, contract_sym: str, strike: float, sell_price: float,
    expiry: str, stock_price: float, cash_required: float,
    csp_strike_discount: float, order_id: str,
) -> None:
    body = f"""
    <div class="section">
      <div class="section-title">Stage 1 — Cash-Secured Put Sold</div>
      {_kv("Symbol", f"<span class='mono'>{symbol}</span>")}
      {_kv("Contract", f"<span class='mono'>{contract_sym}</span>")}
      {_kv("Stock price at entry", f"${stock_price:.2f}")}
      {_kv("Strike", f"${strike:.2f}  ({int(csp_strike_discount*100)}% below stock price)")}
      {_kv("Expiry", expiry)}
      {_kv("Premium collected", f"<span class='green'>${sell_price:.2f}/share = ${sell_price*100:.2f} total</span>")}
      {_kv("Cash reserved as collateral", f"${cash_required:,.0f}")}
      {_kv("Order ID", f"<span class='mono'>{order_id}</span>")}
    </div>

    <div class="section">
      <div class="section-title">Exit Paths</div>
      {_kv("Best case", "Expires worthless — keep full premium, open new put")}
      {_kv("70% profit early close", "Buy back at 70% profit before expiry, reopen")}
      {_kv("Roll up", "If stock rises, roll to higher strike for more premium")}
      {_kv("Assignment", "Stock delivered at ${:.2f} — move to Stage 2 covered call".format(strike))}
    </div>"""

    _send(
        f"TradingBot: [Flywheel] CSP OPENED — SELL {symbol} PUT ${strike:.0f}  premium ${sell_price*100:.2f}",
        _wrap(f"Flywheel — {symbol} Cash-Secured Put Opened",
              '<span class="pill pill-blue">STAGE 1 · CSP OPENED</span>', body),
    )


# ── 2. CSP EXPIRED WORTHLESS ──────────────────────────────────────────────────

def notify_csp_expired(
    symbol: str, entry_prem: float, total_premium: float, grand_total: float,
) -> None:
    body = f"""
    <div class="section">
      <div class="section-title">Put Expired Worthless</div>
      {_kv("Symbol", f"<span class='mono'>{symbol}</span>")}
      {_kv("Premium kept (this cycle)", f"<span class='green'>${entry_prem*100:.2f}</span>")}
      {_kv("Total premium collected ({symbol})", f"${total_premium:,.2f}")}
      {_kv("Grand total (all symbols)", f"${grand_total:,.2f}")}
    </div>
    <div class="highlight">
      Best possible outcome — the put expired worthless and the full premium is yours to keep.
      A new cash-secured put will be opened on the next run.
    </div>"""

    _send(
        f"TradingBot: [Flywheel] PUT EXPIRED WORTHLESS — {symbol}  +${entry_prem*100:.2f}",
        _wrap(f"Flywheel — {symbol} Put Expired Worthless",
              '<span class="pill pill-green">EXPIRED WORTHLESS</span>', body),
    )


# ── 3. ASSIGNED ───────────────────────────────────────────────────────────────

def notify_assigned(
    symbol: str, shares: int, strike: float, entry_prem: float, eff_cost: float,
) -> None:
    body = f"""
    <div class="section">
      <div class="section-title">Put Assigned — Stock Delivered</div>
      {_kv("Symbol", f"<span class='mono'>{symbol}</span>")}
      {_kv("Shares received", str(shares))}
      {_kv("Strike price (paid)", f"${strike:.2f}/share")}
      {_kv("Put premium received", f"<span class='green'>${entry_prem*100:.2f}</span> (offsets cost)")}
      {_kv("Effective cost basis", f"<span class='amber'>${eff_cost:.2f}/share  (strike minus premium)</span>")}
    </div>

    <div class="section">
      <div class="section-title">What Happens Next</div>
      <p style="font-size:14px; color:#444; margin:0;">
        Now holding {shares} shares of {symbol} at an effective cost of ${eff_cost:.2f}.
        Moving to Stage 2 — a covered call will be sold above the current price on the next run
        to collect additional premium and reduce cost basis further.
      </p>
    </div>"""

    _send(
        f"TradingBot: [Flywheel] ASSIGNED — {symbol}  {shares} shares at ${strike:.2f}  cost basis ${eff_cost:.2f}",
        _wrap(f"Flywheel — {symbol} Put Assigned → Moving to Stage 2",
              '<span class="pill pill-amber">ASSIGNED · STAGE 2</span>', body),
    )


# ── 4. CSP ROLLED UP ──────────────────────────────────────────────────────────

def notify_rolled_up(
    symbol: str, old_strike: float, new_strike: float,
    net_credit: float, expiry: str,
) -> None:
    body = f"""
    <div class="section">
      <div class="section-title">Put Rolled to Higher Strike</div>
      {_kv("Symbol", f"<span class='mono'>{symbol}</span>")}
      {_kv("Old strike", f"${old_strike:.2f}")}
      {_kv("New strike", f"<span class='green'>${new_strike:.2f}  (+${new_strike - old_strike:.2f} higher)</span>")}
      {_kv("Net credit from roll", f"<span class='green'>${net_credit*100:.2f} additional premium</span>")}
      {_kv("Expiry (unchanged)", expiry)}
    </div>

    <div class="section">
      <div class="section-title">Why This Happened</div>
      <p style="font-size:14px; color:#444; margin:0;">
        {symbol} rose enough that the put fell to near-zero value (80%+ profit).
        Rather than closing and reopening, the put was rolled up to a higher strike
        on the same expiry — capturing additional premium while keeping the position active.
      </p>
    </div>"""

    _send(
        f"TradingBot: [Flywheel] PUT ROLLED UP — {symbol}  ${old_strike:.0f} → ${new_strike:.0f}  +${net_credit*100:.2f}",
        _wrap(f"Flywheel — {symbol} Put Rolled Up",
              '<span class="pill pill-amber">PUT ROLLED UP</span>', body),
    )


# ── 5. CSP CLOSED EARLY (70% profit) ─────────────────────────────────────────

def notify_csp_closed_early(
    symbol: str, entry_prem: float, current_val: float,
) -> None:
    profit = (entry_prem - current_val) * 100
    pct    = (entry_prem - current_val) / entry_prem * 100 if entry_prem > 0 else 0

    body = f"""
    <div class="section">
      <div class="section-title">Cash-Secured Put — Early Close at 70% Profit</div>
      {_kv("Symbol", f"<span class='mono'>{symbol}</span>")}
      {_kv("Sold (entry premium)", f"${entry_prem:.4f}/share")}
      {_kv("Bought back at", f"${current_val:.4f}/share")}
      {_kv("Profit captured", f"<span class='green'>${profit:.2f}  ({pct:.0f}% of maximum)</span>")}
    </div>
    <div class="highlight">
      70% profit target reached. Closing early removes remaining risk and frees
      collateral to open a new put sooner. A new cash-secured put will be opened on the next run.
    </div>"""

    _send(
        f"TradingBot: [Flywheel] CSP CLOSED EARLY — {symbol}  +${profit:.2f}  ({pct:.0f}% profit)",
        _wrap(f"Flywheel — {symbol} Put Closed Early",
              '<span class="pill pill-green">70% PROFIT · CLOSED</span>', body),
    )


# ── 6. COVERED CALL OPENED ────────────────────────────────────────────────────

def notify_cc_opened(
    symbol: str, contract_sym: str, c_strike: float, sell_price: float,
    expiry: str, stock_price: float, delta: float,
    stock_cost: float, cc_strike_premium: float, order_id: str,
) -> None:
    body = f"""
    <div class="section">
      <div class="section-title">Stage 2 — Covered Call Sold</div>
      {_kv("Symbol", f"<span class='mono'>{symbol}</span>")}
      {_kv("Contract", f"<span class='mono'>{contract_sym}</span>")}
      {_kv("Stock price at entry", f"${stock_price:.2f}")}
      {_kv("Call strike", f"${c_strike:.2f}  ({int(cc_strike_premium*100)}% above stock price)")}
      {_kv("Delta", f"{delta:.3f}  (~{delta*100:.0f}% probability of assignment)")}
      {_kv("Expiry", expiry)}
      {_kv("Premium collected", f"<span class='green'>${sell_price:.2f}/share = ${sell_price*100:.2f} total</span>")}
      {_kv("Effective stock cost basis", f"${stock_cost:.2f}/share  (reduced by put premium)")}
      {_kv("Order ID", f"<span class='mono'>{order_id}</span>")}
    </div>

    <div class="section">
      <div class="section-title">Exit Paths</div>
      {_kv("Best case", "Expires worthless — keep premium, sell new call, reduce cost basis")}
      {_kv("70% profit early close", "Buy back at 70% profit, sell new call sooner")}
      {_kv("Called away", f"Stock sold at ${c_strike:.2f} — return to Stage 1")}
    </div>"""

    _send(
        f"TradingBot: [Flywheel] CC OPENED — SELL {symbol} CALL ${c_strike:.0f}  premium ${sell_price*100:.2f}",
        _wrap(f"Flywheel — {symbol} Covered Call Opened",
              '<span class="pill pill-blue">STAGE 2 · CC OPENED</span>', body),
    )


# ── 7. CALLED AWAY ────────────────────────────────────────────────────────────

def notify_called_away(
    symbol: str, stock_qty: int, call_strike: float,
    stock_pnl: float, stock_cost: float, entry_prem: float,
) -> None:
    pnl_class = "green" if stock_pnl >= 0 else "red"
    total_gain = stock_pnl + entry_prem * 100

    body = f"""
    <div class="section">
      <div class="section-title">Covered Call Exercised — Shares Sold</div>
      {_kv("Symbol", f"<span class='mono'>{symbol}</span>")}
      {_kv("Shares sold", str(stock_qty))}
      {_kv("Sale price (call strike)", f"${call_strike:.2f}/share")}
      {_kv("Stock cost basis", f"${stock_cost:.2f}/share")}
      {_kv("Stock P&amp;L", f"<span class='{pnl_class}'>${stock_pnl:+.2f}</span>")}
      {_kv("Call premium already collected", f"<span class='green'>${entry_prem*100:.2f}</span>")}
      {_kv("Total gain this cycle", f"<span class='green'>${total_gain:.2f}</span>")}
    </div>
    <div class="highlight">
      Shares have been called away at ${call_strike:.2f}. Returning to Stage 1 —
      a new cash-secured put will be opened on the next run to restart the wheel.
    </div>"""

    _send(
        f"TradingBot: [Flywheel] CALLED AWAY — {symbol} {stock_qty} shares sold at ${call_strike:.2f}  P&L ${stock_pnl:+.2f}",
        _wrap(f"Flywheel — {symbol} Shares Called Away → Back to Stage 1",
              '<span class="pill pill-blue">CALLED AWAY · STAGE 1</span>', body),
    )


# ── 8. COVERED CALL EXPIRED WORTHLESS ────────────────────────────────────────

def notify_cc_expired(
    symbol: str, entry_prem: float, stock_qty: int, total_premium: float,
) -> None:
    body = f"""
    <div class="section">
      <div class="section-title">Covered Call Expired Worthless</div>
      {_kv("Symbol", f"<span class='mono'>{symbol}</span>")}
      {_kv("Premium kept (this cycle)", f"<span class='green'>${entry_prem*100:.2f}</span>")}
      {_kv("Still holding", f"{stock_qty} shares")}
      {_kv("Total premium collected ({symbol})", f"${total_premium:,.2f}")}
    </div>
    <div class="highlight">
      The covered call expired worthless — full premium kept and shares retained.
      A new covered call will be sold on the next run to collect more premium.
    </div>"""

    _send(
        f"TradingBot: [Flywheel] CALL EXPIRED WORTHLESS — {symbol}  +${entry_prem*100:.2f}  holding {stock_qty} shares",
        _wrap(f"Flywheel — {symbol} Covered Call Expired Worthless",
              '<span class="pill pill-green">CC EXPIRED WORTHLESS</span>', body),
    )


# ── 9. COVERED CALL CLOSED EARLY (70% profit) ────────────────────────────────

def notify_cc_closed_early(
    symbol: str, entry_prem: float, current_val: float, stock_qty: int,
) -> None:
    profit = (entry_prem - current_val) * 100
    pct    = (entry_prem - current_val) / entry_prem * 100 if entry_prem > 0 else 0

    body = f"""
    <div class="section">
      <div class="section-title">Covered Call — Early Close at 70% Profit</div>
      {_kv("Symbol", f"<span class='mono'>{symbol}</span>")}
      {_kv("Sold (entry premium)", f"${entry_prem:.4f}/share")}
      {_kv("Bought back at", f"${current_val:.4f}/share")}
      {_kv("Profit captured", f"<span class='green'>${profit:.2f}  ({pct:.0f}% of maximum)</span>")}
      {_kv("Still holding", f"{stock_qty} shares")}
    </div>
    <div class="highlight">
      70% profit target reached. Closing early removes assignment risk and allows
      a new covered call to be sold sooner at potentially better terms.
    </div>"""

    _send(
        f"TradingBot: [Flywheel] CC CLOSED EARLY — {symbol}  +${profit:.2f}  ({pct:.0f}% profit)",
        _wrap(f"Flywheel — {symbol} Covered Call Closed Early",
              '<span class="pill pill-green">70% PROFIT · CLOSED</span>', body),
    )


# ── 10. SKIPPED — INSUFFICIENT CASH ──────────────────────────────────────────

def notify_skipped(
    symbol: str, cash: float, cash_required: float, strike: float,
) -> None:
    body = f"""
    <div class="section">
      <div class="section-title">CSP Skipped — Insufficient Cash</div>
      {_kv("Symbol", f"<span class='mono'>{symbol}</span>")}
      {_kv("Cash required", f"<span class='red'>${cash_required:,.0f}  (strike ${strike:.2f} × 100 shares)</span>")}
      {_kv("Cash available", f"${cash:,.0f}")}
      {_kv("Shortfall", f"<span class='red'>${cash_required - cash:,.0f}</span>")}
    </div>
    <div class="warn-box">
      A new put was NOT sold. The strategy requires full cash collateral to be
      truly cash-secured. Please add funds to account PA34EFPV3B80 to resume trading {symbol}.
    </div>"""

    _send(
        f"TradingBot: [Flywheel] SKIPPED {symbol} — insufficient cash  (need ${cash_required:,.0f}, have ${cash:,.0f})",
        _wrap(f"Flywheel — {symbol} CSP Skipped",
              '<span class="pill pill-red">SKIPPED · LOW CASH</span>', body),
    )


# ── 11. DAILY REPORT ─────────────────────────────────────────────────────────

def send_report(html: str, today_str: str) -> None:
    _send(
        f"TradingBot: [Flywheel] Daily Report — {today_str}",
        html,
    )
