"""
Dynamic watchlist: filter by volume/volatility/spread, score by trend strength
(both directions), ATR filter, return top N.
Beast-mode: scores both uptrend and downtrend coins, ATR-based filtering,
configurable thresholds, BTC correlation factor.
"""
import logging
import time
from typing import List, Optional, Set

from . import config
from .data_fetcher import MEXCDataFetcher
from .market_analyzer import analyze

logger = logging.getLogger(__name__)

STABLECOINS = {"USDC", "DAI", "BUSD", "TUSD", "USDP", "USDD", "FRAX", "LUSD"}


def _load_blacklist() -> Set[str]:
    out: Set[str] = set()
    path = config.BLACKLIST_PATH
    if not path.exists():
        return out
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.split("#")[0].strip().upper()
            if line:
                out.add(line)
    except Exception as e:
        logger.warning("Could not load blacklist %s: %s", path, e)
    return out


class WatchlistManager:
    """
    Build and refresh watchlist: fetch futures, filter by volume/volatility/spread,
    score by trend strength (4H/1D) in BOTH directions, return top MAX_COINS.
    """

    def __init__(self, data_fetcher: Optional[MEXCDataFetcher] = None):
        self._fetcher = data_fetcher or MEXCDataFetcher()
        self._watchlist: List[str] = []
        self._last_refresh: float = 0
        self._blacklist = _load_blacklist()

    def _base_from_symbol(self, symbol: str) -> str:
        """BTC/USDT:USDT -> BTC."""
        return symbol.split("/")[0].upper().split(":")[0]

    def get_watchlist(self) -> List[str]:
        """Return current watchlist (refresh if stale)."""
        if not self._watchlist or (time.time() - self._last_refresh) > config.WATCHLIST_REFRESH:
            self.refresh()
        return self._watchlist.copy()

    def refresh(self) -> List[str]:
        """
        Refresh watchlist: fetch markets, filter, score, rank, set internal list.
        Returns the new watchlist.
        """
        self._blacklist = _load_blacklist()
        markets = self._fetcher.fetch_futures_markets()
        if not markets:
            logger.warning("No futures markets from MEXC")
            self._watchlist = []
            self._last_refresh = time.time()
            return self._watchlist

        min_price_change = getattr(config, "MIN_PRICE_CHANGE", 2.0)
        max_spread = getattr(config, "MAX_SPREAD_PCT", 0.1)

        # Get tickers for all symbols (volume, change, bid/ask)
        candidates: List[dict] = []
        for m in markets:
            symbol = m.get("symbol")
            if not symbol:
                continue
            base = self._base_from_symbol(symbol)
            if base in self._blacklist or base in STABLECOINS:
                continue
            ticker = self._fetcher.fetch_ticker(symbol)
            if not ticker:
                continue
            vol = ticker.get("volume") or 0
            if not isinstance(vol, (int, float)):
                vol = 0
            if vol < config.MIN_VOLUME:
                continue
            pct = ticker.get("percentage")
            if pct is None:
                pct = 0
            try:
                pct = float(pct)
            except (TypeError, ValueError):
                pct = 0
            # Beast-mode: relaxed from 3% to configurable (default 2%)
            if abs(pct) < min_price_change:
                continue
            last = ticker.get("last") or 0
            bid = ticker.get("bid") or last
            ask = ticker.get("ask") or last
            try:
                last, bid, ask = float(last), float(bid), float(ask)
            except (TypeError, ValueError):
                continue
            if last <= 0:
                continue
            spread_pct = 100 * (ask - bid) / last
            if spread_pct > max_spread:
                continue
            candidates.append({
                "symbol": symbol,
                "volume": vol,
                "percentage": pct,
                "spread_pct": spread_pct,
            })

        if not candidates:
            self._watchlist = []
            self._last_refresh = time.time()
            return self._watchlist

        adx_threshold = getattr(config, "WATCHLIST_ADX_MIN", 25.0)

        # Score by trend strength: need 4H and 1D OHLCV
        scored: List[tuple] = []
        for c in candidates:
            symbol = c["symbol"]
            try:
                df_4h = self._fetcher.fetch_ohlcv(symbol, "4h", 200)
                df_1d = self._fetcher.fetch_ohlcv(symbol, "1d", 200)
                if df_4h is None or len(df_4h) < 50 or df_1d is None or len(df_1d) < 50:
                    continue
                a_4h = analyze(df_4h, "4h")
                a_1d = analyze(df_1d, "1d")
                if not a_4h or not a_1d:
                    continue

                # Beast-mode: ATR filter -- skip dead or wild coins
                if not a_4h.atr_pct_ok:
                    continue

                score = 0
                # Beast-mode: score BOTH directions (trendiness, not just uptrend)
                # 4H EMA50: price above = uptrend (+2), price below = downtrend (+2)
                if a_4h.ema50 is not None and a_4h.last_close is not None:
                    if a_4h.last_close > a_4h.ema50:
                        score += 2
                    elif a_4h.last_close < a_4h.ema50:
                        score += 2  # trending down is still trending

                # 1D EMA50: same logic
                if a_1d.ema50 is not None and a_1d.last_close is not None:
                    if a_1d.last_close > a_1d.ema50:
                        score += 2
                    elif a_1d.last_close < a_1d.ema50:
                        score += 2

                # ADX > threshold
                if a_4h.adx is not None and a_4h.adx > adx_threshold:
                    score += 1

                # Trending structure (up or down, not range)
                if a_4h.trend in ("uptrend", "downtrend"):
                    score += 1

                # Volume increasing
                if a_4h.volume_ratio and a_4h.volume_ratio > 1.0:
                    score += 1

                if score < 4:
                    continue

                # Rank: volume * volatility * trend strength
                vol_norm = min(c["volume"] / 1e9, 10)
                vol_pct = abs(c["percentage"]) / 100
                rank_score = vol_norm * vol_pct * (score / 7.0)
                scored.append((symbol, rank_score, score))
            except Exception as e:
                logger.debug("Watchlist score error for %s: %s", symbol, e)
                continue

        scored.sort(key=lambda x: x[1], reverse=True)
        self._watchlist = [s[0] for s in scored[: config.MAX_COINS]]
        self._last_refresh = time.time()
        logger.info("Watchlist refreshed: %d coins (from %d candidates)", len(self._watchlist), len(candidates))
        return self._watchlist
