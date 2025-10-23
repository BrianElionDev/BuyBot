"""
Validation utilities for the trading bot.

This module contains utility functions for validating various trading parameters
including symbols, prices, orders, and other trading-related data.
"""

import logging
from typing import Dict, Any, Optional, Tuple

logger = logging.getLogger(__name__)


class ValidationUtils:
    """
    Utility class for validation operations.
    """

    @staticmethod
    def validate_symbol_support(
        trading_pair: str,
        exchange_info: Dict[str, Any]
    ) -> Tuple[bool, Optional[str]]:
        """
        Validate if a symbol is supported and in TRADING status.
        This method now serves as a fallback for when dynamic validation is not available.

        Args:
            trading_pair: The trading pair to validate
            exchange_info: Exchange information from exchange API

        Returns:
            Tuple of (is_valid, error_message)
        """
        if not exchange_info:
            return False, "No exchange info available"

        symbol_info = next(
            (s for s in exchange_info.get('symbols', []) if s['symbol'] == trading_pair),
            None
        )

        if not symbol_info:
            return False, f"Symbol {trading_pair} not found in exchange info"

        if symbol_info.get('status') != 'TRADING':
            return False, f"Symbol {trading_pair} is not in TRADING status: {symbol_info.get('status')}"

        return True, None

    @staticmethod
    async def validate_symbol_support_dynamic(
        trading_pair: str,
        exchange: str,
        exchange_client
    ) -> Tuple[bool, Optional[str]]:
        """
        Validate if a symbol is supported using dynamic validation.

        Args:
            trading_pair: The trading pair to validate
            exchange: Exchange name ('binance' or 'kucoin')
            exchange_client: Exchange client instance

        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            from src.core.dynamic_symbol_validator import dynamic_validator

            is_supported = await dynamic_validator.is_symbol_supported(
                symbol=trading_pair,
                exchange=exchange,
                exchange_client=exchange_client,
                trading_type='futures'
            )

            if is_supported:
                return True, None
            else:
                return False, f"Symbol {trading_pair} not supported or not trading on {exchange}"

        except Exception as e:
            logger.error(f"Error in dynamic symbol validation for {trading_pair}: {e}")
            return False, f"Error validating symbol: {str(e)}"

    @staticmethod
    def validate_price_threshold(
        signal_price: float,
        market_price: float,
        threshold: float = 0.1
    ) -> Tuple[bool, Optional[str]]:
        """
        Validate if a price is within acceptable threshold of market price.

        Args:
            signal_price: The signal price to validate
            market_price: The current market price
            threshold: The acceptable threshold (default 10%)

        Returns:
            Tuple of (is_valid, error_message)
        """
        if not market_price or market_price <= 0:
            return False, "Invalid market price"

        if not signal_price or signal_price <= 0:
            return False, "Invalid signal price"

        price_diff = abs(signal_price - market_price) / market_price

        if price_diff > threshold:
            return False, f"Price difference {price_diff*100:.2f}% exceeds threshold {threshold*100}%"

        return True, None

    @staticmethod
    def validate_order_book_depth(
        order_book: Dict[str, Any],
        trading_pair: str
    ) -> Tuple[bool, Optional[str]]:
        """
        Validate if order book has sufficient depth.

        Args:
            order_book: The order book data
            trading_pair: The trading pair for error messages

        Returns:
            Tuple of (is_valid, error_message)
        """
        if not order_book:
            return False, f"No order book data for {trading_pair}"

        if not order_book.get('bids') or not order_book.get('asks'):
            return False, f"Insufficient order book depth for {trading_pair}"

        return True, None

    @staticmethod
    def validate_trade_amount(
        trade_amount: float,
        min_amount: float = 10.0,
        max_amount: float = 1000.0
    ) -> Tuple[bool, Optional[str]]:
        """
        Validate if trade amount is within acceptable range.

        Args:
            trade_amount: The trade amount to validate
            min_amount: Minimum acceptable amount
            max_amount: Maximum acceptable amount

        Returns:
            Tuple of (is_valid, error_message)
        """
        if trade_amount < min_amount:
            return False, f"Trade amount {trade_amount} below minimum {min_amount}"

        if trade_amount > max_amount:
            return False, f"Trade amount {trade_amount} above maximum {max_amount}"

        return True, None

    @staticmethod
    def validate_position_type(position_type: str) -> Tuple[bool, Optional[str]]:
        """
        Validate if position type is supported.

        Args:
            position_type: The position type to validate

        Returns:
            Tuple of (is_valid, error_message)
        """
        valid_types = ['LONG', 'SHORT']

        if position_type.upper() not in valid_types:
            return False, f"Invalid position type: {position_type}. Must be one of {valid_types}"

        return True, None

    @staticmethod
    def validate_order_type(order_type: str) -> Tuple[bool, Optional[str]]:
        """
        Validate if order type is supported.

        Args:
            order_type: The order type to validate

        Returns:
            Tuple of (is_valid, error_message)
        """
        valid_types = ['MARKET', 'LIMIT']

        if order_type.upper() not in valid_types:
            return False, f"Invalid order type: {order_type}. Must be one of {valid_types}"

        return True, None
