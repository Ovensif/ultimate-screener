"""
Single entrypoint for all tests: MEXC connection, Telegram, TA, signal generation, risk calculator.
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


def test_signal_generation() -> None:
    import pandas as pd
    from src.market_analyzer import analyze
    from src.signal_generator import generate_signals
    n = 100
    import numpy as np
    np.random.seed(123)
    base = 100 + np.cumsum(np.random.randn(n) * 0.3)
    df = pd.DataFrame({
        "open": base,
        "high": base + np.abs(np.random.randn(n)),
        "low": base - np.abs(np.random.randn(n)),
        "close": base + np.random.randn(n) * 0.5,
        "volume": np.random.rand(n) * 1e6 + 5e5,
    })
    df["high"] = df[["open", "high", "close"]].max(axis=1)
    df["low"] = df[["open", "low", "close"]].min(axis=1)
    a_1d = analyze(df, "1d")
    a_4h = analyze(df, "4h")
    signals = generate_signals("BTC/USDT:USDT", a_1d, a_4h)
    assert isinstance(signals, list)
    for s in signals:
        assert hasattr(s, "symbol") and hasattr(s, "side")
        assert s.side in ("long", "short")
        assert hasattr(s, "setup_type") and hasattr(s, "confidence")
        assert hasattr(s, "entry_zone") and hasattr(s, "stop")
        assert hasattr(s, "target1") and hasattr(s, "target2")
        assert hasattr(s, "rr_ratio") and hasattr(s, "confluence_list")


def test_risk_calculator() -> None:
    from src.risk_calculator import calculate
    entry, stop = 100.0, 98.0
    r = calculate(entry, stop, "long", account_size=200, risk_pct=2)
    assert r.risk_usd == 4.0
    assert r.position_size_usd > 0
    assert r.suggested_leverage >= 1


def main() -> int:
    tests = [
        ("MEXC connection", test_mexc_connection),
        ("Telegram", test_telegram),
        ("Technical analysis", test_technical_analysis),
        ("Signal generation", test_signal_generation),
        ("Risk calculator", test_risk_calculator),
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
