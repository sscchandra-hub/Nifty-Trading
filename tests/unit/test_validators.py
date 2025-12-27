"""
Unit tests for validators utility.
"""
import pytest
from datetime import datetime, time as dt_time
from src.utils.validators import (
    is_valid_strike,
    is_valid_option_type,
    is_valid_price,
    is_valid_volume,
    is_liquid_option,
    is_valid_percentage,
    is_valid_token,
    sanitize_index_name
)


class TestIsValidStrike:
    """Tests for is_valid_strike function"""

    def test_valid_strike(self):
        assert is_valid_strike(19250, 50) is True
        assert is_valid_strike(44100, 100) is True

    def test_invalid_strike(self):
        assert is_valid_strike(19255, 50) is False
        assert is_valid_strike(44125, 100) is False


class TestIsValidOptionType:
    """Tests for is_valid_option_type function"""

    def test_valid_call(self):
        assert is_valid_option_type("CE") is True

    def test_valid_put(self):
        assert is_valid_option_type("PE") is True

    def test_invalid_type(self):
        assert is_valid_option_type("CALL") is False
        assert is_valid_option_type("") is False


class TestIsValidPrice:
    """Tests for is_valid_price function"""

    def test_valid_price(self):
        assert is_valid_price(100.50) is True
        assert is_valid_price(0.01) is True

    def test_invalid_price(self):
        assert is_valid_price(0) is False
        assert is_valid_price(-10) is False
        assert is_valid_price(None) is False


class TestIsValidVolume:
    """Tests for is_valid_volume function"""

    def test_valid_volume(self):
        assert is_valid_volume(1000) is True
        assert is_valid_volume(0) is True

    def test_invalid_volume(self):
        assert is_valid_volume(-100) is False
        assert is_valid_volume(None) is False


class TestIsLiquidOption:
    """Tests for is_liquid_option function"""

    def test_liquid_option(self):
        assert is_liquid_option(
            oi=150000,
            volume=15000,
            min_oi=100000,
            min_volume=10000
        ) is True

    def test_low_oi(self):
        assert is_liquid_option(
            oi=50000,
            volume=15000,
            min_oi=100000,
            min_volume=10000
        ) is False

    def test_low_volume(self):
        assert is_liquid_option(
            oi=150000,
            volume=5000,
            min_oi=100000,
            min_volume=10000
        ) is False

    def test_with_spread_check(self):
        assert is_liquid_option(
            oi=150000,
            volume=15000,
            min_oi=100000,
            min_volume=10000,
            bid_ask_spread=1.5,
            max_spread=2.0
        ) is True

    def test_high_spread(self):
        assert is_liquid_option(
            oi=150000,
            volume=15000,
            min_oi=100000,
            min_volume=10000,
            bid_ask_spread=3.0,
            max_spread=2.0
        ) is False


class TestIsValidPercentage:
    """Tests for is_valid_percentage function"""

    def test_valid_percentage(self):
        assert is_valid_percentage(50) is True
        assert is_valid_percentage(0) is True
        assert is_valid_percentage(100) is True

    def test_invalid_percentage(self):
        assert is_valid_percentage(-10) is False
        assert is_valid_percentage(150) is False


class TestIsValidToken:
    """Tests for is_valid_token function"""

    def test_valid_token(self):
        assert is_valid_token(256265) is True
        assert is_valid_token("256265") is True

    def test_invalid_token(self):
        assert is_valid_token(0) is False
        assert is_valid_token(-100) is False
        assert is_valid_token("abc") is False
        assert is_valid_token(None) is False


class TestSanitizeIndexName:
    """Tests for sanitize_index_name function"""

    def test_simple_name(self):
        assert sanitize_index_name("NIFTY") == "NIFTY"

    def test_with_spaces(self):
        assert sanitize_index_name("NIFTY 50") == "NIFTY_50"

    def test_with_special_chars(self):
        assert sanitize_index_name("NIFTY OIL & GAS") == "NIFTY_OIL_GAS"

    def test_lowercase(self):
        assert sanitize_index_name("nifty bank") == "NIFTY_BANK"

    def test_with_whitespace(self):
        assert sanitize_index_name("  NIFTY  ") == "NIFTY"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
