#!/usr/bin/env python3
"""
Fix order ID mapping issues for WebSocket database sync.
This script ensures that trades have the correct exchange_order_id field populated.
"""

import asyncio
import logging
import sys
import os
from datetime import datetime, timedelta, timezone
import json

# Add the project root to Python path
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(script_dir))
sys.path.insert(0, project_root)

from discord_bot.discord_bot import DiscordBot
from config import settings

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def fix_order_id_mapping():
    """
    Fix order ID mapping issues by:
    1. Finding trades without exchange_order_id
    2. Extracting order IDs from binance_response or sync_order_response
    3. Updating the database with correct mappings
    """
    logger.info("🔧 Fixing Order ID Mapping Issues")
    logger.info("=" * 50)

    try:
        # Initialize bot
        bot = DiscordBot()
        supabase = bot.db_manager.supabase

        # Get recent trades (last 7 days)
        cutoff = datetime.now(timezone.utc) - timedelta(days=7)
        cutoff_iso = cutoff.isoformat()

        logger.info(f"Fetching trades from {cutoff_iso}...")

        # Get all recent trades
        response = supabase.from_("trades").select("*").gte("createdAt", cutoff_iso).execute()
        trades = response.data or []

        logger.info(f"Found {len(trades)} recent trades")

        # Analyze trades
        trades_without_order_id = []
        trades_with_order_id = []
        trades_with_binance_response = []
        trades_with_sync_response = []

        for trade in trades:
            trade_id = trade.get('id')
            exchange_order_id = trade.get('exchange_order_id')
            binance_response = trade.get('binance_response')
            sync_order_response = trade.get('sync_order_response')

            if not exchange_order_id:
                trades_without_order_id.append(trade)

                if binance_response:
                    trades_with_binance_response.append(trade)
                if sync_order_response:
                    trades_with_sync_response.append(trade)
            else:
                trades_with_order_id.append(trade)

        logger.info(f"📊 Analysis Results:")
        logger.info(f"  - Trades with order ID: {len(trades_with_order_id)}")
        logger.info(f"  - Trades without order ID: {len(trades_without_order_id)}")
        logger.info(f"  - Trades with binance_response: {len(trades_with_binance_response)}")
        logger.info(f"  - Trades with sync_order_response: {len(trades_with_sync_response)}")

        # Fix trades without order ID
        fixed_count = 0
        for trade in trades_without_order_id:
            trade_id = trade.get('id')
            order_id = None

            # Try to extract from binance_response
            binance_response = trade.get('binance_response')
            if binance_response:
                try:
                    if isinstance(binance_response, str):
                        response_data = json.loads(binance_response)
                    else:
                        response_data = binance_response

                    order_id = response_data.get('orderId') or response_data.get('order_id')
                    if order_id:
                        logger.info(f"Found order ID {order_id} in binance_response for trade {trade_id}")
                except Exception as e:
                    logger.warning(f"Error parsing binance_response for trade {trade_id}: {e}")

            # Try to extract from sync_order_response
            if not order_id:
                sync_order_response = trade.get('sync_order_response')
                if sync_order_response:
                    try:
                        if isinstance(sync_order_response, str):
                            response_data = json.loads(sync_order_response)
                        else:
                            response_data = sync_order_response

                        order_id = response_data.get('orderId') or response_data.get('order_id')
                        if order_id:
                            logger.info(f"Found order ID {order_id} in sync_order_response for trade {trade_id}")
                    except Exception as e:
                        logger.warning(f"Error parsing sync_order_response for trade {trade_id}: {e}")

            # Update database if order ID found
            if order_id:
                try:
                    updates = {
                        'exchange_order_id': str(order_id),
                        'updated_at': datetime.now(timezone.utc).isoformat()
                    }

                    supabase.from_("trades").update(updates).eq("id", trade_id).execute()
                    fixed_count += 1
                    logger.info(f"✅ Fixed trade {trade_id} with order ID {order_id}")
                except Exception as e:
                    logger.error(f"Error updating trade {trade_id}: {e}")
            else:
                logger.warning(f"⚠️ Could not find order ID for trade {trade_id}")

        logger.info(f"🎉 Fixed {fixed_count} trades with order ID mapping")

        # Verify fixes
        logger.info("\n🔍 Verifying fixes...")
        response = supabase.from_("trades").select("*").gte("createdAt", cutoff_iso).execute()
        updated_trades = response.data or []

        trades_with_order_id_after = [t for t in updated_trades if t.get('exchange_order_id')]
        logger.info(f"✅ After fix: {len(trades_with_order_id_after)}/{len(updated_trades)} trades have order ID")

        # Show some examples
        logger.info("\n📋 Example trades with order IDs:")
        for trade in trades_with_order_id_after[:5]:
            logger.info(f"  - Trade {trade.get('id')}: {trade.get('coin_symbol')} - Order ID: {trade.get('exchange_order_id')}")

        return True

    except Exception as e:
        logger.error(f"❌ Error fixing order ID mapping: {e}")
        return False

async def test_websocket_with_fixed_mapping():
    """
    Test WebSocket with fixed order ID mapping.
    """
    logger.info("\n🧪 Testing WebSocket with fixed mapping...")

    try:
        bot = DiscordBot()

        # Start WebSocket
        await bot.start_websocket_sync()
        logger.info("✅ WebSocket started")

        # Wait for 30 seconds to see if we get any execution reports
        logger.info("⏳ Waiting 30 seconds for execution reports...")
        await asyncio.sleep(30)

        # Check status
        status = bot.get_websocket_status()
        logger.info(f"📊 WebSocket Status: {status}")

        # Stop WebSocket
        await bot.close()

        return True

    except Exception as e:
        logger.error(f"❌ Error testing WebSocket: {e}")
        return False

async def main():
    """Main function."""
    logger.info("🔧 Order ID Mapping Fix Script")
    logger.info("=" * 50)

    # Fix order ID mapping
    success = await fix_order_id_mapping()

    if success:
        # Test WebSocket
        await test_websocket_with_fixed_mapping()

    logger.info("✅ Script completed")

if __name__ == "__main__":
    asyncio.run(main())
