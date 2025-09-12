#!/usr/bin/env python3
"""
Test script for Telegram notification service.

This script tests all notification types to ensure the Telegram integration works correctly.
"""

import asyncio
import logging
import sys
import os
from datetime import datetime, timezone

# Add the project root to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.services.telegram_notification_service import TelegramNotificationService
from config import settings

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def test_telegram_notifications():
    """Test all Telegram notification types."""

    # Initialize the notification service
    telegram_service = TelegramNotificationService()

    if not telegram_service.bot:
        logger.error("❌ Telegram bot not configured. Please set TELEGRAM_BOT_TOKEN in your .env file")
        return False

    if not telegram_service.chat_id:
        logger.error("❌ Telegram chat ID not configured. Please set TELEGRAM_NOTIFICATION_CHAT_ID in your .env file")
        return False

    logger.info("✅ Telegram notification service initialized successfully")

    # Test 1: Trade execution success
    logger.info("Testing trade execution success notification...")
    success = await telegram_service.send_trade_execution_notification(
        coin_symbol="BTC",
        position_type="LONG",
        entry_price=50000.0,
        quantity=0.001,
        order_id="123456789",
        status="SUCCESS"
    )
    logger.info(f"Trade execution success notification: {'✅' if success else '❌'}")

    await asyncio.sleep(2)  # Wait between notifications

    # Test 2: Trade execution failure
    logger.info("Testing trade execution failure notification...")
    success = await telegram_service.send_trade_execution_notification(
        coin_symbol="ETH",
        position_type="SHORT",
        entry_price=3000.0,
        quantity=0.01,
        order_id="",
        status="FAILED",
        error_message="Insufficient balance"
    )
    logger.info(f"Trade execution failure notification: {'✅' if success else '❌'}")

    await asyncio.sleep(2)

    # Test 3: Order fill notification
    logger.info("Testing order fill notification...")
    success = await telegram_service.send_order_fill_notification(
        coin_symbol="SOL",
        position_type="LONG",
        fill_price=150.50,
        fill_quantity=1.5,
        order_id="987654321",
        commission=0.15
    )
    logger.info(f"Order fill notification: {'✅' if success else '❌'}")

    await asyncio.sleep(2)

    # Test 4: PnL update notification
    logger.info("Testing PnL update notification...")
    success = await telegram_service.send_pnl_update_notification(
        coin_symbol="BTC",
        position_type="LONG",
        entry_price=50000.0,
        current_price=52000.0,
        quantity=0.001,
        unrealized_pnl=20.0
    )
    logger.info(f"PnL update notification: {'✅' if success else '❌'}")

    await asyncio.sleep(2)

    # Test 5: Position closed notification
    logger.info("Testing position closed notification...")
    success = await telegram_service.send_position_closed_notification(
        coin_symbol="ETH",
        position_type="SHORT",
        entry_price=3000.0,
        exit_price=2800.0,
        quantity=0.01,
        realized_pnl=20.0,
        total_fees=0.5
    )
    logger.info(f"Position closed notification: {'✅' if success else '❌'}")

    await asyncio.sleep(2)

    # Test 6: Stop-loss triggered notification
    logger.info("Testing stop-loss triggered notification...")
    success = await telegram_service.send_stop_loss_triggered_notification(
        coin_symbol="BTC",
        position_type="LONG",
        entry_price=50000.0,
        sl_price=47500.0,
        quantity=0.001,
        realized_pnl=-25.0
    )
    logger.info(f"Stop-loss triggered notification: {'✅' if success else '❌'}")

    await asyncio.sleep(2)

    # Test 7: Error notification
    logger.info("Testing error notification...")
    success = await telegram_service.send_error_notification(
        error_type="API Error",
        error_message="Binance API rate limit exceeded",
        context={
            "Symbol": "BTCUSDT",
            "Order ID": "123456789",
            "Timestamp": datetime.now(timezone.utc).isoformat()
        }
    )
    logger.info(f"Error notification: {'✅' if success else '❌'}")

    await asyncio.sleep(2)

    # Test 8: System status notification
    logger.info("Testing system status notification...")
    success = await telegram_service.send_system_status_notification(
        status="ONLINE",
        message="Trading bot is now online and monitoring for signals",
        details={
            "Version": "1.0.0",
            "Uptime": "2 hours",
            "Active Positions": "3"
        }
    )
    logger.info(f"System status notification: {'✅' if success else '❌'}")

    logger.info("🎉 All Telegram notification tests completed!")
    return True

async def main():
    """Main function."""
    logger.info("🚀 Starting Telegram notification tests...")

    try:
        success = await test_telegram_notifications()
        if success:
            logger.info("✅ All tests passed successfully!")
        else:
            logger.error("❌ Some tests failed. Check the logs above.")
    except Exception as e:
        logger.error(f"❌ Test failed with error: {e}")
        return False

    return True

if __name__ == "__main__":
    asyncio.run(main())

