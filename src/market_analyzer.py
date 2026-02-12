"""
Technical analysis: structure, volume, indicators, liquidity concepts.
Beast-mode upgrade: RSI divergence, order blocks, MSB, sweep confirmation,
volume-weighted S/R, BB squeeze, ADX/ATR booleans.
Outputs a structured result per timeframe for signal_generator.
"""
import logging
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import numpy as np
import pandas as pd

from . import config

logger = logging.getLogger(__name__)

# Try pandas_ta; fallback to manual implementations if not available
try:
    import pandas_ta as ta
    HAS_PANDAS_TA = True
except ImportError:
    HAS_PANDAS_TA = False


@dataclass
class MarketAnalysis:
    """Result of analyzing one timeframe (1D or 4H)."""
    # Structure
    trend: str  # "uptrend" | "downtrend" | "range"
    swing_highs: List[float] = field(default_factory=list)
    swing_lows: List[float] = field(default_factory=list)
    support_levels: List[float] = field(default_factory=list)
    resistance_levels: List[float] = field(default_factory=list)
    strong_support: List[float] = field(default_factory=list)    # volume-weighted top 3
    strong_resistance: List[float] = field(default_factory=list)  # volume-weighted top 3
    pdh: Optional[float] = None
    pdl: Optional[float] = None
    # Volume
    volume_ma: Optional[float] = None
    volume_spike: bool = False
    volume_ratio: float = 1.0
    # Indicators (last bar)
    rsi: Optional[float] = None
    macd_hist: Optional[float] = None
    macd_turning_positive: bool = False
    adx: Optional[float] = None
    ema21: Optional[float] = None
    ema50: Optional[float] = None
    ema200: Optional[float] = None
    bb_upper: Optional[float] = None
    bb_lower: Optional[float] = None
    # Beast-mode: ADX booleans
    adx_strong: bool = False      # ADX > 25
    adx_very_strong: bool = False  # ADX > 35
    # Beast-mode: BB squeeze
    bb_squeeze: bool = False
    # Beast-mode: RSI divergence
    rsi_bull_divergence: bool = False
    rsi_bear_divergence: bool = False
    # Beast-mode: order blocks
    bullish_ob_zone: Optional[Tuple[float, float]] = None  # (low, high) of bullish OB
    bearish_ob_zone: Optional[Tuple[float, float]] = None  # (low, high) of bearish OB
    # Beast-mode: market structure break
    msb_bullish: bool = False
    msb_bearish: bool = False
    # Liquidity
    liquidity_sweep_detected: Optional[str] = None  # "long" | "short" | None
    sweep_confirmed: bool = False  # sweep + next candle confirmation
    fvg_bullish: bool = False
    fvg_bearish: bool = False
    at_support: bool = False
    at_resistance: bool = False
    # Last bar and current price
    last_close: Optional[float] = None
    last_high: Optional[float] = None
    last_low: Optional[float] = None
    last_open: Optional[float] = None
    last_volume: Optional[float] = None
    last_bullish: bool = False
    # For trend continuation: pullback level
    fib_50_level: Optional[float] = None
    recent_low: Optional[float] = None
    recent_high: Optional[float] = None
    # EMA21 slope (for trend continuation confirmation)
    ema21_rising: bool = False
    ema21_falling: bool = False
    # Extra context from pandas-ta (confluence)
    obv_rising: Optional[bool] = None
    atr_pct: Optional[float] = None
    atr_value: Optional[float] = None  # raw ATR for stop/target calculation
    atr_pct_ok: bool = False           # ATR% in healthy range
    stoch_rsi_k: Optional[float] = None


# ---------------------------------------------------------------------------
# Core indicator helpers (fallback when pandas-ta not available)
# ---------------------------------------------------------------------------

def _ema(series: pd.Series, length: int) -> pd.Series:
    return series.ewm(span=length, adjust=False).mean()


