"""
Custom exceptions for the trading system.
"""


class TradingSystemError(Exception):
    """Base exception for all trading system errors"""
    pass


class ConfigurationError(TradingSystemError):
    """Configuration related errors"""
    pass


class APIError(TradingSystemError):
    """API communication errors"""
    pass


class KiteConnectionError(APIError):
    """Kite Connect API connection errors"""
    def __init__(self, message: str, status_code: int = None):
        self.status_code = status_code
        super().__init__(message)


class KiteAuthenticationError(APIError):
    """Kite Connect authentication errors"""
    pass


class RateLimitError(APIError):
    """API rate limit exceeded"""
    def __init__(self, message: str, retry_after: int = None):
        self.retry_after = retry_after
        super().__init__(message)


class DataValidationError(TradingSystemError):
    """Data validation errors"""
    pass


class InstrumentNotFoundError(DataValidationError):
    """Instrument not found in database"""
    def __init__(self, instrument: str):
        self.instrument = instrument
        super().__init__(f"Instrument not found: {instrument}")


class InvalidStrikeError(DataValidationError):
    """Invalid strike price"""
    def __init__(self, strike: int, valid_step: int):
        self.strike = strike
        self.valid_step = valid_step
        super().__init__(f"Invalid strike {strike}, must be multiple of {valid_step}")


class MarketClosedError(TradingSystemError):
    """Operation attempted when market is closed"""
    pass


class InsufficientDataError(TradingSystemError):
    """Not enough data to perform operation"""
    def __init__(self, required: int, available: int):
        self.required = required
        self.available = available
        super().__init__(f"Insufficient data: need {required}, have {available}")


class PatternDetectionError(TradingSystemError):
    """Pattern detection errors"""
    pass


class CacheError(TradingSystemError):
    """Cache read/write errors"""
    pass


class TelegramError(APIError):
    """Telegram bot API errors"""
    pass


class PollingError(TradingSystemError):
    """Data polling errors"""
    pass


class ThreadingError(TradingSystemError):
    """Threading/concurrency errors"""
    pass
