"""
Configuration management for the Live Momentum Trading System.
All configurable parameters should be defined here.
"""
import os
from pathlib import Path
from typing import Dict
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# =========================
# PROJECT PATHS
# =========================
PROJECT_ROOT = Path(__file__).parent.parent.parent
DATA_ROOT = PROJECT_ROOT / "data"
CACHE_DIR = PROJECT_ROOT / ".cache"
LOGS_DIR = PROJECT_ROOT / "logs"

# Create directories if they don't exist
DATA_ROOT.mkdir(exist_ok=True)
CACHE_DIR.mkdir(exist_ok=True)
LOGS_DIR.mkdir(exist_ok=True)

# Data subdirectories
HISTORICAL_DIR = DATA_ROOT / "historical" / "indices"
DEBUG_LOG_DIR = DATA_ROOT / "debug"
HISTORICAL_DIR.mkdir(parents=True, exist_ok=True)
DEBUG_LOG_DIR.mkdir(parents=True, exist_ok=True)

# Cache files
TOKENS_FILE = CACHE_DIR / "tokens.json"
DASHBOARD_CACHE_FILE = CACHE_DIR / "dashboard_cache.pkl"
INSTRUMENTS_FILE = CACHE_DIR / "instruments.parquet"
FLOW_HISTORY_FILE = CACHE_DIR / "flow_history.pkl"
POLLING_LOCK_FILE = CACHE_DIR / "polling.lock"
DEBUG_LOG_FILE = DEBUG_LOG_DIR / "charts_debug.log"

# =========================
# API CREDENTIALS
# =========================
class APIConfig:
    """API configuration and credentials"""
    KITE_API_KEY = os.getenv("KITE_API_KEY")
    KITE_API_SECRET = os.getenv("KITE_API_SECRET")
    KITE_REDIRECT_URL = os.getenv("KITE_REDIRECT_URL", "http://localhost")

    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

    @classmethod
    def validate(cls) -> bool:
        """Check if required credentials are present"""
        required = [cls.KITE_API_KEY, cls.KITE_API_SECRET]
        return all(required)

# =========================
# TRADING PARAMETERS
# =========================
class TradingConfig:
    """Trading logic configuration"""

    # Timezone
    TIMEZONE = "Asia/Kolkata"

    # Polling
    POLL_INTERVAL_SECONDS = 10
    API_TIMEOUT_SECONDS = 30
    MAX_RETRIES = 3

    # Strike price steps for different indices
    STRIKE_STEPS: Dict[str, int] = {
        "BANKNIFTY": 100,
        "NIFTY": 50,
        "FINNIFTY": 50,
        "MIDCPNIFTY": 25,
        "SENSEX": 100,
        "NIFTY MIDCAP 50": 50,
        "NIFTY AUTO": 50,
        "NIFTY PHARMA": 50,
        "NIFTY METAL": 50,
        "NIFTY ENERGY": 50,
        "NIFTY FMCG": 50,
        "NIFTY REALTY": 25,
        "NIFTY PSU BANK": 25,
        "NIFTY INFRA": 50,
        "NIFTY OIL & GAS": 50,
    }

    # Default strike step for unlisted indices
    DEFAULT_STRIKE_STEP = 50

    # Segments
    DERIVATIVE_FUTURES_SEGMENTS = {"NFO-FUT", "BFO-FUT"}
    DERIVATIVE_OPTIONS_SEGMENTS = {"NFO-OPT", "BFO-OPT"}

    # Index whitelist
    INDEX_WHITELIST = {
        "NIFTY 50", "NIFTY BANK", "NIFTY FIN SERVICE",
        "NIFTY MID SELECT", "NIFTY MIDCAP 50",
        "NIFTY AUTO", "NIFTY PHARMA", "NIFTY METAL",
        "NIFTY ENERGY", "NIFTY FMCG", "NIFTY REALTY",
        "NIFTY PSU BANK", "NIFTY INFRA", "NIFTY OIL & GAS"
    }

# =========================
# PATTERN DETECTION
# =========================
class PatternConfig:
    """Pattern detection algorithm parameters"""

    # Historical data
    HISTORICAL_LOOKBACK_DAYS = 7

    # Pattern matching
    SIMILARITY_TOLERANCE = 0.20  # ±20%
    MIN_PATTERN_MATCHES = 3
    SUCCESS_THRESHOLD = 0.70  # 70% success rate
    LOOKBACK_MINUTES = 30

    # Pattern thresholds
    SIDEWAYS_THRESHOLD = 0.5  # ±0.5%
    SURGE_MULTIPLIER = 2.0
    REVERSAL_THRESHOLD = 1.0  # ±1.0%

