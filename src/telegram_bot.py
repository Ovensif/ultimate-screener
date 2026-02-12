"""
Telegram alerts: send signal message and startup message. Plain text, no markdown.
"""
import logging
import time
from typing import Any, Optional

import requests

from . import config
from .risk_calculator import RiskResult, calculate
from .signal_generator import Signal

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


def send_signal(signal: Signal, risk_output: Optional[RiskResult] = None) -> bool:
    """
    Format and send the signal alert. Uses plain text (no markdown).
    risk_output can be computed via risk_calculator.calculate if not provided.
    """
    if risk_output is None:
        entry = (signal.entry_zone[0] + signal.entry_zone[1]) / 2
        risk_output = calculate(entry, signal.stop, signal.side)

    entry_low, entry_high = signal.entry_zone
    stop_dist_pct = abs(entry_low + entry_high) / 2 - signal.stop
    if entry_low != entry_high:
        mid = (entry_low + entry_high) / 2
    else:
        mid = entry_low
    stop_dist_pct = 100 * abs(mid - signal.stop) / mid if mid else 0
    t1_dist = 100 * abs(signal.target1 - mid) / mid if mid else 0
    t2_dist = 100 * abs(signal.target2 - mid) / mid if mid else 0

    side_emoji = "LONG" if signal.side == "long" else "SHORT"
    emoji = "🟢" if signal.side == "long" else "🔴"
    stars = "⭐⭐⭐" if signal.confidence == "HIGH" else "⭐⭐"

    ctx = signal.market_context
    vol_dir = "Increasing" if (ctx.get("volume_change_pct") or 0) >= 0 else "Decreasing"
    vol_pct = ctx.get("volume_change_pct", 0)

    levels = signal.levels
    pdh = levels.get("pdh")
    pdl = levels.get("pdl")
    support = levels.get("support")
    resistance = levels.get("resistance")

    lines = [
        "🚨 FUTURES SIGNAL 🚨",
        "",
        f"{emoji} {side_emoji} {signal.symbol}",
        "",
        f"💎 SETUP: {signal.setup_type}",
        f"⭐ CONFIDENCE: {signal.confidence} {stars}",
        "",
        f"💰 ENTRY ZONE: ${entry_low:.4f} - ${entry_high:.4f}",
        f"🛑 STOP LOSS: ${signal.stop:.4f} ({stop_dist_pct:.2f}%)",
        f"🎯 TARGET 1: ${signal.target1:.4f} ({t1_dist:.2f}%)",
        f"🎯 TARGET 2: ${signal.target2:.4f} ({t2_dist:.2f}%)",
        "",
        f"📊 RISK:REWARD = 1:{signal.rr_ratio:.1f}",
        "",
        "📈 MARKET CONTEXT:",
        f"- Trend (1D): {ctx.get('trend_1d', 'N/A')}",
        f"- Structure (4H): {ctx.get('structure_4h', 'N/A')}",
        f"- Volume: {vol_dir} ({vol_pct}%)",
        f"- RSI: {ctx.get('rsi', 'N/A')}",
        "",
        "💡 KEY LEVELS:",
        f"- PDH: ${pdh:.4f}" if pdh is not None else "- PDH: N/A",
        f"- PDL: ${pdl:.4f}" if pdl is not None else "- PDL: N/A",
        f"- Support: ${support:.4f}" if support is not None else "- Support: N/A",
        f"- Resistance: ${resistance:.4f}" if resistance is not None else "- Resistance: N/A",
        "",
        "⚡ CONFLUENCE:",
    ]
    for c in signal.confluence_list:
        lines.append(f"- {c}")
    lines.extend([
        "",
        f"📊 Position Size (for ${config.ACCOUNT_SIZE:.0f} account, {config.RISK_PER_TRADE}% risk):",
        f"- Risk: ${risk_output.risk_usd:.2f}",
        f"- Position: ${risk_output.position_size_usd:.2f} at {risk_output.suggested_leverage}x leverage",
        "",
        f"⏰ {signal.timestamp}",
        "",
        f"🔗 Chart: https://www.mexc.com/futures/{signal.symbol.replace(':', '/')}",
        "",
        "⚠️ VERIFY SETUP YOURSELF - NOT FINANCIAL ADVICE",
    ])
    text = "\n".join(lines)
    return _send_raw(text)


def send_startup_message(coin_count: int) -> bool:
    """Send 'Scanner started, monitoring N coins'."""
    text = f"🚀 Scanner started, monitoring {coin_count} coins"
    return _send_raw(text)
