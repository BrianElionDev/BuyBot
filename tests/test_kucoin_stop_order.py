#!/usr/bin/env python3
"""
Test script for KuCoin stop order creation.
This script tests the stop order creation logic without sending Telegram notifications.

Usage:
    python test_kucoin_stop_order.py <symbol> <side> <stop_price> [amount]

Example:
    python test_kucoin_stop_order.py BTCUSDTM SELL 113000 0.01
"""

import asyncio
import sys
import os
import logging
from pathlib import Path
from dotenv import load_dotenv

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Load environment variables
load_dotenv()

from src.exchange.kucoin.kucoin_exchange import KucoinExchange
from config import settings

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def test_stop_order(symbol: str, side: str, stop_price: float, amount: float = 0.01):
    """
    Test creating a stop order on KuCoin.

    Args:
        symbol: Trading pair (e.g., BTCUSDTM)
        side: Order side (SELL or BUY)
        stop_price: Stop price
        amount: Position size in assets (default: 0.01)
    """
    logger.info(f"Testing KuCoin stop order creation:")
    logger.info(f"  Symbol: {symbol}")
    logger.info(f"  Side: {side}")
    logger.info(f"  Stop Price: {stop_price}")
    logger.info(f"  Amount: {amount}")

    try:
        # Load credentials from settings
        api_key = settings.KUCOIN_API_KEY
        api_secret = settings.KUCOIN_API_SECRET
        api_passphrase = settings.KUCOIN_API_PASSPHRASE
        is_testnet = settings.KUCOIN_TESTNET

        if not api_key or not api_secret or not api_passphrase:
            logger.error("❌ KuCoin API credentials not found in environment variables")
            logger.error("   Please set KUCOIN_API_KEY, KUCOIN_API_SECRET, and KUCOIN_API_PASSPHRASE")
            return False

        # Initialize exchange
        exchange = KucoinExchange(
            api_key=api_key,
            api_secret=api_secret,
            api_passphrase=api_passphrase,
            is_testnet=is_testnet
        )

        # Initialize the exchange connection
        await exchange.initialize()

        # Test 1: Direct create_futures_order call
        logger.info("\n=== Test 1: Direct create_futures_order ===")
        result1 = await exchange.create_futures_order(
            pair=symbol,
            side=side,
            order_type='STOP_MARKET',
            amount=amount,
            stop_price=stop_price,
            reduce_only=True
        )
        logger.info(f"Result 1: {result1}")

        if result1.get('error'):
            logger.error(f"❌ Test 1 failed: {result1.get('error')}")
        else:
            logger.info(f"✅ Test 1 succeeded: Order ID = {result1.get('orderId')}")

        # Test 2: Using place_stop_loss_with_retry
        logger.info("\n=== Test 2: place_stop_loss_with_retry ===")
        result2 = await exchange.place_stop_loss_with_retry(
            pair=symbol,
            side=side,
            stop_price=stop_price,
            amount=amount,
            reduce_only=True,
            max_attempts=3
        )
        logger.info(f"Result 2: {result2}")

        if result2.get('error'):
            logger.error(f"❌ Test 2 failed: {result2.get('error')}")
        else:
            logger.info(f"✅ Test 2 succeeded: Order ID = {result2.get('orderId')}")

        # Summary
        logger.info("\n=== Summary ===")
        if result1.get('error') and result2.get('error'):
            logger.error("❌ Both tests failed")
            success = False
        elif result1.get('error') or result2.get('error'):
            logger.warning("⚠️  One test failed, one succeeded")
            success = False
        else:
            logger.info("✅ Both tests succeeded")
            success = True

        # Cleanup
        await exchange.close()
        return success

    except Exception as e:
        logger.error(f"❌ Exception during test: {e}", exc_info=True)
        return False


def main():
    """Main entry point."""
    if len(sys.argv) < 4:
        print(__doc__)
        sys.exit(1)

    symbol = sys.argv[1].upper()
    side = sys.argv[2].upper()

    try:
        stop_price = float(sys.argv[3])
    except ValueError:
        print(f"Error: Invalid stop_price '{sys.argv[3]}' - must be a number")
        sys.exit(1)

    amount = 0.01
    if len(sys.argv) >= 5:
        try:
            amount = float(sys.argv[4])
        except ValueError:
            print(f"Error: Invalid amount '{sys.argv[4]}' - must be a number")
            sys.exit(1)

    # Validate side
    if side not in ['BUY', 'SELL']:
        print(f"Error: Invalid side '{side}' - must be 'BUY' or 'SELL'")
        sys.exit(1)

    # Run async test
    success = asyncio.run(test_stop_order(symbol, side, stop_price, amount))
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()

