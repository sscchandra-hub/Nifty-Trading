"""
Data formatting utilities.
"""
from typing import Optional
from src.config.constants import MISSING_DATA_PLACEHOLDER, THOUSAND, MILLION


def format_number(num: Optional[float]) -> str:
    """
    Format number in K/M notation for better readability.

    Examples:
        >>> format_number(850)
        '850'
        >>> format_number(5000)
        '5.0K'
        >>> format_number(1500000)
        '1.50M'
        >>> format_number(-25000)
        '-25.0K'
        >>> format_number(None)
        '—'

    Args:
        num: Number to format (can be None)

    Returns:
        Formatted string with K/M suffix
    """
    if num is None:
        return MISSING_DATA_PLACEHOLDER

    abs_num = abs(num)

    if abs_num >= MILLION:
        # Millions
        return f"{num/MILLION:.2f}M"
    elif abs_num >= THOUSAND:
        # Thousands
        return f"{num/THOUSAND:.1f}K"
    else:
        # Raw number
        return f"{num:.0f}"


def format_percentage(value: Optional[float], decimals: int = 2) -> str:
    """
    Format percentage with specified decimal places.

    Args:
        value: Percentage value (e.g., 0.15 for 15%)
        decimals: Number of decimal places

    Returns:
        Formatted percentage string
    """
    if value is None:
        return MISSING_DATA_PLACEHOLDER

    return f"{value:.{decimals}f}%"


def format_price(price: Optional[float], decimals: int = 2) -> str:
    """
    Format price with specified decimal places.

    Args:
        price: Price value
        decimals: Number of decimal places

    Returns:
        Formatted price string
    """
    if price is None:
        return MISSING_DATA_PLACEHOLDER

    return f"₹{price:,.{decimals}f}"


def format_change(change: Optional[float], show_sign: bool = True) -> str:
    """
    Format change value with optional sign.

    Args:
        change: Change value
        show_sign: Whether to show + sign for positive values

    Returns:
        Formatted change string
    """
    if change is None:
        return MISSING_DATA_PLACEHOLDER

    sign = "+" if change > 0 and show_sign else ""
    return f"{sign}{change:.2f}"


def format_volume(volume: Optional[int]) -> str:
    """
    Format volume with K/M notation.

    Args:
        volume: Volume value

    Returns:
        Formatted volume string
    """
    return format_number(volume)


def format_oi(oi: Optional[int]) -> str:
    """
    Format Open Interest with K/M notation.

    Args:
        oi: Open Interest value

    Returns:
        Formatted OI string
    """
    return format_number(oi)


def format_strike_label(strike: int, atm_strike: int, step: int) -> str:
    """
    Get label for strike relative to ATM (ATM/OTM/ITM).

    Args:
        strike: Strike price
        atm_strike: ATM strike price
        step: Strike step size

    Returns:
        Strike label (e.g., "ATM", "OTM", "Far OTM")
    """
    diff = strike - atm_strike

    if diff == 0:
        return "ATM"
    elif abs(diff) >= step * 3:  # 3+ strikes away
        return f"Far {'OTM' if diff > 0 else 'ITM'}"
    elif diff > 0:
        return "OTM"
    else:
        return "ITM"


def format_time_ago(seconds: int) -> str:
    """
    Format seconds into human-readable time ago string.

    Args:
        seconds: Number of seconds

    Returns:
        Human-readable string (e.g., "2m ago", "1h ago")
    """
    if seconds < 60:
        return f"{seconds}s ago"
    elif seconds < 3600:
        minutes = seconds // 60
        return f"{minutes}m ago"
    elif seconds < 86400:
        hours = seconds // 3600
        return f"{hours}h ago"
    else:
        days = seconds // 86400
        return f"{days}d ago"


def format_ratio(numerator: float, denominator: float, decimals: int = 2) -> str:
    """
    Format ratio safely handling division by zero.

    Args:
        numerator: Numerator value
        denominator: Denominator value
        decimals: Number of decimal places

    Returns:
        Formatted ratio string
    """
    if denominator == 0:
        return "N/A"

    ratio = numerator / denominator
    return f"{ratio:.{decimals}f}"
