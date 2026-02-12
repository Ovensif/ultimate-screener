"""
Signal generation: 1D trend filter, 3 setup types, confluence, R:R gate.
Only HIGH confidence signals when CONFIDENCE_THRESHOLD is HIGH.
"""
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional, Tuple

from . import config
from .market_analyzer import MarketAnalysis

logger = logging.getLogger(__name__)

# Stop distance cap from entry (fraction)
MAX_STOP_PCT = 0.03
MIN_STOP_PCT = 0.01


@dataclass
class Signal:
    symbol: str
    side: str  # "long" | "short"
    setup_type: str  # "Breakout Retest" | "Liquidity Sweep" | "Trend Continuation"
    confidence: str  # "HIGH" | "MEDIUM"
    entry_zone: Tuple[float, float]
    stop: float
    target1: float
    target2: float
    rr_ratio: float
    market_context: dict = field(default_factory=dict)
    levels: dict = field(default_factory=dict)
    confluence_list: List[str] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


def _confluence_count_long(a_4h: MarketAnalysis) -> Tuple[int, List[str]]:
    factors = []
    if a_4h.volume_spike:
        factors.append("Volume spike confirming direction")
    if a_4h.rsi is not None and a_4h.rsi > 50:
        factors.append("RSI > 50")
    if a_4h.macd_turning_positive:
        factors.append("MACD histogram turning positive")
    if a_4h.at_support or a_4h.fvg_bullish:
        factors.append("Price at major support or FVG")
    if a_4h.obv_rising is True:
        factors.append("OBV trending up (pandas-ta)")
    if a_4h.stoch_rsi_k is not None and a_4h.stoch_rsi_k < 50:
        factors.append("Stoch RSI bullish zone (pandas-ta)")
    return len(factors), factors


def _confluence_count_short(a_4h: MarketAnalysis) -> Tuple[int, List[str]]:
    factors = []
    if a_4h.volume_spike:
        factors.append("Volume spike confirming direction")
    if a_4h.rsi is not None and a_4h.rsi < 50:
        factors.append("RSI < 50")
    if a_4h.macd_hist is not None and a_4h.macd_hist < 0 and not a_4h.macd_turning_positive:
        factors.append("MACD bearish")
    if a_4h.at_resistance or a_4h.fvg_bearish:
        factors.append("Price at major resistance or FVG")
    if a_4h.obv_rising is False and a_4h.obv_rising is not None:
        factors.append("OBV trending down (pandas-ta)")
    if a_4h.stoch_rsi_k is not None and a_4h.stoch_rsi_k > 50:
        factors.append("Stoch RSI bearish zone (pandas-ta)")
    return len(factors), factors


def _check_1d_uptrend(a_1d: MarketAnalysis) -> bool:
    if a_1d.ema50 is None or a_1d.last_close is None:
        return False
    if a_1d.last_close <= a_1d.ema50:
        return False
    if len(a_1d.swing_lows) >= 2 and a_1d.swing_lows[-1] <= a_1d.swing_lows[-2]:
        return False
    return True


def _check_1d_downtrend(a_1d: MarketAnalysis) -> bool:
    if a_1d.ema50 is None or a_1d.last_close is None:
        return False
    if a_1d.last_close >= a_1d.ema50:
        return False
    if len(a_1d.swing_highs) >= 2 and a_1d.swing_highs[-1] >= a_1d.swing_highs[-2]:
        return False
    return True


def _setup_breakout_retest_long(a_4h: MarketAnalysis) -> bool:
    if not a_4h.resistance_levels or a_4h.last_close is None:
        return False
    # Simplified: price above recent resistance, pulled back (last low near resistance), bouncing
    prev_res = a_4h.resistance_levels[-1]
    if a_4h.last_close <= prev_res:
        return False
    if a_4h.last_low is None:
        return False
    # Retest: low touched near breakout level (within 0.5%)
    near_retest = abs(a_4h.last_low - prev_res) / prev_res <= 0.005
    if not near_retest:
        return False
    if not a_4h.volume_spike:
        return False
    if not a_4h.last_bullish:
        return False
    return True


def _setup_breakout_retest_short(a_4h: MarketAnalysis) -> bool:
    if not a_4h.support_levels or a_4h.last_close is None:
        return False
    prev_sup = a_4h.support_levels[0]
    if a_4h.last_close >= prev_sup:
        return False
    if a_4h.last_high is None:
        return False
    near_retest = abs(a_4h.last_high - prev_sup) / prev_sup <= 0.005
    if not near_retest or not a_4h.volume_spike:
        return False
    if a_4h.last_bullish:
        return False
    return True