def _rsi(series: pd.Series, length: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = (-delta).where(delta < 0, 0.0)
    avg_gain = gain.ewm(alpha=1 / length, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / length, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def _macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> Tuple[pd.Series, pd.Series, pd.Series]:
    ema_f = _ema(close, fast)
    ema_s = _ema(close, slow)
    macd_line = ema_f - ema_s
    signal_line = _ema(macd_line, signal)
    hist = macd_line - signal_line
    return macd_line, signal_line, hist


def _adx(high: pd.Series, low: pd.Series, close: pd.Series, length: int = 14) -> pd.Series:
    """Simplified ADX."""
    plus_dm = high.diff()
    minus_dm = -low.diff()
    plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0.0)
    minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0.0)
    tr = pd.concat([
        high - low,
        (high - close.shift(1)).abs(),
        (low - close.shift(1)).abs(),
    ], axis=1).max(axis=1)
    atr = tr.ewm(span=length, adjust=False).mean()
    plus_di = 100 * (plus_dm.ewm(span=length, adjust=False).mean() / atr)
    minus_di = 100 * (minus_dm.ewm(span=length, adjust=False).mean() / atr)
    dx = 100 * (abs(plus_di - minus_di) / (plus_di + minus_di))
    return dx.ewm(span=length, adjust=False).mean()


def _bb(close: pd.Series, length: int = 20, std: float = 2.0) -> Tuple[pd.Series, pd.Series, pd.Series]:
    mid = close.rolling(length).mean()
    sd = close.rolling(length).std()
    upper = mid + std * sd
    lower = mid - std * sd
    return upper, mid, lower


