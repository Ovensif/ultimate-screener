"""
Signal generation: 1D trend filter, 3 setup types, confluence, R:R gate.
Beast-mode: ADX gate, tighter retest, sweep confirmation, 12 confluence factors,
4+ for HIGH, ATR-based stops/targets, R:R quality bonus.
"""
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional, Tuple

from . import config
from .market_analyzer import MarketAnalysis

logger = logging.getLogger(__name__)


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


# ---------------------------------------------------------------------------
# Confluence counting (12 possible factors per side)
# ---------------------------------------------------------------------------

def _confluence_count_long(a_4h: MarketAnalysis) -> Tuple[int, List[str]]:
    factors: List[str] = []
    # Original 6
    if a_4h.volume_spike:
        factors.append("Volume spike confirming direction")
    if a_4h.rsi is not None and a_4h.rsi > 50:
        factors.append("RSI > 50")
    if a_4h.macd_turning_positive:
        factors.append("MACD histogram turning positive")
    if a_4h.at_support or a_4h.fvg_bullish:
        factors.append("Price at major support or FVG")
    if a_4h.obv_rising is True:
        factors.append("OBV trending up")
    if a_4h.stoch_rsi_k is not None and a_4h.stoch_rsi_k < 50:
        factors.append("Stoch RSI bullish zone")
    # Beast-mode 6 new factors
    if a_4h.rsi_bull_divergence:
        factors.append("RSI bullish divergence")
    if a_4h.bullish_ob_zone is not None and a_4h.last_close is not None:
        ob_low, ob_high = a_4h.bullish_ob_zone
        if ob_low <= a_4h.last_close <= ob_high * 1.005:
            factors.append("Price at bullish order block")
    if a_4h.msb_bullish:
        factors.append("Bullish market structure break")
    if a_4h.bb_squeeze:
        factors.append("BB squeeze breakout")
    if a_4h.adx_very_strong:
        factors.append("ADX very strong (>35)")
    if a_4h.atr_pct_ok:
        factors.append("ATR% in healthy range")
    return len(factors), factors


def _confluence_count_short(a_4h: MarketAnalysis) -> Tuple[int, List[str]]:
    factors: List[str] = []
    # Original 6
    if a_4h.volume_spike:
        factors.append("Volume spike confirming direction")
    if a_4h.rsi is not None and a_4h.rsi < 50:
        factors.append("RSI < 50")
    if a_4h.macd_hist is not None and a_4h.macd_hist < 0 and not a_4h.macd_turning_positive:
        factors.append("MACD bearish")
    if a_4h.at_resistance or a_4h.fvg_bearish:
        factors.append("Price at major resistance or FVG")
    if a_4h.obv_rising is False and a_4h.obv_rising is not None:
        factors.append("OBV trending down")
    if a_4h.stoch_rsi_k is not None and a_4h.stoch_rsi_k > 50:
        factors.append("Stoch RSI bearish zone")
    # Beast-mode 6 new factors
    if a_4h.rsi_bear_divergence:
        factors.append("RSI bearish divergence")
    if a_4h.bearish_ob_zone is not None and a_4h.last_close is not None:
        ob_low, ob_high = a_4h.bearish_ob_zone
        if ob_low * 0.995 <= a_4h.last_close <= ob_high:
            factors.append("Price at bearish order block")
    if a_4h.msb_bearish:
        factors.append("Bearish market structure break")
    if a_4h.bb_squeeze:
        factors.append("BB squeeze breakout")
    if a_4h.adx_very_strong:
        factors.append("ADX very strong (>35)")
    if a_4h.atr_pct_ok:
        factors.append("ATR% in healthy range")
    return len(factors), factors


# ---------------------------------------------------------------------------
# 1D trend filters
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# 4H Setup detection (beast-mode tightened)
# ---------------------------------------------------------------------------

def _setup_breakout_retest_long(a_4h: MarketAnalysis) -> bool:
    if not a_4h.resistance_levels or a_4h.last_close is None:
        return False
    prev_res = a_4h.resistance_levels[-1]
    if a_4h.last_close <= prev_res:
        return False
    if a_4h.last_low is None or a_4h.last_open is None:
        return False
    # Tightened retest tolerance (configurable, default 0.3%)
    tolerance = getattr(config, "RETEST_TOLERANCE", 0.003)
    near_retest = abs(a_4h.last_low - prev_res) / prev_res <= tolerance
    if not near_retest:
        return False
    if not a_4h.volume_spike:
        return False
    if not a_4h.last_bullish:
        return False
    # Beast-mode: candle wick rejection -- lower wick > 60% of body
    body = abs(a_4h.last_close - a_4h.last_open)
    lower_wick = min(a_4h.last_close, a_4h.last_open) - a_4h.last_low
    if body > 0 and lower_wick < 0.6 * body:
        return False
    return True


