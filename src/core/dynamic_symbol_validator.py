"""
Dynamic Symbol Validation Service

This module provides real-time symbol validation by querying exchange APIs
instead of relying on hardcoded whitelists. It includes caching to minimize
API calls and improve performance.
"""

import asyncio
import logging
from typing import Dict, List, Optional, Set, Tuple, Any
from datetime import datetime, timedelta
from dataclasses import dataclass

from src.config.dynamic_validation_config import (
    is_dynamic_validation_enabled,
    is_offline_mode_enabled,
    get_validation_config
)

logger = logging.getLogger(__name__)


@dataclass
class SymbolCache:
    """Cache entry for symbol validation data."""
    symbols: Set[str]
    timestamp: datetime
    exchange: str
    trading_type: str  # 'futures' or 'spot'


class DynamicSymbolValidator:
    """
    Real-time symbol validation service that queries exchange APIs
    instead of using hardcoded whitelists.
    """

    def __init__(self, cache_duration_minutes: int = 10):
        """
        Initialize the dynamic symbol validator.

        Args:
            cache_duration_minutes: How long to cache symbol data (default: 10 minutes)
        """
        self.config = get_validation_config()
        self.cache_duration = timedelta(minutes=cache_duration_minutes)
        self.cache: Dict[str, SymbolCache] = {}
        self._lock = asyncio.Lock()
        self._offline_mode = is_offline_mode_enabled()
        self._dynamic_validation_enabled = is_dynamic_validation_enabled()

    def _get_cache_key(self, exchange: str, trading_type: str) -> str:
        """Generate cache key for exchange and trading type."""
        return f"{exchange}_{trading_type}"

    def _is_cache_valid(self, cache_entry: SymbolCache) -> bool:
        """Check if cache entry is still valid."""
        return datetime.now() - cache_entry.timestamp < self.cache_duration

    async def _fetch_binance_futures_symbols(self, exchange_client) -> Set[str]:
        """Fetch all active futures symbols from Binance."""
        try:
            exchange_info = await exchange_client.futures_exchange_info()
            symbols = set()

            for symbol_info in exchange_info.get('symbols', []):
                # Only include symbols that are actively trading
                if symbol_info.get('status') == 'TRADING':
                    symbols.add(symbol_info['symbol'])

            logger.info(f"Fetched {len(symbols)} active Binance futures symbols")
            return symbols

        except Exception as e:
            logger.error(f"Failed to fetch Binance futures symbols: {e}")
            return set()

    async def _fetch_kucoin_futures_symbols(self, exchange_client) -> Set[str]:
        """Fetch all active futures symbols from KuCoin."""
        try:
            # Use the existing method from KuCoin exchange
            symbols_list = await exchange_client.get_futures_symbols()
            symbols = set(symbols_list) if symbols_list else set()

            logger.info(f"Fetched {len(symbols)} active KuCoin futures symbols")
            return symbols

        except Exception as e:
            logger.error(f"Failed to fetch KuCoin futures symbols: {e}")
            return set()

    async def _fetch_symbols_from_exchange(self, exchange: str, exchange_client) -> Set[str]:
        """Fetch symbols from the specified exchange."""
        if exchange.lower() == 'binance':
            return await self._fetch_binance_futures_symbols(exchange_client)
        elif exchange.lower() == 'kucoin':
            return await self._fetch_kucoin_futures_symbols(exchange_client)
        else:
            logger.error(f"Unsupported exchange: {exchange}")
            return set()

    async def get_active_symbols(self, exchange: str, exchange_client, trading_type: str = 'futures') -> Set[str]:
        """
        Get active symbols for the specified exchange and trading type.
        Uses caching to minimize API calls and supports offline mode.

        Args:
            exchange: Exchange name ('binance' or 'kucoin')
            exchange_client: Exchange client instance
            trading_type: Trading type ('futures' or 'spot')

        Returns:
            Set of active symbol strings
        """
        cache_key = self._get_cache_key(exchange, trading_type)

        async with self._lock:
            # Check if we have valid cached data
            if cache_key in self.cache and self._is_cache_valid(self.cache[cache_key]):
                logger.debug(f"Using cached symbols for {exchange} {trading_type}")
                return self.cache[cache_key].symbols

            # Check if dynamic validation is disabled
            if not self._dynamic_validation_enabled:
                logger.info(f"Dynamic validation disabled, using fallback for {exchange} {trading_type}")
                return await self._get_fallback_symbols(exchange, exchange_client, trading_type)

            # Check if we're in offline mode
            if self._offline_mode:
                logger.warning(f"Offline mode enabled, using cached data only for {exchange} {trading_type}")
                if cache_key in self.cache:
                    return self.cache[cache_key].symbols
                else:
                    return await self._get_fallback_symbols(exchange, exchange_client, trading_type)

            # Fetch fresh data from exchange
            logger.info(f"Fetching fresh symbol data for {exchange} {trading_type}")
            try:
                symbols = await self._fetch_symbols_from_exchange(exchange, exchange_client)

                # Update cache
                self.cache[cache_key] = SymbolCache(
                    symbols=symbols,
                    timestamp=datetime.now(),
                    exchange=exchange,
                    trading_type=trading_type
                )

                return symbols

            except Exception as e:
                logger.error(f"Failed to fetch symbols from {exchange}: {e}")

                # Use cached data if available
                if cache_key in self.cache:
                    logger.warning(f"Using stale cached data for {exchange} {trading_type}")
                    return self.cache[cache_key].symbols

                # Fallback to exchange methods
                return await self._get_fallback_symbols(exchange, exchange_client, trading_type)

    async def _get_fallback_symbols(self, exchange: str, exchange_client, trading_type: str = 'futures') -> Set[str]:
        """
        Get fallback symbols when dynamic validation fails.

        Args:
            exchange: Exchange name
            exchange_client: Exchange client instance
            trading_type: Trading type

        Returns:
            Set of fallback symbol strings
        """
        try:
            # Try to use exchange's existing method
            if hasattr(exchange_client, 'get_futures_symbols'):
                symbols_list = await exchange_client.get_futures_symbols()
                if symbols_list:
                    symbols = set(symbols_list)
                    logger.info(f"Got {len(symbols)} fallback symbols from {exchange}")
                    return symbols

            logger.warning(f"No fallback symbols available for {exchange} {trading_type}")
            return set()

        except Exception as e:
            logger.error(f"Error getting fallback symbols for {exchange}: {e}")
            return set()

    async def is_symbol_supported(self, symbol: str, exchange: str, exchange_client, trading_type: str = 'futures') -> bool:
        """
        Check if a symbol is supported on the specified exchange.

        Args:
            symbol: Symbol to check (e.g., 'XPLUSDT')
            exchange: Exchange name ('binance' or 'kucoin')
            exchange_client: Exchange client instance
            trading_type: Trading type ('futures' or 'spot')

        Returns:
            True if symbol is supported and actively trading
        """
        try:
            active_symbols = await self.get_active_symbols(exchange, exchange_client, trading_type)

            # For KuCoin, convert the symbol to the proper format before checking
            if exchange.lower() == 'kucoin':
                from src.exchange.kucoin.kucoin_symbol_converter import symbol_converter

                # Convert the symbol to KuCoin format
                if trading_type.lower() == 'futures':
                    converted_symbol = symbol_converter.convert_bot_to_kucoin_futures(symbol)
                else:
                    converted_symbol = symbol_converter.convert_bot_to_kucoin_spot(symbol)

                # Check if the converted symbol is supported
                is_supported = converted_symbol.upper() in active_symbols
                logger.debug(f"Symbol {symbol} -> {converted_symbol} support check on {exchange}: {is_supported}")
            else:
                # For other exchanges, check directly
                is_supported = symbol.upper() in active_symbols
                logger.debug(f"Symbol {symbol} support check on {exchange}: {is_supported}")

            return is_supported

        except Exception as e:
            logger.error(f"Error checking symbol support for {symbol} on {exchange}: {e}")
            return False

    async def get_symbol_info(self, symbol: str, exchange: str, exchange_client, trading_type: str = 'futures') -> Dict[str, Any]:
        """
        Get comprehensive symbol information.

        Args:
            symbol: Symbol to get info for
            exchange: Exchange name
            exchange_client: Exchange client instance
            trading_type: Trading type

        Returns:
            Dictionary with symbol information
        """
        try:
            active_symbols = await self.get_active_symbols(exchange, exchange_client, trading_type)
            is_supported = symbol.upper() in active_symbols

            return {
                'symbol': symbol.upper(),
                'exchange': exchange,
                'trading_type': trading_type,
                'is_supported': is_supported,
                'is_trading': is_supported,
                'cache_timestamp': self.cache.get(self._get_cache_key(exchange, trading_type), {}).get('timestamp'),
                'total_active_symbols': len(active_symbols)
            }

        except Exception as e:
            logger.error(f"Error getting symbol info for {symbol} on {exchange}: {e}")
            return {
                'symbol': symbol.upper(),
                'exchange': exchange,
                'trading_type': trading_type,
                'is_supported': False,
                'is_trading': False,
                'error': str(e)
            }

    def clear_cache(self, exchange: Optional[str] = None, trading_type: Optional[str] = None):
        """
        Clear cache for specific exchange/trading type or all cache.

        Args:
            exchange: Exchange to clear cache for (None for all)
            trading_type: Trading type to clear cache for (None for all)
        """
        if exchange and trading_type:
            cache_key = self._get_cache_key(exchange, trading_type)
            if cache_key in self.cache:
                del self.cache[cache_key]
                logger.info(f"Cleared cache for {exchange} {trading_type}")
        else:
            self.cache.clear()
            logger.info("Cleared all symbol validation cache")

    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        now = datetime.now()
        valid_entries = 0
        expired_entries = 0

        for cache_entry in self.cache.values():
            if self._is_cache_valid(cache_entry):
                valid_entries += 1
            else:
                expired_entries += 1

        return {
            'total_entries': len(self.cache),
            'valid_entries': valid_entries,
            'expired_entries': expired_entries,
            'cache_duration_minutes': self.cache_duration.total_seconds() / 60,
            'entries': {
                key: {
                    'symbol_count': len(entry.symbols),
                    'timestamp': entry.timestamp.isoformat(),
                    'is_valid': self._is_cache_valid(entry)
                }
                for key, entry in self.cache.items()
            }
        }


# Global instance for easy access
dynamic_validator = DynamicSymbolValidator()