def _atr(high: pd.Series, low: pd.Series, close: pd.Series, length: int = 14) -> pd.Series:
    """Average True Range."""
    tr = pd.concat([
        high - low,
        (high - close.shift(1)).abs(),
        (low - close.shift(1)).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(span=length, adjust=False).mean()


# ---------------------------------------------------------------------------
# Compute all indicators
# ---------------------------------------------------------------------------

def _compute_indicators(df: pd.DataFrame) -> dict:
    """Add RSI, MACD, ADX, EMA, BB, ATR, OBV, StochRSI and return last values."""
    if df is None or len(df) < 50:
        return {}
    close = df["close"]
    high = df["high"]
    low = df["low"]
    out = {}

    if HAS_PANDAS_TA:
        try:
            out["rsi"] = ta.rsi(close, length=14).iloc[-1] if len(close) >= 14 else None
            macd = ta.macd(close, fast=12, slow=26, signal=9)
            if macd is not None and not macd.empty:
                if isinstance(macd, pd.DataFrame):
                    hist_col = [c for c in macd.columns if "MACDH" in c.upper() or "MACD_12_26_9" in str(c)]
                    if not hist_col:
                        hist_col = list(macd.columns)[-1]
                    else:
                        hist_col = hist_col[0]
                    out["macd_hist"] = macd[hist_col].iloc[-1]
                    out["macd_turning_positive"] = len(macd) >= 2 and macd[hist_col].iloc[-2] < 0 <= macd[hist_col].iloc[-1]
                else:
                    out["macd_hist"] = macd.iloc[-1]
                    out["macd_turning_positive"] = False
            adx_df = ta.adx(high, low, close, length=14)
            if isinstance(adx_df, pd.DataFrame) and "ADX_14" in adx_df.columns:
                out["adx"] = adx_df["ADX_14"].iloc[-1]
            elif isinstance(adx_df, pd.Series):
                out["adx"] = adx_df.iloc[-1]
            out["ema21"] = ta.ema(close, length=21).iloc[-1]
            out["ema50"] = ta.ema(close, length=50).iloc[-1]
            out["ema200"] = ta.ema(close, length=200).iloc[-1] if len(close) >= 200 else None
            bb = ta.bbands(close, length=20, std=2)
            if bb is not None and not bb.empty:
                if isinstance(bb, pd.DataFrame):
                    ub = [c for c in bb.columns if "BBU" in c or "upper" in c.lower()]
                    lb = [c for c in bb.columns if "BBL" in c or "lower" in c.lower()]
                    out["bb_upper"] = bb[ub[0]].iloc[-1] if ub else None
                    out["bb_lower"] = bb[lb[0]].iloc[-1] if lb else None
                    # BB squeeze: width in bottom 20th percentile of last 50 bars
                    if ub and lb:
                        bb_width = bb[ub[0]] - bb[lb[0]]
                        if len(bb_width) >= 50:
                            recent_width = bb_width.iloc[-50:]
                            percentile_20 = recent_width.quantile(0.2)
                            out["bb_squeeze"] = bool(bb_width.iloc[-1] <= percentile_20)
                else:
                    out["bb_upper"] = out["bb_lower"] = None
            # Extra context from pandas-ta
            vol = df["volume"] if "volume" in df.columns else pd.Series(dtype=float)
            if len(vol) >= 20:
                obv = ta.obv(close, vol)
                if obv is not None and len(obv) >= 5:
                    out["obv_rising"] = bool(obv.iloc[-1] > obv.iloc[-5])
                atr_series = ta.atr(high, low, close, length=14)
                if atr_series is not None and len(atr_series) and close.iloc[-1] and close.iloc[-1] > 0:
                    out["atr_value"] = float(atr_series.iloc[-1])
                    out["atr_pct"] = float(100 * atr_series.iloc[-1] / close.iloc[-1])
                stoch = ta.stochrsi(close, length=14, rsi_length=14, k=3, d=3)
                if stoch is not None and not stoch.empty:
                    sk = stoch.iloc[:, 0] if isinstance(stoch, pd.DataFrame) else stoch
                    out["stoch_rsi_k"] = float(sk.iloc[-1]) if len(sk) else None
            # RSI series for divergence detection
            rsi_series = ta.rsi(close, length=14)
            if rsi_series is not None and len(rsi_series) >= 30:
                out["_rsi_series"] = rsi_series
            # EMA21 series for slope detection
            ema21_series = ta.ema(close, length=21)
            if ema21_series is not None and len(ema21_series) >= 5:
                out["_ema21_series"] = ema21_series
        except Exception as e:
            logger.debug("pandas_ta indicators failed: %s", e)
            out = {}

    # Fallbacks for core indicators
    if out.get("rsi") is None:
        rsi_s = _rsi(close, 14)
        out["rsi"] = rsi_s.iloc[-1]
        if len(rsi_s) >= 30:
            out.setdefault("_rsi_series", rsi_s)
    if out.get("macd_hist") is None:
        _, _, hist = _macd(close, 12, 26, 9)
        out["macd_hist"] = hist.iloc[-1]
        out["macd_turning_positive"] = len(hist) >= 2 and hist.iloc[-2] < 0 <= hist.iloc[-1]
    if out.get("adx") is None:
        out["adx"] = _adx(high, low, close, 14).iloc[-1]
    if out.get("ema21") is None:
        ema21_s = _ema(close, 21)
        out["ema21"] = ema21_s.iloc[-1]
        if len(ema21_s) >= 5:
            out.setdefault("_ema21_series", ema21_s)
    if out.get("ema50") is None:
        out["ema50"] = _ema(close, 50).iloc[-1]
    if out.get("ema200") is None and len(close) >= 200:
        out["ema200"] = _ema(close, 200).iloc[-1]
    if out.get("bb_upper") is None:
        ub, _, lb = _bb(close, 20, 2)
        out["bb_upper"] = ub.iloc[-1]
        out["bb_lower"] = lb.iloc[-1]
        # BB squeeze fallback
        bb_width = ub - lb
        if len(bb_width) >= 50:
            recent_width = bb_width.iloc[-50:]
            percentile_20 = recent_width.quantile(0.2)
            out["bb_squeeze"] = bool(bb_width.iloc[-1] <= percentile_20)
    if out.get("atr_value") is None:
        atr_s = _atr(high, low, close, 14)
        if len(atr_s) and close.iloc[-1] and close.iloc[-1] > 0:
            out["atr_value"] = float(atr_s.iloc[-1])
            out["atr_pct"] = float(100 * atr_s.iloc[-1] / close.iloc[-1])
    return out


# ---------------------------------------------------------------------------
# Structure detection
# ---------------------------------------------------------------------------

def _detect_pivots(df: pd.DataFrame, left: int = 7, right: int = 3) -> Tuple[List[Tuple[int, float]], List[Tuple[int, float]]]:
    """Swing highs/lows by rolling max/min. Returns list of (index, value) tuples."""
    if df is None or len(df) < left + right + 1:
        return [], []
    high = df["high"]
    low = df["low"]
    swing_highs: List[Tuple[int, float]] = []
    swing_lows: List[Tuple[int, float]] = []
    for i in range(left, len(df) - right):
        window_high = high.iloc[i - left: i + right + 1]
        window_low = low.iloc[i - left: i + right + 1]
        if high.iloc[i] >= window_high.max():
            swing_highs.append((i, float(high.iloc[i])))
        if low.iloc[i] <= window_low.min():
            swing_lows.append((i, float(low.iloc[i])))
    return swing_highs[-10:], swing_lows[-10:]


def _trend_from_structure(swing_highs: List[float], swing_lows: List[float]) -> str:
    if len(swing_highs) < 2 or len(swing_lows) < 2:
        return "range"
    if swing_highs[-1] > swing_highs[-2] and swing_lows[-1] > swing_lows[-2]:
        return "uptrend"
    if swing_highs[-1] < swing_highs[-2] and swing_lows[-1] < swing_lows[-2]:
        return "downtrend"
    return "range"


def _detect_msb(swing_highs: List[float], swing_lows: List[float], last_close: float) -> Tuple[bool, bool]:
    """Market Structure Break: price breaks above last lower-high (bullish) or below last higher-low (bearish)."""
    msb_bull = False
    msb_bear = False
    if len(swing_highs) >= 2:
        # Bullish MSB: in a downtrend (LH), price breaks above last swing high
        if swing_highs[-1] < swing_highs[-2] and last_close > swing_highs[-1]:
            msb_bull = True
    if len(swing_lows) >= 2:
        # Bearish MSB: in an uptrend (HL), price breaks below last swing low
        if swing_lows[-1] > swing_lows[-2] and last_close < swing_lows[-1]:
            msb_bear = True
    return msb_bull, msb_bear


def _detect_rsi_divergence(df: pd.DataFrame, rsi_series: pd.Series, swing_lows_idx: List[Tuple[int, float]], swing_highs_idx: List[Tuple[int, float]]) -> Tuple[bool, bool]:
    """
    Bullish divergence: price makes lower low, RSI makes higher low.
    Bearish divergence: price makes higher high, RSI makes lower high.
    """
    bull_div = False
    bear_div = False
    # Bullish: check last two swing lows
    if len(swing_lows_idx) >= 2:
        idx_a, price_a = swing_lows_idx[-2]
        idx_b, price_b = swing_lows_idx[-1]
        if price_b < price_a and idx_a < len(rsi_series) and idx_b < len(rsi_series):
            rsi_a = rsi_series.iloc[idx_a]
            rsi_b = rsi_series.iloc[idx_b]
            if not (np.isnan(rsi_a) or np.isnan(rsi_b)) and rsi_b > rsi_a:
                bull_div = True
    # Bearish: check last two swing highs
    if len(swing_highs_idx) >= 2:
        idx_a, price_a = swing_highs_idx[-2]
        idx_b, price_b = swing_highs_idx[-1]
        if price_b > price_a and idx_a < len(rsi_series) and idx_b < len(rsi_series):
            rsi_a = rsi_series.iloc[idx_a]
            rsi_b = rsi_series.iloc[idx_b]
            if not (np.isnan(rsi_a) or np.isnan(rsi_b)) and rsi_b < rsi_a:
                bear_div = True
    return bull_div, bear_div


def _detect_order_blocks(df: pd.DataFrame) -> Tuple[Optional[Tuple[float, float]], Optional[Tuple[float, float]]]:
    """
    Bullish OB: last bearish candle before a strong bullish move.
    Bearish OB: last bullish candle before a strong bearish move.
    Looks at last 20 bars.
    """
    bullish_ob = None
    bearish_ob = None
    if df is None or len(df) < 10:
        return bullish_ob, bearish_ob
    lookback = min(20, len(df) - 1)
    for i in range(len(df) - 1, len(df) - lookback - 1, -1):
        cur = df.iloc[i]
        prev = df.iloc[i - 1]
        # Bullish OB: prev candle bearish, current candle strong bullish (close > prev high)
        if prev["close"] < prev["open"] and cur["close"] > prev["high"]:
            body_size = abs(cur["close"] - cur["open"])
            avg_body = abs(df["close"].iloc[max(0, i - 10):i] - df["open"].iloc[max(0, i - 10):i]).mean()
            if avg_body > 0 and body_size > 1.5 * avg_body:
                bullish_ob = (float(prev["low"]), float(prev["high"]))
                break
    for i in range(len(df) - 1, len(df) - lookback - 1, -1):
        cur = df.iloc[i]
        prev = df.iloc[i - 1]
        # Bearish OB: prev candle bullish, current candle strong bearish (close < prev low)
        if prev["close"] > prev["open"] and cur["close"] < prev["low"]:
            body_size = abs(cur["close"] - cur["open"])
            avg_body = abs(df["close"].iloc[max(0, i - 10):i] - df["open"].iloc[max(0, i - 10):i]).mean()
            if avg_body > 0 and body_size > 1.5 * avg_body:
                bearish_ob = (float(prev["low"]), float(prev["high"]))
                break
    return bullish_ob, bearish_ob


def _detect_liquidity_sweep(df: pd.DataFrame, support: float, resistance: float) -> Tuple[Optional[str], bool]:
    """
    Detect wick beyond level with close back inside.
    Returns (sweep_direction, sweep_confirmed).
    sweep_confirmed = sweep candle closes inside AND next candle confirms direction.
    """
    if df is None or len(df) < 3:
        return None, False
    last = df.iloc[-1]
    prev = df.iloc[-2]
    low = last["low"]
    high = last["high"]
    close = last["close"]
    mid = (high + low) / 2

    # Sweep below support then close above
    if low < support and close > support and close > mid:
        # Confirmation: need previous bar context (sweep candle is prev, current confirms)
        # Or: this bar sweeps and closes inside = the sweep, we check that close is bullish
        confirmed = close > last["open"]  # bullish close on sweep bar
        return "long", confirmed
    # Sweep above resistance then close below
    if high > resistance and close < resistance and close < mid:
        confirmed = close < last["open"]  # bearish close on sweep bar
        return "short", confirmed

    # Check if previous bar swept and current bar confirms
    prev_low = prev["low"]
    prev_close = prev["close"]
    prev_high = prev["high"]
    if prev_low < support and prev_close > support:
        # Previous bar swept below support; current bar confirms if it closes higher
        if close > prev_close and close > last["open"]:
            return "long", True
    if prev_high > resistance and prev_close < resistance:
        # Previous bar swept above resistance; current bar confirms if it closes lower
        if close < prev_close and close < last["open"]:
            return "short", True

    return None, False


def _detect_fvg(df: pd.DataFrame) -> Tuple[bool, bool]:
    """Bullish FVG: current low > previous high. Bearish: current high < previous low."""
    if df is None or len(df) < 2:
        return False, False
    cur = df.iloc[-1]
    prev = df.iloc[-2]
    bull = cur["low"] > prev["high"]
    bear = cur["high"] < prev["low"]
    return bull, bear


def _volume_weighted_levels(
    pivot_list: List[Tuple[int, float]],
    volumes: pd.Series,
) -> List[float]:
    """Weight pivot levels by volume at pivot bar. Return top 3 by volume."""
    if not pivot_list or volumes is None or len(volumes) == 0:
        return []
    weighted = []
    for idx, price in pivot_list:
        if 0 <= idx < len(volumes):
            weighted.append((price, float(volumes.iloc[idx])))
    weighted.sort(key=lambda x: x[1], reverse=True)
    return [w[0] for w in weighted[:3]]


# ---------------------------------------------------------------------------
# Main analysis function
# ---------------------------------------------------------------------------

def analyze(df: pd.DataFrame, timeframe: str = "4h") -> Optional[MarketAnalysis]:
    """
    Run full technical analysis on OHLCV DataFrame.
    Returns MarketAnalysis or None if insufficient data.
    """
    if df is None or len(df) < 50:
        return None
    df = df.copy()
    df = df.dropna()

    # Pivots with wider left, faster right detection
    swing_highs_idx, swing_lows_idx = _detect_pivots(df, 7, 3)
    swing_highs = [v for _, v in swing_highs_idx]
    swing_lows = [v for _, v in swing_lows_idx]
    support_levels = sorted(set(swing_lows))[-5:] if swing_lows else []
    resistance_levels = sorted(set(swing_highs))[-5:] if swing_highs else []

    trend = _trend_from_structure(swing_highs, swing_lows)

    # Volume-weighted S/R
    vol_series = df["volume"] if "volume" in df.columns else pd.Series(dtype=float)
    strong_support = _volume_weighted_levels(swing_lows_idx, vol_series)
    strong_resistance = _volume_weighted_levels(swing_highs_idx, vol_series)

    # PDH/PDL from last completed bar
    if len(df) >= 2:
        prev = df.iloc[-2]
        pdh = float(prev["high"])
        pdl = float(prev["low"])
    else:
        pdh = pdl = None

    # Volume
    volume_ma = vol_series.rolling(20).mean().iloc[-1] if len(vol_series) >= 20 else None
    last_vol = float(df["volume"].iloc[-1])
    spike_mult = getattr(config, "VOLUME_SPIKE_MULT", 1.5)
    volume_spike = volume_ma is not None and last_vol > spike_mult * volume_ma
    volume_ratio = (last_vol / volume_ma) if volume_ma and volume_ma > 0 else 1.0

    # Indicators
    ind = _compute_indicators(df)
    last = df.iloc[-1]
    last_close = float(last["close"])
    last_high = float(last["high"])
    last_low = float(last["low"])
    last_open = float(last["open"])
    last_bullish = last["close"] >= last["open"]

    # ADX booleans
    adx_val = ind.get("adx")
    adx_strong = adx_val is not None and adx_val > getattr(config, "WATCHLIST_ADX_MIN", 25)
    adx_very_strong = adx_val is not None and adx_val > getattr(config, "ADX_STRONG", 35)

    # BB squeeze
    bb_squeeze = ind.get("bb_squeeze", False)

    # ATR
    atr_value = ind.get("atr_value")
    atr_pct = ind.get("atr_pct")
    min_atr = getattr(config, "MIN_ATR_PCT", 1.0)
    max_atr = getattr(config, "MAX_ATR_PCT", 8.0)
    atr_pct_ok = atr_pct is not None and min_atr <= atr_pct <= max_atr

    # EMA21 slope
    ema21_series = ind.get("_ema21_series")
    ema21_rising = False
    ema21_falling = False
    if ema21_series is not None and len(ema21_series) >= 3:
        slope = ema21_series.iloc[-1] - ema21_series.iloc[-3]
        ema21_rising = slope > 0
        ema21_falling = slope < 0

    # RSI divergence
    rsi_series = ind.get("_rsi_series")
    rsi_bull_div = False
    rsi_bear_div = False
    if rsi_series is not None and len(rsi_series) >= 30:
        rsi_bull_div, rsi_bear_div = _detect_rsi_divergence(df, rsi_series, swing_lows_idx, swing_highs_idx)

    # Order blocks
    bullish_ob, bearish_ob = _detect_order_blocks(df)

    # Market structure break
    msb_bull, msb_bear = _detect_msb(swing_highs, swing_lows, last_close)

    # Fib 50% for trend continuation
    recent_low = float(min(swing_lows[-3:])) if len(swing_lows) >= 3 else float(df["low"].min())
    recent_high = float(max(swing_highs[-3:])) if len(swing_highs) >= 3 else float(df["high"].max())
    fib_50 = (recent_high + recent_low) / 2

    # Liquidity sweep (with confirmation)
    sup = support_levels[-1] if support_levels else df["low"].min()
    res = resistance_levels[-1] if resistance_levels else df["high"].max()
    liquidity_sweep, sweep_confirmed = _detect_liquidity_sweep(df, sup, res)

    fvg_bull, fvg_bear = _detect_fvg(df)

    # At support/resistance (within 0.5%)
    at_support = False
    at_resistance = False
    if support_levels:
        nearest_sup = min(support_levels, key=lambda x: abs(x - last_close))
        at_support = abs(nearest_sup - last_close) / last_close <= 0.005
    if resistance_levels:
        nearest_res = min(resistance_levels, key=lambda x: abs(x - last_close))
        at_resistance = abs(nearest_res - last_close) / last_close <= 0.005

    return MarketAnalysis(
        trend=trend,
        swing_highs=swing_highs,
        swing_lows=swing_lows,
        support_levels=support_levels,
        resistance_levels=resistance_levels,
        strong_support=strong_support,
        strong_resistance=strong_resistance,
        pdh=pdh,
        pdl=pdl,
        volume_ma=volume_ma,
        volume_spike=volume_spike,
        volume_ratio=volume_ratio,
        rsi=ind.get("rsi"),
        macd_hist=ind.get("macd_hist"),
        macd_turning_positive=ind.get("macd_turning_positive", False),
        adx=adx_val,
        ema21=ind.get("ema21"),
        ema50=ind.get("ema50"),
        ema200=ind.get("ema200"),
        bb_upper=ind.get("bb_upper"),
        bb_lower=ind.get("bb_lower"),
        adx_strong=adx_strong,
        adx_very_strong=adx_very_strong,
        bb_squeeze=bb_squeeze,
        rsi_bull_divergence=rsi_bull_div,
        rsi_bear_divergence=rsi_bear_div,
        bullish_ob_zone=bullish_ob,
        bearish_ob_zone=bearish_ob,
        msb_bullish=msb_bull,
        msb_bearish=msb_bear,
        liquidity_sweep_detected=liquidity_sweep,
        sweep_confirmed=sweep_confirmed,
        fvg_bullish=fvg_bull,
        fvg_bearish=fvg_bear,
        at_support=at_support,
        at_resistance=at_resistance,
        last_close=last_close,
        last_high=last_high,
        last_low=last_low,
        last_open=last_open,
        last_volume=last_vol,
        last_bullish=last_bullish,
        fib_50_level=fib_50,
        recent_low=recent_low,
        recent_high=recent_high,
        ema21_rising=ema21_rising,
        ema21_falling=ema21_falling,
        obv_rising=ind.get("obv_rising"),
        atr_pct=atr_pct,
        atr_value=atr_value,
        atr_pct_ok=atr_pct_ok,
        stoch_rsi_k=ind.get("stoch_rsi_k"),
    )
