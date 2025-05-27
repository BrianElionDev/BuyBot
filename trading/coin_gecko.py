# crypto-signal-bot/trading/coin_gecko.py

import logging
import aiohttp
import asyncio
import time # Import time for rate limiting
from typing import Dict, Any, Optional

from config.settings import settings

logger = logging.getLogger(__name__)

class CoinGeckoAPI:
    """
    Handles CoinGecko API interactions for fetching coin prices and IDs.
    Implements a simple in-memory cache for coin IDs to reduce API calls.
    Uses aiohttp for asynchronous HTTP requests and respects rate limits.
    """

    def __init__(self):
        self.base_url = settings.COINGECKO_API_URL
        self._coin_id_cache: Dict[str, str] = {} # Cache: {symbol: coin_id}
        self._last_api_call_time: float = 0.0
        self.session = None # aiohttp ClientSession will be initialized on first use

    async def _get_session(self):
        """Initializes aiohttp ClientSession if not already created."""
        if self.session is None:
            self.session = aiohttp.ClientSession()
        return self.session

    async def close_session(self):
        """Closes the aiohttp ClientSession."""
        if self.session:
            await self.session.close()
            self.session = None

    async def _wait_for_rate_limit(self):
        """Ensures CoinGecko API rate limits are respected."""
        elapsed = time.time() - self._last_api_call_time
        if elapsed < settings.COINGECKO_RATE_LIMIT_DELAY:
            wait_time = settings.COINGECKO_RATE_LIMIT_DELAY - elapsed
            logger.debug(f"Waiting {wait_time:.2f}s for CoinGecko rate limit.")
            await asyncio.sleep(wait_time)
        self._last_api_call_time = time.time()

    async def get_price(self, coin_id: str) -> Optional[float]:
        """
        Asynchronously fetches the current price for a given CoinGecko ID.

        Args:
            coin_id (str): The unique ID of the cryptocurrency on CoinGecko (e.g., 'bitcoin', 'ethereum').

        Returns:
            Optional[float]: The current price in USD, or None if fetching fails.
        """
        await self._wait_for_rate_limit()
        session = await self._get_session()
        params = {'ids': coin_id, 'vs_currencies': settings.BASE_CURRENCY}
        try:
            async with session.get(f"{self.base_url}/simple/price", params=params) as response:
                response.raise_for_status()
                data = await response.json()
                price = data.get(coin_id, {}).get(settings.BASE_CURRENCY)
                if price is None:
                    logger.warning(f"Price for {coin_id} in {settings.BASE_CURRENCY} not found in CoinGecko response: {data}")
                    return None
                logger.info(f"Fetched price for {coin_id}: {price} {settings.BASE_CURRENCY.upper()}")
                return float(price)
        except aiohttp.ClientError as e:
            logger.error(f"CoinGecko API network error for price of {coin_id}: {e}")
            return None
        except Exception as e:
            logger.error(f"CoinGecko API unexpected error for price of {coin_id}: {e}")
            return None

    async def get_coin_id(self, symbol: str) -> Optional[str]:
        """
        Asynchronously converts a coin symbol (e.g., 'BTC') to its CoinGecko ID (e.g., 'bitcoin').
        Uses an in-memory cache to avoid repeated API calls for already resolved symbols.

        Args:
            symbol (str): The cryptocurrency symbol (e.g., 'BTC', 'ETH').

        Returns:
            Optional[str]: The CoinGecko ID, or None if not found.
        """
        symbol_upper = symbol.upper()
        if symbol_upper in self._coin_id_cache:
            logger.debug(f"Coin ID for {symbol_upper} found in cache: {self._coin_id_cache[symbol_upper]}")
            return self._coin_id_cache[symbol_upper]

        await self._wait_for_rate_limit()
        session = await self._get_session()
        try:
            async with session.get(f"{self.base_url}/coins/list") as response:
                response.raise_for_status()
                coins_list = await response.json()
                for coin in coins_list:
                    if coin['symbol'].upper() == symbol_upper:
                        self._coin_id_cache[symbol_upper] = coin['id']
                        logger.info(f"Resolved {symbol_upper} to CoinGecko ID: {coin['id']}")
                        return coin['id']
                logger.warning(f"CoinGecko ID not found for symbol: {symbol_upper}")
                return None
        except aiohttp.ClientError as e:
            logger.error(f"CoinGecko API network error for coin list: {e}")
            return None
        except Exception as e:
            logger.error(f"CoinGecko API unexpected error for coin list: {e}")
            return None