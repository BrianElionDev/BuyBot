#!/usr/bin/env python3
"""
Reprocess Alert 3719 Script

This script reprocesses the specific alert ID 3719 that has the coin symbol issue.
"""

import os
import sys
import asyncio
import logging
from dotenv import load_dotenv
from supabase import create_client, Client

# Add the project root to Python path
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(os.path.dirname(script_dir)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from discord_bot.discord_bot import DiscordBot

# Setup logging
load_dotenv()
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def reprocess_alert_3719():
    """Reprocess the specific alert ID 3719"""
    logger.info("=== Reprocessing Alert ID 3719 ===")

    # Initialize Supabase
    supabase = create_client(os.getenv('SUPABASE_URL'), os.getenv('SUPABASE_KEY'))

    # Initialize DiscordBot
    bot = DiscordBot()

    try:
        # Get the specific alert
        response = supabase.table("alerts").select("*").eq("id", 3719).execute()

        if not response.data:
            logger.error("Alert ID 3719 not found")
            return

        alert = response.data[0]
        logger.info(f"Found alert: {alert['content']}")
        logger.info(f"Current status: {alert['status']}")
        logger.info(f"Current binance_response: {alert.get('binance_response')}")

        # Reset the alert status to allow reprocessing
        reset_response = supabase.table("alerts").update({
            "status": "PENDING",
            "binance_response": None,
            "processed_at": None
        }).eq("id", 3719).execute()

        if reset_response.data:
            logger.info("✅ Reset alert status to PENDING")
        else:
            logger.error("❌ Failed to reset alert status")
            return

        # Now reprocess the alert
        logger.info("Reprocessing alert...")

        # Create signal payload
        signal_payload = {
            "timestamp": alert.get("timestamp"),
            "content": alert.get("content"),
            "trade": alert.get("trade"),
            "discord_id": alert.get("discord_id"),
            "trader": alert.get("trader"),
            "structured": alert.get("structured"),
        }

        # Process the alert
        result = await bot.process_update_signal(signal_payload)

        logger.info(f"Processing result: {result}")

        # Get the updated alert
        updated_response = supabase.table("alerts").select("*").eq("id", 3719).execute()
        if updated_response.data:
            updated_alert = updated_response.data[0]
            logger.info(f"Updated status: {updated_alert['status']}")
            logger.info(f"Updated binance_response: {updated_alert.get('binance_response')}")

    except Exception as e:
        logger.error(f"Error reprocessing alert: {e}")
    finally:
        # Clean up
        await bot.close()

async def main():
    """Main entry point"""
    await reprocess_alert_3719()

if __name__ == "__main__":
    asyncio.run(main())
