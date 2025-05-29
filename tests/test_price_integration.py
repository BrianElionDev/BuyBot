#!/usr/bin/env python3
"""
Test script to verify CoinGecko price integration works
"""
import asyncio
import logging
from src.services.price_service import PriceService

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_price_service():
    """Test the price service functionality"""
    price_service = PriceService()

    # Test with common tokens
    test_symbols = ['ETH', 'BTC', 'USDC', 'DSYNC']

    for symbol in test_symbols:
        try:
            logger.info(f"Testing price fetch for {symbol}...")
            price = await price_service.get_coin_price(symbol)

            if price:
                logger.info(f"✅ {symbol}: ${price:.6f}")
            else:
                logger.warning(f"❌ {symbol}: Price not available")

        except Exception as e:
            logger.error(f"❌ {symbol}: Error - {e}")

    logger.info("Price service test completed!")

if __name__ == "__main__":
    asyncio.run(test_price_service())
