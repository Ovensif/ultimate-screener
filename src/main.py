"""
Simple screener: filter pairs by min volume (300k), run every 10 min,
check if pair already swept Swing High / Swing Low (Pine Crypto View 1.0 logic).
Runs as a Linux systemd service only.
"""
import argparse
import json
import logging
import logging.handlers
import signal as sig
import sys
from datetime import datetime, timezone
from pathlib import Path

# Run from project root (parent of src)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Linux only
if sys.platform != "linux":
    print("This bot is intended to run as a service on Linux only. Exiting.")
    sys.exit(1)

from src import config
from src.data_fetcher import MEXCDataFetcher
from src.sweep_screener import get_pairs_by_volume, pairs_that_swept
from src.telegram_bot import send_top10_sweep_table

_fetcher: MEXCDataFetcher = None
_shutdown = False


def _load_top10_sent() -> set:
    """Load last sent Top 10 symbols from JSON. Return empty set if missing/invalid."""
    path = config.TOP10_SWEEP_SENT_FILE
    if not path.exists():
        return set()
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        symbols = data.get("symbols")
        return set(symbols) if isinstance(symbols, list) else set()
    except Exception:
        return set()


def _save_top10_sent(symbols: list) -> None:
    """Save current Top 10 symbols to JSON (only after successful Telegram send)."""
    path = config.TOP10_SWEEP_SENT_FILE
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(
                {"symbols": symbols, "updated_utc": datetime.now(timezone.utc).isoformat()},
                f,
                indent=2,
            )
    except Exception as e:
        logging.getLogger(__name__).warning("Could not write top10_sweep_sent.json: %s", e)


def _setup_logging() -> None:
    config.LOGS_DIR.mkdir(parents=True, exist_ok=True)
    log_file = config.LOGS_DIR / "screener.log"
    handler = logging.handlers.RotatingFileHandler(
        log_file, maxBytes=2 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    )
    logging.root.addHandler(handler)
    logging.root.setLevel(logging.INFO)
    console = logging.StreamHandler()
    console.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
    logging.root.addHandler(console)


def _run_scan() -> None:
    """Get pairs with volume >= MIN_VOLUME, check SWH/SWL sweep, log and optionally notify."""
    logger = logging.getLogger(__name__)
    if _shutdown:
        return
    symbols = get_pairs_by_volume(_fetcher, config.MIN_VOLUME)
    if not symbols:
        logger.warning("No pairs above min volume %s", config.MIN_VOLUME)
        return
    logger.info("Scanning %d pairs (volume >= %s)", len(symbols), config.MIN_VOLUME)
    results = pairs_that_swept(
        symbols,
        _fetcher,
        timeframe=config.SWING_TIMEFRAME,
        limit=100,
        pivot_len=config.SWING_PIVOT_LEN,
        swing_lookback=config.SWING_LOOKBACK,
    )
    if not results:
        logger.info("No pairs with SWH/SWL sweep this run")
        return
    for r in results:
        msg = (
            f"{r.symbol} swept SWH={r.swept_swing_high} SWL={r.swept_swing_low} "
            f"(SH={r.last_swing_high} SL={r.last_swing_low} close={r.last_close})"
        )
        logger.info(msg)

    # Rank: both SWH+SWL first, then volume order; take top 10
    indexed = list(enumerate(results))
    ranked = sorted(
        indexed,
        key=lambda item: (
            0 if (item[1].swept_swing_high and item[1].swept_swing_low) else 1,
            -item[0],
        ),
    )
    top10 = [item[1] for item in ranked[:10]]

    # Only send notification when there's at least one new pair worth watching (not in previous watchlist)
    if top10:
        previous = _load_top10_sent()
        has_new = any(r.symbol not in previous for r in top10)
        if has_new and send_top10_sweep_table(top10, previous):
            _save_top10_sent([r.symbol for r in top10])
        elif not has_new:
            logger.info("Top 10 unchanged (no new pairs); skipping notification")


def main() -> int:
    global _fetcher, _shutdown

    parser = argparse.ArgumentParser(
        description="Screener: volume filter + SWH/SWL sweep check, every 10 min (Linux service)"
    )
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

    if args.once:
        _run_scan()
        return 0

    from apscheduler.schedulers.blocking import BlockingScheduler

    scheduler = BlockingScheduler()
    scheduler.add_job(
        _run_scan,
        "interval",
        seconds=config.SCAN_INTERVAL,
        id="sweep_scan",
    )
    _run_scan()

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
