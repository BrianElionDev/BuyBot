import asyncio
import logging
import os
import sys

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

async def retry_whitelist_failures():
    """
    Fetches and re-processes trades that failed due to the static whitelist
    and now might be valid.
    """
    logging.info("--- Starting Whitelist Failure Retry Script ---")

    try:
        # 1. Fetch all trades that failed with the specific whitelist error message.
        # The 'ilike' operator provides a case-insensitive pattern match.
        response = (
            supabase.from_("trades")
            .select("*")
            .eq("status", "FAILED")
            .ilike("binance_response", "Trading pair % not available in futures whitelist")
            .execute()
        )

        if not response.data:
            logging.info("No trades found that failed due to whitelist errors.")
            return

        failed_trades = response.data
        logging.info(f"Found {len(failed_trades)} trades that failed due to whitelist errors. Re-processing now...")

    except Exception as e:
        logging.error(f"Error fetching failed trades from Supabase: {e}")
        return

    # 2. Process each failed trade
    for trade in failed_trades:
        logging.info(f"\nRetrying trade DB ID: {trade.get('id')}, Discord ID: {trade.get('discord_id')}")
        try:
            # Reconstruct the signal payload from the database row.
            # We need the 'structured' field which contains the clean signal.
            signal_payload = {
                "timestamp": trade.get("timestamp"),
                "content": trade.get("content"),
                "discord_id": trade.get("discord_id"),
                "trader": trade.get("trader"),
                "structured": trade.get("structured"),
            }

            # Reset the status to 'pending' in the DB before processing
            # to avoid confusion if the script is run multiple times.
            logging.info(f"Resetting status to 'pending' for trade ID: {trade.get('id')}")
            supabase.from_("trades").update({"status": "pending"}).eq("id", trade.get('id')).execute()


            await bot.process_initial_signal(signal_payload)
            logging.info(f"Successfully re-processed signal for trade {trade.get('id')}.")

        except Exception as e:
            logging.error(f"Error re-processing signal for trade {trade.get('id')}: {e}", exc_info=True)
            # Set status back to FAILED if an unexpected error occurs during retry logic
            supabase.from_("trades").update({"status": "FAILED", "binance_response": f"Retry script failed: {e}"}).eq("id", trade.get('id')).execute()

        logging.info("--- Waiting 10 seconds before processing next trade ---")
        await asyncio.sleep(10)


async def main():
    """Main function to run the retry script."""
    await retry_whitelist_failures()
    logging.info("\n--- Whitelist Failure Retry Script Complete ---")
    await bot.close()


if __name__ == "__main__":
    asyncio.run(main())