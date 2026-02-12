"""
Orchestrator: scheduler, watchlist refresh, scan loop, Telegram alerts, signal logging.
"""
import argparse
import json
import logging
import signal as sig
import sys
import time
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


COOLDOWN_SEC = 4 * 3600  # 4 hours
BTC_SYMBOL = "BTC/USDT:USDT"
SIGNALS_FILE = config.DATA_DIR / "signals.json"

# Module-level state for scheduler jobs
_fetcher: MEXCDataFetcher = None
_watchlist_manager: WatchlistManager = None
_last_signal_time: dict = {}
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


def _btc_1h_change() -> float:
    """Return BTC 1h percentage change or 0 if unavailable."""
    try:
        df = _fetcher.fetch_ohlcv(BTC_SYMBOL, "1h", 5)
        if df is None or len(df) < 2:
            return 0.0
        prev = df["close"].iloc[-2]
        curr = df["close"].iloc[-1]
        if prev and prev > 0:
            return 100 * (curr - prev) / prev
    except Exception:
        pass
    return 0.0


def _run_scan() -> None:
    global _last_signal_time
    logger = logging.getLogger(__name__)
    watchlist = _watchlist_manager.get_watchlist()
    if not watchlist:
        logger.info("Watchlist empty, skipping scan")
        return

    btc_change = _btc_1h_change()
    btc_dump = btc_change < -5.0
    if btc_dump:
        logger.info("BTC 1h change %.2f%%, suppressing new signals", btc_change)

    for symbol in watchlist:
        if _shutdown:
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
                if btc_dump and s.confidence != "HIGH":
                    continue
                now = time.time()
                if _last_signal_time.get(symbol, 0) + COOLDOWN_SEC > now:
                    logger.debug("Skip signal %s: cooldown", symbol)
                    continue
                risk_result = calculate(
                    (s.entry_zone[0] + s.entry_zone[1]) / 2,
                    s.stop,
                    s.side,
                )
                ok = send_signal(s, risk_result)
                if ok:
                    _last_signal_time[symbol] = now
                    _append_signal_log({
                        "timestamp": s.timestamp,
                        "symbol": s.symbol,
                        "side": s.side,
                        "setup": s.setup_type,
                        "confidence": s.confidence,
                        "outcome": None,
                    })
                    logger.info("Signal sent: %s %s %s", s.symbol, s.side, s.setup_type)
        except Exception as e:
            logger.exception("Scan error for %s: %s", symbol, e)


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