def _setup_breakout_retest_short(a_4h: MarketAnalysis) -> bool:
    if not a_4h.support_levels or a_4h.last_close is None:
        return False
    prev_sup = a_4h.support_levels[0]
    if a_4h.last_close >= prev_sup:
        return False
    if a_4h.last_high is None or a_4h.last_open is None:
        return False
    tolerance = getattr(config, "RETEST_TOLERANCE", 0.003)
    near_retest = abs(a_4h.last_high - prev_sup) / prev_sup <= tolerance
    if not near_retest or not a_4h.volume_spike:
        return False
    if a_4h.last_bullish:
        return False
    # Beast-mode: upper wick rejection > 60% of body
    body = abs(a_4h.last_close - a_4h.last_open)
    upper_wick = a_4h.last_high - max(a_4h.last_close, a_4h.last_open)
    if body > 0 and upper_wick < 0.6 * body:
        return False
    return True


def _setup_liquidity_sweep_long(a_4h: MarketAnalysis) -> bool:
    # Beast-mode: require sweep_confirmed (reversal confirmation) + volume spike
    return (
        a_4h.liquidity_sweep_detected == "long"
        and a_4h.sweep_confirmed
        and a_4h.volume_spike
    )


def _setup_liquidity_sweep_short(a_4h: MarketAnalysis) -> bool:
    return (
        a_4h.liquidity_sweep_detected == "short"
        and a_4h.sweep_confirmed
        and a_4h.volume_spike
    )


def _setup_trend_continuation_long(a_4h: MarketAnalysis) -> bool:
    if a_4h.trend != "uptrend":
        return False
    if a_4h.ema21 is None or a_4h.last_close is None:
        return False
    # Beast-mode: wider RSI range (35-55)
    if a_4h.rsi is None or a_4h.rsi < 35 or a_4h.rsi > 55:
        return False
    near_ema = abs(a_4h.last_close - a_4h.ema21) / a_4h.ema21 <= 0.01
    near_fib = a_4h.fib_50_level and abs(a_4h.last_close - a_4h.fib_50_level) / a_4h.fib_50_level <= 0.01
    if not (near_ema or near_fib):
        return False
    if not a_4h.last_bullish:
        return False
    # Beast-mode: EMA21 must be rising
    if not a_4h.ema21_rising:
        return False
    return True


def _setup_trend_continuation_short(a_4h: MarketAnalysis) -> bool:
    if a_4h.trend != "downtrend":
        return False
    if a_4h.ema21 is None or a_4h.last_close is None:
        return False
    # Beast-mode: wider RSI range (45-65)
    if a_4h.rsi is None or a_4h.rsi < 45 or a_4h.rsi > 65:
        return False
    near_ema = abs(a_4h.last_close - a_4h.ema21) / a_4h.ema21 <= 0.01
    near_fib = a_4h.fib_50_level and abs(a_4h.last_close - a_4h.fib_50_level) / a_4h.fib_50_level <= 0.01
    if not (near_ema or near_fib):
        return False
    if a_4h.last_bullish:
        return False
    # Beast-mode: EMA21 must be falling
    if not a_4h.ema21_falling:
        return False
    return True


# ---------------------------------------------------------------------------
# Stops, targets, R:R (ATR-based with volume-weighted levels)
# ---------------------------------------------------------------------------

def _stops_and_targets(
    side: str,
    entry: float,
    a_4h: MarketAnalysis,
) -> Optional[Tuple[float, float, float, float]]:
    """
    Return (stop, target1, target2, rr_ratio) or None if R:R too low.
    Beast-mode: ATR-based stops/targets, volume-weighted levels, 2.5% cap.
    """
    max_stop_pct = getattr(config, "MAX_STOP_PCT", 0.025)
    atr = a_4h.atr_value  # raw ATR value

    if side == "long":
        # Structure-based stop
        struct_stop = a_4h.recent_low
        if a_4h.last_low is not None and (struct_stop is None or a_4h.last_low < struct_stop):
            struct_stop = a_4h.last_low
        # ATR-based stop (1.5x ATR below entry)
        atr_stop = entry - 1.5 * atr if atr else None
        # Use tighter of structure and ATR, but never override a tighter structure stop
        if struct_stop is None and atr_stop is None:
            return None
        if struct_stop is not None and atr_stop is not None:
            stop = max(struct_stop, atr_stop)  # choose higher (tighter) stop
        else:
            stop = struct_stop if struct_stop is not None else atr_stop
        # Cap at max_stop_pct but never override a tighter structure stop
        floor = entry * (1 - max_stop_pct)
        if stop < floor:
            stop = floor
        # Targets: prefer volume-weighted resistance, then raw, then ATR-based
        targets = []
        for lvl in (a_4h.strong_resistance or []):
            if lvl > entry:
                targets.append(lvl)
        if not targets:
            for lvl in sorted(a_4h.resistance_levels or []):
                if lvl > entry:
                    targets.append(lvl)
        targets = sorted(targets)[:2]
        if not targets:
            # ATR-based fallback: 1.5x ATR for T1, 3x ATR for T2
            t1_atr = entry + 1.5 * atr if atr else entry * 1.02
            t2_atr = entry + 3.0 * atr if atr else entry * 1.04
            target1, target2 = t1_atr, t2_atr
        else:
            target1 = targets[0]
            if len(targets) > 1:
                target2 = targets[1]
            else:
                target2 = entry + 3.0 * atr if atr else entry * 1.04
    else:
        # Short side
        struct_stop = a_4h.recent_high
        if a_4h.last_high is not None and (struct_stop is None or a_4h.last_high > struct_stop):
            struct_stop = a_4h.last_high
        atr_stop = entry + 1.5 * atr if atr else None
        if struct_stop is None and atr_stop is None:
            return None
        if struct_stop is not None and atr_stop is not None:
            stop = min(struct_stop, atr_stop)  # choose lower (tighter) stop
        else:
            stop = struct_stop if struct_stop is not None else atr_stop
        ceil = entry * (1 + max_stop_pct)
        if stop > ceil:
            stop = ceil
        targets = []
        for lvl in (a_4h.strong_support or []):
            if lvl < entry:
                targets.append(lvl)
        if not targets:
            for lvl in sorted(a_4h.support_levels or [], reverse=True):
                if lvl < entry:
                    targets.append(lvl)
        targets = sorted(targets, reverse=True)[:2]
        if not targets:
            t1_atr = entry - 1.5 * atr if atr else entry * 0.98
            t2_atr = entry - 3.0 * atr if atr else entry * 0.96
            target1, target2 = t1_atr, t2_atr
        else:
            target1 = targets[0]
            if len(targets) > 1:
                target2 = targets[1]
            else:
                target2 = entry - 3.0 * atr if atr else entry * 0.96

    risk = abs(entry - stop)
    reward1 = abs(target1 - entry)
    rr = (reward1 / risk) if risk > 0 else 0
    if rr < config.MIN_RR_RATIO:
        return None
    return stop, target1, target2, rr


