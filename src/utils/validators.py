"""
Data validation utilities.
"""
from typing import Optional, List, Any
from datetime import datetime, time as dt_time


def is_market_open(current_time: Optional[datetime] = None) -> bool:
    """
    Check if market is currently open.

    Args:
        current_time: Time to check (defaults to now)

    Returns:
        True if market is open
    """
    if current_time is None:
        current_time = datetime.now()

    # Market hours: 9:15 AM to 3:30 PM IST (Monday-Friday)
    market_open = dt_time(9, 15)
    market_close = dt_time(15, 30)

    # Check if weekday
    if current_time.weekday() >= 5:  # Saturday = 5, Sunday = 6
        return False

    current_time_only = current_time.time()
    return market_open <= current_time_only <= market_close


def is_valid_strike(strike: int, step: int) -> bool:
    """
    Validate if strike is a valid multiple of step.

    Args:
        strike: Strike price
        step: Strike step size

    Returns:
        True if valid
    """
    return strike % step == 0


def is_valid_option_type(option_type: str) -> bool:
    """
    Validate option type.

    Args:
        option_type: Option type string

    Returns:
        True if valid (CE or PE)
    """
    return option_type in ["CE", "PE"]


def is_valid_price(price: float) -> bool:
    """
    Validate if price is valid (positive number).

    Args:
        price: Price value

    Returns:
        True if valid
    """
    return price is not None and price > 0


def is_valid_volume(volume: int) -> bool:
    """
    Validate if volume is valid (non-negative).

    Args:
        volume: Volume value

    Returns:
        True if valid
    """
    return volume is not None and volume >= 0


def is_liquid_option(
    oi: int,
    volume: int,
    min_oi: int,
    min_volume: int,
    bid_ask_spread: Optional[float] = None,
    max_spread: Optional[float] = None
) -> bool:
    """
    Check if option meets liquidity requirements.

    Args:
        oi: Open Interest
        volume: Trading volume
        min_oi: Minimum required OI
        min_volume: Minimum required volume
        bid_ask_spread: Bid-ask spread percentage
        max_spread: Maximum allowed spread percentage

    Returns:
        True if liquid
    """
    # Check OI and volume
    if oi < min_oi or volume < min_volume:
        return False

    # Check spread if provided
    if bid_ask_spread is not None and max_spread is not None:
        if bid_ask_spread > max_spread:
            return False

    return True


def validate_data_completeness(
    data: dict,
    required_fields: List[str]
) -> tuple[bool, List[str]]:
    """
    Validate that all required fields are present in data.

    Args:
        data: Data dictionary
        required_fields: List of required field names

    Returns:
        Tuple of (is_valid, missing_fields)
    """
    missing = [field for field in required_fields if field not in data or data[field] is None]
    return (len(missing) == 0, missing)


def is_valid_percentage(value: float) -> bool:
    """
    Validate percentage value is in valid range.

    Args:
        value: Percentage value (0-100)

    Returns:
        True if valid
    """
    return 0 <= value <= 100


def is_valid_token(token: Any) -> bool:
    """
    Validate instrument token.

    Args:
        token: Token value

    Returns:
        True if valid (positive integer)
    """
    try:
        token_int = int(token)
        return token_int > 0
    except (ValueError, TypeError):
        return False


def sanitize_index_name(name: str) -> str:
    """
    Sanitize index name for file system and lookup.

    Args:
        name: Raw index name

    Returns:
        Sanitized name
    """
    # Remove special characters, replace spaces with underscores
    sanitized = name.upper().strip()
    sanitized = sanitized.replace(" ", "_")
    sanitized = ''.join(c for c in sanitized if c.isalnum() or c == '_')
    return sanitized


def is_within_trading_hours(
    current_time: Optional[datetime] = None,
    include_pre_market: bool = False
) -> bool:
    """
    Check if current time is within trading hours.

    Args:
        current_time: Time to check (defaults to now)
        include_pre_market: Include pre-market hours (9:00-9:15)

    Returns:
        True if within trading hours
    """
    if current_time is None:
        current_time = datetime.now()

    # Check if weekday
    if current_time.weekday() >= 5:
        return False

    current_time_only = current_time.time()

    if include_pre_market:
        start_time = dt_time(9, 0)
    else:
        start_time = dt_time(9, 15)

    end_time = dt_time(15, 30)

    return start_time <= current_time_only <= end_time
