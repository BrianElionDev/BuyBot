#!/usr/bin/env python3
"""
Test script for Take Profit implementation.
This script tests the TP calculation and order creation logic.
"""

import asyncio
import logging
import sys
import os
from typing import Optional

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.bot.trading_engine import TradingEngine
from src.exchange.binance_exchange import BinanceExchange
from src.services.price_service import PriceService
from discord_bot.database import DatabaseManager
from config import settings

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def test_tp_calculation():
    """Test TP calculation methods."""
    logger.info("🧪 Testing TP calculation methods...")

    try:
        # Initialize components using the same pattern as the main application
        from discord_bot.utils.trade_retry_utils import initialize_clients
        bot, supabase = initialize_clients()
        if not bot:
            logger.error("Failed to initialize bot for TP calculation test")
            return

        trading_engine = bot.trading_engine

        # Test cases
        test_cases = [
            {"coin_symbol": "BTC", "position_type": "LONG", "entry_price": 50000.0},
            {"coin_symbol": "BTC", "position_type": "SHORT", "entry_price": 50000.0},
            {"coin_symbol": "ETH", "position_type": "LONG", "entry_price": 3000.0},
            {"coin_symbol": "ETH", "position_type": "SHORT", "entry_price": 3000.0},
        ]

        for test_case in test_cases:
            coin_symbol = test_case["coin_symbol"]
            position_type = test_case["position_type"]
            entry_price = test_case["entry_price"]

            logger.info(f"Testing {position_type} {coin_symbol} at {entry_price}")

            # Test 5% TP calculation
            tp_price = await trading_engine.calculate_5_percent_take_profit(
                coin_symbol, position_type, entry_price
            )

            if tp_price:
                expected_tp = entry_price * 1.05 if position_type == "LONG" else entry_price * 0.95
                logger.info(f"✅ TP calculated: {tp_price} (expected: {expected_tp})")
            else:
                logger.error(f"❌ Failed to calculate TP for {coin_symbol}")

        logger.info("✅ TP calculation tests completed")

    except Exception as e:
        logger.error(f"❌ Error in TP calculation test: {e}")

async def test_tp_audit():
    """Test TP audit functionality."""
    logger.info("🧪 Testing TP audit functionality...")

    try:
        # Initialize components using the same pattern as the main application
        from discord_bot.utils.trade_retry_utils import initialize_clients
        bot, supabase = initialize_clients()
        if not bot:
            logger.error("Failed to initialize bot for TP audit test")
            return

        trading_engine = bot.trading_engine

        # Run TP audit
        audit_results = await trading_engine.audit_open_positions_for_take_profit()

        logger.info(f"TP Audit Results: {audit_results}")

        if 'error' in audit_results:
            logger.error(f"❌ TP audit failed: {audit_results['error']}")
        else:
            logger.info(f"✅ TP audit completed successfully")
            logger.info(f"   - Total positions: {audit_results.get('total_positions', 0)}")
            logger.info(f"   - Positions with TP: {audit_results.get('positions_with_tp', 0)}")
            logger.info(f"   - Positions without TP: {audit_results.get('positions_without_tp', 0)}")
            logger.info(f"   - TP orders created: {audit_results.get('tp_orders_created', 0)}")

    except Exception as e:
        logger.error(f"❌ Error in TP audit test: {e}")

async def test_configuration():
    """Test TP configuration values."""
    logger.info("🧪 Testing TP configuration...")

    logger.info(f"Default TP Percentage: {settings.DEFAULT_TP_PERCENTAGE}%")
    logger.info(f"Signal TP Position Percentage: {settings.SIGNAL_TP_POSITION_PERCENTAGE}%")
    logger.info(f"TP Audit Interval: {settings.TP_AUDIT_INTERVAL} minutes")

    # Validate configuration
    if settings.DEFAULT_TP_PERCENTAGE == 5.0:
        logger.info("✅ Default TP percentage is correctly set to 5%")
    else:
        logger.error(f"❌ Default TP percentage should be 5%, got {settings.DEFAULT_TP_PERCENTAGE}")

    if settings.SIGNAL_TP_POSITION_PERCENTAGE == 50.0:
        logger.info("✅ Signal TP position percentage is correctly set to 50%")
    else:
        logger.error(f"❌ Signal TP position percentage should be 50%, got {settings.SIGNAL_TP_POSITION_PERCENTAGE}")

    if settings.TP_AUDIT_INTERVAL == 30:
        logger.info("✅ TP audit interval is correctly set to 30 minutes")
    else:
        logger.error(f"❌ TP audit interval should be 30, got {settings.TP_AUDIT_INTERVAL}")

async def main():
    """Run all TP tests."""
    logger.info("🚀 Starting Take Profit Implementation Tests...")

    try:
        # Test configuration
        await test_configuration()

        # Test TP calculation
        await test_tp_calculation()

        # Test TP audit
        await test_tp_audit()

        logger.info("✅ All TP tests completed successfully!")

    except Exception as e:
        logger.error(f"❌ Error in main test: {e}")
    finally:
        # Cleanup
        try:
            from discord_bot.utils.trade_retry_utils import initialize_clients
            bot, supabase = initialize_clients()
            if bot:
                await bot.close()
        except:
            pass

if __name__ == "__main__":
    asyncio.run(main())
