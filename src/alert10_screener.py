"""
Alert 10: build top-N list of altcoins with liquidity sweep (SH/SL) only.
Screens across 1D, 4H, and 1H; includes coin if at least one TF has confirmed sweep.
Ranks by number of timeframes with sweep, then by 4H volume ratio; returns ordered list.
"""
import logging
from typing import List, Optional, Tuple

from . import config
from .data_fetcher import MEXCDataFetcher
from .market_analyzer import MarketAnalysis, analyze

logger = logging.getLogger(__name__)

ALERT10_TFS = ("1d", "4h", "1h")


def _has_sweep(a: Optional[MarketAnalysis]) -> bool:
    """True if analysis has confirmed liquidity sweep (long or short)."""
    if not a:
        return False
    return (
        a.liquidity_sweep_detected in ("long", "short")
        and a.sweep_confirmed
    )


def build_alert10_list(
    candidates: List[str],
    fetcher: MEXCDataFetcher,
    max_coins: Optional[int] = None,
) -> List[str]:
    """
    From candidate symbols, keep only those with confirmed liquidity sweep
    on at least one of 1D, 4H, or 1H. Rank by sweep count then volume_ratio; return top max_coins.
    """
    if max_coins is None:
        max_coins = config.ALERT10_MAX_COINS

    scored: List[Tuple[str, int, float]] = []  # (symbol, sweep_count, volume_ratio)

    for symbol in candidates:
        try:
            sweep_count = 0
            volume_ratio = 0.0

            for tf in ALERT10_TFS:
                df = fetcher.fetch_ohlcv(symbol, tf, 200)
                if df is None or len(df) < 50:
                    continue
                a = analyze(df, tf)
                if _has_sweep(a):
                    sweep_count += 1
                if tf == "4h" and a is not None and a.volume_ratio is not None:
                    volume_ratio = a.volume_ratio

            if sweep_count == 0:
                continue

            scored.append((symbol, sweep_count, volume_ratio))
        except Exception as e:
            logger.debug("Alert10 sweep check %s: %s", symbol, e)
            continue

    # Rank: primary = sweep_count (desc), secondary = volume_ratio (desc)
    scored.sort(key=lambda x: (x[1], x[2]), reverse=True)
    return [s[0] for s in scored[:max_coins]]
