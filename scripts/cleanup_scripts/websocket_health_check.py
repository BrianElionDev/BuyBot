#!/usr/bin/env python3
"""
WebSocket Health Check Script
Diagnoses WebSocket connection issues and verifies real-time updates are working.
"""

import os
import sys
import asyncio
import logging
from datetime import datetime, timezone
from dotenv import load_dotenv

# Add the project root to Python path
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(script_dir))
sys.path.insert(0, project_root)

from config import settings
from discord_bot.discord_bot import DiscordBot

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def websocket_health_check():
    """
    Check WebSocket connection health and diagnose issues.
    """
    try:
        # Load environment variables
        load_dotenv()

        logger.info("🔍 WebSocket Health Check Started")
        logger.info("=" * 50)

        # Initialize Discord bot (which includes WebSocket)
        bot = DiscordBot()

        # Test WebSocket connection
        logger.info("📡 Testing WebSocket connection...")

        try:
            await bot.start_websocket_sync()
            logger.info("✅ WebSocket connection established")

            # Wait for messages
            logger.info("⏳ Waiting for WebSocket messages (30 seconds)...")
            await asyncio.sleep(30)

            # Check connection status
            status = bot.get_websocket_status()
            logger.info(f"📊 WebSocket Status: {status}")

            # Test specific functionality
            logger.info("🧪 Testing order status updates...")

            # Get current positions
            positions = await bot.binance_exchange.get_futures_position_information()
            logger.info(f"💰 Current positions: {len(positions)}")

            for position in positions:
                if float(position.get('positionAmt', '0')) != 0:
                    logger.info(f"  - {position.get('symbol')}: {position.get('positionAmt')} @ {position.get('markPrice')}")

            # Get open orders
            orders = await bot.binance_exchange.get_all_open_futures_orders()
            logger.info(f"📋 Open orders: {len(orders)}")

            for order in orders:
                logger.info(f"  - {order.get('symbol')}: {order.get('status')} - {order.get('orderId')}")

        except Exception as e:
            logger.error(f"❌ WebSocket connection failed: {e}")
            return False

        finally:
            # Cleanup
            await bot.close()

        logger.info("✅ WebSocket health check completed")
        return True

    except Exception as e:
        logger.error(f"❌ Health check failed: {e}")
        return False

async def main():
    """Main function."""
    print("🔍 WebSocket Health Check")
    print("=" * 30)

    success = await websocket_health_check()

    if success:
        print("✅ WebSocket is healthy")
    else:
        print("❌ WebSocket has issues - check logs above")

if __name__ == "__main__":
    asyncio.run(main())
