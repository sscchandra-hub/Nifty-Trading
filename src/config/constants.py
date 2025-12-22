"""
Constants and immutable values used throughout the application.
These should not be configurable by users.
"""

# =========================
# MARKET CONSTANTS
# =========================

# Trading session times (24-hour format)
MARKET_OPEN_TIME = "09:15"
MARKET_CLOSE_TIME = "15:30"
PRE_MARKET_OPEN_TIME = "09:00"

# Option types
OPTION_TYPE_CALL = "CE"
OPTION_TYPE_PUT = "PE"

# Instrument types
INSTRUMENT_TYPE_SPOT = "SPOT"
INSTRUMENT_TYPE_FUTURES = "FUT"
INSTRUMENT_TYPE_OPTIONS = "OPT"

# Categories
CATEGORY_INDEX = "INDEX"
CATEGORY_STOCK = "STOCK"

# =========================
# DISPLAY CONSTANTS
# =========================

# Emojis for alerts
EMOJI_FIRE = "🔥"
EMOJI_WARNING = "🟡"
EMOJI_SUCCESS = "🟢"
EMOJI_BULL = "🚀"
EMOJI_BEAR = "📉"
EMOJI_NEUTRAL = "⚖️"
EMOJI_CHART = "📊"

# Alert levels
ALERT_LEVEL_STRONG = "STRONG"
ALERT_LEVEL_MODERATE = "MODERATE"
ALERT_LEVEL_NORMAL = "NORMAL"

# Colors (hex codes)
COLOR_GREEN = "#00aa00"
COLOR_RED = "#ff0000"
COLOR_YELLOW = "#ffaa00"
COLOR_ORANGE = "#ff4444"

# =========================
# DATA CONSTANTS
# =========================

# Missing data placeholder
MISSING_DATA_PLACEHOLDER = "—"

# Number formatting thresholds
THOUSAND = 1_000
MILLION = 1_000_000

# =========================
# API CONSTANTS
# =========================

# Kite Connect
KITE_API_VERSION = "3"
KITE_INSTRUMENTS_URL = "https://api.kite.trade/instruments"

# Quote batch size
QUOTE_BATCH_SIZE = 500

# =========================
# MOMENTUM SIGNALS
# =========================

MOMENTUM_ACCELERATING = "🔥 ACCELERATING"
MOMENTUM_SURGING = "🚀 SURGING"
MOMENTUM_STEADY = "➡️ STEADY"
MOMENTUM_SLOWING = "⬇️ SLOWING"
MOMENTUM_REVERSING = "🔄 REVERSING"

# =========================
# CHART CONSTANTS
# =========================

# Chart types
CHART_TYPE_LINE = "line"
CHART_TYPE_BAR = "bar"
CHART_TYPE_CANDLESTICK = "candlestick"

# Default dimensions
DEFAULT_CHART_HEIGHT = 400
DEFAULT_CHART_WIDTH = None  # Auto

# =========================
# FILE FORMATS
# =========================

FILE_FORMAT_CSV = ".csv"
FILE_FORMAT_PARQUET = ".parquet"
FILE_FORMAT_JSON = ".json"
FILE_FORMAT_PICKLE = ".pkl"

# Date format for file names
DATE_FORMAT_FILE = "%Y-%m-%d"
DATETIME_FORMAT_FILE = "%Y-%m-%d_%H-%M-%S"
