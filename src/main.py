"""
Crypto View screener: filter by min volume, run every 1 hour.
Grading list: (1) pairs that swept SWH/SWL this bar, (2) pairs with a deviation
candle in the last 4 bars (4H/1H only) whose high/low was already swept.
Only new candidates in top 10 trigger Telegram. Runs as a Linux systemd service.
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
from src.sweep_screener import (
    get_pairs_by_volume,
    pairs_that_swept,
    pairs_with_deviation_swept,
)
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
    """
    Get pairs with volume >= MIN_VOLUME; build grading list from:
    1) Current bar SWH/SWL sweep (existing logic)
    2) Deviation candle in last 4 bars (4H/1H only) whose high/low was already swept.
    Rank, take top 10; send Telegram only if at least one new candidate (same as before).
    """
    logger = logging.getLogger(__name__)
    if _shutdown:
        return
    symbols = get_pairs_by_volume(_fetcher, config.MIN_VOLUME)
    if not symbols:
        logger.warning("No pairs above min volume %s", config.MIN_VOLUME)
        return
    logger.info("Scanning %d pairs (volume >= %s)", len(symbols), config.MIN_VOLUME)

    # 1) Current bar sweep (SWH/SWL)
    sweep_results = pairs_that_swept(
        symbols,
        _fetcher,
        timeframe=config.SWING_TIMEFRAME,
        limit=100,
        pivot_len=config.SWING_PIVOT_LEN,
        swing_lookback=config.SWING_LOOKBACK,
    )
    # 2) Deviation candle in last 4 bars on 4H/1H with level already swept
    deviation_results = pairs_with_deviation_swept(
        symbols,
        _fetcher,
        timeframes=config.DEV_TIMEFRAMES,
        lookback_bars=config.DEV_LOOKBACK_BARS,
        limit=100,
        pivot_len=config.SWING_PIVOT_LEN,
        swing_lookback=config.SWING_LOOKBACK,
    )

    # Merge into grading list: sweep first, then deviation; dedupe by symbol (keep sweep if both)
    seen = set()
    results: list = []
    for r in sweep_results:
        seen.add(r.symbol)
        results.append(r)
    for r in deviation_results:
        if r.symbol not in seen:
            seen.add(r.symbol)
            results.append(r)

    if not results:
        logger.info("No pairs in grading list this run (sweep or deviation)")
        return
    for r in results:
        src = f" dev[{r.deviation_tf}]" if getattr(r, "deviation_tf", None) else " sweep"
        msg = (
            f"{r.symbol}{src} SWH={r.swept_swing_high} SWL={r.swept_swing_low} "
            f"(SH={r.last_swing_high} SL={r.last_swing_low} close={r.last_close})"
        )
        logger.info(msg)

    # Rank: both SWH+SWL first, then by order; take top 10
    indexed = list(enumerate(results))
    ranked = sorted(
        indexed,
        key=lambda item: (
            0 if (item[1].swept_swing_high and item[1].swept_swing_low) else 1,
            -item[0],
        ),
    )
    top10 = [item[1] for item in ranked[:10]]

    # Only send when at least one new pair (not in previous watchlist)
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
        description="Screener: volume filter + sweep + deviation (4 bars, 4H/1H), every 1h (Linux service)"
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
