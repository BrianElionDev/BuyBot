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
    logging.error("Supabase URL or Key not found. Please check your .env file.")
    sys.exit(1)

supabase: Client = create_client(url, key)

def is_price_threshold_error(binance_response: str) -> bool:
    """Check if the binance_response contains a price threshold error."""
    if not binance_response:
        return False

    try:
        # Try to parse as JSON first
        if isinstance(binance_response, str):
            response_data = json.loads(binance_response)
        else:
            response_data = binance_response

        # Check for price threshold error
        if isinstance(response_data, dict):
            error_message = response_data.get('message', '')
            return 'Price difference too high' in error_message

        # Also check as string for the error pattern
        if isinstance(binance_response, str):
            return 'Price difference too high' in binance_response

    except (json.JSONDecodeError, TypeError):
        # If not JSON, check as plain string
        if isinstance(binance_response, str):
            return 'Price difference too high' in binance_response

    return False

async def retry_price_threshold_failures():
    """
    Fetches and retries trades that failed due to price threshold issues.
    """
    logging.info("--- Starting Retry Script for Price Threshold Failures ---")

    try:
        # 1. Fetch all failed trades with pagination
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
        logging.info(f"Found {len(failed_trades)} total failed trades. Analyzing for price threshold errors...")

        # 2. Filter trades that failed due to price threshold issues
        retry_candidates = []
        for trade in failed_trades:
            binance_response = trade.get('binance_response')

            if is_price_threshold_error(binance_response):
                retry_candidates.append(trade)
                logging.info(f"Found price threshold failure: {trade.get('discord_id')} - {trade.get('structured')}")

        if not retry_candidates:
            logging.info("No trades found that failed due to price threshold errors.")
            return

        logging.info(f"Found {len(retry_candidates)} trades to retry. Processing now...")

        # 3. Initialize DiscordBot for processing
        bot = DiscordBot()

        # 4. Process each retry candidate
        success_count = 0
        failed_count = 0

        for trade in retry_candidates:
            try:
                discord_id = trade.get('discord_id')
                structured_signal = trade.get('structured')
                parsed_signal = trade.get('parsed_signal')

                logging.info(f"Retrying trade {discord_id}: {structured_signal}")

                if not structured_signal or not parsed_signal:
                    logging.warning(f"Skipping {discord_id} - missing structured signal or parsed signal")
                    failed_count += 1
                    continue

                # Create initial signal data for retry
                initial_signal_data = {
                    'discord_id': discord_id,
                    'trader': trade.get('trader'),
                    'content': trade.get('content'),
                    'structured': structured_signal,
                    'timestamp': trade.get('timestamp'),
                    'parsed_signal': parsed_signal,
                    'price_threshold_override': 99999  # Effectively disable price check for retry
                }

                # Process the signal with the new logic
                result = await bot.process_initial_signal(initial_signal_data)

                if result.get("status") == "success":
                    success_count += 1
                    logging.info(f"✅ Successfully retried {discord_id}")
                else:
                    failed_count += 1
                    logging.error(f"❌ Failed to retry {discord_id}: {result.get('message')}")

            except Exception as e:
                failed_count += 1
                logging.error(f"❌ Error retrying trade {trade.get('discord_id')}: {e}")

        # 5. Final summary
        logging.info(f"\n--- Retry Summary ---")
        logging.info(f"Successfully retried: {success_count}")
        logging.info(f"Failed to retry: {failed_count}")
        logging.info(f"Total processed: {len(retry_candidates)}")

    except Exception as e:
        logging.error(f"Error in retry_price_threshold_failures: {e}", exc_info=True)

async def main():
    """Main function to run the price threshold retry script."""
    await retry_price_threshold_failures()
    logging.info("\n--- Price Threshold Retry Script Complete ---")

if __name__ == "__main__":
    asyncio.run(main())