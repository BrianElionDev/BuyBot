import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch
from typing import List, Tuple

from src.bot.trading_engine import TradingEngine


class TestPriceRangeLogic:
    """Test cases for price range handling logic in TradingEngine"""

    def setup_method(self):
        """Set up test fixtures"""
        self.price_service = Mock()
        self.binance_exchange = Mock()
        self.db_manager = Mock()
        self.trading_engine = TradingEngine(
            price_service=self.price_service,
            binance_exchange=self.binance_exchange,
            db_manager=self.db_manager
        )

    def test_single_price_no_range(self):
        """Test handling of single entry price (no range)"""
        entry_prices = [100.0]
        order_type = "MARKET"
        position_type = "LONG"
        current_price = 105.0

        effective_price, reason = self.trading_engine._handle_price_range_logic(
            entry_prices, order_type, position_type, current_price
        )

        assert effective_price == 100.0
        assert "Single entry price provided" in reason

    def test_market_order_with_range(self):
        """Test market order with price range - should execute at current price"""
        entry_prices = [100.0, 110.0]  # Range: 100-110
        order_type = "MARKET"
        position_type = "LONG"
        current_price = 105.0

        effective_price, reason = self.trading_engine._handle_price_range_logic(
            entry_prices, order_type, position_type, current_price
        )

        assert effective_price == 105.0  # Current market price
        assert "Market order - executing at current price" in reason

    def test_limit_order_long_with_range(self):
        """Test limit order for long position with price range"""
        entry_prices = [100.0, 110.0]  # Range: 100-110
        order_type = "LIMIT"
        position_type = "LONG"
        current_price = 105.0

        effective_price, reason = self.trading_engine._handle_price_range_logic(
            entry_prices, order_type, position_type, current_price
        )

        assert effective_price == 100.0  # Lower bound (best buy price)
        assert "Long limit order - placing at lower bound" in reason
        assert "100.00000000-$110.00000000" in reason

    def test_limit_order_short_with_range(self):
        """Test limit order for short position with price range"""
        entry_prices = [100.0, 110.0]  # Range: 100-110
        order_type = "LIMIT"
        position_type = "SHORT"
        current_price = 105.0

        effective_price, reason = self.trading_engine._handle_price_range_logic(
            entry_prices, order_type, position_type, current_price
        )

        assert effective_price == 110.0  # Upper bound (best sell price)
        assert "Short limit order - placing at upper bound" in reason
        assert "100.00000000-$110.00000000" in reason

    def test_limit_order_long_current_price_above_range(self):
        """Test limit order for long when current price is above range"""
        entry_prices = [100.0, 110.0]  # Range: 100-110
        order_type = "LIMIT"
        position_type = "LONG"
        current_price = 115.0  # Above range

        effective_price, reason = self.trading_engine._handle_price_range_logic(
            entry_prices, order_type, position_type, current_price
        )

        assert effective_price == 100.0
        assert "waiting for entry" in reason
        assert "above range" in reason

    def test_limit_order_long_current_price_below_range(self):
        """Test limit order for long when current price is below range"""
        entry_prices = [100.0, 110.0]  # Range: 100-110
        order_type = "LIMIT"
        position_type = "LONG"
        current_price = 95.0  # Below range

        effective_price, reason = self.trading_engine._handle_price_range_logic(
            entry_prices, order_type, position_type, current_price
        )

        assert effective_price == 100.0
        assert "order may fill immediately" in reason
        assert "below range" in reason

    def test_limit_order_short_current_price_below_range(self):
        """Test limit order for short when current price is below range"""
        entry_prices = [100.0, 110.0]  # Range: 100-110
        order_type = "LIMIT"
        position_type = "SHORT"
        current_price = 95.0  # Below range

        effective_price, reason = self.trading_engine._handle_price_range_logic(
            entry_prices, order_type, position_type, current_price
        )

        assert effective_price == 110.0
        assert "waiting for entry" in reason
        assert "below range" in reason

    def test_limit_order_short_current_price_above_range(self):
        """Test limit order for short when current price is above range"""
        entry_prices = [100.0, 110.0]  # Range: 100-110
        order_type = "LIMIT"
        position_type = "SHORT"
        current_price = 115.0  # Above range

        effective_price, reason = self.trading_engine._handle_price_range_logic(
            entry_prices, order_type, position_type, current_price
        )

        assert effective_price == 110.0
        assert "order may fill immediately" in reason
        assert "above range" in reason

    def test_multiple_prices_market_order(self):
        """Test market order with more than 2 prices"""
        entry_prices = [100.0, 110.0, 120.0]  # Multiple prices
        order_type = "MARKET"
        position_type = "LONG"
        current_price = 105.0

        effective_price, reason = self.trading_engine._handle_price_range_logic(
            entry_prices, order_type, position_type, current_price
        )

        assert effective_price == 105.0  # Current market price
        assert "Market order with multiple prices" in reason

    def test_multiple_prices_limit_order_long(self):
        """Test limit order for long with more than 2 prices"""
        entry_prices = [100.0, 110.0, 120.0]  # Multiple prices
        order_type = "LIMIT"
        position_type = "LONG"
        current_price = 105.0

        effective_price, reason = self.trading_engine._handle_price_range_logic(
            entry_prices, order_type, position_type, current_price
        )

        assert effective_price == 100.0  # Lowest price (best buy)
        assert "Long limit order with multiple prices" in reason
        assert "using lowest price" in reason

    def test_multiple_prices_limit_order_short(self):
        """Test limit order for short with more than 2 prices"""
        entry_prices = [100.0, 110.0, 120.0]  # Multiple prices
        order_type = "LIMIT"
        position_type = "SHORT"
        current_price = 105.0

        effective_price, reason = self.trading_engine._handle_price_range_logic(
            entry_prices, order_type, position_type, current_price
        )

        assert effective_price == 120.0  # Highest price (best sell)
        assert "Short limit order with multiple prices" in reason
        assert "using highest price" in reason

    def test_empty_entry_prices(self):
        """Test handling of empty entry prices list"""
        entry_prices = []
        order_type = "MARKET"
        position_type = "LONG"
        current_price = 105.0

        effective_price, reason = self.trading_engine._handle_price_range_logic(
            entry_prices, order_type, position_type, current_price
        )

        assert effective_price == 105.0  # Current market price
        assert "No entry prices provided" in reason

    def test_none_entry_prices(self):
        """Test handling of None entry prices"""
        entry_prices = None
        order_type = "MARKET"
        position_type = "LONG"
        current_price = 105.0

        effective_price, reason = self.trading_engine._handle_price_range_logic(
            entry_prices, order_type, position_type, current_price
        )

        assert effective_price == 105.0  # Current market price
        assert "No entry prices provided" in reason

    def test_unknown_order_type(self):
        """Test handling of unknown order type"""
        entry_prices = [100.0, 110.0]
        order_type = "UNKNOWN"
        position_type = "LONG"
        current_price = 105.0

        effective_price, reason = self.trading_engine._handle_price_range_logic(
            entry_prices, order_type, position_type, current_price
        )

        assert effective_price == 100.0  # First price
        assert "Unknown order type" in reason

    def test_unknown_position_type(self):
        """Test handling of unknown position type"""
        entry_prices = [100.0, 110.0]
        order_type = "LIMIT"
        position_type = "UNKNOWN"
        current_price = 105.0

        effective_price, reason = self.trading_engine._handle_price_range_logic(
            entry_prices, order_type, position_type, current_price
        )

        assert effective_price == 100.0  # First price
        assert "Unknown position type" in reason

    def test_reversed_price_range(self):
        """Test handling when prices are provided in reverse order"""
        entry_prices = [110.0, 100.0]  # Higher price first
        order_type = "LIMIT"
        position_type = "LONG"
        current_price = 105.0

        effective_price, reason = self.trading_engine._handle_price_range_logic(
            entry_prices, order_type, position_type, current_price
        )

        assert effective_price == 100.0  # Should still use lower bound
        assert "100.00000000-$110.00000000" in reason

    def test_identical_prices(self):
        """Test handling when both prices are identical"""
        entry_prices = [100.0, 100.0]  # Same price
        order_type = "LIMIT"
        position_type = "LONG"
        current_price = 105.0

        effective_price, reason = self.trading_engine._handle_price_range_logic(
            entry_prices, order_type, position_type, current_price
        )

        assert effective_price == 100.0
        assert "100.00000000-$100.00000000" in reason


