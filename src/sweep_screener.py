"""
Swing High / Swing Low sweep detection (Pine Script Crypto View 1.0 style).
- Pivot High/Low with configurable left/right bars (default 5 like Pine confPivotLen).
- Notify only when the current bar has swept the nearest SWH or nearest SWL (within lookback).
"""
import logging
from dataclasses import dataclass
from typing import List, Optional, Tuple

import pandas as pd

logger = logging.getLogger(__name__)

# Defaults from Pine: confPivotLen=5, confSwingBars=30
DEFAULT_PIVOT_LEN = 5
DEFAULT_SWING_LOOKBACK = 30

# Base symbols to exclude (stablecoins)
STABLECOIN_BASES = frozenset({
    "USDT", "USDC", "BUSD", "DAI", "TUSD", "USDP", "USDD", "FRAX", "GUSD", "LUSD",
})


def pivot_high(high: pd.Series, left: int, right: int) -> List[Tuple[int, float]]:
    """
    Pine-style ta.pivothigh(high, left, right).
    Returns list of (index, price) for each pivot high.
    """
    out: List[Tuple[int, float]] = []
    for i in range(left, len(high) - right):
        window = high.iloc[i - left : i + right + 1]
        if high.iloc[i] >= window.max():
            out.append((i, float(high.iloc[i])))
    return out


def pivot_low(low: pd.Series, left: int, right: int) -> List[Tuple[int, float]]:
    """
    Pine-style ta.pivotlow(low, left, right).
    Returns list of (index, price) for each pivot low.
    """
    out: List[Tuple[int, float]] = []
    for i in range(left, len(low) - right):
        window = low.iloc[i - left : i + right + 1]
        if low.iloc[i] <= window.min():
            out.append((i, float(low.iloc[i])))
    return out


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
    pivot_len: int = DEFAULT_PIVOT_LEN,
    swing_lookback: int = DEFAULT_SWING_LOOKBACK,
) -> Optional[SweepResult]:
    """
    Check if the current bar has swept the nearest Swing High or nearest Swing Low only.
    "Nearest" = the swing (within lookback before current bar) closest to the current bar.
    Only then we count a sweep and notify. Returns SweepResult or None if insufficient data.
    """
    if df is None or len(df) < pivot_len * 2 + swing_lookback + 5:
        return None
    high = df["high"]
    low = df["low"]
    n = len(df)

    ph_list = pivot_high(high, pivot_len, pivot_len)
    pl_list = pivot_low(low, pivot_len, pivot_len)
    if not ph_list and not pl_list:
        return None

    current_bar = n - 1

    # Nearest swing high: among swing highs before current bar and within lookback, take the one closest to current bar (max index).
    ph_near = [(idx, p) for (idx, p) in ph_list if idx < current_bar and 0 < current_bar - idx <= swing_lookback]
    nearest_sh_idx, nearest_sh_price = max(ph_near, key=lambda x: x[0]) if ph_near else (None, None)

    # Nearest swing low: same idea.
    pl_near = [(idx, p) for (idx, p) in pl_list if idx < current_bar and 0 < current_bar - idx <= swing_lookback]
    nearest_sl_idx, nearest_sl_price = max(pl_near, key=lambda x: x[0]) if pl_near else (None, None)

    # Only notify when the current bar has swept the nearest SWH or nearest SWL (nothing else).
    swept_high = False
    swept_low = False
    if nearest_sh_idx is not None and nearest_sh_price is not None:
        if high.iloc[current_bar] >= nearest_sh_price:
            swept_high = True
    if nearest_sl_idx is not None and nearest_sl_price is not None:
        if low.iloc[current_bar] <= nearest_sl_price:
            swept_low = True

    last = df.iloc[-1]
    return SweepResult(
        symbol=symbol,
        swept_swing_high=swept_high,
        swept_swing_low=swept_low,
        last_swing_high=nearest_sh_price,
        last_swing_low=nearest_sl_price,
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
    pivot_len: int = DEFAULT_PIVOT_LEN,
    swing_lookback: int = DEFAULT_SWING_LOOKBACK,
) -> List[SweepResult]:
    """
    For each symbol, fetch OHLCV, run check_sweep. Return list of SweepResult
    where swept_swing_high or swept_swing_low is True.
    """
    results: List[SweepResult] = []
    for symbol in symbols:
        try:
            df = fetcher.fetch_ohlcv(symbol, timeframe, limit=limit)
            r = check_sweep(df, symbol=symbol, pivot_len=pivot_len, swing_lookback=swing_lookback)
            if r and (r.swept_swing_high or r.swept_swing_low):
                results.append(r)
        except Exception as e:
            logger.debug("Sweep check %s: %s", symbol, e)
    return results
