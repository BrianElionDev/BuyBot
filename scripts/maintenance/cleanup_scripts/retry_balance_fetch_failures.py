import asyncio
import logging
import os
import sys
import json
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

def is_balance_fetch_error(binance_response: str) -> bool:
    """Check if the binance_response contains a balance fetch error."""
    if not binance_response:
        return False

    # Check for the specific balance fetch error
    if isinstance(binance_response, str):
        return 'Failed to get account balances from Binance Futures' in binance_response

    return False

async def retry_failed_trades():
    """
    Fetches and retries trades that failed due to balance fetch errors.
    """
    logging.info("--- Starting Retry Script for Balance Fetch Failures ---")

    try:
        # 1. Fetch all failed trades with pagination (no date filter)
        all_failed_trades = []
        page = 0
        page_size = 1000

        while True:
            response = (
                supabase.from_("trades")
                .select("*")
                .eq("status", "FAILED")
                .range(page * page_size, (page + 1) * page_size - 1)
                .execute()
            )

            if not response.data:
                break

            all_failed_trades.extend(response.data)
            logging.info(f"Fetched page {page + 1}: {len(response.data)} trades")

            # If we got less than page_size, we've reached the end
            if len(response.data) < page_size:
                break

            page += 1

        if not all_failed_trades:
            logging.info("No failed trades found.")
            return

        failed_trades = all_failed_trades
        logging.info(f"Found {len(failed_trades)} total failed trades. Analyzing for balance fetch errors...")

        # 2. Filter trades that failed due to balance fetch error
        retry_candidates = []
        for trade in failed_trades:
            binance_response = trade.get('binance_response', '')

            if is_balance_fetch_error(binance_response):
                logging.info(f"Trade {trade.get('id')} failed due to balance fetch error - adding to retry list")
                retry_candidates.append(trade)

        if not retry_candidates:
            logging.info("No trades found that failed due to balance fetch errors.")
            return

        logging.info(f"Found {len(retry_candidates)} trades to retry. Processing now...")

    except Exception as e:
        logging.error(f"Error fetching failed trades from Supabase: {e}")
        return

    # 3. Process each retry candidate
    for i, trade in enumerate(retry_candidates, 1):
        trade_id = trade.get('id')
        discord_id = trade.get('discord_id')
        original_response = trade.get('binance_response', '')

        logging.info(f"\n--- Processing retry {i}/{len(retry_candidates)} ---")
        logging.info(f"Trade DB ID: {trade_id}, Discord ID: {discord_id}")
        logging.info(f"Original error: {original_response[:200]}...")

        try:
            # Clear the binance_response to allow reprocessing
            supabase.from_("trades").update({
                "binance_response": "",
                "status": "PENDING"
            }).eq("id", trade_id).execute()

            # Construct the signal payload from the database row
            signal_payload = {
                "timestamp": trade.get("timestamp"),
                "content": trade.get("content"),
                "discord_id": trade.get("discord_id"),
                "trader": trade.get("trader"),
                "structured": trade.get("structured"),
            }

            # Validate required fields
            if not all([signal_payload["content"], signal_payload["discord_id"], signal_payload["trader"]]):
                logging.error(f"Skipping trade {trade_id} - missing required fields")
                continue

            logging.info(f"Retrying initial signal for trade {trade_id}...")
            await bot.process_initial_signal(signal_payload)
            logging.info(f"✅ Successfully retried trade {trade_id}.")

        except Exception as e:
            logging.error(f"Error retrying trade {trade_id}: {e}", exc_info=True)
            # Mark as failed again with the new error
            supabase.from_("trades").update({
                "status": "FAILED",
                "binance_response": json.dumps({"error": f"Retry failed: {str(e)}"})
            }).eq("id", trade_id).execute()

        # Wait between retries to avoid rate limiting
        if i < len(retry_candidates):
            logging.info("--- Waiting 15 seconds before next retry ---")
            await asyncio.sleep(15)

async def main():
    """Main function to run the balance fetch retry script."""
    await retry_failed_trades()
    logging.info("\n--- Balance Fetch Retry Script Complete ---")

if __name__ == "__main__":
    asyncio.run(main())