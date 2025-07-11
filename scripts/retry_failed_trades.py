import asyncio
import logging
import os
import sys
from dotenv import load_dotenv
from supabase import create_client, Client

# Add project root to the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from discord_bot.discord_bot import DiscordBot

# --- Setup ---
load_dotenv()
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- Initialize Clients ---
def initialize_clients():
    """Initializes and returns Supabase client and DiscordBot instance."""
    # Supabase
    url: str = os.environ.get("SUPABASE_URL")
    key: str = os.environ.get("SUPABASE_KEY")
    if not url or not key:
        raise ValueError("Supabase credentials not found.")
    supabase: Client = create_client(url, key)

    # DiscordBot (which contains the TradingEngine)
    bot = DiscordBot()

    return supabase, bot

async def retry_failed_trades():
    """
    Finds and retries trades that failed due to cooldowns.
    """
    logging.info("--- Starting Failed Trade Retry Script ---")

    try:
        supabase, bot = initialize_clients()
    except ValueError as e:
        logging.error(f"Failed to initialize clients: {e}")
        return

    # 1. Define the error pattern to search for, matching the user's successful SQL query.
    # The '%' is a wildcard that matches any sequence of characters (e.g., the coin symbol).
    cooldown_pattern = "Trade cooldown active for%"

    # 2. Fetch all trades matching the failure reason
    try:
        logging.info(f"Searching for trades where binance_response LIKE '{cooldown_pattern}'")
        response = supabase.from_("trades").select("*").like("binance_response", cooldown_pattern).execute()

        if not response.data:
            logging.info("✅ No trades found that failed due to a cooldown.")
            return

        failed_trades = response.data
        logging.info(f"Found {len(failed_trades)} failed trade(s) to retry.")

    except Exception as e:
        logging.error(f"Failed to fetch failed trades from Supabase: {e}")
        return

    # 3. Iterate through failed trades and re-process them
    for trade in failed_trades:
        trade_id = trade.get('id')
        discord_id = trade.get('discord_id')
        logging.info(f"--- Retrying trade ID: {trade_id} (Discord ID: {discord_id}) ---")

        # Reconstruct the original signal payload
        signal_data = {
            "timestamp": trade.get("timestamp"),
            "content": trade.get("content"),
            "discord_id": discord_id,
            "trader": trade.get("trader"),
            "structured": trade.get("structured"),
        }

        # Check if all necessary data is present
        if not all(signal_data.values()):
            logging.error(f"Skipping trade ID {trade_id} due to missing data in the database row.")
            continue

        try:
            # Re-process the signal
            result = await bot.process_initial_signal(signal_data)

            if result.get("status") == "success":
                logging.info(f"✅ Successfully re-processed trade ID {trade_id}. New status: OPEN")
            else:
                logging.error(f"❌ Failed to re-process trade ID {trade_id}. Reason: {result.get('message')}")

        except Exception as e:
            logging.error(f"An unexpected error occurred while retrying trade ID {trade_id}: {e}", exc_info=True)

    logging.info("--- Failed Trade Retry Script Finished ---")

if __name__ == "__main__":
    asyncio.run(retry_failed_trades())



