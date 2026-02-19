"""
Swing High / Swing Low sweep detection.
- Pivot logic from commit aec9c8e (market_analyzer): left=7, right=3; last 10 swing highs/lows.
- Sweep = liquidity sweep with confirmation: wick beyond S/R, close back inside, confirmed by candle direction.
"""
import logging
from dataclasses import dataclass
from typing import List, Optional, Tuple

import pandas as pd

logger = logging.getLogger(__name__)

# Pivot params from aec9c8e market_analyzer: wider left, faster right
DEFAULT_PIVOT_LEFT = 7
DEFAULT_PIVOT_RIGHT = 3
# Keep last N pivots (aec9c8e returns last 10)
PIVOT_TAIL = 10

# Backward compatibility with config that may still use Pine-style names
DEFAULT_PIVOT_LEN = 5
DEFAULT_SWING_LOOKBACK = 30

# Base symbols to exclude (stablecoins)
STABLECOIN_BASES = frozenset({
    "USDT", "USDC", "BUSD", "DAI", "TUSD", "USDP", "USDD", "FRAX", "GUSD", "LUSD",
})


def _detect_pivots(
    df: pd.DataFrame,
    left: int = DEFAULT_PIVOT_LEFT,
    right: int = DEFAULT_PIVOT_RIGHT,
) -> Tuple[List[Tuple[int, float]], List[Tuple[int, float]]]:
    """
    Swing highs/lows by rolling max/min (aec9c8e style).
    Returns (list of (index, price) for swing highs, same for swing lows), last PIVOT_TAIL each.
    """
    if df is None or len(df) < left + right + 1:
        return [], []
    high = df["high"]
    low = df["low"]
    swing_highs: List[Tuple[int, float]] = []
    swing_lows: List[Tuple[int, float]] = []
    for i in range(left, len(df) - right):
        window_high = high.iloc[i - left : i + right + 1]
        window_low = low.iloc[i - left : i + right + 1]
        if high.iloc[i] >= window_high.max():
            swing_highs.append((i, float(high.iloc[i])))
        if low.iloc[i] <= window_low.min():
            swing_lows.append((i, float(low.iloc[i])))
    return swing_highs[-PIVOT_TAIL:], swing_lows[-PIVOT_TAIL:]


def _detect_liquidity_sweep(
    df: pd.DataFrame,
    support: float,
    resistance: float,
) -> Tuple[Optional[str], bool]:
    """
    Detect wick beyond level with close back inside (aec9c8e).
    Returns (sweep_direction, sweep_confirmed). "long" = swept below support, "short" = swept above resistance.
    sweep_confirmed = sweep candle closes inside and direction confirmed (bullish/bearish close).
    """
    if df is None or len(df) < 3:
        return None, False
    last = df.iloc[-1]
    prev = df.iloc[-2]
    low = last["low"]
    high = last["high"]
    close = last["close"]
    mid = (high + low) / 2

    # Current bar: sweep below support then close above
    if low < support and close > support and close > mid:
        confirmed = close > last["open"]
        return "long", confirmed
    # Current bar: sweep above resistance then close below
    if high > resistance and close < resistance and close < mid:
        confirmed = close < last["open"]
        return "short", confirmed

    # Previous bar swept, current bar confirms
    prev_low = prev["low"]
    prev_close = prev["close"]
    prev_high = prev["high"]
    if prev_low < support and prev_close > support:
        if close > prev_close and close > last["open"]:
            return "long", True
    if prev_high > resistance and prev_close < resistance:
        if close < prev_close and close < last["open"]:
            return "short", True

    return None, False


def _base_from_symbol(symbol: str) -> str:
    """Extract base asset from symbol, e.g. ETH/USDT:USDT -> ETH."""
    if not symbol:
        return ""
    return symbol.split("/")[0].strip().upper()


def is_stablecoin_pair(symbol: str) -> bool:
    """True if the pair's base asset is a known stablecoin (excluded from scan)."""
    return _base_from_symbol(symbol) in STABLECOIN_BASES


def symbol_to_display_ticker(symbol: str) -> str:
    """Convert exchange symbol to short display ticker, e.g. ETH/USDT:USDT -> ETHUSDT."""
    base = _base_from_symbol(symbol)
    return f"{base}USDT" if base else symbol


