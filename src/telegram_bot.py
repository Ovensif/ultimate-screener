"""
Telegram alerts for Crypto View style screener. 10/10 notification for daily trading.
"""
import logging
import time
from typing import List, Optional, Set

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
    if not s:
        return s
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _fmt_level(level: Optional[float]) -> str:
    if level is None:
        return "—"
    if level >= 1000:
        return f"{level:,.0f}"
    if level >= 1:
        return f"{level:,.2f}"
    return f"{level:.4f}"


def send_startup_message(coin_count: int) -> bool:
    text = f"🚀 Crypto View screener started — monitoring {coin_count} pairs"
    return _send_raw(text)


def send_alert10_list_change(
    delisted: List[str],
    new_coins: List[str],
    current_list: List[str],
) -> bool:
    lines = ["📋 Alert 10 list changed", ""]
    if delisted:
        lines.append("Out: " + ", ".join(delisted))
    if new_coins:
        lines.append("In: " + ", ".join(new_coins))
    lines.append("")
    lines.append("Current list: " + ", ".join(current_list) if current_list else "Current list: (empty)")
    return _send_raw("\n".join(lines))


def send_sweep_report(results: List) -> bool:
    lines = ["📊 SWH/SWL sweep", ""]
    for r in results:
        parts = [r.symbol]
        if r.swept_swing_high:
            parts.append("SWH✓")
        if r.swept_swing_low:
            parts.append("SWL✓")
        lines.append(" ".join(parts))
    return _send_raw("\n".join(lines))


def send_top10_sweep_table(
    top10_results: List,
    previous_symbols: Set[str],
) -> bool:
    """
    10/10 Telegram alert for daily trading (Crypto View 1.0 style).
    Table: No | Ticker | Signal | Level | Status.
    Signal = ▲ LONG / ▼ SHORT / ▲▼ BOTH. Level = key price to watch. Status = 🆕 new or 🔁 returning.
    """
    if not top10_results:
        return True

    tf = _html_escape(getattr(config, "SWING_TIMEFRAME", "4h"))
    w_no, w_ticker, w_signal, w_level, w_status = 3, 12, 10, 12, 6
    pad = lambda s, w: (str(s))[:w].ljust(w)

    header = pad("No", w_no) + pad("Ticker", w_ticker) + pad("Signal", w_signal) + pad("Level", w_level) + pad("Status", w_status)
    sep = "─" * (w_no + w_ticker + w_signal + w_level + w_status)
    rows = []
    for i, r in enumerate(top10_results, 1):
        ticker = symbol_to_display_ticker(r.symbol)
        sig = r.signal if hasattr(r, "signal") else ("BOTH" if (r.swept_swing_high and r.swept_swing_low) else ("SHORT" if r.swept_swing_high else "LONG"))
        if sig == "LONG":
            signal_str = "▲ LONG"
        elif sig == "SHORT":
            signal_str = "▼ SHORT"
        else:
            signal_str = "▲▼ BOTH"
        level_str = _fmt_level(getattr(r, "level", None))
        status = "🔁" if r.symbol in previous_symbols else "🆕"
        rows.append(pad(str(i), w_no) + pad(ticker, w_ticker) + pad(signal_str, w_signal) + pad(level_str, w_level) + pad(status, w_status))
    table = "\n".join([header, sep] + rows)

    body = (
        "📊 <b>Crypto View — Top 10 Sweep Alerts</b>\n"
        f"<i>{tf} • SWH/SWL swept this bar</i>\n\n"
        "<i>Check charts for deviation / continuation. Level = key price swept.</i>\n\n"
        f"<pre>{_html_escape(table)}</pre>\n\n"
        f"<i>MEXC futures • Scan every {getattr(config, 'SCAN_INTERVAL', 600) // 60} min</i>"
    )
    return _send_raw(body, parse_mode="HTML")
