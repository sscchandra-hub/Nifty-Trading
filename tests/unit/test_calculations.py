"""
Unit tests for calculations utility.
"""
import pytest
from src.utils.calculations import (
    calculate_atm_strike,
    calculate_strike_distance,
    get_surrounding_strikes,
    calculate_percentage_change,
    calculate_spike_ratio,
    calculate_ce_pe_ratio,
    is_within_range
)


class TestCalculateAtmStrike:
    """Tests for calculate_atm_strike function"""

    def test_nifty_atm(self):
        atm, step = calculate_atm_strike(19247.50, "NIFTY")
        assert atm == 19250
        assert step == 50

    def test_banknifty_atm(self):
        atm, step = calculate_atm_strike(44123.25, "BANKNIFTY")
        assert atm == 44100
        assert step == 100

    def test_finnifty_atm(self):
        atm, step = calculate_atm_strike(19785.00, "FINNIFTY")
        assert atm == 19800
        assert step == 50

    def test_unknown_index(self):
        atm, step = calculate_atm_strike(10000.00, "UNKNOWN")
        assert atm == 10000
        assert step == 50  # Default step


class TestCalculateStrikeDistance:
    """Tests for calculate_strike_distance function"""

    def test_positive_distance(self):
        assert calculate_strike_distance(19300, 19250) == 50

    def test_negative_distance(self):
        assert calculate_strike_distance(19200, 19250) == -50

    def test_zero_distance(self):
        assert calculate_strike_distance(19250, 19250) == 0


class TestGetSurroundingStrikes:
    """Tests for get_surrounding_strikes function"""

    def test_default_count(self):
        strikes = get_surrounding_strikes(19250, 50, count=2)
        assert strikes == [19150, 19200, 19250, 19300, 19350]

    def test_single_strike(self):
        strikes = get_surrounding_strikes(19250, 50, count=0)
        assert strikes == [19250]

    def test_large_count(self):
        strikes = get_surrounding_strikes(19250, 50, count=3)
        assert len(strikes) == 7
        assert strikes[0] == 19100
        assert strikes[-1] == 19400


class TestCalculatePercentageChange:
    """Tests for calculate_percentage_change function"""

    def test_positive_change(self):
        assert calculate_percentage_change(110, 100) == 10.0

    def test_negative_change(self):
        assert calculate_percentage_change(95, 100) == -5.0

    def test_zero_change(self):
        assert calculate_percentage_change(100, 100) == 0.0

    def test_division_by_zero(self):
        assert calculate_percentage_change(100, 0) is None

    def test_none_input(self):
        assert calculate_percentage_change(100, None) is None


class TestCalculateSpikeRatio:
    """Tests for calculate_spike_ratio function"""

    def test_normal_spike(self):
        assert calculate_spike_ratio(5000, 1000) == 5.0

    def test_no_spike(self):
        assert calculate_spike_ratio(1000, 1000) == 1.0

    def test_zero_average(self):
        assert calculate_spike_ratio(5000, 0) == 0.0


class TestCalculateCePeRatio:
    """Tests for calculate_ce_pe_ratio function"""

    def test_normal_ratio(self):
        assert calculate_ce_pe_ratio(150000, 100000) == 1.5

    def test_zero_pe(self):
        assert calculate_ce_pe_ratio(150000, 0) is None


class TestIsWithinRange:
    """Tests for is_within_range function"""

    def test_within_range(self):
        assert is_within_range(102, 100, 0.05) is True

    def test_outside_range(self):
        assert is_within_range(110, 100, 0.05) is False

    def test_exact_match(self):
        assert is_within_range(100, 100, 0.05) is True

    def test_boundary_lower(self):
        assert is_within_range(95, 100, 0.05) is True

    def test_boundary_upper(self):
        assert is_within_range(105, 100, 0.05) is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
