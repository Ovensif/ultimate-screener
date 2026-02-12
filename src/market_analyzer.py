"""
Technical analysis: structure, volume, indicators, liquidity concepts.
Outputs a structured result per timeframe for signal_generator.
"""
import logging
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import numpy as np
import pandas as pd

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
    # Liquidity
    liquidity_sweep_detected: Optional[str] = None  # "long" | "short" | None
    fvg_bullish: bool = False
    fvg_bearish: bool = False
    at_support: bool = False
    at_resistance: bool = False
    # Last bar and current price
    last_close: Optional[float] = None
    last_high: Optional[float] = None
    last_low: Optional[float] = None
    last_volume: Optional[float] = None
    last_bullish: bool = False
    # For trend continuation: pullback level
    fib_50_level: Optional[float] = None
    recent_low: Optional[float] = None
    recent_high: Optional[float] = None
    # Extra context from pandas-ta (confluence)
    obv_rising: Optional[bool] = None  # On-Balance Volume trend
    atr_pct: Optional[float] = None  # ATR as % of price (volatility context)
    stoch_rsi_k: Optional[float] = None  # Stoch RSI for momentum confluence


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


def _compute_indicators(df: pd.DataFrame) -> dict:
    """Add RSI, MACD, ADX, EMA, BB to a copy and return last values."""
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
            out["adx"] = ta.adx(high, low, close, length=14).iloc[-1] if isinstance(ta.adx(high, low, close, length=14), pd.Series) else None
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
                else:
                    out["bb_upper"] = out["bb_lower"] = None
            # Extra context and confluence from pandas-ta
            vol = df["volume"] if "volume" in df.columns else pd.Series(dtype=float)
            if len(vol) >= 20:
                obv = ta.obv(close, vol)
                if obv is not None and len(obv) >= 5:
                    out["obv_rising"] = bool(obv.iloc[-1] > obv.iloc[-5])
                atr = ta.atr(high, low, close, length=14)
                if atr is not None and len(atr) and close.iloc[-1] and close.iloc[-1] > 0:
                    out["atr_pct"] = float(100 * atr.iloc[-1] / close.iloc[-1])
                stoch = ta.stochrsi(close, length=14, rsi_length=14, k=3, d=3)
                if stoch is not None and not stoch.empty:
                    sk = stoch.iloc[:, 0] if isinstance(stoch, pd.DataFrame) else stoch
                    out["stoch_rsi_k"] = float(sk.iloc[-1]) if len(sk) else None
        except Exception as e:
            logger.debug("pandas_ta indicators failed: %s", e)
            out = {}
    if out.get("rsi") is None:
        out["rsi"] = _rsi(close, 14).iloc[-1]
    if out.get("macd_hist") is None:
        _, _, hist = _macd(close, 12, 26, 9)
        out["macd_hist"] = hist.iloc[-1]
        out["macd_turning_positive"] = len(hist) >= 2 and hist.iloc[-2] < 0 <= hist.iloc[-1]
    if out.get("adx") is None:
        out["adx"] = _adx(high, low, close, 14).iloc[-1]
    if out.get("ema21") is None:
        out["ema21"] = _ema(close, 21).iloc[-1]
    if out.get("ema50") is None:
        out["ema50"] = _ema(close, 50).iloc[-1]
    if out.get("ema200") is None and len(close) >= 200:
        out["ema200"] = _ema(close, 200).iloc[-1]
    if out.get("bb_upper") is None:
        ub, _, lb = _bb(close, 20, 2)
        out["bb_upper"] = ub.iloc[-1]
        out["bb_lower"] = lb.iloc[-1]
    return out


def _detect_pivots(df: pd.DataFrame, left: int = 5, right: int = 5) -> Tuple[List[float], List[float]]:
    """Swing highs and swing lows by rolling max/min."""
    if df is None or len(df) < left + right + 1:
        return [], []
    high = df["high"]
    low = df["low"]
    swing_highs = []
    swing_lows = []
    for i in range(left, len(df) - right):
        window_high = high.iloc[i - left : i + right + 1]
        window_low = low.iloc[i - left : i + right + 1]
        if high.iloc[i] >= window_high.max():
            swing_highs.append(high.iloc[i])
        if low.iloc[i] <= window_low.min():
            swing_lows.append(low.iloc[i])
    return swing_highs[-10:], swing_lows[-10:]  # keep last 10


def _trend_from_structure(swing_highs: List[float], swing_lows: List[float]) -> str:
    if len(swing_highs) < 2 or len(swing_lows) < 2:
        return "range"
    if swing_highs[-1] > swing_highs[-2] and swing_lows[-1] > swing_lows[-2]:
        return "uptrend"
    if swing_highs[-1] < swing_highs[-2] and swing_lows[-1] < swing_lows[-2]:
        return "downtrend"
    return "range"


