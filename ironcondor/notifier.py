"""notifier.py  --  Rich HTML email alerts for the Iron Condor bot

Four notification types:
  notify_condor_opened   -- trade entry with all 4 legs + S/R context
  notify_adjustment      -- roll details with before/after and P&L snapshot
  notify_closed          -- full trade summary with P&L and adjustment history
  notify_no_entry        -- daily scan skipped (no valid setup found)
"""

import smtplib
import sys
from datetime import date, datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from config import NOTIFY_EMAIL, SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD

# ── HTML email skeleton ────────────────────────────────────────────────────────

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
  <div class="footer">Iron Condor Bot &mdash; SPY Paper Trading</div>
</div></body></html>"""


def _kv(label: str, value: str) -> str:
    return f'<div class="kv"><span class="k">{label}</span><span class="v">{value}</span></div>'


def _send(subject: str, html: str) -> None:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = SMTP_USER
    msg["To"]      = NOTIFY_EMAIL
    # Plain text fallback: strip tags roughly
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


# ── 1. TRADE OPENED ───────────────────────────────────────────────────────────

def notify_condor_opened(
    spy_price: float, expiry: str,
    sp_strike: float, sp_delta: float, sp_credit: float,
    sc_strike: float, sc_delta: float, sc_credit: float,
    lp_strike: float, lc_strike: float,
    lp_debit: float, lc_debit: float,
    net_credit: float, max_risk: float, credit_ratio: float,
    trend: str, sr_notes: str,
    support_levels: list = None, resistance_levels: list = None,
) -> None:
    profit_target_credit = round(net_credit * 0.50, 2)
    profit_target_dollar = round(profit_target_credit * 100, 0)
    stop_loss_credit     = round(net_credit * 2.00, 2)
    stop_loss_dollar     = round(stop_loss_credit * 100, 0)
    lp_debit_str         = f"${lp_debit:.2f}" if lp_debit else "—"
    lc_debit_str         = f"${lc_debit:.2f}" if lc_debit else "—"

    trend_pill = {
        "up":      '<span class="pill pill-amber">UPTREND — call side tighter</span>',
        "down":    '<span class="pill pill-blue">DOWNTREND — put side tighter</span>',
        "neutral": '<span class="pill pill-green">NEUTRAL — balanced condor</span>',
    }.get(trend, f'<span class="pill pill-blue">{trend.upper()}</span>')

    support_str    = ", ".join(f"${s:.0f}" for s in (support_levels or [])[:4]) or "—"
    resistance_str = ", ".join(f"${r:.0f}" for r in (resistance_levels or [])[:4]) or "—"

    legs_html = f"""
    <table>
      <tr><th>Leg</th><th>Strike</th><th>Delta</th><th>Credit / Debit</th><th>Role</th></tr>
      <tr><td>Sell Put</td><td class="mono">${sp_strike:.0f}</td>
          <td class="mono">{sp_delta:.3f}</td>
          <td class="mono green">+${sp_credit:.2f}</td>
          <td>Short put — lower boundary</td></tr>
      <tr><td>Buy Put</td><td class="mono">${lp_strike:.0f}</td>
          <td class="mono">—</td>
          <td class="mono red">−{lp_debit_str}</td>
          <td>Long put — protection wing</td></tr>
      <tr><td>Sell Call</td><td class="mono">${sc_strike:.0f}</td>
          <td class="mono">{sc_delta:.3f}</td>
          <td class="mono green">+${sc_credit:.2f}</td>
          <td>Short call — upper boundary</td></tr>
      <tr><td>Buy Call</td><td class="mono">${lc_strike:.0f}</td>
          <td class="mono">—</td>
          <td class="mono red">−{lc_debit_str}</td>
          <td>Long call — protection wing</td></tr>
    </table>"""

    body = f"""
    <div class="section">
      <div class="section-title">Position</div>
      {_kv("SPY price at entry", f"${spy_price:.2f}")}
      {_kv("Expiry", expiry)}
      {_kv("Days to expiry", str((date.fromisoformat(expiry) - date.today()).days))}
      {_kv("Structure", f"${sp_strike:.0f}/{lp_strike:.0f} put spread  &middot;  ${sc_strike:.0f}/{lc_strike:.0f} call spread")}
    </div>

    <div class="section">
      <div class="section-title">Four Legs</div>
      {legs_html}
    </div>

    <div class="section">
      <div class="section-title">Economics</div>
      {_kv("Net credit collected", f"<span class='green'>${net_credit:.2f}/share &nbsp; (${net_credit*100:.0f} total)</span>")}
      {_kv("Maximum possible loss", f"<span class='red'>${max_risk:.2f}/share &nbsp; (${max_risk*100:.0f} total)</span>")}
      {_kv("Credit as % of max loss", f"{credit_ratio*100:.0f}%  (min required: 33%)")}
      {_kv("Profit target (50%)", f"${profit_target_credit:.2f}/share &nbsp; close when P&amp;L = +${profit_target_dollar:.0f}")}
      {_kv("Stop-loss (2× credit)", f"${stop_loss_credit:.2f}/share &nbsp; close when cost = ${stop_loss_dollar:.0f}")}
      {_kv("Adjustment trigger", "Either short strike delta reaches 0.45")}
    </div>

    <div class="section">
      <div class="section-title">Market Context</div>
      {_kv("Trend bias", trend_pill)}
      {_kv("Support levels (nearest first)", support_str)}
      {_kv("Resistance levels (nearest first)", resistance_str)}
      {_kv("S/R detail", sr_notes)}
    </div>"""

    subject = (
        f"[IronCondor] OPENED SPY  "
        f"${sp_strike:.0f}/{lp_strike:.0f}P · ${sc_strike:.0f}/{lc_strike:.0f}C  "
        f"exp {expiry}  credit=${net_credit:.2f}"
    )
    badge = '<span class="pill pill-blue">TRADE OPENED</span>'
    _send(subject, _wrap("Iron Condor — Trade Opened", badge, body))


# ── 2. ADJUSTMENT / ROLL ──────────────────────────────────────────────────────

def notify_adjustment(
    side: str,
    old_short_strike: float,
    new_short_strike: float,
    new_long_strike: float,
    roll_credit: float,
    days_remaining: int,
    spy_price: float = 0,
    current_pnl_pct: float = None,
    cumulative_credit: float = None,
) -> None:
    side_upper  = side.upper()
    roll_sign   = "+" if roll_credit >= 0 else ""
    roll_colour = "green" if roll_credit >= 0 else "amber"
    roll_label  = "credit received" if roll_credit >= 0 else "debit paid"
    direction   = "lower (further OTM)" if side == "put" else "higher (further OTM)"

    pnl_row = ""
    if current_pnl_pct is not None:
        colour = "green" if current_pnl_pct >= 0 else "red"
        pnl_row = _kv("P&amp;L before roll", f"<span class='{colour}'>{current_pnl_pct:+.0f}% of max profit captured</span>")

    credit_row = ""
    if cumulative_credit is not None:
        credit_row = _kv("Cumulative net credit after roll", f"${cumulative_credit:.2f}/share")

    body = f"""
    <div class="section">
      <div class="section-title">Adjustment Trigger</div>
      {_kv("Side adjusted", f"<span class='amber'>{side_upper} spread</span>")}
      {_kv("Trigger", "Short strike delta reached 0.45 (risk too high)")}
      {_kv("SPY price now", f"${spy_price:.2f}" if spy_price else "—")}
      {_kv("Days remaining to expiry", str(days_remaining))}
    </div>

    <div class="section">
      <div class="section-title">Roll Details</div>
      <table>
        <tr><th></th><th>Old strike</th><th>New strike</th><th>Change</th></tr>
        <tr>
          <td>Short {side} (sold)</td>
          <td class="mono">${old_short_strike:.0f}</td>
          <td class="mono">${new_short_strike:.0f}</td>
          <td>{direction}</td>
        </tr>
        <tr>
          <td>Long {side} (protection)</td>
          <td class="mono">—</td>
          <td class="mono">${new_long_strike:.0f}</td>
          <td>Wing maintained at same width</td>
        </tr>
      </table>
      <br>
      {_kv(f"Roll net ({roll_label})", f"<span class='{roll_colour}'>{roll_sign}${abs(roll_credit):.2f}/share</span>")}
      {pnl_row}
      {credit_row}
    </div>

    <div class="section">
      <div class="section-title">What Happens Next</div>
      <p style="font-size:14px; color:#444; margin:0;">
        The threatened {side_upper} spread has been moved ${abs(new_short_strike - old_short_strike):.1f}
        points further away from the current SPY price. Delta is reset to a safe level.
        The other spread is untouched. Monitoring continues every 30 minutes.
      </p>
    </div>"""

    subject = (
        f"[IronCondor] ADJUSTMENT — {side_upper} side rolled  "
        f"${old_short_strike:.0f} → ${new_short_strike:.0f}  "
        f"({days_remaining} DTE)"
    )
    badge = '<span class="pill pill-amber">ADJUSTMENT / ROLL</span>'
    _send(subject, _wrap(f"Iron Condor — {side_upper} Spread Rolled", badge, body))


# ── 3. TRADE CLOSED ───────────────────────────────────────────────────────────

def notify_closed(
    reason: str,
    net_credit: float,
    cost_to_close: float,
    net_pnl: float,
    pos: dict = None,
) -> None:
    """
    Full trade summary email.
    Pass the full `pos` dict (from state_manager) for the richest output.
    Falls back gracefully if pos is not provided.
    """
    result      = "PROFIT" if net_pnl >= 0 else "LOSS"
    pnl_colour  = "green" if net_pnl >= 0 else "red"
    pill_class  = "pill-green" if net_pnl >= 0 else "pill-red"
    pnl_pct     = round((1 - cost_to_close / net_credit) * 100) if net_credit > 0 else 0

    # ── Trade summary from full pos dict ──────────────────────────────────────
    trade_section = ""
    adj_section   = ""
    duration_str  = "—"

    if pos:
        entry_date = pos.get("entry_date", "—")
        close_date = pos.get("close_date", date.today().isoformat())
        expiry     = pos.get("expiry", "—")
        spy_entry  = pos.get("spy_price_at_entry", 0)

        try:
            d0 = date.fromisoformat(entry_date)
            d1 = date.fromisoformat(close_date)
            duration_str = f"{(d1 - d0).days} days"
        except Exception:
            pass

        sp = pos.get("short_put_strike",  0)
        lp = pos.get("long_put_strike",   0)
        sc = pos.get("short_call_strike", 0)
        lc = pos.get("long_call_strike",  0)

        put_adj_tag  = " <em>(rolled)</em>" if pos.get("put_adjusted")  else ""
        call_adj_tag = " <em>(rolled)</em>" if pos.get("call_adjusted") else ""

        trade_section = f"""
        <div class="section">
          <div class="section-title">Trade Summary</div>
          {_kv("Entry date", entry_date)}
          {_kv("Close date", close_date)}
          {_kv("Duration", duration_str)}
          {_kv("Expiry", expiry)}
          {_kv("SPY at entry", f"${spy_entry:.2f}" if spy_entry else "—")}
          {_kv("Structure (final)", f"${sp:.0f}/{lp:.0f}P{put_adj_tag} &middot; ${sc:.0f}/{lc:.0f}C{call_adj_tag}")}
        </div>"""

        # Adjustment history
        adj_log = pos.get("adjustment_log", [])
        if adj_log:
            rows = ""
            for a in adj_log:
                credit_sign = "+" if a["roll_credit"] >= 0 else ""
                rows += (
                    f"<tr>"
                    f"<td>{a['date']}</td>"
                    f"<td>{a['side'].upper()}</td>"
                    f"<td class='mono'>${a.get('new_short_strike',0):.0f} / ${a.get('new_long_strike',0):.0f}</td>"
                    f"<td class='mono'>{credit_sign}${abs(a['roll_credit']):.2f}</td>"
                    f"</tr>"
                )
            adj_section = f"""
            <div class="section">
              <div class="section-title">Adjustments Made ({len(adj_log)})</div>
              <table>
                <tr><th>Date</th><th>Side</th><th>New spread</th><th>Roll credit</th></tr>
                {rows}
              </table>
            </div>"""
        else:
            adj_section = """
            <div class="section">
              <div class="section-title">Adjustments</div>
              <p style="font-size:14px; color:#444; margin:0;">No adjustments were made — position held as originally entered.</p>
            </div>"""

    # ── P&L breakdown ─────────────────────────────────────────────────────────
    reason_map = {
        "Expired at max profit": "Options expired worthless — max profit achieved",
        "Expired worthless (max profit)": "Options expired worthless — max profit achieved",
    }
    reason_display = reason_map.get(reason, reason)

    if cost_to_close == 0:
        close_cost_display = "$0.00  (expired worthless — no closing orders needed)"
    else:
        close_cost_display = f"${cost_to_close:.2f}/share  (${cost_to_close*100:.0f} total)"

    pnl_section = f"""
    <div class="section">
      <div class="section-title">P&amp;L Result</div>
      {_kv("Close reason", reason_display)}
      {_kv("Original credit collected", f"${net_credit:.2f}/share &nbsp; (${net_credit*100:.0f} total)")}
      {_kv("Cost to close", close_cost_display)}
      {_kv("Net P&amp;L", f"<span class='{pnl_colour}'>{'+' if net_pnl>=0 else ''}${net_pnl:.2f}  ({pnl_pct:+.0f}% of max profit)</span>")}
    </div>"""

    # Expiry-specific note
    extra = ""
    if cost_to_close == 0:
        extra = """
        <div class="section">
          <p style="font-size:14px; color:#155724; background:#d4edda;
             padding:10px; border-radius:6px; margin:0;">
            All four option legs expired worthless.
            The full premium collected at entry is yours to keep — this is the best possible outcome for an Iron Condor.
          </p>
        </div>"""

    body = trade_section + adj_section + pnl_section + extra

    sign   = "+" if net_pnl >= 0 else ""
    subject = (
        f"[IronCondor] CLOSED — {result}  {sign}${abs(net_pnl):.0f}  |  "
        f"SPY  {reason[:40]}"
    )
    title = f"Iron Condor — Trade Closed ({result})"
    badge = f'<span class="pill {pill_class}">CLOSED · {result}</span>'
    _send(subject, _wrap(title, badge, body))


# ── 4. NO ENTRY ───────────────────────────────────────────────────────────────

def notify_no_entry(reason: str) -> None:
    body = f"""
    <div class="section">
      <div class="section-title">Scan Result</div>
      <p style="font-size:14px; color:#444; margin:0;">
        The Iron Condor bot scanned for a valid setup today but did not find one
        that met all entry criteria.
      </p>
      <br>
      {_kv("Reason", reason)}
    </div>
    <div class="section">
      <div class="section-title">Entry Criteria Reminder</div>
      {_kv("DTE window", "12–16 days (target 14)")}
      {_kv("Short strike delta", "≤ 0.20 on both sides")}
      {_kv("S/R alignment", "Short strikes just beyond nearest S/R level")}
      {_kv("Minimum credit", "≥ 33% of wing width ($5)")}
      {_kv("Max open condors", "1 at a time")}
    </div>"""

    _send(
        "[IronCondor] Entry scan — no trade placed",
        _wrap("Iron Condor — No Entry Today",
              '<span class="pill pill-blue">SCAN · NO TRADE</span>', body),
    )
