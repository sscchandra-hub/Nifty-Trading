"""
Trading calculations and mathematical utilities.
"""
from typing import Tuple, Optional, List
from src.config.settings import TradingConfig


def calculate_atm_strike(spot_price: float, index_name: str) -> Tuple[int, int]:
    """
    Calculate ATM (At The Money) strike based on index name and spot price.

    Args:
        spot_price: Current spot price of the index
        index_name: Name of the index (e.g., "NIFTY", "BANKNIFTY")

    Returns:
        Tuple of (atm_strike, step_size)

    Example:
        >>> calculate_atm_strike(19247.50, "NIFTY")
        (19250, 50)
        >>> calculate_atm_strike(44123.25, "BANKNIFTY")
        (44100, 100)
    """
    step = TradingConfig.STRIKE_STEPS.get(
        index_name,
        TradingConfig.DEFAULT_STRIKE_STEP
    )
    atm_strike = round(spot_price / step) * step
    return atm_strike, step


def calculate_strike_distance(strike: int, atm_strike: int) -> int:
    """
    Calculate distance from ATM strike.

    Args:
        strike: Strike price
        atm_strike: ATM strike price

    Returns:
        Distance in points (can be negative for ITM)
    """
    return strike - atm_strike


def get_surrounding_strikes(
    atm_strike: int,
    step: int,
    count: int = 5
) -> List[int]:
    """
    Get list of strikes surrounding ATM.

    Args:
        atm_strike: ATM strike price
        step: Strike step size
        count: Number of strikes on each side (default 5)

    Returns:
        List of strikes [ATM-5*step, ..., ATM, ..., ATM+5*step]

    Example:
        >>> get_surrounding_strikes(19250, 50, 2)
        [19150, 19200, 19250, 19300, 19350]
    """
    strikes = []
    for i in range(-count, count + 1):
        strikes.append(atm_strike + i * step)
    return strikes


def calculate_percentage_change(
    current: float,
    previous: float
) -> Optional[float]:
    """
    Calculate percentage change.

    Args:
        current: Current value
        previous: Previous value

    Returns:
        Percentage change (e.g., 0.15 for 15% increase)
        Returns None if previous is 0 or None

    Example:
        >>> calculate_percentage_change(110, 100)
        10.0
        >>> calculate_percentage_change(95, 100)
        -5.0
    """
    if previous is None or previous == 0:
        return None

    return ((current - previous) / previous) * 100


def calculate_delta(
    current: float,
    previous: float
) -> float:
    """
    Calculate absolute delta (difference).

    Args:
        current: Current value
        previous: Previous value

    Returns:
        Absolute difference
    """
    return current - previous


def calculate_spike_ratio(
    current_volume: int,
    avg_volume: float
) -> float:
    """
    Calculate volume spike ratio.

    Args:
        current_volume: Current volume
        avg_volume: Average volume

    Returns:
        Spike ratio (e.g., 3.5 means 3.5x average)
    """
    if avg_volume == 0:
        return 0.0

    return current_volume / avg_volume


def calculate_ce_pe_ratio(
    ce_value: float,
    pe_value: float
) -> Optional[float]:
    """
    Calculate CE/PE ratio.

    Args:
        ce_value: Call value
        pe_value: Put value

    Returns:
        CE/PE ratio or None if PE is 0
    """
    if pe_value == 0:
        return None

    return ce_value / pe_value


def calculate_pcr(
    put_oi: int,
    call_oi: int
) -> Optional[float]:
    """
    Calculate Put-Call Ratio (PCR).

    Args:
        put_oi: Put Open Interest
        call_oi: Call Open Interest

    Returns:
        PCR value or None if call OI is 0
    """
    if call_oi == 0:
        return None

    return put_oi / call_oi


def is_within_range(
    value: float,
    target: float,
    tolerance: float
) -> bool:
    """
    Check if value is within tolerance of target.

    Args:
        value: Value to check
        target: Target value
        tolerance: Tolerance as decimal (e.g., 0.05 for 5%)

    Returns:
        True if within range
    """
    lower = target * (1 - tolerance)
    upper = target * (1 + tolerance)
    return lower <= value <= upper


def calculate_momentum_score(
    delta_1min: float,
    delta_5min: Optional[float],
    acceleration_threshold: float = 1.5
) -> Tuple[str, str]:
    """
    Calculate momentum signal based on deltas.

    Args:
        delta_1min: 1-minute delta
        delta_5min: 5-minute delta (can be None)
        acceleration_threshold: Threshold for acceleration

    Returns:
        Tuple of (signal, color)
    """
    if delta_5min is None:
        return "⏳ BUILDING", "#888888"

    if abs(delta_1min) < 1000:
        return "➡️ STEADY", "#666666"

    # Check for acceleration
    if abs(delta_5min) > 0:
        ratio = abs(delta_1min * 5) / abs(delta_5min)

        if ratio >= acceleration_threshold * 2:
            if delta_1min > 0:
                return "🚀 SURGING UP", "#00ff00"
            else:
                return "📉 CRASHING DOWN", "#ff0000"
        elif ratio >= acceleration_threshold:
            if delta_1min > 0:
                return "🔥 ACCELERATING UP", "#00cc00"
            else:
                return "⚠️ ACCELERATING DOWN", "#ff4444"

    # Steady momentum
    if delta_1min > 0:
        return "✅ STEADY UP", "#00aa00"
    else:
        return "🔴 STEADY DOWN", "#aa0000"


def calculate_bid_ask_spread_percentage(
    bid: float,
    ask: float
) -> Optional[float]:
    """
    Calculate bid-ask spread as percentage.

    Args:
        bid: Bid price
        ask: Ask price

    Returns:
        Spread percentage or None if bid is 0
    """
    if bid == 0 or bid is None or ask is None:
        return None

    return ((ask - bid) / bid) * 100
