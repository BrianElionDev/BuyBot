import logging
import asyncio
from pycoingecko import CoinGeckoAPI
from typing import Optional, Dict
from config import settings as config

logger = logging.getLogger(__name__)

class PriceService:
    def __init__(self):
        self.cg = CoinGeckoAPI()
        self._coin_cache: Dict[str, str] = {}  # symbol -> coin_id cache
        self._last_call = 0

    async def _rate_limit(self):
        # CoinGecko free tier: 50 calls/minute
        elapsed = asyncio.get_event_loop().time() - self._last_call
        if elapsed < 1.2:  # ~50 calls per minute
            await asyncio.sleep(1.2 - elapsed)
        self._last_call = asyncio.get_event_loop().time()

    async def get_coin_id(self, symbol: str) -> Optional[str]:
        symbol = symbol.upper()

        if symbol in self._coin_cache:
            return self._coin_cache[symbol]

        await self._rate_limit()

        try:
            # Run in thread pool to avoid blocking
            coins_list = await asyncio.get_event_loop().run_in_executor(
                None, self.cg.get_coins_list
            )

            for coin in coins_list:
                if coin['symbol'].upper() == symbol:
                    self._coin_cache[symbol] = coin['id']
                    logger.info(f"Resolved {symbol} -> {coin['id']}")
                    return coin['id']

        except Exception as e:
            logger.error(f"Failed to resolve coin ID for {symbol}: {e}")

        return None

    async def get_price(self, coin_id: str) -> Optional[float]:
        await self._rate_limit()

        try:
            # Run in thread pool to avoid blocking
            price_data = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self.cg.get_price(ids=coin_id, vs_currencies='usd')
            )

            price = price_data.get(coin_id, {}).get('usd')
            if price:
                logger.info(f"Price for {coin_id}: ${price}")
                return float(price)

        except Exception as e:
            logger.error(f"Failed to get price for {coin_id}: {e}")

        return None

    async def get_coin_price(self, symbol: str) -> Optional[float]:
        """Get price by symbol (combines coin_id lookup and price fetch)"""
        coin_id = await self.get_coin_id(symbol)
        if not coin_id:
            return None
        return await self.get_price(coin_id)