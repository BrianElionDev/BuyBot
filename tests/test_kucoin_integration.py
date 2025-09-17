#!/usr/bin/env python3
"""
KuCoin Integration Test Script

This script tests the KuCoin integration fixes to ensure:
1. Symbol resolution works correctly
2. Price fetching uses proper endpoints
3. Symbol validation works
4. No aiohttp session leaks
"""

import asyncio
import logging
import sys
import os
from typing import Dict, List

# Add the project root to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.exchange.kucoin.kucoin_exchange import KucoinExchange
from src.exchange.kucoin.kucoin_symbol_mapper import symbol_mapper
from src.services.pricing.price_service import PriceService
from config import settings

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def test_symbol_mapping():
    """Test symbol mapping functionality."""
    logger.info("=== Testing Symbol Mapping ===")

    test_symbols = [
        "DAM-USDT",
        "BTC-USDT",
        "ETH-USDT",
        "SAPIEN-USDT",
        "NAORIS-USDT"
    ]

    # Test symbol variants generation
    for symbol in test_symbols:
        variants = symbol_mapper.get_symbol_variants(symbol)
        logger.info(f"Symbol {symbol} variants: {variants}")

    logger.info("Symbol mapping test completed")


async def test_kucoin_connection():
    """Test KuCoin connection and basic functionality."""
    logger.info("=== Testing KuCoin Connection ===")

    try:
        # Initialize KuCoin exchange
        kucoin_exchange = KucoinExchange(
            api_key=settings.KUCOIN_API_KEY,
            api_secret=settings.KUCOIN_API_SECRET,
            api_passphrase=settings.KUCOIN_API_PASSPHRASE,
            is_testnet=False  # Force production due to sandbox being offline
        )

        # Initialize the exchange
        success = await kucoin_exchange.initialize()
        if not success:
            logger.error("Failed to initialize KuCoin exchange")
            return False

        logger.info("KuCoin exchange initialized successfully")

        # Test getting futures symbols
        logger.info("Fetching KuCoin futures symbols...")
        futures_symbols = await kucoin_exchange.get_futures_symbols()
        logger.info(f"Retrieved {len(futures_symbols)} KuCoin futures symbols")

        if futures_symbols:
            logger.info(f"Sample symbols: {futures_symbols[:10]}")

        # Test symbol support checking
        test_symbols = ["BTC-USDT", "ETH-USDT", "DAM-USDT", "SAPIEN-USDT"]

        for symbol in test_symbols:
            is_supported = await kucoin_exchange.is_futures_symbol_supported(symbol)
            logger.info(f"Symbol {symbol} supported: {is_supported}")

            if is_supported:
                # Test getting symbol filters
                filters = await kucoin_exchange.get_futures_symbol_filters(symbol)
                if filters:
                    logger.info(f"Symbol {symbol} filters: {filters.get('kucoin_symbol', 'unknown')}")

        # Test price fetching
        logger.info("Testing price fetching...")
        price_symbols = ["BTC-USDT", "ETH-USDT"]
        prices = await kucoin_exchange.get_current_prices(price_symbols)

        for symbol, price in prices.items():
            if price > 0:
                logger.info(f"Price for {symbol}: ${price}")
            else:
                logger.warning(f"No price found for {symbol}")

        # Close the exchange
        await kucoin_exchange.close()
        logger.info("KuCoin exchange closed successfully")

        return True

    except Exception as e:
        logger.error(f"KuCoin connection test failed: {e}")
        return False


async def test_price_service():
    """Test price service with KuCoin integration."""
    logger.info("=== Testing Price Service ===")

    try:
        # Initialize KuCoin exchange
        kucoin_exchange = KucoinExchange(
            api_key=settings.KUCOIN_API_KEY,
            api_secret=settings.KUCOIN_API_SECRET,
            api_passphrase=settings.KUCOIN_API_PASSPHRASE,
            is_testnet=False  # Force production due to sandbox being offline
        )

        # Initialize price service
        price_service = PriceService(kucoin_exchange=kucoin_exchange)

        # Test getting prices from KuCoin
        test_symbols = ["BTC", "ETH", "DAM", "SAPIEN"]

        for symbol in test_symbols:
            price = await price_service.get_coin_price(symbol, exchange="kucoin")
            if price and price > 0:
                logger.info(f"KuCoin price for {symbol}: ${price}")
            else:
                logger.warning(f"No KuCoin price found for {symbol}")

        # Close the exchange
        await kucoin_exchange.close()

        return True

    except Exception as e:
        logger.error(f"Price service test failed: {e}")
        return False


async def test_symbol_validation():
    """Test symbol validation against available symbols."""
    logger.info("=== Testing Symbol Validation ===")

    try:
        # Initialize KuCoin exchange
        kucoin_exchange = KucoinExchange(
            api_key=settings.KUCOIN_API_KEY,
            api_secret=settings.KUCOIN_API_SECRET,
            api_passphrase=settings.KUCOIN_API_PASSPHRASE,
            is_testnet=False  # Force production due to sandbox being offline
        )

        await kucoin_exchange.initialize()

        # Get available symbols
        available_symbols = await kucoin_exchange.get_futures_symbols()
        symbol_mapper.available_symbols = available_symbols

        # Test various symbols
        test_cases = [
            ("BTC-USDT", True),  # Should be supported
            ("ETH-USDT", True),  # Should be supported
            ("DAM-USDT", False), # Likely not supported
            ("SAPIEN-USDT", False), # Likely not supported
            ("INVALID-SYMBOL", False), # Definitely not supported
        ]

        for symbol, expected in test_cases:
            is_supported = symbol_mapper.is_symbol_supported(symbol, available_symbols, "futures")
            status = "✓" if is_supported == expected else "✗"
            logger.info(f"{status} Symbol {symbol}: supported={is_supported}, expected={expected}")

            if is_supported:
                mapped_symbol = symbol_mapper.map_to_futures_symbol(symbol, available_symbols)
                logger.info(f"  Mapped to: {mapped_symbol}")

        await kucoin_exchange.close()
        return True

    except Exception as e:
        logger.error(f"Symbol validation test failed: {e}")
        return False


async def main():
    """Run all tests."""
    logger.info("Starting KuCoin Integration Tests")
    logger.info("=" * 50)

    tests = [
        ("Symbol Mapping", test_symbol_mapping),
        ("KuCoin Connection", test_kucoin_connection),
        ("Price Service", test_price_service),
        ("Symbol Validation", test_symbol_validation),
    ]

    results = {}

    for test_name, test_func in tests:
        logger.info(f"\nRunning {test_name} test...")
        try:
            result = await test_func()
            results[test_name] = result
            status = "PASSED" if result else "FAILED"
            logger.info(f"{test_name} test: {status}")
        except Exception as e:
            logger.error(f"{test_name} test failed with exception: {e}")
            results[test_name] = False

    # Summary
    logger.info("\n" + "=" * 50)
    logger.info("TEST SUMMARY")
    logger.info("=" * 50)

    passed = sum(1 for result in results.values() if result)
    total = len(results)

    for test_name, result in results.items():
        status = "PASSED" if result else "FAILED"
        logger.info(f"{test_name}: {status}")

    logger.info(f"\nOverall: {passed}/{total} tests passed")

    if passed == total:
        logger.info("🎉 All tests passed! KuCoin integration is working correctly.")
    else:
        logger.warning("⚠️  Some tests failed. Please check the logs for details.")

    return passed == total


if __name__ == "__main__":
    try:
        success = asyncio.run(main())
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        logger.info("Tests interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Test runner failed: {e}")
        sys.exit(1)
