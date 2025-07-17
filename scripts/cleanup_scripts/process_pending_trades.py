import asyncio
import logging
import os
import sys
from typing import List

# Add the project root to the Python path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from dotenv import load_dotenv
from supabase import create_client, Client
from discord_bot.discord_bot import DiscordBot

# --- Setup ---
load_dotenv()
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- Supabase Client ---
url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_KEY")
if not url or not key:
    logging.error("Supabase URL or Key not found. Please set SUPABASE_URL and SUPABASE_KEY in your .env file.")
    sys.exit(1)

supabase: Client = create_client(url, key)
bot = DiscordBot()

async def process_pending_trades_for_july_9_and_10():
    """
    Fetches and processes all trades from the database with a 'pending' status
    for July 9th and 10th, 2024.
    """
    logging.info("--- Starting Pending Trade Processing for July 9th & 10th ---")

    try:
        # 1. Fetch all trades with 'pending' status for July 9th and 10th
        start_date = "2025-07-14T00:00:00.000Z"
        end_date = "2025-07-15T23:59:59.999Z"

        # binance_response is a text field, I want to process if empty
        response = (
            supabase.from_("trades")
            .select("*")
            .eq("binance_response", "")
            .gte("timestamp", start_date)
            .execute()
        )

        if not response.data:
            logging.info("No pending trades found for July 9th and 10th.")
            return

        pending_trades = response.data
        logging.info(f"Found {len(pending_trades)} pending trades. Processing now...")

    except Exception as e:
        logging.error(f"Error fetching pending trades from Supabase: {e}")
        return

    # 2. Process each pending trade
    for trade in pending_trades:
        logging.info(f"\nProcessing initial signal for trade DB ID: {trade.get('id')}, Discord ID: {trade.get('discord_id')}")
        try:
            # Construct the signal payload from the database row
            signal_payload = {
                "timestamp": trade.get("timestamp"),
                "content": trade.get("content"),
                "discord_id": trade.get("discord_id"),
                "trader": trade.get("trader"),
                "structured": trade.get("structured"),
            }

            await bot.process_initial_signal(signal_payload)
            logging.info(f"Successfully processed trade {trade.get('id')}.")

        except Exception as e:
            logging.error(f"Error processing initial signal for trade {trade.get('id')}: {e}", exc_info=True)

        logging.info("--- Waiting 10 seconds before processing next row ---")
        await asyncio.sleep(10)


async def main():
    """Main function to run the pending trade processing."""
    await process_pending_trades_for_july_9_and_10()
    logging.info("\n--- Pending Trade Processing Complete ---")

if __name__ == "__main__":
    asyncio.run(main())