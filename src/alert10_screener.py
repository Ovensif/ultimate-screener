"""
Top 10 altcoins: 4H only. Must have (1) RSI in strong or weak zone, (2) confirmed sweep of swing high/low.
Rank by RSI extremity then volume; return top N.
"""
import logging
from typing import List, Optional, Tuple

from . import config
from .data_fetcher import MEXCDataFetcher
from .market_analyzer import MarketAnalysis, analyze

logger = logging.getLogger(__name__)

TF_4H = "4h"


def _has_sweep_4h(a: Optional[MarketAnalysis]) -> bool:
    """True if 4H analysis has confirmed liquidity sweep (swing high/low)."""
    if not a:
        return False
    return (
        a.liquidity_sweep_detected in ("long", "short")
        and a.sweep_confirmed
    )


def _rsi_strong_or_weak(a: Optional[MarketAnalysis]) -> bool:
    """True if RSI is in strong (>= threshold) or weak (<= threshold) zone."""
    if not a or a.rsi is None:
        return False
    rsi = a.rsi
    strong = getattr(config, "ALERT10_RSI_STRONG", 65.0)
    weak = getattr(config, "ALERT10_RSI_WEAK", 35.0)
    return rsi >= strong or rsi <= weak


def build_alert10_list(
    candidates: List[str],
    fetcher: MEXCDataFetcher,
    max_coins: Optional[int] = None,
) -> List[str]:
    """
    From candidates: keep only those with 4H confirmed sweep AND RSI strong/weak.
    Rank by |RSI - 50| (more extreme first), then volume_ratio; return top max_coins.
    """
    if max_coins is None:
        max_coins = config.ALERT10_MAX_COINS

    scored: List[Tuple[str, float, float]] = []  # (symbol, rsi_extremity, volume_ratio)

    for symbol in candidates:
        try:
            df = fetcher.fetch_ohlcv(symbol, TF_4H, 200)
            if df is None or len(df) < 50:
                continue
            a = analyze(df, TF_4H)
            if not a:
                continue
            if not _has_sweep_4h(a):
                continue
            if not _rsi_strong_or_weak(a):
                continue
            rsi = a.rsi if a.rsi is not None else 50.0
            rsi_extremity = abs(rsi - 50.0)
            vol_ratio = a.volume_ratio if a.volume_ratio is not None else 0.0
            scored.append((symbol, rsi_extremity, vol_ratio))
        except Exception as e:
            logger.debug("Alert10 check %s: %s", symbol, e)
            continue

    # Rank: most extreme RSI first, then volume
    scored.sort(key=lambda x: (x[1], x[2]), reverse=True)
    return [s[0] for s in scored[:max_coins]]
