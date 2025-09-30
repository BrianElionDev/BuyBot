"""
Tests for PriceRangeHandler utility.
"""

import pytest
from src.bot.utils.price_range_handler import PriceRangeHandler
from src.core.constants import ORDER_TYPE_MARKET, ORDER_TYPE_LIMIT, POSITION_TYPE_LONG, POSITION_TYPE_SHORT


class TestPriceRangeHandler:
    """Test cases for PriceRangeHandler."""

    def test_no_entry_prices(self):
        """Test handling when no entry prices are provided."""
        result_price, reason = PriceRangeHandler.handle_price_range_logic(
            None, ORDER_TYPE_MARKET, POSITION_TYPE_LONG, 100.0
        )
        assert result_price == 100.0
        assert "No entry prices provided" in reason

    def test_empty_entry_prices(self):
        """Test handling when empty entry prices list is provided."""
        result_price, reason = PriceRangeHandler.handle_price_range_logic(
            [], ORDER_TYPE_MARKET, POSITION_TYPE_LONG, 100.0
        )
        assert result_price == 100.0
        assert "No entry prices provided" in reason

    def test_single_entry_price(self):
        """Test handling of single entry price."""
        result_price, reason = PriceRangeHandler.handle_price_range_logic(
            [95.0], ORDER_TYPE_MARKET, POSITION_TYPE_LONG, 100.0
        )
        assert result_price == 95.0
        assert "Single entry price provided" in reason

    def test_market_order_long_within_range(self):
        """Test market order for long position when current price is within range."""
        result_price, reason = PriceRangeHandler.handle_price_range_logic(
            [90.0, 110.0], ORDER_TYPE_MARKET, POSITION_TYPE_LONG, 100.0
        )
        assert result_price == 100.0
        assert "Market order - executing at current price" in reason
        assert "within range" in reason

    def test_market_order_long_above_range(self):
        """Test market order for long position when current price is above range."""
        result_price, reason = PriceRangeHandler.handle_price_range_logic(
            [90.0, 110.0], ORDER_TYPE_MARKET, POSITION_TYPE_LONG, 120.0
        )
        assert result_price is None
        assert "Market order REJECTED" in reason
        assert "above range" in reason

    def test_market_order_short_within_range(self):
        """Test market order for short position when current price is within range."""
        result_price, reason = PriceRangeHandler.handle_price_range_logic(
            [90.0, 110.0], ORDER_TYPE_MARKET, POSITION_TYPE_SHORT, 100.0
        )
        assert result_price == 100.0
        assert "Market order - executing at current price" in reason
        assert "within range" in reason

    def test_market_order_short_below_range(self):
        """Test market order for short position when current price is below range."""
        result_price, reason = PriceRangeHandler.handle_price_range_logic(
            [90.0, 110.0], ORDER_TYPE_MARKET, POSITION_TYPE_SHORT, 80.0
        )
        assert result_price is None
        assert "Market order REJECTED" in reason
        assert "below range" in reason

    def test_limit_order_long(self):
        """Test limit order for long position."""
        result_price, reason = PriceRangeHandler.handle_price_range_logic(
            [90.0, 110.0], ORDER_TYPE_LIMIT, POSITION_TYPE_LONG, 100.0
        )
        assert result_price == 110.0  # Upper bound for long
        assert "Long limit order" in reason
        assert "upper bound" in reason

    def test_limit_order_short(self):
        """Test limit order for short position."""
        result_price, reason = PriceRangeHandler.handle_price_range_logic(
            [90.0, 110.0], ORDER_TYPE_LIMIT, POSITION_TYPE_SHORT, 100.0
        )
        assert result_price == 90.0  # Lower bound for short
        assert "Short limit order" in reason
        assert "lower bound" in reason

    def test_multiple_prices_market_order(self):
        """Test market order with multiple entry prices."""
        result_price, reason = PriceRangeHandler.handle_price_range_logic(
            [90.0, 95.0, 100.0, 105.0, 110.0], ORDER_TYPE_MARKET, POSITION_TYPE_LONG, 102.0
        )
        assert result_price == 102.0
        assert "Market order with multiple prices" in reason

    def test_multiple_prices_limit_order_long(self):
        """Test limit order for long position with multiple prices."""
        result_price, reason = PriceRangeHandler.handle_price_range_logic(
            [90.0, 95.0, 100.0, 105.0, 110.0], ORDER_TYPE_LIMIT, POSITION_TYPE_LONG, 102.0
        )
        assert result_price == 90.0  # Minimum price for long
        assert "Long limit order with multiple prices" in reason
        assert "lowest price" in reason

    def test_multiple_prices_limit_order_short(self):
        """Test limit order for short position with multiple prices."""
        result_price, reason = PriceRangeHandler.handle_price_range_logic(
            [90.0, 95.0, 100.0, 105.0, 110.0], ORDER_TYPE_LIMIT, POSITION_TYPE_SHORT, 102.0
        )
        assert result_price == 110.0  # Maximum price for short
        assert "Short limit order with multiple prices" in reason
        assert "highest price" in reason

    def test_unknown_position_type(self):
        """Test handling of unknown position type."""
        result_price, reason = PriceRangeHandler.handle_price_range_logic(
            [90.0, 110.0], ORDER_TYPE_MARKET, "UNKNOWN", 100.0
        )
        assert result_price == 100.0
        assert "unknown position type" in reason

    def test_unknown_order_type(self):
        """Test handling of unknown order type."""
        result_price, reason = PriceRangeHandler.handle_price_range_logic(
            [90.0, 110.0], "UNKNOWN", POSITION_TYPE_LONG, 100.0
        )
        assert result_price == 90.0  # First price as fallback
        assert "Unknown order type" in reason

    def test_price_range_context_current_above(self):
        """Test price range context when current price is above range."""
        result_price, reason = PriceRangeHandler.handle_price_range_logic(
            [90.0, 110.0], ORDER_TYPE_LIMIT, POSITION_TYPE_LONG, 120.0
        )
        assert result_price == 110.0
        assert "Current price 120.0 above range" in reason
        assert "waiting for entry" in reason

    def test_price_range_context_current_below(self):
        """Test price range context when current price is below range."""
        result_price, reason = PriceRangeHandler.handle_price_range_logic(
            [90.0, 110.0], ORDER_TYPE_LIMIT, POSITION_TYPE_LONG, 80.0
        )
        assert result_price == 110.0
        assert "Current price 80.0 below range" in reason
        assert "order may fill immediately" in reason

    def test_price_range_context_current_within(self):
        """Test price range context when current price is within range."""
        result_price, reason = PriceRangeHandler.handle_price_range_logic(
            [90.0, 110.0], ORDER_TYPE_LIMIT, POSITION_TYPE_LONG, 100.0
        )
        assert result_price == 110.0
        assert "Current price 100.0 within range" in reason
