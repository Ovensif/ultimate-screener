"""
Read signal log and compute performance stats. Can be run manually or via cron for daily summary.
"""
import json
import sys
from pathlib import Path

# Project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src import config


def load_signals() -> list:
    path = config.DATA_DIR / "signals.json"
    if not path.exists():
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def main() -> int:
    data = load_signals()
    total = len(data)
    if total == 0:
        print("No signals recorded yet.")
        return 0
    by_side = {}
    by_setup = {}
    outcomes = []
    for r in data:
        side = r.get("side", "unknown")
        by_side[side] = by_side.get(side, 0) + 1
        setup = r.get("setup", "unknown")
        by_setup[setup] = by_setup.get(setup, 0) + 1
        if r.get("outcome") is not None:
            outcomes.append(r["outcome"])
    print(f"Total signals: {total}")
    print("By side:", by_side)
    print("By setup:", by_setup)
    if outcomes:
        wins = sum(1 for o in outcomes if o in ("tp1", "tp2", "hit"))
        print(f"Tracked outcomes: {len(outcomes)}, wins: {wins}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