def _setup_liquidity_sweep_long(a_4h: MarketAnalysis) -> bool:
    return a_4h.liquidity_sweep_detected == "long" and (a_4h.volume_spike or a_4h.volume_ratio >= 1.2)


def _setup_liquidity_sweep_short(a_4h: MarketAnalysis) -> bool:
    return a_4h.liquidity_sweep_detected == "short" and (a_4h.volume_spike or a_4h.volume_ratio >= 1.2)


def _setup_trend_continuation_long(a_4h: MarketAnalysis) -> bool:
    if a_4h.trend != "uptrend":
        return False
    if a_4h.ema21 is None or a_4h.last_close is None:
        return False
    if a_4h.rsi is None or a_4h.rsi < 40 or a_4h.rsi > 55:
        return False
    near_ema = abs(a_4h.last_close - a_4h.ema21) / a_4h.ema21 <= 0.01
    near_fib = a_4h.fib_50_level and abs(a_4h.last_close - a_4h.fib_50_level) / a_4h.fib_50_level <= 0.01
    if not (near_ema or near_fib):
        return False
    return a_4h.last_bullish


def _setup_trend_continuation_short(a_4h: MarketAnalysis) -> bool:
    if a_4h.trend != "downtrend":
        return False
    if a_4h.ema21 is None or a_4h.last_close is None:
        return False
    if a_4h.rsi is None or a_4h.rsi < 45 or a_4h.rsi > 60:
        return False
    near_ema = abs(a_4h.last_close - a_4h.ema21) / a_4h.ema21 <= 0.01
    near_fib = a_4h.fib_50_level and abs(a_4h.last_close - a_4h.fib_50_level) / a_4h.fib_50_level <= 0.01
    if not (near_ema or near_fib):
        return False
    return not a_4h.last_bullish


def _stops_and_targets(
    side: str,
    entry: float,
    a_4h: MarketAnalysis,
) -> Optional[Tuple[float, float, float, float]]:
    """Return (stop, target1, target2, rr_ratio) or None if R:R too low. Stop capped at 2-3% from entry."""
    if side == "long":
        stop = a_4h.recent_low
        if a_4h.last_low is not None and (stop is None or a_4h.last_low < stop):
            stop = a_4h.last_low
        if stop is None:
            return None
        # Cap stop distance at MAX_STOP_PCT below entry (stop not too far)
        stop = max(stop, entry * (1 - MAX_STOP_PCT))
        targets = [r for r in (a_4h.resistance_levels or []) if r > entry]
        targets = sorted(targets)[:2]
        if not targets:
            target1 = entry * 1.02
            target2 = entry * 1.04
        else:
            target1 = targets[0]
            target2 = targets[1] if len(targets) > 1 else entry * 1.04
    else:
        stop = a_4h.recent_high
        if a_4h.last_high is not None and (stop is None or a_4h.last_high > stop):
            stop = a_4h.last_high
        if stop is None:
            return None
        # Cap stop distance at MAX_STOP_PCT above entry
        stop = min(stop, entry * (1 + MAX_STOP_PCT))
        supports = [s for s in (a_4h.support_levels or []) if s < entry]
        supports = sorted(supports, reverse=True)[:2]
        if not supports:
            target1 = entry * 0.98
            target2 = entry * 0.96
        else:
            target1 = supports[0]
            target2 = supports[1] if len(supports) > 1 else entry * 0.96
    risk = abs(entry - stop)
    reward1 = abs(target1 - entry)
    rr = (reward1 / risk) if risk > 0 else 0
    if rr < config.MIN_RR_RATIO:
        return None
    return stop, target1, target2, rr


