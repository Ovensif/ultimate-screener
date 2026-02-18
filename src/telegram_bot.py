"""
Telegram alerts: startup message and Alert 10 list-change notification. Plain text, no markdown.
"""
import logging
import time
from typing import List

import requests

from . import config

logger = logging.getLogger(__name__)

BASE_URL = "https://api.telegram.org/bot{token}/sendMessage"


def _send_raw(text: str) -> bool:
    url = BASE_URL.format(token=config.TELEGRAM_BOT_TOKEN)
    for attempt in range(2):
        try:
            r = requests.get(
                url,
                params={"chat_id": config.TELEGRAM_CHAT_ID, "text": text},
                timeout=10,
            )
            if r.status_code == 200:
                return True
            logger.warning("Telegram sendMessage %s: %s", r.status_code, r.text[:200])
        except Exception as e:
            logger.warning("Telegram send failed: %s", e)
        if attempt == 0:
            time.sleep(1)
    return False


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
