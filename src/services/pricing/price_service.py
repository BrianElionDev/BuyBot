import logging
import asyncio
from typing import Optional, List
from pycoingecko import CoinGeckoAPI
from .price_models import PriceServiceConfig, PriceData, MarketData
from .price_cache import PriceCache
from .price_validator import PriceValidator

logger = logging.getLogger(__name__)


class PriceService:
    """Core price service for cryptocurrency price data"""

    def __init__(self, config: Optional[PriceServiceConfig] = None):
        """Initialize the price service"""
        self.config = config or PriceServiceConfig()
        self.cg = CoinGeckoAPI()
        self.cache = PriceCache(self.config)
        self.validator = PriceValidator()
        self._last_call = 0

    async def _rate_limit(self) -> None:
        """Apply rate limiting for API calls"""
        elapsed = asyncio.get_event_loop().time() - self._last_call
        if elapsed < self.config.rate_limit_delay:
            await asyncio.sleep(self.config.rate_limit_delay - elapsed)
        self._last_call = asyncio.get_event_loop().time()

    async def get_coin_id(self, symbol: str) -> Optional[str]:
        """
        Get coin ID from symbol with improved resolution logic

        Args:
            symbol: Trading symbol (e.g., 'BTC')

        Returns:
            Coin ID from CoinGecko or None if not found
        """
        if not symbol:
            logger.error("Empty symbol received")
            return None

        symbol = symbol.upper().strip()

        # Check cache first
        cached_coin_id = self.cache.get_cached_coin_id(symbol)
        if cached_coin_id:
            logger.info(f"Cache hit: {symbol} -> {cached_coin_id}")
            return cached_coin_id

        # High priority check for Solana
        if symbol in ["SOL", "SOLANA"]:
            coin_id = "solana"
            self.cache.set_cached_coin_id(symbol, coin_id)
            logger.info(f"High-priority match for {symbol} -> {coin_id}")
            return coin_id

        # Handle special cases for SHIB token variations
        if symbol in ["SHIB", "SHIBA", "SHIBAINU", "SHIBA-INU"]:
            coin_id = "shiba-inu"
            self.cache.set_cached_coin_id(symbol, coin_id)
            logger.info(f"Special handling for SHIB token: {symbol} -> {coin_id}")
            return coin_id

        # Try alternative name normalizations
        alternatives = self._get_symbol_alternatives(symbol)
        for alt in alternatives:
            cached_alt = self.cache.get_cached_coin_id(alt)
            if cached_alt:
                self.cache.set_cached_coin_id(symbol, cached_alt)
                logger.info(f"Alternative match: {symbol} via {alt} -> {cached_alt}")
                return cached_alt

        # If not in cache, use CoinGecko API
        coin_id = await self._fetch_coin_id_from_api(symbol)
        if coin_id:
            self.cache.set_cached_coin_id(symbol, coin_id)

        return coin_id

    def _get_symbol_alternatives(self, symbol: str) -> List[str]:
        """Get alternative symbol variations for matching"""
        alternatives = [symbol]

        # Remove common prefixes/suffixes
        if symbol.startswith("$"):
            alternatives.append(symbol[1:])

        # Handle cases like SOL.X -> SOL
        if "." in symbol:
            alternatives.append(symbol.split('.')[0])

        # Handle cases like SHIBA-INU -> SHIBA
        if "-" in symbol:
            alternatives.append(symbol.split('-')[0])

        return alternatives

    async def _fetch_coin_id_from_api(self, symbol: str) -> Optional[str]:
        """Fetch coin ID from CoinGecko API"""
        await self._rate_limit()

        try:
            coins_list = await asyncio.get_event_loop().run_in_executor(
                None, self.cg.get_coins_list
            )

            # Find exact symbol matches
            candidates = [
                coin for coin in coins_list
                if coin['symbol'].upper() == symbol
            ]

            if not candidates:
                logger.warning(f"No coins found with symbol '{symbol}' on CoinGecko")
                return None

            # If single candidate, validate and return
            if len(candidates) == 1:
                if self.validator.validate_coin_data(candidates[0]):
                    coin_id = candidates[0]['id']
                    logger.info(f"Single exact match found for {symbol}: {coin_id}")
                    return coin_id
                else:
                    logger.warning(f"Single candidate for {symbol} rejected as illegitimate")
                    return None

            # Multiple candidates - find best match
            logger.info(f"Found {len(candidates)} candidates for symbol {symbol}. Evaluating best match...")

            # Check for exact name match first
            for coin in candidates:
                if coin['name'].upper() == symbol and self.validator.validate_coin_data(coin):
                    coin_id = coin['id']
                    logger.info(f"Exact name match for {symbol}: {coin_id}")
                    return coin_id

            # Fall back to highest market cap
            best_match_id = await self._get_highest_market_cap_coin(candidates)
            if best_match_id:
                logger.info(f"Best match by market cap for {symbol}: {best_match_id}")
                return best_match_id

        except Exception as e:
            logger.error(f"Error fetching coin ID for {symbol}: {e}")

        return None

    async def _get_highest_market_cap_coin(self, coin_candidates: List[dict]) -> Optional[str]:
        """Find the coin with highest market cap from candidates"""
        if not coin_candidates:
            return None

        if len(coin_candidates) == 1:
            return coin_candidates[0]['id']

        await self._rate_limit()

        try:
            ids = [coin['id'] for coin in coin_candidates]
            ids_str = ','.join(ids)

            market_data = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self.cg.get_coins_markets(vs_currency='usd', ids=ids_str)
            )

            if not market_data:
                return coin_candidates[0]['id']

            # Sort by market cap
            sorted_data = sorted(
                market_data,
                key=lambda x: x.get('market_cap', 0) if x.get('market_cap') else 0,
                reverse=True
            )

            if sorted_data:
                return sorted_data[0]['id']

        except Exception as e:
            logger.warning(f"Error getting market data: {e}")

        return coin_candidates[0]['id']

    async def get_price(self, coin_id: str) -> Optional[float]:
        """
        Get price for a specific coin ID

        Args:
            coin_id: CoinGecko coin ID

        Returns:
            Current price in USD or None if failed
        """
        await self._rate_limit()

        try:
            price_data = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self.cg.get_price(ids=coin_id, vs_currencies='usd')
            )

            price = price_data.get(coin_id, {}).get('usd')
            if price:
                price_float = float(price)
                logger.info(f"Price for {coin_id}: ${price_float}")
                return price_float

        except Exception as e:
            logger.error(f"Failed to get price for {coin_id}: {e}")

        return None

    async def get_coin_price(self, symbol: str) -> Optional[float]:
        """
        Get price by symbol (combines coin_id lookup and price fetch)

        Args:
            symbol: Trading symbol (e.g., 'BTC')

        Returns:
            Current price in USD or None if failed
        """
        # Check cache first
        cached_price = self.cache.get_cached_price(symbol)
        if cached_price:
            return cached_price

        # Get coin ID and then price
        coin_id = await self.get_coin_id(symbol)
        if not coin_id:
            return None

        price = await self.get_price(coin_id)
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

    def get_cache_stats(self) -> dict:
        """Get cache statistics"""
        return self.cache.get_cache_stats()

    def clear_cache(self) -> None:
        """Clear all cached data"""
        self.cache.clear_all_cache()

    def clear_expired_cache(self) -> int:
        """Clear expired cache entries"""
        return self.cache.clear_expired_cache()
