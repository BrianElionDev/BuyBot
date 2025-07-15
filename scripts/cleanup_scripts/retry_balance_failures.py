import asyncio
import logging
import os
import sys
from dotenv import load_dotenv
from supabase import create_client, Client

# Add project root to the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

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

async def retry_balance_check_failures():
    """
    Finds and retries trades that failed due to the 'Failed to get account balances' error.
    """
    logging.info("--- Starting Retry Script for Balance Check Failures ---")

    try:
        supabase, bot = initialize_clients()
    except ValueError as e:
        logging.error(f"Failed to initialize clients: {e}")
        return

    balance_error_pattern = "%Failed to get account balances from Binance Futures%"

    try:
        logging.info(f"Searching for trades with binance_response matching: '{balance_error_pattern}'")
        response = supabase.from_("trades").select("*").like("binance_response", balance_error_pattern).execute()

        if not response.data:
            logging.info("✅ No trades found that failed due to the balance check error.")
            return

        failed_trades = response.data
        logging.warning(f"Found {len(failed_trades)} trade(s) to retry.")

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

            if not all(signal_data.values()):
                logging.error(f"Skipping trade ID {trade_id} due to missing data.")
                continue

            try:
                result = await bot.process_initial_signal(signal_data)
                if result.get("status") == "success":
                    logging.info(f"✅ Successfully re-processed trade ID {trade_id}.")
                else:
                    logging.error(f"❌ Failed to re-process trade ID {trade_id}. Reason: {result.get('message')}")

            except Exception as e_retry:
                logging.error(f"An unexpected error occurred while retrying trade ID {trade_id}: {e_retry}", exc_info=True)

    except Exception as e_fetch:
        logging.error(f"An error occurred while fetching failed trades: {e_fetch}", exc_info=True)

    logging.info("--- Retry Script Finished ---")

if __name__ == "__main__":
    asyncio.run(retry_balance_check_failures())