"""
MEXC futures data fetcher: OHLCV, ticker, markets.
Uses ccxt with defaultType future; includes cache and retry with exponential backoff.
"""
import logging
import time
from pathlib import Path
from typing import Any, Optional

import pandas as pd

from . import config

logger = logging.getLogger(__name__)

# Cache TTL in seconds (1 min for 4h/1d to avoid duplicate calls in same scan)
CACHE_TTL = 60


def _get_exchange():
    """Lazy ccxt MEXC instance with futures as default."""
    import ccxt
    opts = {"defaultType": "future"}
    if config.MEXC_API_KEY and config.MEXC_API_SECRET:
        opts["apiKey"] = config.MEXC_API_KEY
        opts["secret"] = config.MEXC_API_SECRET
    return ccxt.mexc(opts)


def _retry(fn, *args, max_retries: int = 3, **kwargs) -> Any:
    """Run fn with exponential backoff; respect 429/Retry-After."""
    last_exc = None
    for attempt in range(max_retries):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            last_exc = e
            if attempt == max_retries - 1:
                raise
            wait = 2 ** attempt
            if hasattr(e, "response") and getattr(e.response, "status_code", None) == 429:
                retry_after = getattr(e.response, "headers", {}).get("Retry-After")
                if retry_after:
                    try:
                        wait = int(retry_after)
                    except ValueError:
                        pass
            logger.warning("Retry in %ss after %s: %s", wait, type(e).__name__, e)
            time.sleep(wait)
    raise last_exc


class MEXCDataFetcher:
    """Fetch OHLCV, ticker, and futures markets from MEXC."""

    def __init__(self, cache_dir: Optional[Path] = None, cache_ttl: int = CACHE_TTL):
        self._cache_dir = cache_dir or (config.DATA_DIR / "cache")
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._cache_ttl = cache_ttl
        self._exchange = None

    @property
    def exchange(self):
        if self._exchange is None:
            self._exchange = _get_exchange()
        return self._exchange

    def _cache_path(self, symbol: str, timeframe: str) -> Path:
        safe = symbol.replace("/", "_").replace(":", "_")
        return self._cache_dir / f"ohlcv_{safe}_{timeframe}.parquet"

    def _read_cache(self, path: Path) -> Optional[pd.DataFrame]:
        if not path.exists():
            return None
        try:
            mtime = path.stat().st_mtime
            if time.time() - mtime > self._cache_ttl:
                return None
            df = pd.read_parquet(path)
            if df is not None and not df.empty:
                if hasattr(df.index, "tz_localize"):
                    # keep as is if already tz-aware
                    pass
                return df
        except Exception as e:
            logger.debug("Cache read failed %s: %s", path, e)
        return None

    def _write_cache(self, path: Path, df: pd.DataFrame) -> None:
        try:
            df.to_parquet(path)
        except Exception as e:
            logger.debug("Cache write failed %s: %s", path, e)

    def fetch_ohlcv(
        self, symbol: str, timeframe: str, limit: int = 200
    ) -> Optional[pd.DataFrame]:
        """
        Fetch OHLCV for symbol. Returns DataFrame with open, high, low, close, volume and datetime index.
        Returns None on error.
        """
        cache_path = self._cache_path(symbol, timeframe)
        cached = self._read_cache(cache_path)
        if cached is not None and len(cached) >= limit:
            return cached.tail(limit).copy()

        try:
            ohlcv = _retry(
                self.exchange.fetch_ohlcv,
                symbol,
                timeframe=timeframe,
                limit=limit,
            )
        except Exception as e:
            logger.error("fetch_ohlcv %s %s: %s", symbol, timeframe, e)
            return None

        if not ohlcv:
            return None

        df = pd.DataFrame(
            ohlcv,
            columns=["timestamp", "open", "high", "low", "close", "volume"],
        )
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
        df.set_index("timestamp", inplace=True)
        df = df.astype(
            {
                "open": float,
                "high": float,
                "low": float,
                "close": float,
                "volume": float,
            }
        )
        self._write_cache(cache_path, df)
        return df

    def fetch_ticker(self, symbol: str) -> Optional[dict]:
        """Fetch 24h ticker (volume, last, bid, ask). Returns None on error."""
        try:
            t = _retry(self.exchange.fetch_ticker, symbol)
            if t is None:
                return None
            return {
                "last": t.get("last"),
                "bid": t.get("bid"),
                "ask": t.get("ask"),
                "volume": t.get("quoteVolume") or t.get("baseVolume"),
                "percentage": t.get("percentage"),
                "symbol": t.get("symbol", symbol),
            }
        except Exception as e:
            logger.error("fetch_ticker %s: %s", symbol, e)
            return None

    def fetch_futures_markets(self) -> list[dict]:
        """Fetch all USDT perpetual futures markets."""
        try:
            markets = _retry(self.exchange.fetch_markets)
        except Exception as e:
            logger.error("fetch_markets: %s", e)
            return []

        out = []
        for m in markets:
            if m.get("type") != "future" and m.get("swap") is not True:
                continue
            quote = m.get("quote", "")
            if quote and quote.upper() != "USDT":
                continue
            symbol = m.get("symbol")
            if symbol:
                out.append(m)
        return out