@dataclass
class SweepResult:
    """Result of sweep check for one pair."""
    symbol: str
    swept_swing_high: bool
    swept_swing_low: bool
    last_swing_high: Optional[float]
    last_swing_low: Optional[float]
    last_high: float
    last_low: float
    last_close: float


def check_sweep(
    df: pd.DataFrame,
    symbol: str = "",
    pivot_left: int = DEFAULT_PIVOT_LEFT,
    pivot_right: int = DEFAULT_PIVOT_RIGHT,
) -> Optional[SweepResult]:
    """
    Check if the pair has a confirmed liquidity sweep (aec9c8e logic).
    Pivots: left/right bars; S/R from last 5 swing lows/highs; sweep = wick beyond level + close back inside + confirmation.
    Returns SweepResult or None if insufficient data.
    """
    if df is None or len(df) < pivot_left + pivot_right + 20:
        return None

    swing_highs_idx, swing_lows_idx = _detect_pivots(df, left=pivot_left, right=pivot_right)
    swing_highs = [v for _, v in swing_highs_idx]
    swing_lows = [v for _, v in swing_lows_idx]

    support_levels = sorted(set(swing_lows))[-5:] if swing_lows else []
    resistance_levels = sorted(set(swing_highs))[-5:] if swing_highs else []
    support = float(support_levels[-1]) if support_levels else float(df["low"].min())
    resistance = float(resistance_levels[-1]) if resistance_levels else float(df["high"].max())

    liquidity_sweep, sweep_confirmed = _detect_liquidity_sweep(df, support, resistance)

    # Map to our SweepResult: "long" = swept swing low, "short" = swept swing high
    swept_swing_low = liquidity_sweep == "long" and sweep_confirmed
    swept_swing_high = liquidity_sweep == "short" and sweep_confirmed

    last_sh = float(resistance_levels[-1]) if resistance_levels else None
    last_sl = float(support_levels[-1]) if support_levels else None
    last = df.iloc[-1]
    return SweepResult(
        symbol=symbol,
        swept_swing_high=swept_swing_high,
        swept_swing_low=swept_swing_low,
        last_swing_high=last_sh,
        last_swing_low=last_sl,
        last_high=float(last["high"]),
        last_low=float(last["low"]),
        last_close=float(last["close"]),
    )


def get_pairs_by_volume(fetcher, min_volume: int) -> List[str]:
    """
    Fetch USDT perpetual futures, keep only symbols with 24h volume >= min_volume.
    Returns list of symbols sorted by volume descending.
    """
    markets = fetcher.fetch_futures_markets()
    if not markets:
        return []
    candidates: List[Tuple[str, float]] = []
    for m in markets:
        symbol = m.get("symbol")
        if not symbol or is_stablecoin_pair(symbol):
            continue
        ticker = fetcher.fetch_ticker(symbol)
        if not ticker:
            continue
        vol = ticker.get("volume") or 0
        try:
            vol = float(vol)
        except (TypeError, ValueError):
            vol = 0
        if vol >= min_volume:
            candidates.append((symbol, vol))
    candidates.sort(key=lambda x: x[1], reverse=True)
    return [s[0] for s in candidates]


def pairs_that_swept(
    symbols: List[str],
    fetcher,
    timeframe: str = "4h",
    limit: int = 100,
    pivot_left: int = DEFAULT_PIVOT_LEFT,
    pivot_right: int = DEFAULT_PIVOT_RIGHT,
) -> List[SweepResult]:
    """
    For each symbol, fetch OHLCV, run check_sweep (aec9c8e liquidity-sweep logic).
    Return list of SweepResult where swept_swing_high or swept_swing_low is True.
    """
    results: List[SweepResult] = []
    for symbol in symbols:
        try:
            df = fetcher.fetch_ohlcv(symbol, timeframe, limit=limit)
            r = check_sweep(df, symbol=symbol, pivot_left=pivot_left, pivot_right=pivot_right)
            if r and (r.swept_swing_high or r.swept_swing_low):
                results.append(r)
        except Exception as e:
            logger.debug("Sweep check %s: %s", symbol, e)
    return results
