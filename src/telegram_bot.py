"""
Telegram alerts: startup message, Alert 10 list-change, and Top 10 sweep table. Plain text, no markdown.
"""
import logging
import time
from typing import List, Set

import requests

from . import config
from .sweep_screener import symbol_to_display_ticker

logger = logging.getLogger(__name__)

BASE_URL = "https://api.telegram.org/bot{token}/sendMessage"


def _send_raw(text: str, parse_mode: str = None) -> bool:
    url = BASE_URL.format(token=config.TELEGRAM_BOT_TOKEN)
    params = {"chat_id": config.TELEGRAM_CHAT_ID, "text": text}
    if parse_mode:
        params["parse_mode"] = parse_mode
    for attempt in range(2):
        try:
            r = requests.get(url, params=params, timeout=10)
            if r.status_code == 200:
                return True
            logger.warning("Telegram sendMessage %s: %s", r.status_code, r.text[:200])
        except Exception as e:
            logger.warning("Telegram send failed: %s", e)
        if attempt == 0:
            time.sleep(1)
    return False


def _html_escape(s: str) -> str:
    """Escape for Telegram HTML: & < >."""
    if not s:
        return s
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def send_startup_message(coin_count: int) -> bool:
    """Send 'Scanner started, monitoring N coins'."""
    text = f"🚀 Scanner started, monitoring {coin_count} coins"
    return _send_raw(text)


def send_alert10_list_change(
    delisted: List[str],
    new_coins: List[str],
    current_list: List[str],
) -> bool:
    """
    Send one Telegram message when Alert 10 list composition changed (out / in).
    Plain text, no markdown.
    """
    lines = [
        "📋 Alert 10 list changed",
        "",
    ]
    if delisted:
        lines.append("Out: " + ", ".join(delisted))
    if new_coins:
        lines.append("In: " + ", ".join(new_coins))
    lines.append("")
    lines.append("Current list: " + ", ".join(current_list) if current_list else "Current list: (empty)")
    text = "\n".join(lines)
    return _send_raw(text)


def send_sweep_report(results: List) -> bool:
    """Send one Telegram message listing pairs that swept SWH/SWL."""
    lines = ["📊 SWH/SWL sweep", ""]
    for r in results:
        parts = [r.symbol]
        if r.swept_swing_high:
            parts.append("SWH✓")
        if r.swept_swing_low:
            parts.append("SWL✓")
        lines.append(" ".join(parts))
    text = "\n".join(lines)
    return _send_raw(text)


def send_top10_sweep_table(
    top10_results: List,
    previous_symbols: Set[str],
) -> bool:
    """
    Send one Telegram message: Top 10 table (No | Ticker | Sweep | Status).
    previous_symbols: set of symbols we already sent before -> 🔁, else 🆕.
    Returns True if send succeeded.
    """
    if not top10_results:
        return True

    w_no, w_ticker, w_sweep, w_status = 4, 14, 10, 6
    pad = lambda s, w: (str(s))[:w].ljust(w)

    header = pad("No", w_no) + pad("Ticker", w_ticker) + pad("Sweep", w_sweep) + pad("Status", w_status)
    sep = "─" * (w_no + w_ticker + w_sweep + w_status)
    rows = []
    for i, r in enumerate(top10_results, 1):
        ticker = symbol_to_display_ticker(r.symbol)
        if r.swept_swing_high and r.swept_swing_low:
            sweep = "SH+SL"
        elif r.swept_swing_high:
            sweep = "SH"
        else:
            sweep = "SL"
        status = "🔁" if r.symbol in previous_symbols else "🆕"
        rows.append(pad(str(i), w_no) + pad(ticker, w_ticker) + pad(sweep, w_sweep) + pad(status, w_status))
    table = "\n".join([header, sep] + rows)

    tf = _html_escape(getattr(config, "SWING_TIMEFRAME", "4h"))
    body = (
        "🔔 <b>TOP 10 — Sweep SWH/SWL</b>\n\n"
        "<i>Pairs with confirmed liquidity sweep.</i>\n\n"
        f"<pre>{_html_escape(table)}</pre>\n\n"
        f"<i>MEXC futures • {tf}</i>"
    )
    return _send_raw(body, parse_mode="HTML")
