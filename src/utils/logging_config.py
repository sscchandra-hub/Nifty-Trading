"""
Centralized logging configuration for the trading system.
"""
import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional
from src.config.settings import LoggingConfig


# Global logger registry
_loggers = {}


def setup_logger(
    name: str,
    log_file: Optional[Path] = None,
    level: Optional[str] = None,
    console_output: bool = True
) -> logging.Logger:
    """
    Setup a logger with file and console handlers.

    Args:
        name: Logger name
        log_file: Path to log file (optional)
        level: Logging level (defaults to config)
        console_output: Whether to output to console

    Returns:
        Configured logger instance
    """
    # Return existing logger if already configured
    if name in _loggers:
        return _loggers[name]

    # Create logger
    logger = logging.getLogger(name)

    # Set level
    log_level = level or LoggingConfig.LOG_LEVEL
    logger.setLevel(getattr(logging, log_level.upper()))

    # Remove existing handlers
    logger.handlers.clear()

    # Create formatter
    formatter = logging.Formatter(
        LoggingConfig.LOG_FORMAT,
        datefmt=LoggingConfig.LOG_DATE_FORMAT
    )

    # Add file handler if log_file specified
    if log_file:
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=LoggingConfig.LOG_MAX_BYTES,
            backupCount=LoggingConfig.LOG_BACKUP_COUNT
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    # Add console handler
    if console_output:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    # Prevent propagation to root logger
    logger.propagate = False

    # Store in registry
    _loggers[name] = logger

    return logger


def get_logger(name: str) -> logging.Logger:
    """
    Get existing logger or create new one.

    Args:
        name: Logger name

    Returns:
        Logger instance
    """
    if name in _loggers:
        return _loggers[name]

    return setup_logger(name, log_file=LoggingConfig.LOG_FILE)


def setup_system_loggers():
    """
    Setup all system loggers.
    Call this once at application startup.
    """
    # Main system logger
    setup_logger(
        'trading_system',
        log_file=LoggingConfig.LOG_FILE,
        console_output=True
    )

    # API logger (Kite, Telegram)
    setup_logger(
        'trading_system.api',
        log_file=LoggingConfig.LOG_FILE,
        console_output=True
    )

    # Data polling logger
    setup_logger(
        'trading_system.polling',
        log_file=LoggingConfig.LOG_FILE,
        console_output=True
    )

    # Pattern detection logger
    setup_logger(
        'trading_system.patterns',
        log_file=LoggingConfig.LOG_FILE,
        console_output=True
    )

    # Chart debug logger (separate file)
    if LoggingConfig.CHART_DEBUG_ENABLED:
        setup_logger(
            'trading_system.charts',
            log_file=LoggingConfig.CHART_DEBUG_LOG,
            level='DEBUG',
            console_output=False
        )


def log_exception(logger: logging.Logger, error: Exception, context: str = ""):
    """
    Log exception with context and traceback.

    Args:
        logger: Logger instance
        error: Exception to log
        context: Additional context string
    """
    if context:
        logger.error(f"{context}: {type(error).__name__}: {error}", exc_info=True)
    else:
        logger.error(f"{type(error).__name__}: {error}", exc_info=True)


class LoggerAdapter(logging.LoggerAdapter):
    """
    Custom logger adapter that adds context to all log messages.
    """

    def process(self, msg, kwargs):
        """Add context to message"""
        if self.extra:
            context_str = " | ".join(f"{k}={v}" for k, v in self.extra.items())
            return f"[{context_str}] {msg}", kwargs
        return msg, kwargs


def get_contextual_logger(name: str, **context) -> LoggerAdapter:
    """
    Get logger with additional context.

    Args:
        name: Logger name
        **context: Key-value pairs to add to all log messages

    Returns:
        LoggerAdapter with context

    Example:
        >>> logger = get_contextual_logger('trading_system', index='NIFTY', strike=19250)
        >>> logger.info("Processing option")
        # Logs: [index=NIFTY | strike=19250] Processing option
    """
    base_logger = get_logger(name)
    return LoggerAdapter(base_logger, context)