# ---------------------------------------------------------------------------
# Main signal generation
# ---------------------------------------------------------------------------

def generate_signals(
    symbol: str,
    a_1d: Optional[MarketAnalysis],
    a_4h: Optional[MarketAnalysis],
    current_price: Optional[float] = None,
) -> List[Signal]:
    """
    Evaluate 1D trend + 4H setup + confluence + R:R.
    Beast-mode: ADX gate, 4+ for HIGH, R:R quality bonus.
    """
    if not a_1d or not a_4h:
        return []
    price = current_price or a_4h.last_close
    if price is None:
        return []

    signals: List[Signal] = []

    # Volume filter: skip if current candle volume too low
    if a_4h.volume_ma and a_4h.last_volume is not None and a_4h.last_volume < 0.5 * a_4h.volume_ma:
        return []

    # Beast-mode: ADX gate -- no signal if market is ranging
    adx_min = getattr(config, "ADX_MIN_SIGNAL", 20.0)
    if a_4h.adx is not None and a_4h.adx < adx_min:
        logger.debug("Skip %s: ADX %.1f < %.1f", symbol, a_4h.adx, adx_min)
        return []

    # Beast-mode: ATR filter -- skip dead coins or extreme volatility
    if not a_4h.atr_pct_ok:
        logger.debug("Skip %s: ATR%% %.2f out of range", symbol, a_4h.atr_pct or 0)
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
                # Beast-mode: 4+ = HIGH, 3 = MEDIUM (was 3+ = HIGH)
                confidence = "HIGH" if conf_count >= 4 else "MEDIUM"
                entry_low = a_4h.last_low or price
                entry_high = a_4h.last_high or price
                entry = (entry_low + entry_high) / 2
                result = _stops_and_targets("long", entry, a_4h)
                if result:
                    stop, t1, t2, rr = result
                    # Beast-mode: R:R quality bonus -- allow MEDIUM if R:R >= 3.0
                    send = False
                    if config.CONFIDENCE_THRESHOLD == "HIGH":
                        if confidence == "HIGH":
                            send = True
                        elif confidence == "MEDIUM" and rr >= 3.0:
                            send = True  # quality bonus
                    elif config.CONFIDENCE_THRESHOLD == "MEDIUM":
                        send = confidence in ("HIGH", "MEDIUM")
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
                                "adx": round(a_4h.adx, 1) if a_4h.adx is not None else None,
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
                confidence = "HIGH" if conf_count >= 4 else "MEDIUM"
                entry_low = a_4h.last_low or price
                entry_high = a_4h.last_high or price
                entry = (entry_low + entry_high) / 2
                result = _stops_and_targets("short", entry, a_4h)
                if result:
                    stop, t1, t2, rr = result
                    send = False
                    if config.CONFIDENCE_THRESHOLD == "HIGH":
                        if confidence == "HIGH":
                            send = True
                        elif confidence == "MEDIUM" and rr >= 3.0:
                            send = True
                    elif config.CONFIDENCE_THRESHOLD == "MEDIUM":
                        send = confidence in ("HIGH", "MEDIUM")
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
                                "adx": round(a_4h.adx, 1) if a_4h.adx is not None else None,
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
