"""
Swing High / Swing Low sweep detection — aligned with Pine Script Crypto View 1.0.
- Pivot: ta.pivothigh(high, 5, 5) / ta.pivotlow(low, 5, 5) → confPivotLen = 5.
- Swept: (bar_index - swingBar) <= confSwingBars and current bar breaks level (Pine Tables group).
- Used for daily trading: pairs that just swept SWH/SWL so you can check for deviation / continuation.
"""
import logging
from dataclasses import dataclass
from typing import List, Optional, Tuple

import pandas as pd

logger = logging.getLogger(__name__)

# Crypto View 1.0 defaults (Tables group)
CONF_PIVOT_LEN = 5   # confPivotLen
CONF_SWING_BARS = 30  # confSwingBars

# Stablecoins to exclude
STABLECOIN_BASES = frozenset({
    "USDT", "USDC", "BUSD", "DAI", "TUSD", "USDP", "USDD", "FRAX", "GUSD", "LUSD",
})


def pivot_high(high: pd.Series, left: int, right: int) -> List[Tuple[int, float]]:
    """Pine ta.pivothigh(high, left, right). Returns [(index, price), ...]."""
    out: List[Tuple[int, float]] = []
    for i in range(left, len(high) - right):
        window = high.iloc[i - left : i + right + 1]
        if high.iloc[i] >= window.max():
            out.append((i, float(high.iloc[i])))
    return out


def pivot_low(low: pd.Series, left: int, right: int) -> List[Tuple[int, float]]:
    """Pine ta.pivotlow(low, left, right). Returns [(index, price), ...]."""
    out: List[Tuple[int, float]] = []
    for i in range(left, len(low) - right):
        window = low.iloc[i - left : i + right + 1]
        if low.iloc[i] <= window.min():
            out.append((i, float(low.iloc[i])))
    return out


def _base_from_symbol(symbol: str) -> str:
    """Extract base asset, e.g. ETH/USDT:USDT -> ETH."""
    if not symbol:
        return ""
    return symbol.split("/")[0].strip().upper()


def is_stablecoin_pair(symbol: str) -> bool:
    return _base_from_symbol(symbol) in STABLECOIN_BASES


def symbol_to_display_ticker(symbol: str) -> str:
    """Exchange symbol -> display ticker, e.g. ETH/USDT:USDT -> ETHUSDT."""
    base = _base_from_symbol(symbol)
    return f"{base}USDT" if base else symbol


@dataclass
class SweepResult:
    """One pair's sweep result for Crypto View style alerts."""
    symbol: str
    swept_swing_high: bool
    swept_swing_low: bool
    last_swing_high: Optional[float]
    last_swing_low: Optional[float]
    last_high: float
    last_low: float
    last_close: float
    # For 10/10 Telegram: actionable signal and level
    signal: str  # "LONG" | "SHORT" | "BOTH"
    level: Optional[float]  # Key level swept (SL for LONG, SH for SHORT; BOTH = primary)


def check_sweep(
    df: pd.DataFrame,
    symbol: str = "",
    pivot_len: int = CONF_PIVOT_LEN,
    swing_lookback: int = CONF_SWING_BARS,
    use_closed_bar_only: bool = True,
) -> Optional[SweepResult]:
    """
    Pine Crypto View 1.0 logic: most recent swing high/low, then check if bar swept.
    swingHighSwept = (bar_index - swingHighBar) <= confSwingBars and high >= lastSwingHigh
    swingLowSwept  = (bar_index - swingLowBar) <= confSwingBars and low <= lastSwingLow

    When use_closed_bar_only is True (default), the sweep is evaluated on the last *closed*
    candle only. This avoids inconsistent SH/SL results caused by the forming candle's
    high/low changing between fetches.
    """
    if df is None or len(df) < pivot_len * 2 + swing_lookback + 5:
        return None
    high = df["high"]
    low = df["low"]
    n = len(df)
    # Use last closed bar for stable results; forming candle changes every fetch
    if use_closed_bar_only and n >= 2:
        current_bar = n - 2
    else:
        current_bar = n - 1

    ph_list = pivot_high(high, pivot_len, pivot_len)
    pl_list = pivot_low(low, pivot_len, pivot_len)
    # Only use pivots confirmed by current_bar (pivot at i is confirmed at i + pivot_len)
    max_confirmed_idx = current_bar - pivot_len
    ph_list = [(i, p) for i, p in ph_list if i <= max_confirmed_idx]
    pl_list = [(i, p) for i, p in pl_list if i <= max_confirmed_idx]
    if not ph_list and not pl_list:
        return None

    last_sh_idx, last_sh_price = max(ph_list, key=lambda x: x[0]) if ph_list else (None, None)
    last_sl_idx, last_sl_price = max(pl_list, key=lambda x: x[0]) if pl_list else (None, None)

    swept_high = False
    swept_low = False
    if last_sh_idx is not None and last_sh_price is not None:
        if (current_bar - last_sh_idx) <= swing_lookback and high.iloc[current_bar] >= last_sh_price:
            swept_high = True
    if last_sl_idx is not None and last_sl_price is not None:
        if (current_bar - last_sl_idx) <= swing_lookback and low.iloc[current_bar] <= last_sl_price:
            swept_low = True

    if not swept_high and not swept_low:
        return None

    # Signal and level for Telegram (daily trading: what to look for)
    if swept_high and swept_low:
        signal = "BOTH"
        level = last_sl_price  # show SL as primary for level
    elif swept_high:
        signal = "SHORT"
        level = last_sh_price
    else:
        signal = "LONG"
        level = last_sl_price

    last = df.iloc[current_bar]
    return SweepResult(
        symbol=symbol,
        swept_swing_high=swept_high,
        swept_swing_low=swept_low,
        last_swing_high=last_sh_price,
        last_swing_low=last_sl_price,
        last_high=float(last["high"]),
        last_low=float(last["low"]),
        last_close=float(last["close"]),
        signal=signal,
        level=level,
    )


def get_pairs_by_volume(fetcher, min_volume: int) -> List[str]:
    """USDT perpetuals with 24h volume >= min_volume, sorted by volume desc. Excludes stablecoins."""
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
    pivot_len: int = CONF_PIVOT_LEN,
    swing_lookback: int = CONF_SWING_BARS,
) -> List[SweepResult]:
    """Fetch OHLCV per symbol, run check_sweep (Pine logic). Return only pairs that swept SWH or SWL."""
    results: List[SweepResult] = []
    for symbol in symbols:
        try:
            df = fetcher.fetch_ohlcv(symbol, timeframe, limit=limit)
            r = check_sweep(df, symbol=symbol, pivot_len=pivot_len, swing_lookback=swing_lookback)
            if r:
                results.append(r)
        except Exception as e:
            logger.debug("Sweep check %s: %s", symbol, e)
    return results
