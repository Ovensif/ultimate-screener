"""
Swing High / Swing Low sweep detection — aligned with Pine Script Crypto View 1.0 / V3.0.
- Pivot: ta.pivothigh(high, 5, 5) / ta.pivotlow(low, 5, 5) → confPivotLen = 5.
- Sweep: (bar_index - swingBar) <= confSwingBars and current bar breaks level.
- Deviation (V3.0): sweep + rejection + wick/body ratio; only 4H/1H; look back 4 bars for candle whose high/low was later swept.
"""
import logging
from dataclasses import dataclass
from typing import List, Optional, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# Crypto View 1.0 defaults (Tables group)
CONF_PIVOT_LEN = 5   # confPivotLen
CONF_SWING_BARS = 30  # confSwingBars

# Crypto View V3.0 deviation (Deviation group)
DEV_WICK_RATIO = 1.5       # devWickRatio; Pine uses * 0.85 for bear market
DEV_MIN_REJECTION_PCT = 0.5  # devMinRejection; Pine uses * 0.4 for strongRejection
DEV_RSI_OVERSOLD = 45
DEV_RSI_OVERBOUGHT = 55
DEV_LOOKBACK_BARS = 4       # search last 4 closed bars for a deviation candle
DEV_TIMEFRAMES = ("4h", "1h")  # only 4H and 1H

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
    # Optional: when from deviation-candle logic (4 bars back, 4H/1H, level already swept)
    deviation_tf: Optional[str] = None  # "4h" | "1h" if from deviation scan


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


