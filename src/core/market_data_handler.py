"""
Market data handling utilities for the trading bot.

This module contains core functions for handling market data operations
including price fetching, order book operations, and exchange information.
"""

import logging
from typing import Dict, Any, Optional, Tuple

logger = logging.getLogger(__name__)


class MarketDataHandler:
    """
    Core class for handling market data operations.
    """

    def __init__(self, binance_exchange, price_service):
        """
        Initialize the market data handler.

        Args:
            binance_exchange: The Binance exchange instance
            price_service: The price service instance
        """
        self.binance_exchange = binance_exchange
        self.price_service = price_service

    async def get_current_market_price(self, coin_symbol: str) -> Optional[float]:
        """
        Get the current market price for a coin symbol.

        Args:
            coin_symbol: The trading symbol (e.g., 'BTC')

        Returns:
            Current market price or None if failed
        """
        try:
            current_price = await self.binance_exchange.get_futures_mark_price(f'{coin_symbol.upper()}USDT')
            if current_price:
                logger.debug(f"Current market price for {coin_symbol}: {current_price}")
                return current_price
            else:
                logger.error(f"Failed to get price for {coin_symbol}")
                return None
        except Exception as e:
            logger.error(f"Error getting market price for {coin_symbol}: {e}")
            return None

    async def get_order_book_data(self, trading_pair: str) -> Optional[Dict[str, Any]]:
        """
        Get order book data for a trading pair.

        Args:
            trading_pair: The trading pair (e.g., 'BTCUSDT')

        Returns:
            Order book data or None if failed
        """
        try:
            if hasattr(self.binance_exchange, 'get_order_book'):
                order_book = await self.binance_exchange.get_order_book(trading_pair)
                if order_book and order_book.get('bids') and order_book.get('asks'):
                    logger.debug(f"Order book data retrieved for {trading_pair}")
                    return order_book
                else:
                    logger.warning(f"No order book depth for {trading_pair}")
                    return None
            else:
                logger.warning("Order book method not implemented in exchange")
                return None
        except Exception as e:
            logger.error(f"Error getting order book for {trading_pair}: {e}")
            return None

    async def get_exchange_info(self) -> Optional[Dict[str, Any]]:
        """
        Get exchange information from Binance.

        Returns:
            Exchange information or None if failed
        """
        try:
            exchange_info = await self.binance_exchange.get_exchange_info()
            if exchange_info:
                logger.debug("Exchange info retrieved successfully")
                return exchange_info
            else:
                logger.error("Failed to retrieve exchange info")
                return None
        except Exception as e:
            logger.error(f"Error getting exchange info: {e}")
            return None

    async def get_symbol_filters(self, trading_pair: str) -> Optional[Dict[str, Any]]:
        """
        Get symbol filters for a trading pair.

        Args:
            trading_pair: The trading pair (e.g., 'BTCUSDT')

        Returns:
            Symbol filters or None if failed
        """
        try:
            filters = await self.binance_exchange.get_futures_symbol_filters(trading_pair)
            if filters:
                logger.debug(f"Symbol filters retrieved for {trading_pair}")
                return filters
            else:
                logger.error(f"Could not retrieve symbol filters for {trading_pair}")
                return None
        except Exception as e:
            logger.error(f"Error getting symbol filters for {trading_pair}: {e}")
            return None

    async def validate_symbol_support(self, trading_pair: str) -> Tuple[bool, Optional[str]]:
        """
        Validate if a symbol is supported and in TRADING status.

        Args:
            trading_pair: The trading pair to validate

        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            # Check if symbol is supported
            is_supported = await self.binance_exchange.is_futures_symbol_supported(trading_pair)
            if not is_supported:
                return False, f"Symbol {trading_pair} not supported or not trading on Binance Futures."

            # Check if symbol is in TRADING status
            exchange_info = await self.get_exchange_info()
            if exchange_info:
                from src.bot.utils.validation_utils import ValidationUtils
                return ValidationUtils.validate_symbol_support(trading_pair, exchange_info)
            else:
                return False, f"Could not retrieve exchange info for {trading_pair}"

        except Exception as e:
            logger.error(f"Error validating symbol support for {trading_pair}: {e}")
            return False, f"Error validating symbol: {str(e)}"

    async def validate_price_threshold(
        self,
        signal_price: float,
        coin_symbol: str,
        threshold: float = 0.1
    ) -> Tuple[bool, Optional[str]]:
        """
        Validate if a price is within acceptable threshold of market price.

        Args:
            signal_price: The signal price to validate
            coin_symbol: The coin symbol
            threshold: The acceptable threshold (default 10%)

        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            market_price = await self.get_current_market_price(coin_symbol)
            if not market_price:
                return False, f"Failed to get market price for {coin_symbol}"

            from src.bot.utils.validation_utils import ValidationUtils
            return ValidationUtils.validate_price_threshold(signal_price, market_price, threshold)

        except Exception as e:
            logger.error(f"Error validating price threshold for {coin_symbol}: {e}")
            return False, f"Error validating price: {str(e)}"

    async def validate_order_book_depth(self, trading_pair: str) -> Tuple[bool, Optional[str]]:
        """
        Validate if order book has sufficient depth.

        Args:
            trading_pair: The trading pair to validate

        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            order_book = await self.get_order_book_data(trading_pair)
            from src.bot.utils.validation_utils import ValidationUtils
            if order_book is None:
                return False, f"No order book data available for {trading_pair}"
            return ValidationUtils.validate_order_book_depth(order_book, trading_pair)

        except Exception as e:
            logger.error(f"Error validating order book depth for {trading_pair}: {e}")
            return False, f"Error validating order book: {str(e)}"
