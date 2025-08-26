#!/usr/bin/env python3
"""
Script to remove test trades from the database.
"""

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

import asyncio
import logging
from supabase import create_client
from config import settings

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def remove_test_trades():
    """Remove test trades from the database."""
    try:
        # Initialize Supabase client
        supabase_url = settings.SUPABASE_URL
        supabase_key = settings.SUPABASE_KEY
        if not supabase_url or not supabase_key:
            raise ValueError("SUPABASE_URL and SUPABASE_KEY must be set")
        
        supabase = create_client(supabase_url, supabase_key)
        
        # Find test trades
        response = supabase.from_("trades").select("id, discord_id, exchange_order_id").ilike("discord_id", "%test%").execute()
        
        if not response.data:
            logger.info("No test trades found")
            return
        
        logger.info(f"Found {len(response.data)} test trades:")
        for trade in response.data:
            logger.info(f"  Trade ID: {trade['id']}, Discord ID: {trade['discord_id']}, Order ID: {trade['exchange_order_id']}")
        
        # Delete test trades
        for trade in response.data:
            trade_id = trade['id']
            discord_id = trade['discord_id']
            
            logger.info(f"Deleting test trade {trade_id} with discord_id: {discord_id}")
            
            delete_response = supabase.from_("trades").delete().eq("id", trade_id).execute()
            
            if delete_response.data:
                logger.info(f"Successfully deleted test trade {trade_id}")
            else:
                logger.error(f"Failed to delete test trade {trade_id}")
        
        logger.info("Test trade removal completed!")
        
    except Exception as e:
        logger.error(f"Error removing test trades: {e}")

async def main():
    """Main function."""
    logger.info("Starting test trade removal...")
    await remove_test_trades()

if __name__ == "__main__":
    asyncio.run(main())
