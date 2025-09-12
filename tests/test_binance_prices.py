#!/usr/bin/env python3
"""
Test script to verify Binance price fetching for BTC, ETH, and SOL
"""

import asyncio
import logging
import sys
import os
from pathlib import Path

# Add the src directory to the Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.exchange.binance.binance_exchange import BinanceExchange
from src.services.pricing.price_service import PriceService
from src.services.pricing.price_models import PriceServiceConfig

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def test_binance_prices():
    """Test fetching prices for BTC, ETH, and SOL from Binance"""

    # Test symbols
    test_symbols = ['BTC', 'ETH', 'SOL']

    # Initialize Binance exchange (using testnet for safety)
    # You'll need to set your API credentials
    api_key = os.getenv('BINANCE_API_KEY', 'test_key')
    api_secret = os.getenv('BINANCE_API_SECRET', 'test_secret')

    binance_exchange = BinanceExchange(
        api_key=api_key,
        api_secret=api_secret,
        is_testnet=True  # Use testnet for safety
    )

    # Initialize price service
    config = PriceServiceConfig()
    price_service = PriceService(config=config, binance_exchange=binance_exchange)

    try:
        # Initialize the exchange
        logger.info("Initializing Binance exchange...")
        success = await binance_exchange.initialize()
        if not success:
            logger.error("Failed to initialize Binance exchange")
            return False

        logger.info("Binance exchange initialized successfully")

        # Test individual price fetching
        logger.info("\n=== Testing Individual Price Fetching ===")
        for symbol in test_symbols:
            logger.info(f"Fetching price for {symbol}...")
            price = await price_service.get_coin_price(symbol)
            if price:
                logger.info(f"✅ {symbol}: ${price:,.2f}")
            else:
                logger.error(f"❌ Failed to get price for {symbol}")

        # Test multiple price fetching
        logger.info("\n=== Testing Multiple Price Fetching ===")
        prices = await price_service.get_multiple_prices(test_symbols)
        if prices:
            logger.info("Multiple prices fetched successfully:")
            for symbol, price in prices.items():
                if price > 0:
                    logger.info(f"✅ {symbol}: ${price:,.2f}")
                else:
                    logger.error(f"❌ {symbol}: No price data")
        else:
            logger.error("❌ Failed to fetch multiple prices")

        # Test cache stats
        logger.info("\n=== Cache Statistics ===")
        cache_stats = price_service.get_cache_stats()
        logger.info(f"Cache stats: {cache_stats}")

        return True

    except Exception as e:
        logger.error(f"Test failed with error: {e}")
        return False

    finally:
        # Clean up
        await binance_exchange.close()
        logger.info("Binance exchange connection closed")


async def test_direct_binance_calls():
    """Test direct Binance API calls without price service"""

    logger.info("\n=== Testing Direct Binance API Calls ===")

    api_key = os.getenv('BINANCE_API_KEY', 'test_key')
    api_secret = os.getenv('BINANCE_API_SECRET', 'test_secret')

    binance_exchange = BinanceExchange(
        api_key=api_key,
        api_secret=api_secret,
        is_testnet=True
    )

    try:
        success = await binance_exchange.initialize()
        if not success:
            logger.error("Failed to initialize Binance exchange")
            return False

        # Test individual mark prices
        test_symbols = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT']

        for symbol in test_symbols:
            logger.info(f"Fetching mark price for {symbol}...")
            price = await binance_exchange.get_futures_mark_price(symbol)
            if price:
                logger.info(f"✅ {symbol}: ${price:,.2f}")
            else:
                logger.error(f"❌ Failed to get price for {symbol}")

        # Test multiple prices
        logger.info("Fetching multiple prices...")
        prices = await binance_exchange.get_current_prices(test_symbols)
        if prices:
            logger.info("Multiple prices from Binance:")
            for symbol, price in prices.items():
                logger.info(f"✅ {symbol}: ${price:,.2f}")

        return True

    except Exception as e:
        logger.error(f"Direct Binance test failed: {e}")
        return False

    finally:
        await binance_exchange.close()


async def main():
    """Main test function"""
    logger.info("Starting Binance price fetching tests...")
    logger.info("Note: This test uses Binance testnet for safety")
    logger.info("Make sure to set BINANCE_API_KEY and BINANCE_API_SECRET environment variables")

    # Test 1: Direct Binance API calls
    success1 = await test_direct_binance_calls()

    # Test 2: Price service integration
    success2 = await test_binance_prices()

    if success1 and success2:
        logger.info("\n🎉 All tests passed! Binance integration is working correctly.")
    else:
        logger.error("\n❌ Some tests failed. Check the logs above for details.")

    return success1 and success2


if __name__ == "__main__":
    # Run the test
    result = asyncio.run(main())
    sys.exit(0 if result else 1)
