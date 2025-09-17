#!/usr/bin/env python3
"""
Quick KuCoin Test Script

Tests the key fixes:
1. Symbol fetching from production API
2. Price fetching with correct field parsing
3. Symbol mapping
"""

import asyncio
import logging
import sys
import os

# Add the project root to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.exchange.kucoin.kucoin_exchange import KucoinExchange
from src.exchange.kucoin.kucoin_symbol_mapper import symbol_mapper
from config import settings

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def test_quick():
    """Quick test of KuCoin fixes."""
    logger.info("=== Quick KuCoin Test ===")

    try:
        # Initialize with production API
        kucoin_exchange = KucoinExchange(
            api_key=settings.KUCOIN_API_KEY,
            api_secret=settings.KUCOIN_API_SECRET,
            api_passphrase=settings.KUCOIN_API_PASSPHRASE,
            is_testnet=False  # Force production
        )

        await kucoin_exchange.initialize()
        logger.info("✅ KuCoin exchange initialized")

        # Test 1: Get futures symbols
        logger.info("Testing futures symbols...")
        symbols = await kucoin_exchange.get_futures_symbols()
        logger.info(f"✅ Retrieved {len(symbols)} futures symbols")

        if symbols:
            logger.info(f"Sample symbols: {symbols[:5]}")

            # Test 2: Symbol mapping
            logger.info("Testing symbol mapping...")
            test_symbols = ["BTC-USDT", "ETH-USDT", "LINEA-USDT", "AVNT-USDT", "DAM-USDT"]

            for symbol in test_symbols:
                mapped = symbol_mapper.map_to_futures_symbol(symbol, symbols)
                status = "✅" if mapped else "❌"
                logger.info(f"{status} {symbol} -> {mapped}")

            # Test 3: Price fetching
            logger.info("Testing price fetching...")
            price_symbols = ["BTC-USDT", "ETH-USDT"]
            prices = await kucoin_exchange.get_current_prices(price_symbols)

            for symbol, price in prices.items():
                if price > 0:
                    logger.info(f"✅ {symbol}: ${price}")
                else:
                    logger.warning(f"❌ {symbol}: No price")

        await kucoin_exchange.close()
        logger.info("✅ Test completed successfully")

    except Exception as e:
        logger.error(f"❌ Test failed: {e}")
        return False

    return True


if __name__ == "__main__":
    success = asyncio.run(test_quick())
    sys.exit(0 if success else 1)
