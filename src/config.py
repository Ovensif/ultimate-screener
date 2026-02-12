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

SCAN_INTERVAL = _int("SCAN_INTERVAL", 600)
WATCHLIST_REFRESH = _int("WATCHLIST_REFRESH", 3600)
MIN_VOLUME = _int("MIN_VOLUME", 100_000_000)
MAX_COINS = _int("MAX_COINS", 20)
ACCOUNT_SIZE = _float("ACCOUNT_SIZE", 200.0)
RISK_PER_TRADE = _float("RISK_PER_TRADE", 2.0)
MIN_RR_RATIO = _float("MIN_RR_RATIO", 2.0)
TIMEFRAME = os.environ.get("TIMEFRAME", "4h").strip().lower()
CONFIDENCE_THRESHOLD = os.environ.get("CONFIDENCE_THRESHOLD", "HIGH").strip().upper()

# Paths
DATA_DIR = PROJECT_ROOT / os.environ.get("DATA_DIR", "data")
LOGS_DIR = PROJECT_ROOT / os.environ.get("LOGS_DIR", "logs")
BLACKLIST_PATH = PROJECT_ROOT / "config" / "blacklist.txt"

# Ensure dirs exist
DATA_DIR.mkdir(parents=True, exist_ok=True)
LOGS_DIR.mkdir(parents=True, exist_ok=True)
(DATA_DIR / "cache").mkdir(parents=True, exist_ok=True)


def validate_config() -> None:
    """Assert required env vars are present. Call at startup."""
    if not TELEGRAM_BOT_TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN is required. Set it in .env or environment.")
    if not TELEGRAM_CHAT_ID:
        raise ValueError("TELEGRAM_CHAT_ID is required. Set it in .env or environment.")