class TestPriceRangeIntegration:
    """Integration tests for price range logic with actual trading engine calls"""

    def test_price_range_logic_integration(self):
        """Test that the price range logic works correctly in isolation"""
        price_service = Mock()
        binance_exchange = Mock()
        db_manager = Mock()

        trading_engine = TradingEngine(
            price_service=price_service,
            binance_exchange=binance_exchange,
            db_manager=db_manager
        )

        # Test the core logic with various scenarios
        test_cases = [
            # (entry_prices, order_type, position_type, expected_price, expected_behavior)
            ([100.0, 110.0], "MARKET", "LONG", None, "market_execution"),
            ([100.0, 110.0], "LIMIT", "LONG", 100.0, "lower_bound"),
            ([100.0, 110.0], "LIMIT", "SHORT", 110.0, "upper_bound"),
            ([110.0, 100.0], "LIMIT", "LONG", 100.0, "reversed_range"),
            ([100.0], "LIMIT", "LONG", 100.0, "single_price"),
        ]

        for entry_prices, order_type, position_type, expected_price, behavior in test_cases:
            effective_price, reason = trading_engine._handle_price_range_logic(
                entry_prices, order_type, position_type, 105.0
            )

            if expected_price is not None:
                assert effective_price == expected_price, f"Failed for {behavior}: expected {expected_price}, got {effective_price}"

            # Verify the reason contains appropriate information
            if behavior == "market_execution":
                assert "Market order" in reason
            elif behavior == "lower_bound":
                assert "lower bound" in reason
            elif behavior == "upper_bound":
                assert "upper bound" in reason
            elif behavior == "reversed_range":
                assert "lower bound" in reason
            elif behavior == "single_price":
                assert "Single entry price" in reason

    def test_edge_cases(self):
        """Test edge cases and error handling"""
        price_service = Mock()
        binance_exchange = Mock()
        db_manager = Mock()

        trading_engine = TradingEngine(
            price_service=price_service,
            binance_exchange=binance_exchange,
            db_manager=db_manager
        )

        # Test with None entry_prices
        effective_price, reason = trading_engine._handle_price_range_logic(
            None, "MARKET", "LONG", 100.0
        )
        assert effective_price == 100.0
        assert "No entry prices provided" in reason

        # Test with empty list
        effective_price, reason = trading_engine._handle_price_range_logic(
            [], "MARKET", "LONG", 100.0
        )
        assert effective_price == 100.0
        assert "No entry prices provided" in reason

        # Test with more than 2 prices
        effective_price, reason = trading_engine._handle_price_range_logic(
            [100.0, 110.0, 120.0], "LIMIT", "LONG", 100.0
        )
        assert effective_price == 100.0
        assert "multiple prices" in reason


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