def generate_signals(
    symbol: str,
    a_1d: Optional[MarketAnalysis],
    a_4h: Optional[MarketAnalysis],
    current_price: Optional[float] = None,
) -> List[Signal]:
    """
    Evaluate 1D trend + 4H setup + confluence + R:R. Return list of signals (usually 0 or 1).
    Only returns signals with confidence >= CONFIDENCE_THRESHOLD and R:R >= MIN_RR_RATIO.
    """
    if not a_1d or not a_4h:
        return []
    price = current_price or a_4h.last_close
    if price is None:
        return []

    signals = []
    # Volume filter: skip if current candle volume too low
    if a_4h.volume_ma and a_4h.last_volume is not None and a_4h.last_volume < 0.5 * a_4h.volume_ma:
        return []

    # ---- LONG ----
    if _check_1d_uptrend(a_1d):
        setup_type = None
        if _setup_breakout_retest_long(a_4h):
            setup_type = "Breakout Retest"
        elif _setup_liquidity_sweep_long(a_4h):
            setup_type = "Liquidity Sweep"
        elif _setup_trend_continuation_long(a_4h):
            setup_type = "Trend Continuation"
        if setup_type:
            conf_count, conf_list = _confluence_count_long(a_4h)
            if conf_count >= 2:
                confidence = "HIGH" if conf_count >= 3 else "MEDIUM"
                entry_low = a_4h.last_low or price
                entry_high = a_4h.last_high or price
                entry = (entry_low + entry_high) / 2
                result = _stops_and_targets("long", entry, a_4h)
                if result:
                    stop, t1, t2, rr = result
                    send = (config.CONFIDENCE_THRESHOLD == "HIGH" and confidence == "HIGH") or (
                        config.CONFIDENCE_THRESHOLD == "MEDIUM" and confidence in ("HIGH", "MEDIUM")
                    )
                    if rr >= config.MIN_RR_RATIO and send:
                        signals.append(Signal(
                            symbol=symbol,
                            side="long",
                            setup_type=setup_type,
                            confidence=confidence,
                            entry_zone=(entry_low, entry_high),
                            stop=stop,
                            target1=t1,
                            target2=t2,
                            rr_ratio=rr,
                            market_context={
                                "trend_1d": "Bullish",
                                "structure_4h": "HH/HL" if a_4h.trend == "uptrend" else a_4h.trend,
                                "volume_change_pct": round((a_4h.volume_ratio - 1) * 100, 1) if a_4h.volume_ratio else 0,
                                "rsi": round(a_4h.rsi, 1) if a_4h.rsi is not None else None,
                            },
                            levels={
                                "pdh": a_4h.pdh,
                                "pdl": a_4h.pdl,
                                "support": a_4h.support_levels[-1] if a_4h.support_levels else None,
                                "resistance": a_4h.resistance_levels[-1] if a_4h.resistance_levels else None,
                            },
                            confluence_list=conf_list,
                        ))

    # ---- SHORT ----
    if _check_1d_downtrend(a_1d):
        setup_type = None
        if _setup_breakout_retest_short(a_4h):
            setup_type = "Breakout Retest"
        elif _setup_liquidity_sweep_short(a_4h):
            setup_type = "Liquidity Sweep"
        elif _setup_trend_continuation_short(a_4h):
            setup_type = "Trend Continuation"
        if setup_type:
            conf_count, conf_list = _confluence_count_short(a_4h)
            if conf_count >= 2:
                confidence = "HIGH" if conf_count >= 3 else "MEDIUM"
                entry_low = a_4h.last_low or price
                entry_high = a_4h.last_high or price
                entry = (entry_low + entry_high) / 2
                result = _stops_and_targets("short", entry, a_4h)
                if result:
                    stop, t1, t2, rr = result
                    send = (config.CONFIDENCE_THRESHOLD == "HIGH" and confidence == "HIGH") or (
                        config.CONFIDENCE_THRESHOLD == "MEDIUM" and confidence in ("HIGH", "MEDIUM")
                    )
                    if rr >= config.MIN_RR_RATIO and send:
                        signals.append(Signal(
                            symbol=symbol,
                            side="short",
                            setup_type=setup_type,
                            confidence=confidence,
                            entry_zone=(entry_low, entry_high),
                            stop=stop,
                            target1=t1,
                            target2=t2,
                            rr_ratio=rr,
                            market_context={
                                "trend_1d": "Bearish",
                                "structure_4h": "LH/LL" if a_4h.trend == "downtrend" else a_4h.trend,
                                "volume_change_pct": round((a_4h.volume_ratio - 1) * 100, 1) if a_4h.volume_ratio else 0,
                                "rsi": round(a_4h.rsi, 1) if a_4h.rsi is not None else None,
                            },
                            levels={
                                "pdh": a_4h.pdh,
                                "pdl": a_4h.pdl,
                                "support": a_4h.support_levels[-1] if a_4h.support_levels else None,
                                "resistance": a_4h.resistance_levels[-1] if a_4h.resistance_levels else None,
                            },
                            confluence_list=conf_list,
                        ))

    return signals