# =========================
# VOLUME ANALYSIS
# =========================
class VolumeConfig:
    """Volume spike detection parameters"""

    # Spike detection
    STRONG_SPIKE_RATIO = 5.0
    MODERATE_SPIKE_RATIO = 3.0
    NORMAL_SPIKE_RATIO = 2.0

    # History sizes (deque maxlen)
    SPIKE_QUEUE_SIZE = 50
    CE_PE_HISTORY_SIZE = 60  # 10 minutes
    TIMELINE_DATA_SIZE = 180  # 30 minutes
    INTENSITY_HISTORY_SIZE = 180

    # ATM strike range
    ATM_STRIKES_RANGE = 2  # ±2 strikes from ATM

# =========================
# LIQUIDITY FILTERS
# =========================
class LiquidityConfig:
    """Liquidity filtering thresholds"""

    THRESHOLDS: Dict[str, Dict[str, float]] = {
        'NIFTY': {
            'min_oi': 100_000,
            'min_volume': 10_000,
            'max_bid_ask_spread': 2.0  # percentage
        },
        'BANKNIFTY': {
            'min_oi': 50_000,
            'min_volume': 5_000,
            'max_bid_ask_spread': 2.0
        },
        'FINNIFTY': {
            'min_oi': 20_000,
            'min_volume': 2_000,
            'max_bid_ask_spread': 3.0
        },
        'MIDCPNIFTY': {
            'min_oi': 20_000,
            'min_volume': 2_000,
            'max_bid_ask_spread': 3.0
        },
        'SENSEX': {
            'min_oi': 20_000,
            'min_volume': 2_000,
            'max_bid_ask_spread': 3.0
        }
    }

    # Default for stocks
    DEFAULT_STOCK_THRESHOLDS = {
        'min_oi': 10_000,
        'min_volume': 1_000,
        'max_bid_ask_spread': 3.0
    }

# =========================
# UI CONFIGURATION
# =========================
class UIConfig:
    """Streamlit UI settings"""

    PAGE_TITLE = "Live Momentum Trading System"
    PAGE_LAYOUT = "wide"
    SIDEBAR_STATE = "expanded"

    # Auto-refresh
    AUTO_REFRESH_ENABLED = True
    AUTO_REFRESH_INTERVAL_MS = 30000  # 30 seconds

    # Chart settings
    CHART_HEIGHT = 400
    CHART_THEME = "plotly_dark"

# =========================
# LOGGING
# =========================
class LoggingConfig:
    """Logging configuration"""

    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

    # File logging
    LOG_FILE = LOGS_DIR / "trading_system.log"
    LOG_MAX_BYTES = 10 * 1024 * 1024  # 10MB
    LOG_BACKUP_COUNT = 5

    # Chart debug logging
    CHART_DEBUG_LOG = DEBUG_LOG_FILE
    CHART_DEBUG_ENABLED = True

# =========================
# MOMENTUM SIGNALS
# =========================
class SignalConfig:
    """Signal generation thresholds"""

    # CE/PE dominance
    CE_DOMINATING_THRESHOLD = 75  # %
    PE_DOMINATING_THRESHOLD = 75  # %

    CE_VERY_AGGRESSIVE_THRESHOLD = 65  # %
    CE_AGGRESSIVE_THRESHOLD = 55  # %
    PE_VERY_AGGRESSIVE_THRESHOLD = 65  # %
    PE_AGGRESSIVE_THRESHOLD = 55  # %

    # Momentum
    ACCELERATION_THRESHOLD = 1.5  # multiplier
    SURGE_THRESHOLD = 2.0  # multiplier

# =========================
# VALIDATION
# =========================
def validate_config() -> tuple[bool, list[str]]:
    """
    Validate configuration settings

    Returns:
        (is_valid, error_messages)
    """
    errors = []

    # Check API credentials
    if not APIConfig.validate():
        errors.append("Missing required API credentials (KITE_API_KEY, KITE_API_SECRET)")

    # Check directories exist
    required_dirs = [DATA_ROOT, CACHE_DIR, LOGS_DIR]
    for directory in required_dirs:
        if not directory.exists():
            errors.append(f"Required directory does not exist: {directory}")

    # Validate numeric ranges
    if not (0 < PatternConfig.SIMILARITY_TOLERANCE < 1):
        errors.append("Pattern similarity tolerance must be between 0 and 1")

    if PatternConfig.MIN_PATTERN_MATCHES < 1:
        errors.append("Minimum pattern matches must be at least 1")

    if not (0 < PatternConfig.SUCCESS_THRESHOLD <= 1):
        errors.append("Success threshold must be between 0 and 1")

    return (len(errors) == 0, errors)

# Run validation on import
_is_valid, _errors = validate_config()
if not _is_valid:
    import warnings
    for error in _errors:
        warnings.warn(f"Configuration error: {error}")
