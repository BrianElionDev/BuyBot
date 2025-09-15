#!/usr/bin/env python3
"""
Manual script to sync trade statuses with Binance.
This checks all OPEN trades in the database and verifies their actual status on Binance.
"""

import asyncio
import logging
import os
import sys
from datetime import datetime, timedelta, timezone

# Add project root to the Python path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from dotenv import load_dotenv
from discord_bot.utils.trade_retry_utils import initialize_clients, sync_trade_statuses_with_binance

# --- Setup ---
load_dotenv()
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

async def main():
    """Main function to run the trade status sync."""
    logging.info("--- Starting Manual Trade Status Sync ---")

    bot, supabase = initialize_clients()
    if not bot or not supabase:
        logging.error("Failed to initialize clients.")
        return

    try:
        await sync_trade_statuses_with_binance(bot, supabase)
        logging.info("--- Trade Status Sync Complete ---")
    except Exception as e:
        logging.error(f"Error during sync: {e}", exc_info=True)
    finally:
        if bot and bot.binance_exchange:
            await bot.binance_exchange.close()
            logging.info("Binance client connection closed.")

if __name__ == "__main__":
    asyncio.run(main())