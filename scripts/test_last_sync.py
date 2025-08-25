#!/usr/bin/env python3
"""
Test script to verify last sync time functionality.
"""

import asyncio
import logging
from datetime import datetime, timezone

# Add the project root to the path
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from discord_bot.database import DatabaseManager
from discord_bot.discord_bot import DiscordBot

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def test_last_sync():
    """Test the last sync time functionality."""
    bot = DiscordBot()
    db_manager = DatabaseManager(bot.supabase)
    
    # Test 1: Get last sync time
    logger.info("🧪 Testing last sync time...")
    last_sync = await db_manager.get_last_transaction_sync_time()
    
    if last_sync == 0:
        logger.info("✅ Last sync time is 0 (no transactions in database)")
    else:
        dt = datetime.fromtimestamp(last_sync / 1000, tz=timezone.utc)
        logger.info(f"✅ Last sync time: {last_sync} ({dt})")
    
    # Test 2: Check if we have any transactions
    response = db_manager.supabase.from_("transaction_history").select("id").execute()
    count = len(response.data) if response.data else 0
    logger.info(f"📊 Current transaction count: {count}")
    
    if count > 0:
        # Test 3: Show most recent transaction
        recent_response = db_manager.supabase.from_("transaction_history").select("time").order("time", desc=True).limit(1).execute()
        if recent_response.data:
            recent_time = recent_response.data[0]['time']
            logger.info(f"📅 Most recent transaction time: {recent_time}")
    
    logger.info("✅ Last sync test completed")


if __name__ == "__main__":
    asyncio.run(test_last_sync())
