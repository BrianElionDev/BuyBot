#!/usr/bin/env python3
"""
Debug script to analyze what's in the binance_response field for recent trades.
"""

import asyncio
import logging
import sys
import os
import json
from datetime import datetime, timedelta, timezone

# Add the project root to Python path
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(script_dir))
sys.path.insert(0, project_root)

from discord_bot.discord_bot import DiscordBot

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def debug_order_responses():
    """
    Debug what's in the binance_response field for recent trades.
    """
    logger.info("🔍 Debugging Order Responses")
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

        # Analyze binance_response field
        trades_with_response = []
        trades_without_response = []
        trades_with_order_id = []
        trades_without_order_id = []

        for trade in trades:
            trade_id = trade.get('id')
            binance_response = trade.get('binance_response')
            exchange_order_id = trade.get('exchange_order_id')

            if binance_response:
                trades_with_response.append(trade)

                # Try to parse the response
                try:
                    if isinstance(binance_response, str):
                        response_data = json.loads(binance_response)
                    else:
                        response_data = binance_response

                    order_id = response_data.get('orderId') or response_data.get('order_id')
                    if order_id:
                        trades_with_order_id.append(trade)
                        logger.info(f"✅ Trade {trade_id}: Found orderId {order_id} in binance_response")
                    else:
                        trades_without_order_id.append(trade)
                        logger.warning(f"❌ Trade {trade_id}: No orderId in binance_response")
                        logger.warning(f"   Response keys: {list(response_data.keys()) if isinstance(response_data, dict) else 'Not a dict'}")

                        # Show first 200 chars of response for debugging
                        response_str = str(binance_response)
                        logger.warning(f"   Response preview: {response_str[:200]}...")

                except Exception as e:
                    logger.error(f"❌ Trade {trade_id}: Error parsing binance_response: {e}")
                    logger.error(f"   Raw response: {binance_response}")
            else:
                trades_without_response.append(trade)

        logger.info(f"📊 Analysis Results:")
        logger.info(f"  - Trades with binance_response: {len(trades_with_response)}")
        logger.info(f"  - Trades without binance_response: {len(trades_without_response)}")
        logger.info(f"  - Trades with orderId in response: {len(trades_with_order_id)}")
        logger.info(f"  - Trades without orderId in response: {len(trades_without_order_id)}")

        # Show examples of successful responses
        if trades_with_order_id:
            logger.info("\n📋 Examples of successful responses:")
            for trade in trades_with_order_id[:3]:
                trade_id = trade.get('id')
                binance_response = trade.get('binance_response')
                exchange_order_id = trade.get('exchange_order_id')

                try:
                    if isinstance(binance_response, str):
                        response_data = json.loads(binance_response)
                    else:
                        response_data = binance_response

                    logger.info(f"  Trade {trade_id}:")
                    logger.info(f"    - orderId: {response_data.get('orderId')}")
                    logger.info(f"    - symbol: {response_data.get('symbol')}")
                    logger.info(f"    - status: {response_data.get('status')}")
                    logger.info(f"    - exchange_order_id in DB: {exchange_order_id}")
                    logger.info(f"    - Match: {'✅' if str(response_data.get('orderId')) == str(exchange_order_id) else '❌'}")
                except Exception as e:
                    logger.error(f"    Error parsing response: {e}")

        # Show examples of failed responses
        if trades_without_order_id:
            logger.info("\n❌ Examples of failed responses:")
            for trade in trades_without_order_id[:3]:
                trade_id = trade.get('id')
                binance_response = trade.get('binance_response')

                logger.info(f"  Trade {trade_id}:")
                logger.info(f"    - Response type: {type(binance_response)}")
                if isinstance(binance_response, str):
                    logger.info(f"    - Response length: {len(binance_response)}")
                    logger.info(f"    - Response preview: {binance_response[:200]}...")
                else:
                    logger.info(f"    - Response: {binance_response}")

        return True

    except Exception as e:
        logger.error(f"❌ Error debugging order responses: {e}")
        return False

async def main():
    """Main function."""
    logger.info("🔍 Order Response Debug Script")
    logger.info("=" * 50)

    success = await debug_order_responses()

    if success:
        logger.info("✅ Debug completed")
    else:
        logger.error("❌ Debug failed")

if __name__ == "__main__":
    asyncio.run(main())
