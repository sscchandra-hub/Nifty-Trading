"""
Unit tests for formatters utility.
"""
import pytest
from src.utils.formatters import (
    format_number,
    format_percentage,
    format_price,
    format_strike_label,
    format_ratio
)


class TestFormatNumber:
    """Tests for format_number function"""

    def test_format_none(self):
        assert format_number(None) == "—"

    def test_format_small_number(self):
        assert format_number(850) == "850"
        assert format_number(999) == "999"

    def test_format_thousands(self):
        assert format_number(5000) == "5.0K"
        assert format_number(25000) == "25.0K"
        assert format_number(1500) == "1.5K"

    def test_format_millions(self):
        assert format_number(1500000) == "1.50M"
        assert format_number(2750000) == "2.75M"

    def test_format_negative(self):
        assert format_number(-25000) == "-25.0K"
        assert format_number(-1500000) == "-1.50M"


class TestFormatPercentage:
    """Tests for format_percentage function"""

    def test_format_none(self):
        assert format_percentage(None) == "—"

    def test_format_positive(self):
        assert format_percentage(15.5) == "15.50%"

    def test_format_negative(self):
        assert format_percentage(-5.25) == "-5.25%"

    def test_format_zero(self):
        assert format_percentage(0.0) == "0.00%"

    def test_custom_decimals(self):
        assert format_percentage(15.567, decimals=1) == "15.6%"


class TestFormatPrice:
    """Tests for format_price function"""

    def test_format_none(self):
        assert format_price(None) == "—"

    def test_format_positive(self):
        assert format_price(19250.50) == "₹19,250.50"

    def test_format_large(self):
        assert format_price(1000000.00) == "₹1,000,000.00"


class TestFormatStrikeLabel:
    """Tests for format_strike_label function"""

    def test_atm_strike(self):
        assert format_strike_label(19250, 19250, 50) == "ATM"

    def test_otm_strike(self):
        assert format_strike_label(19300, 19250, 50) == "OTM"

    def test_itm_strike(self):
        assert format_strike_label(19200, 19250, 50) == "ITM"

    def test_far_otm(self):
        assert format_strike_label(19400, 19250, 50) == "Far OTM"

    def test_far_itm(self):
        assert format_strike_label(19100, 19250, 50) == "Far ITM"


class TestFormatRatio:
    """Tests for format_ratio function"""

    def test_normal_ratio(self):
        assert format_ratio(10, 5) == "2.00"

    def test_division_by_zero(self):
        assert format_ratio(10, 0) == "N/A"

    def test_custom_decimals(self):
        assert format_ratio(10, 3, decimals=3) == "3.333"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