def _rsi_series(close: pd.Series, length: int = 14) -> pd.Series:
    """RSI for deviation confluence (Pine uses 14)."""
    delta = close.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = (-delta).where(delta < 0, 0.0)
    avg_gain = gain.ewm(alpha=1 / length, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / length, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def _check_deviation_at_bar(
    df: pd.DataFrame,
    bar_idx: int,
    pivot_len: int,
    swing_lookback: int,
    dev_wick_ratio: float = DEV_WICK_RATIO,
    dev_min_rejection: float = DEV_MIN_REJECTION_PCT,
    use_rsi: bool = True,
) -> Tuple[Optional[str], Optional[float], Optional[float], Optional[float]]:
    """
    Check if bar at bar_idx is a bullish or bearish deviation candle (Crypto View V3.0).
    Uses only data up to and including bar_idx (as if we were at that bar).
    Returns (signal, level, dev_high, dev_low) or (None, None, None, None).
    """
    if df is None or bar_idx < pivot_len * 2 + swing_lookback or bar_idx >= len(df):
        return (None, None, None, None)
    slice_df = df.iloc[: bar_idx + 1]
    high = slice_df["high"]
    low = slice_df["low"]
    open_ = slice_df["open"]
    close = slice_df["close"]
    n = len(slice_df)
    ph_list = pivot_high(high, pivot_len, pivot_len)
    pl_list = pivot_low(low, pivot_len, pivot_len)
    max_confirmed_idx = n - 1 - pivot_len
    ph_list = [(i, p) for i, p in ph_list if i <= max_confirmed_idx]
    pl_list = [(i, p) for i, p in pl_list if i <= max_confirmed_idx]
    last_sh_idx, last_sh_price = max(ph_list, key=lambda x: x[0]) if ph_list else (None, None)
    last_sl_idx, last_sl_price = max(pl_list, key=lambda x: x[0]) if pl_list else (None, None)

    o = float(open_.iloc[bar_idx])
    c = float(close.iloc[bar_idx])
    h = float(high.iloc[bar_idx])
    l = float(low.iloc[bar_idx])
    body = abs(c - o)
    hl_range = h - l
    body_ref = max(body, hl_range * 0.01) if hl_range > 0 else 0.0
    lower_wick = min(o, c) - l
    upper_wick = h - max(o, c)
    # Volume: accept any (Pine relaxed). RSI optional.
    rsi_ok_bull = True
    rsi_ok_bear = True
    if use_rsi and len(slice_df) >= 15:
        rsi_s = _rsi_series(slice_df["close"], 14)
        rsi_val = rsi_s.iloc[bar_idx] if bar_idx < len(rsi_s) else None
        if rsi_val is not None and not np.isnan(rsi_val):
            rsi_ok_bull = rsi_val < DEV_RSI_OVERSOLD
            rsi_ok_bear = rsi_val > DEV_RSI_OVERBOUGHT

    # Bullish deviation at bar_idx
    if last_sl_price is not None and last_sl_idx is not None:
        swing_low_swept = (bar_idx - last_sl_idx) <= swing_lookback and l < last_sl_price
        body_low = min(o, c)
        rejection_dist = body_low - last_sl_price
        rejection_pct = (rejection_dist / last_sl_price) * 100.0 if last_sl_price else 0
        strong_rejection = rejection_pct > (dev_min_rejection * 0.4)
        big_wick = lower_wick >= body_ref * (dev_wick_ratio * 0.85) if body_ref else False
        closed_above = body_low > last_sl_price
        if swing_low_swept and strong_rejection and big_wick and closed_above and rsi_ok_bull:
            return ("LONG", last_sl_price, h, l)

    # Bearish deviation at bar_idx
    if last_sh_price is not None and last_sh_idx is not None:
        swing_high_swept = (bar_idx - last_sh_idx) <= swing_lookback and h > last_sh_price
        body_high = max(o, c)
        rejection_dist = last_sh_price - body_high
        rejection_pct = (rejection_dist / last_sh_price) * 100.0 if last_sh_price else 0
        strong_rejection = rejection_pct > (dev_min_rejection * 0.4)
        big_wick = upper_wick >= body_ref * (dev_wick_ratio * 0.85) if body_ref else False
        closed_below = body_high < last_sh_price
        if swing_high_swept and strong_rejection and big_wick and closed_below and rsi_ok_bear:
            return ("SHORT", last_sh_price, h, l)

    return (None, None, None, None)


def find_deviation_swept_in_last_n_bars(
    df: pd.DataFrame,
    n_bars: int = DEV_LOOKBACK_BARS,
    pivot_len: int = CONF_PIVOT_LEN,
    swing_lookback: int = CONF_SWING_BARS,
) -> Optional[Tuple[str, float, float, float]]:
    """
    Look at the last n_bars closed bars (before the last closed bar). If any of them
    was a deviation candle and its high or low has since been swept by a later bar,
    return (signal, level, dev_high, dev_low). Otherwise None.
    Bar indices: last closed = len-2 (0-based), so we check len-2-1, len-2-2, ... (4 bars).
    """
    if df is None or len(df) < pivot_len * 2 + swing_lookback + n_bars + 2:
        return None
    # Last closed bar index (we don't consider the forming candle)
    last_closed_idx = len(df) - 2
    # Check the 4 bars that have at least one bar after them (so "already swept" can happen)
    start_idx = max(0, last_closed_idx - n_bars)
    for bar_idx in range(last_closed_idx - 1, start_idx - 1, -1):
        if bar_idx < pivot_len * 2 + swing_lookback:
            continue
        signal, level, dev_high, dev_low = _check_deviation_at_bar(
            df, bar_idx, pivot_len, swing_lookback
        )
        if signal is None:
            continue
        # Check if any bar after bar_idx (up to last closed) swept dev_high or dev_low
        for j in range(bar_idx + 1, last_closed_idx + 1):
            if j >= len(df):
                break
            row = df.iloc[j]
            body_high = max(float(row["open"]), float(row["close"]))
            body_low = min(float(row["open"]), float(row["close"]))
            # Sweep = full body breaks level (Pine: brokenByBody)
            if signal == "LONG":
                if body_low < dev_low:
                    return (signal, level, dev_high, dev_low)
            else:
                if body_high > dev_high:
                    return (signal, level, dev_high, dev_low)
    return None


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


def pairs_with_deviation_swept(
    symbols: List[str],
    fetcher,
    timeframes: Tuple[str, ...] = DEV_TIMEFRAMES,
    lookback_bars: int = DEV_LOOKBACK_BARS,
    limit: int = 100,
    pivot_len: int = CONF_PIVOT_LEN,
    swing_lookback: int = CONF_SWING_BARS,
) -> List[SweepResult]:
    """
    Find pairs that had a deviation candle in the last lookback_bars (4) on 4H or 1H,
    and that candle's high or low has already been swept by a later bar.
    Returns SweepResult list with deviation_tf set ("4h" or "1h").
    """
    results: List[SweepResult] = []
    for symbol in symbols:
        for tf in timeframes:
            try:
                df = fetcher.fetch_ohlcv(symbol, tf, limit=limit)
                if df is None or len(df) < pivot_len * 2 + swing_lookback + lookback_bars + 2:
                    continue
                found = find_deviation_swept_in_last_n_bars(
                    df, n_bars=lookback_bars, pivot_len=pivot_len, swing_lookback=swing_lookback
                )
                if not found:
                    continue
                signal, level, dev_high, dev_low = found
                last = df.iloc[-2]
                results.append(
                    SweepResult(
                        symbol=symbol,
                        swept_swing_high=(signal == "SHORT"),
                        swept_swing_low=(signal == "LONG"),
                        last_swing_high=dev_high if signal == "SHORT" else None,
                        last_swing_low=dev_low if signal == "LONG" else None,
                        last_high=float(last["high"]),
                        last_low=float(last["low"]),
                        last_close=float(last["close"]),
                        signal=signal,
                        level=level,
                        deviation_tf=tf,
                    )
                )
                break
            except Exception as e:
                logger.debug("Deviation check %s %s: %s", symbol, tf, e)
    return results
