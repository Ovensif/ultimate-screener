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

# Watchlist (candidate pool for Alert 10)
WATCHLIST_REFRESH = _int("WATCHLIST_REFRESH", 3600)
MIN_VOLUME = _int("MIN_VOLUME", 100_000_000)
MAX_COINS = _int("MAX_COINS", 20)
MIN_PRICE_CHANGE = _float("MIN_PRICE_CHANGE", 2.0)
MAX_SPREAD_PCT = _float("MAX_SPREAD_PCT", 0.1)
WATCHLIST_ADX_MIN = _float("WATCHLIST_ADX_MIN", 25.0)
MIN_ATR_PCT = _float("MIN_ATR_PCT", 1.0)
MAX_ATR_PCT = _float("MAX_ATR_PCT", 8.0)
# Market analyzer (used by watchlist + Alert 10 screener)
VOLUME_SPIKE_MULT = _float("VOLUME_SPIKE_MULT", 1.5)
ADX_STRONG = _float("ADX_STRONG", 35.0)

# Alert 10: sweep-only altcoin list, notify only when list composition changes
def _bool(key: str, default: bool) -> bool:
    val = os.environ.get(key, "").strip().lower()
    if val in ("1", "true", "yes"):
        return True
    if val in ("0", "false", "no"):
        return False
    return default

ALERT10_ENABLED = _bool("ALERT10_ENABLED", True)
ALERT10_INTERVAL = _int("ALERT10_INTERVAL", 3600)
ALERT10_MAX_COINS = _int("ALERT10_MAX_COINS", 10)
ALERT10_RSI_STRONG = _float("ALERT10_RSI_STRONG", 65.0)   # RSI >= this = strong zone
ALERT10_RSI_WEAK = _float("ALERT10_RSI_WEAK", 35.0)       # RSI <= this = weak zone

# Paths
DATA_DIR = PROJECT_ROOT / os.environ.get("DATA_DIR", "data")
LOGS_DIR = PROJECT_ROOT / os.environ.get("LOGS_DIR", "logs")
BLACKLIST_PATH = PROJECT_ROOT / "config" / "blacklist.txt"
ALERT10_LIST_FILE = DATA_DIR / "alert10_list.json"

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