def _detect_liquidity_sweep(df: pd.DataFrame, support: float, resistance: float) -> Optional[str]:
    """Detect wick beyond level with close back inside. Returns 'long' or 'short' or None."""
    if df is None or len(df) < 3:
        return None
    last = df.iloc[-1]
    prev_low = df["low"].iloc[-2]
    prev_high = df["high"].iloc[-2]
    low = last["low"]
    high = last["high"]
    close = last["close"]
    # Sweep below support then close above
    if low < support and close > support and close > (high + low) / 2:
        return "long"
    # Sweep above resistance then close below
    if high > resistance and close < resistance and close < (high + low) / 2:
        return "short"
    return None


def _detect_fvg(df: pd.DataFrame) -> Tuple[bool, bool]:
    """Bullish FVG: current low > previous high. Bearish: current high < previous low."""
    if df is None or len(df) < 2:
        return False, False
    cur = df.iloc[-1]
    prev = df.iloc[-2]
    bull = cur["low"] > prev["high"]
    bear = cur["high"] < prev["low"]
    return bull, bear


def analyze(df: pd.DataFrame, timeframe: str = "4h") -> Optional[MarketAnalysis]:
    """
    Run full technical analysis on OHLCV DataFrame.
    Returns MarketAnalysis or None if insufficient data.
    """
    if df is None or len(df) < 50:
        return None
    df = df.copy()
    df = df.dropna()

    swing_highs, swing_lows = _detect_pivots(df, 5, 5)
    support_levels = sorted(set(swing_lows))[-5:] if swing_lows else []
    resistance_levels = sorted(set(swing_highs))[:5]  # lowest first for nearest
    if resistance_levels:
        resistance_levels = sorted(resistance_levels)[-5:]

    trend = _trend_from_structure(swing_highs, swing_lows)

    # PDH/PDL from last completed bar (prior period)
    if len(df) >= 2:
        prev = df.iloc[-2]
        pdh = float(prev["high"])
        pdl = float(prev["low"])
    else:
        pdh = pdl = None

    # Volume
    vol = df["volume"]
    volume_ma = vol.rolling(20).mean().iloc[-1] if len(vol) >= 20 else None
    last_vol = float(df["volume"].iloc[-1])
    volume_spike = volume_ma is not None and last_vol > 1.5 * volume_ma
    volume_ratio = (last_vol / volume_ma) if volume_ma and volume_ma > 0 else 1.0

    # Indicators
    ind = _compute_indicators(df)
    last = df.iloc[-1]
    last_close = float(last["close"])
    last_high = float(last["high"])
    last_low = float(last["low"])
    last_bullish = last["close"] >= last["open"]

    # Fib 50% for trend continuation (between recent swing low and high)
    recent_low = float(min(swing_lows[-3:])) if len(swing_lows) >= 3 else float(df["low"].min())
    recent_high = float(max(swing_highs[-3:])) if len(swing_highs) >= 3 else float(df["high"].max())
    fib_50 = (recent_high + recent_low) / 2

    # Liquidity sweep
    sup = support_levels[-1] if support_levels else (df["low"].min())
    res = resistance_levels[-1] if resistance_levels else (df["high"].max())
    liquidity_sweep = _detect_liquidity_sweep(df, sup, res)
    fvg_bull, fvg_bear = _detect_fvg(df)

    # At support/resistance (within 0.5% of level)
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
        pdh=pdh,
        pdl=pdl,
        volume_ma=volume_ma,
        volume_spike=volume_spike,
        volume_ratio=volume_ratio,
        rsi=ind.get("rsi"),
        macd_hist=ind.get("macd_hist"),
        macd_turning_positive=ind.get("macd_turning_positive", False),
        adx=ind.get("adx"),
        ema21=ind.get("ema21"),
        ema50=ind.get("ema50"),
        ema200=ind.get("ema200"),
        bb_upper=ind.get("bb_upper"),
        bb_lower=ind.get("bb_lower"),
        liquidity_sweep_detected=liquidity_sweep,
        fvg_bullish=fvg_bull,
        fvg_bearish=fvg_bear,
        at_support=at_support,
        at_resistance=at_resistance,
        last_close=last_close,
        last_high=last_high,
        last_low=last_low,
        last_volume=last_vol,
        last_bullish=last_bullish,
        fib_50_level=fib_50,
        recent_low=recent_low,
        recent_high=recent_high,
        obv_rising=ind.get("obv_rising"),
        atr_pct=ind.get("atr_pct"),
        stoch_rsi_k=ind.get("stoch_rsi_k"),
    )
