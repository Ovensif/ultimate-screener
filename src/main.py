"""
Bot: Top 10 altcoins with RSI strong/weak + 4H sweep. Telegram only when list changes.
"""
import argparse
import json
import logging
import signal as sig
import sys
from datetime import datetime, timezone
from pathlib import Path

# Run from project root (parent of src)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src import config
from src.alert10_screener import build_alert10_list
from src.data_fetcher import MEXCDataFetcher
from src.telegram_bot import send_alert10_list_change, send_startup_message
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


# Module-level state for scheduler jobs
_fetcher: MEXCDataFetcher = None
_watchlist_manager: WatchlistManager = None
_shutdown = False


def _refresh_watchlist() -> None:
    _watchlist_manager.refresh()


def _load_alert10_list() -> list:
    """Load previous Alert 10 list from file. Return list of symbols or [] if missing/invalid."""
    path = getattr(config, "ALERT10_LIST_FILE", config.DATA_DIR / "alert10_list.json")
    if not path.exists():
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        symbols = data.get("symbols")
        return list(symbols) if isinstance(symbols, list) else []
    except Exception:
        return []


def _save_alert10_list(symbols: list) -> None:
    """Persist Alert 10 list to file."""
    path = getattr(config, "ALERT10_LIST_FILE", config.DATA_DIR / "alert10_list.json")
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(
                {"symbols": symbols, "updated_utc": datetime.now(timezone.utc).isoformat()},
                f,
                indent=2,
            )
    except Exception as e:
        logging.getLogger(__name__).warning("Could not write alert10_list.json: %s", e)


def _run_alert10() -> None:
    """
    Build Alert 10 list (4H sweep + RSI strong/weak), compare with previous.
    Send Telegram only when list composition changed; then persist.
    """
    logger = logging.getLogger(__name__)
    if _shutdown:
        return
    watchlist = _watchlist_manager.get_watchlist()
    if not watchlist:
        logger.debug("Alert10: watchlist empty, skip")
        return
    current_list = build_alert10_list(watchlist, _fetcher)
    previous_list = _load_alert10_list()
    previous_set = set(previous_list)
    current_set = set(current_list)
    delisted = sorted(previous_set - current_set)
    new_coins = sorted(current_set - previous_set)
    if delisted or new_coins:
        ok = send_alert10_list_change(delisted, new_coins, current_list)
        if ok:
            logger.info("Alert10 list changed: out=%s in=%s", delisted, new_coins)
    _save_alert10_list(current_list)


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
        _run_alert10()
        return 0

    from apscheduler.schedulers.blocking import BlockingScheduler
    scheduler = BlockingScheduler()
    scheduler.add_job(_refresh_watchlist, "interval", seconds=config.WATCHLIST_REFRESH, id="watchlist")
    if getattr(config, "ALERT10_ENABLED", False):
        scheduler.add_job(_run_alert10, "interval", seconds=config.ALERT10_INTERVAL, id="alert10")
        _run_alert10()  # run once at startup so first list is persisted and user notified if list exists

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
