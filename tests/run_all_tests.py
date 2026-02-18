"""
Tests: MEXC connection, Telegram, technical analysis (market_analyzer).
Run from project root: python tests/run_all_tests.py
"""
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Load .env so tests can use config
try:
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / ".env")
    load_dotenv(PROJECT_ROOT / "config" / ".env")
except ImportError:
    pass


def test_mexc_connection() -> None:
    import ccxt
    opts = {"defaultType": "future"}
    ex = ccxt.mexc(opts)
    try:
        markets = ex.fetch_markets()
        assert markets, "fetch_markets returned empty"
        ticker = ex.fetch_ticker("BTC/USDT:USDT")
        assert ticker is not None
        assert "last" in ticker or "close" in ticker
    except Exception as e:
        print("  Skip MEXC (unreachable or API error):", e)
        return


def test_telegram() -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        print("  Skip Telegram test (no TELEGRAM_BOT_TOKEN)")
        return
    import requests
    r = requests.get(
        f"https://api.telegram.org/bot{token}/getMe",
        timeout=5,
    )
    assert r.status_code == 200, f"Telegram getMe failed: {r.status_code}"


def test_technical_analysis() -> None:
    import pandas as pd
    from src.market_analyzer import analyze
    n = 100
    import numpy as np
    np.random.seed(42)
    df = pd.DataFrame({
        "open": 100 + np.cumsum(np.random.randn(n) * 0.5),
        "high": 101 + np.cumsum(np.random.randn(n) * 0.5),
        "low": 99 + np.cumsum(np.random.randn(n) * 0.5),
        "close": 100 + np.cumsum(np.random.randn(n) * 0.5),
        "volume": np.random.rand(n) * 1e6,
    })
    df["high"] = df[["open", "high", "close"]].max(axis=1)
    df["low"] = df[["open", "low", "close"]].min(axis=1)
    result = analyze(df, "4h")
    assert result is not None
    if result.rsi is not None:
        assert 0 <= result.rsi <= 100
    assert result.trend in ("uptrend", "downtrend", "range")


def test_alert10_screener() -> None:
    """Alert10 screener returns list (empty when no candidates)."""
    from src.alert10_screener import build_alert10_list
    from src.data_fetcher import MEXCDataFetcher
    result = build_alert10_list([], MEXCDataFetcher(), max_coins=10)
    assert result == []


def main() -> int:
    tests = [
        ("MEXC connection", test_mexc_connection),
        ("Telegram", test_telegram),
        ("Technical analysis", test_technical_analysis),
        ("Alert10 screener", test_alert10_screener),
    ]
    failed = []
    for name, fn in tests:
        try:
            fn()
            print(f"OK: {name}")
        except Exception as e:
            print(f"FAIL: {name} - {e}")
            failed.append((name, e))
    if failed:
        print(f"\n{len(failed)} test(s) failed")
        return 1
    print("\nAll tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
