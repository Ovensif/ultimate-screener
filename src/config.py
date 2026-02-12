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

# Beast-mode signal quality tunables
ADX_MIN_SIGNAL = _float("ADX_MIN_SIGNAL", 20.0)       # min ADX for any signal
ADX_STRONG = _float("ADX_STRONG", 35.0)                # ADX for "very strong trend" confluence
RETEST_TOLERANCE = _float("RETEST_TOLERANCE", 0.003)   # 0.3% breakout retest proximity
VOLUME_SPIKE_MULT = _float("VOLUME_SPIKE_MULT", 1.5)   # volume spike multiplier
MAX_STOP_PCT = _float("MAX_STOP_PCT", 0.025)           # 2.5% max stop distance
MIN_ATR_PCT = _float("MIN_ATR_PCT", 1.0)               # min ATR% (filter dead coins)
MAX_ATR_PCT = _float("MAX_ATR_PCT", 8.0)               # max ATR% (filter extreme volatility)
MIN_PRICE_CHANGE = _float("MIN_PRICE_CHANGE", 2.0)     # watchlist min 24h price change %
MAX_SPREAD_PCT = _float("MAX_SPREAD_PCT", 0.1)         # watchlist max bid-ask spread %
WATCHLIST_ADX_MIN = _float("WATCHLIST_ADX_MIN", 25.0)  # watchlist trend score ADX threshold
BTC_DUMP_1H = _float("BTC_DUMP_1H", -5.0)              # BTC 1H dump threshold %
BTC_DUMP_4H = _float("BTC_DUMP_4H", -3.0)              # BTC 4H dump threshold %
ETH_DUMP_4H = _float("ETH_DUMP_4H", -3.0)              # ETH 4H dump threshold %
MAX_SIGNALS_PER_DAY = _int("MAX_SIGNALS_PER_DAY", 8)   # daily signal cap
MAX_LEVERAGE = _int("MAX_LEVERAGE", 3)                  # max suggested leverage (was 5)

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
