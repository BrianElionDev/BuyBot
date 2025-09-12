import logging
import asyncio
from typing import Optional, List
from .price_models import PriceServiceConfig, PriceData, MarketData
from .price_cache import PriceCache
from .price_validator import PriceValidator

logger = logging.getLogger(__name__)


class PriceService:
    """Core price service for cryptocurrency price data using Binance API"""

    def __init__(self, config: Optional[PriceServiceConfig] = None, binance_exchange=None):
        """Initialize the price service"""
        self.config = config or PriceServiceConfig()
        self.binance_exchange = binance_exchange
        self.cache = PriceCache(self.config)
        self.validator = PriceValidator()
        self._last_call = 0

    async def _rate_limit(self) -> None:
        """Apply rate limiting for API calls"""
        elapsed = asyncio.get_event_loop().time() - self._last_call
        if elapsed < self.config.rate_limit_delay:
            await asyncio.sleep(self.config.rate_limit_delay - elapsed)
        self._last_call = asyncio.get_event_loop().time()

    def _get_binance_symbol(self, symbol: str) -> str:
        """
        Convert symbol to Binance trading pair format

        Args:
            symbol: Trading symbol (e.g., 'BTC')

        Returns:
            Binance trading pair (e.g., 'BTCUSDT')
        """
        return f"{symbol.upper()}USDT"

    async def get_price(self, symbol: str) -> Optional[float]:
        """
        Get price for a specific symbol using Binance API

        Args:
            symbol: Trading symbol (e.g., 'BTC')

        Returns:
            Current price in USD or None if failed
        """
        if not self.binance_exchange:
            logger.error("Binance exchange not initialized")
            return None

        await self._rate_limit()

        try:
            binance_symbol = self._get_binance_symbol(symbol)
            price = await self.binance_exchange.get_futures_mark_price(binance_symbol)

            if price and price > 0:
                logger.info(f"Price for {symbol}: ${price}")
                return float(price)
            else:
                logger.warning(f"Invalid price received for {symbol}: {price}")
                return None

        except Exception as e:
            logger.error(f"Failed to get price for {symbol}: {e}")
            return None

    async def get_coin_price(self, symbol: str) -> Optional[float]:
        """
        Get price by symbol (combines symbol conversion and price fetch)

        Args:
            symbol: Trading symbol (e.g., 'BTC')

        Returns:
            Current price in USD or None if failed
        """
        # Check cache first
        cached_price = self.cache.get_cached_price(symbol)
        if cached_price:
            return cached_price

        # Get price from Binance
        price = await self.get_price(symbol)
        if price:
            # Cache the price
            self.cache.set_cached_price(symbol, price)

            # Validate the price
            validation_result = self.validator.validate_price(price, symbol)
            if not validation_result.is_valid:
                logger.warning(f"Price validation failed for {symbol}: {validation_result.validation_errors}")

            if validation_result.warnings:
                logger.info(f"Price warnings for {symbol}: {validation_result.warnings}")

        return price

    async def get_multiple_prices(self, symbols: List[str]) -> dict:
        """
        Get prices for multiple symbols

        Args:
            symbols: List of trading symbols (e.g., ['BTC', 'ETH', 'SOL'])

        Returns:
            Dict mapping symbol to price
        """
        if not self.binance_exchange:
            logger.error("Binance exchange not initialized")
            return {}

        await self._rate_limit()

        try:
            binance_symbols = [self._get_binance_symbol(symbol) for symbol in symbols]
            prices = await self.binance_exchange.get_current_prices(binance_symbols)

            # Convert back to original symbol format
            result = {}
            for i, symbol in enumerate(symbols):
                binance_symbol = binance_symbols[i]
                if binance_symbol in prices:
                    result[symbol] = prices[binance_symbol]
                else:
                    logger.warning(f"Price not found for {symbol} ({binance_symbol})")
                    result[symbol] = 0.0

            return result

        except Exception as e:
            logger.error(f"Failed to get multiple prices: {e}")
            return {}

    def get_cache_stats(self) -> dict:
        """Get cache statistics"""
        return self.cache.get_cache_stats()