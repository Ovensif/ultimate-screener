"""
Configuration loaded from environment and .env.
All settings for the MEXC futures signal screener.
"""
import os
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:
    raise ImportError(
        "Missing dependency: python-dotenv. Install with:\n"
        "  pip install -r requirements.txt\n"
        "or: pip install python-dotenv\n"
        "If using systemd, ensure the same Python (or venv) that has these packages is used in ExecStart."
    ) from None

# Project root: parent of src/
PROJECT_ROOT = Path(__file__).resolve().parent.parent
# Load .env from project root or config/
load_dotenv(PROJECT_ROOT / ".env")
load_dotenv(PROJECT_ROOT / "config" / ".env")

# Required
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()

# Optional MEXC
MEXC_API_KEY = os.environ.get("MEXC_API_KEY", "").strip()
MEXC_API_SECRET = os.environ.get("MEXC_API_SECRET", "").strip()

# Tunables with defaults
def _int(key: str, default: int) -> int:
    try:
        return int(os.environ.get(key, str(default)))
    except ValueError:
        return default

def _float(key: str, default: float) -> float:
    try:
        return float(os.environ.get(key, str(default)))
    except ValueError:
        return default

# Screener: filter pairs by 24h volume (min 300k)
MIN_VOLUME = _int("MIN_VOLUME", 300_000)
# Run scan every 1 hour (3600); set SCAN_INTERVAL in .env to override
SCAN_INTERVAL = _int("SCAN_INTERVAL", 3600)
# Swing (Crypto View 1.0: confPivotLen, confSwingBars)
SWING_PIVOT_LEN = _int("SWING_PIVOT_LEN", 5)
SWING_LOOKBACK = _int("SWING_LOOKBACK", 30)
SWING_TIMEFRAME = os.environ.get("SWING_TIMEFRAME", "4h").strip() or "4h"

# Deviation (Crypto View V3.0): look back 4 bars for deviation candle on 4H/1H only
DEV_LOOKBACK_BARS = _int("DEV_LOOKBACK_BARS", 4)
DEV_TIMEFRAMES = ("4h", "1h")  # only these timeframes for deviation

# Paths
DATA_DIR = PROJECT_ROOT / os.environ.get("DATA_DIR", "data")
LOGS_DIR = PROJECT_ROOT / os.environ.get("LOGS_DIR", "logs")
BLACKLIST_PATH = PROJECT_ROOT / "config" / "blacklist.txt"
TOP10_SWEEP_SENT_FILE = DATA_DIR / "top10_sweep_sent.json"

# Ensure dirs exist
DATA_DIR.mkdir(parents=True, exist_ok=True)
LOGS_DIR.mkdir(parents=True, exist_ok=True)
(DATA_DIR / "cache").mkdir(parents=True, exist_ok=True)


def validate_config() -> None:
    """Assert required env vars are present (Telegram is used to send sweep alerts)."""
    if not TELEGRAM_BOT_TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN is required. Set it in .env or environment.")
    if not TELEGRAM_CHAT_ID:
        raise ValueError("TELEGRAM_CHAT_ID is required. Set it in .env or environment.")
