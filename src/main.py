"""
Orchestrator: scheduler, watchlist refresh, scan loop, Telegram alerts, signal logging.
Beast-mode: BTC+ETH dual filter, dynamic cooldown, daily signal cap, scan stats.
"""
import argparse
import json
import logging
import signal as sig
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Run from project root (parent of src)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src import config
from src.data_fetcher import MEXCDataFetcher
from src.market_analyzer import analyze
from src.risk_calculator import calculate
from src.signal_generator import generate_signals
from src.telegram_bot import send_signal, send_startup_message
from src.watchlist_manager import WatchlistManager
import logging.handlers

# Logging: set up after config is loaded
def _setup_logging() -> None:
    config.LOGS_DIR.mkdir(parents=True, exist_ok=True)
    log_file = config.LOGS_DIR / "screener.log"
    handler = logging.handlers.RotatingFileHandler(
        log_file, maxBytes=2 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
    logging.root.addHandler(handler)
    logging.root.setLevel(logging.INFO)
    console = logging.StreamHandler()
    console.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
    logging.root.addHandler(console)


BTC_SYMBOL = "BTC/USDT:USDT"
ETH_SYMBOL = "ETH/USDT:USDT"
SIGNALS_FILE = config.DATA_DIR / "signals.json"

# Module-level state for scheduler jobs
_fetcher: MEXCDataFetcher = None
_watchlist_manager: WatchlistManager = None
_last_signal_time: dict = {}          # symbol -> timestamp
_last_signal_setup: dict = {}         # symbol -> setup_type
_daily_signal_count: int = 0
_daily_signal_date: str = ""          # YYYY-MM-DD to reset daily counter
_shutdown = False


def _load_signals_log() -> list:
    if not SIGNALS_FILE.exists():
        return []
    try:
        with open(SIGNALS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _append_signal_log(record: dict) -> None:
    data = _load_signals_log()
    data.append(record)
    try:
        with open(SIGNALS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        logging.getLogger(__name__).warning("Could not write signals.json: %s", e)


def _pct_change(symbol: str, timeframe: str, bars: int = 5) -> float:
    """Return percentage change over the last completed bar, or 0."""
    try:
        df = _fetcher.fetch_ohlcv(symbol, timeframe, bars)
        if df is None or len(df) < 2:
            return 0.0
        prev = df["close"].iloc[-2]
        curr = df["close"].iloc[-1]
        if prev and prev > 0:
            return 100 * (curr - prev) / prev
    except Exception:
        pass
    return 0.0


def _check_market_health() -> dict:
    """
    Beast-mode: check BTC (1H + 4H) and ETH (4H).
    Returns dict with flags.
    """
    btc_1h = _pct_change(BTC_SYMBOL, "1h")
    btc_4h = _pct_change(BTC_SYMBOL, "4h")
    eth_4h = _pct_change(ETH_SYMBOL, "4h")

    btc_dump_1h = getattr(config, "BTC_DUMP_1H", -5.0)
    btc_dump_4h = getattr(config, "BTC_DUMP_4H", -3.0)
    eth_dump_4h = getattr(config, "ETH_DUMP_4H", -3.0)

    full_suppress = False
    partial_suppress = False

    # Full suppression: BTC 4H < -3% OR BTC 1H < -5%
    if btc_4h < btc_dump_4h or btc_1h < btc_dump_1h:
        full_suppress = True
    # Full suppression: both BTC and ETH dumping on 4H
    if btc_4h < btc_dump_4h and eth_4h < eth_dump_4h:
        full_suppress = True
    # Partial: BTC 4H < -2% (only allow HIGH + R:R >= 3)
    if btc_4h < (btc_dump_4h + 1.0):  # e.g. -2% if threshold is -3%
        partial_suppress = True

    return {
        "btc_1h": btc_1h,
        "btc_4h": btc_4h,
        "eth_4h": eth_4h,
        "full_suppress": full_suppress,
        "partial_suppress": partial_suppress,
    }


def _dynamic_cooldown(symbol: str, setup_type: str) -> bool:
    """
    Beast-mode dynamic cooldown:
    - 6h if same setup type on same coin
    - 4h for different confidence
    - 2h if different setup type
    Returns True if cooldown is active (should skip).
    """
    now = time.time()
    last_time = _last_signal_time.get(symbol, 0)
    last_setup = _last_signal_setup.get(symbol, "")

    if last_time == 0:
        return False

    elapsed = now - last_time

    if setup_type == last_setup:
        # Same setup type: 6 hour cooldown
        return elapsed < 6 * 3600
    else:
        # Different setup type: 2 hour cooldown
        return elapsed < 2 * 3600


def _run_scan() -> None:
    global _last_signal_time, _last_signal_setup, _daily_signal_count, _daily_signal_date
    logger = logging.getLogger(__name__)

    # Reset daily counter if new day
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if today != _daily_signal_date:
        _daily_signal_count = 0
        _daily_signal_date = today

    watchlist = _watchlist_manager.get_watchlist()
    if not watchlist:
        logger.info("Watchlist empty, skipping scan")
        return

    # Beast-mode: market health check (BTC + ETH)
    health = _check_market_health()
    if health["full_suppress"]:
        logger.info(
            "Market dump detected (BTC 1H=%.2f%%, BTC 4H=%.2f%%, ETH 4H=%.2f%%), suppressing ALL signals",
            health["btc_1h"], health["btc_4h"], health["eth_4h"],
        )
        return

    max_daily = getattr(config, "MAX_SIGNALS_PER_DAY", 8)
    scan_found = 0
    scan_sent = 0

    for symbol in watchlist:
        if _shutdown:
            break
        # Beast-mode: daily cap
        if _daily_signal_count >= max_daily:
            logger.info("Daily signal cap (%d) reached, stopping scan", max_daily)
            break
        try:
            df_1d = _fetcher.fetch_ohlcv(symbol, "1d", 200)
            df_4h = _fetcher.fetch_ohlcv(symbol, "4h", 200)
            if df_1d is None or df_4h is None or len(df_1d) < 50 or len(df_4h) < 50:
                continue
            a_1d = analyze(df_1d, "1d")
            a_4h = analyze(df_4h, "4h")
            if not a_1d or not a_4h:
                continue
            signals = generate_signals(symbol, a_1d, a_4h)
            for s in signals:
                scan_found += 1
                # Beast-mode: partial suppress -- only HIGH + R:R >= 3
                if health["partial_suppress"]:
                    if s.confidence != "HIGH" or s.rr_ratio < 3.0:
                        continue
                # Beast-mode: dynamic cooldown
                if _dynamic_cooldown(symbol, s.setup_type):
                    logger.debug("Skip signal %s %s: cooldown", symbol, s.setup_type)
                    continue
                # Daily cap check
                if _daily_signal_count >= max_daily:
                    break
                risk_result = calculate(
                    (s.entry_zone[0] + s.entry_zone[1]) / 2,
                    s.stop,
                    s.side,
                    confidence=s.confidence,
                    atr_pct=a_4h.atr_pct,
                )
                ok = send_signal(s, risk_result)
                if ok:
                    _last_signal_time[symbol] = time.time()
                    _last_signal_setup[symbol] = s.setup_type
                    _daily_signal_count += 1
                    scan_sent += 1
                    _append_signal_log({
                        "timestamp": s.timestamp,
                        "symbol": s.symbol,
                        "side": s.side,
                        "setup": s.setup_type,
                        "confidence": s.confidence,
                        "rr_ratio": round(s.rr_ratio, 2),
                        "confluence_count": len(s.confluence_list),
                        "outcome": None,
                    })
                    logger.info("Signal sent: %s %s %s (conf=%s, R:R=%.1f, %d confluence)",
                                s.symbol, s.side, s.setup_type, s.confidence, s.rr_ratio, len(s.confluence_list))
        except Exception as e:
            logger.exception("Scan error for %s: %s", symbol, e)

    # Beast-mode: scan stats logging
    logger.info("Scan complete: %d coins scanned, %d setups found, %d signals sent (daily total: %d/%d)",
                len(watchlist), scan_found, scan_sent, _daily_signal_count, max_daily)


def _refresh_watchlist() -> None:
    _watchlist_manager.refresh()


def main() -> int:
    global _fetcher, _watchlist_manager, _shutdown

    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="Run one scan then exit")
    args = parser.parse_args()

    try:
        config.validate_config()
    except ValueError as e:
        print("Config error:", e)
        return 1

    _setup_logging()
    logger = logging.getLogger(__name__)

    _fetcher = MEXCDataFetcher()
    _watchlist_manager = WatchlistManager(_fetcher)
    _watchlist_manager.refresh()
    watchlist = _watchlist_manager.get_watchlist()
    send_startup_message(len(watchlist))

    if args.once:
        _run_scan()
        return 0

    from apscheduler.schedulers.blocking import BlockingScheduler
    scheduler = BlockingScheduler()
    scheduler.add_job(_run_scan, "interval", seconds=config.SCAN_INTERVAL, id="scan")
    scheduler.add_job(_refresh_watchlist, "interval", seconds=config.WATCHLIST_REFRESH, id="watchlist")

    def _graceful(signum, frame):
        global _shutdown
        _shutdown = True
        logger.info("Shutting down...")

    sig.signal(sig.SIGINT, _graceful)
    sig.signal(sig.SIGTERM, _graceful)

    scheduler.start()
    return 0


if __name__ == "__main__":
    sys.exit(main())
