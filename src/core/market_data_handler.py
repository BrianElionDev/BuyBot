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

    def __init__(self, exchange, price_service):
        """
        Initialize the market data handler.

        Args:
            exchange: The exchange instance (Binance, KuCoin, etc.)
            price_service: The price service instance
        """
        self.exchange = exchange
        self.price_service = price_service

    def _get_trading_pair(self, coin_symbol: str) -> str:
        """
        Get trading pair format based on exchange type.

        Args:
            coin_symbol: The coin symbol (e.g., 'BTC')

        Returns:
            Trading pair in exchange format
        """
        # Check if exchange has a method to get trading pair format
        if hasattr(self.exchange, 'get_futures_trading_pair'):
            return self.exchange.get_futures_trading_pair(coin_symbol)
        elif hasattr(self.exchange, 'get_trading_pair'):
            return self.exchange.get_trading_pair(coin_symbol)
        else:
            # Default format for most exchanges
            return f"{coin_symbol.upper()}USDT"

    async def get_current_market_price(self, coin_symbol: str) -> Optional[float]:
        """
        Get the current market price for a coin symbol.

        Args:
            coin_symbol: The trading symbol (e.g., 'BTC')

        Returns:
            Current market price or None if failed
        """
        try:
            # Try to get mark price first (for futures)
            if hasattr(self.exchange, 'get_mark_price'):
                trading_pair = self._get_trading_pair(coin_symbol)
                current_price = await self.exchange.get_mark_price(trading_pair)
                if current_price:
                    logger.info(f"Current market price for {coin_symbol}: {current_price}")
                    return current_price

            # Fallback to price service
            current_price = await self.price_service.get_coin_price(coin_symbol)
            if current_price:
                logger.info(f"Current market price for {coin_symbol}: {current_price}")
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
            if hasattr(self.exchange, 'get_order_book'):
                order_book = await self.exchange.get_order_book(trading_pair)
                if order_book and order_book.get('bids') and order_book.get('asks'):
                    logger.info(f"Order book data retrieved for {trading_pair}")
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
        Get exchange information.

        Returns:
            Exchange information or None if failed
        """
        try:
            if hasattr(self.exchange, 'get_exchange_info'):
                exchange_info = await self.exchange.get_exchange_info()
                if exchange_info:
                    logger.info("Exchange info retrieved successfully")
                    return exchange_info
                else:
                    logger.error("Failed to retrieve exchange info")
                    return None
            else:
                logger.warning("Exchange info method not implemented")
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
            if hasattr(self.exchange, 'get_futures_symbol_filters'):
                filters = await self.exchange.get_futures_symbol_filters(trading_pair)
                if filters:
                    logger.info(f"Symbol filters retrieved for {trading_pair}")
                    return filters
                else:
                    logger.error(f"Could not retrieve symbol filters for {trading_pair}")
                    return None
            else:
                logger.warning("Symbol filters method not implemented")
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
            if hasattr(self.exchange, 'is_futures_symbol_supported'):
                is_supported = await self.exchange.is_futures_symbol_supported(trading_pair)
                if not is_supported:
                    return False, f"Symbol {trading_pair} not supported or not trading on futures."

            # Check if symbol is in TRADING status
            exchange_info = await self.get_exchange_info()
            if exchange_info:
                from src.bot.utils.validation_utils import ValidationUtils
                return ValidationUtils.validate_symbol_support(trading_pair, exchange_info)
            else:
                # If no exchange info available, just check if symbol is supported
                if hasattr(self.exchange, 'is_futures_symbol_supported'):
                    is_supported = await self.exchange.is_futures_symbol_supported(trading_pair)
                    return is_supported, None if is_supported else f"Symbol {trading_pair} not supported"
                else:
                    return True, None  # Assume supported if no validation available

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
