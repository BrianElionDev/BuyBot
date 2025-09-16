#!/usr/bin/env python3
"""
Simple test script to verify Binance price fetching for BTC, ETH, and SOL
"""

import asyncio
import logging
import sys
import os
from pathlib import Path

# Add the src directory to the Python path
sys.path.insert(0, str(Path(__file__).parent))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def test_binance_direct():
    """Test direct Binance API calls"""

    try:
        # Import binance directly
        from binance import AsyncClient

        logger.info("Testing Binance API connection...")

        # Initialize client (no API key needed for public data)
        client = await AsyncClient.create()

        # Test symbols
        test_symbols = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT']

        logger.info("Fetching prices from Binance...")

        # Get ticker data
        tickers = await client.futures_ticker()

        prices = {}
        for ticker in tickers:
            symbol = ticker['symbol']
            if symbol in test_symbols:
                price = float(ticker['lastPrice'])
                prices[symbol] = price
                logger.info(f"✅ {symbol}: ${price:,.2f}")

        # Test mark prices
        logger.info("\nTesting mark prices...")
        for symbol in test_symbols:
            try:
                mark_price_data = await client.futures_mark_price(symbol=symbol)
                mark_price = float(mark_price_data['markPrice'])
                logger.info(f"✅ {symbol} Mark Price: ${mark_price:,.2f}")
            except Exception as e:
                logger.error(f"❌ Failed to get mark price for {symbol}: {e}")

        # Close client
        await client.close_connection()

        if prices:
            logger.info(f"\n🎉 Successfully fetched prices for {len(prices)} symbols!")
            return True
        else:
            logger.error("❌ No prices were fetched")
            return False

    except Exception as e:
        logger.error(f"❌ Test failed: {e}")
        return False


async def main():
    """Main test function"""
    logger.info("Starting simple Binance price test...")

    success = await test_binance_direct()

    if success:
        logger.info("\n🎉 Test passed! Binance integration is working.")
    else:
        logger.error("\n❌ Test failed. Check the logs above for details.")

    return success


if __name__ == "__main__":
    # Run the test
    result = asyncio.run(main())
    sys.exit(0 if result else 1)
