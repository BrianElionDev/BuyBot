import asyncio
import logging
import os
import sys
import json
import re
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

def is_memecoin_quantity_error(binance_response: str) -> bool:
    """Check if the binance_response contains a memecoin quantity/price error."""
    if not binance_response:
        return False

    # Check for the specific error patterns
    if isinstance(binance_response, str):
        return ('Failed to get price for' in binance_response and
                any(char.isdigit() for char in binance_response.split('Failed to get price for')[-1]))

    return False

def extract_quantity_from_signal(structured_signal: str) -> tuple:
    """
    Extract quantity and coin symbol from signals like "1000TOSHI|Entry:|0.7172|SL:|0.692"
    Returns: (quantity, coin_symbol, cleaned_signal)
    """
    if not structured_signal:
        return None, None, structured_signal

    # Common memecoin patterns with known symbols
    memecoin_patterns = [
        (r'^(\d+)(PEPE)', 'PEPE'),
        (r'^(\d+)(TOSHI)', 'TOSHI'),
        (r'^(\d+)(TURBO)', 'TURBO'),
        (r'^(\d+)(FARTCOIN)', 'FARTCOIN'),
        (r'^(\d+)(HYPE)', 'HYPE'),
        (r'^(\d+)(DOGE)', 'DOGE'),
        (r'^(\d+)(SHIB)', 'SHIB'),
        (r'^(\d+)(BONK)', 'BONK'),
        (r'^(\d+)(WIF)', 'WIF'),
        (r'^(\d+)(FLOKI)', 'FLOKI'),
        # Generic pattern for other coins (less greedy)
        (r'^(\d+)([A-Z]{2,10})', None),  # 2-10 uppercase letters
    ]

    for pattern, expected_symbol in memecoin_patterns:
        match = re.match(pattern, structured_signal)
        if match:
            quantity = int(match.group(1))
            coin_symbol = match.group(2)

            # Use expected symbol if provided, otherwise use matched symbol
            final_symbol = expected_symbol if expected_symbol else coin_symbol

            # Remove the quantity prefix from the signal
            cleaned_signal = structured_signal.replace(f"{quantity}{coin_symbol}", final_symbol, 1)
            return quantity, final_symbol, cleaned_signal

    return None, None, structured_signal

async def retry_failed_trades():
    """
    Fetches and retries trades that failed due to memecoin quantity/price confusion.
    """
    logging.info("--- Starting Retry Script for Memecoin Quantity Failures ---")

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
        logging.info(f"Found {len(failed_trades)} total failed trades. Analyzing for memecoin quantity errors...")

        # 2. Filter trades that failed due to memecoin quantity error
        retry_candidates = []
        for trade in failed_trades:
            binance_response = trade.get('binance_response', '')
            structured_signal = trade.get('structured', '')

            if is_memecoin_quantity_error(binance_response):
                # Check if the structured signal has a quantity prefix
                quantity, coin_symbol, cleaned_signal = extract_quantity_from_signal(structured_signal)
                if quantity and coin_symbol:
                    logging.info(f"Trade {trade.get('id')} failed due to memecoin quantity error - {quantity}{coin_symbol} detected")
                    retry_candidates.append((trade, quantity, coin_symbol, cleaned_signal))

        if not retry_candidates:
            logging.info("No trades found that failed due to memecoin quantity errors.")
            return

        logging.info(f"Found {len(retry_candidates)} trades to retry. Processing now...")

    except Exception as e:
        logging.error(f"Error fetching failed trades from Supabase: {e}")
        return

    # 3. Process each retry candidate
    for i, (trade, quantity, coin_symbol, cleaned_signal) in enumerate(retry_candidates, 1):
        trade_id = trade.get('id')
        discord_id = trade.get('discord_id')
        original_response = trade.get('binance_response', '')

        logging.info(f"\n--- Processing retry {i}/{len(retry_candidates)} ---")
        logging.info(f"Trade DB ID: {trade_id}, Discord ID: {discord_id}")
        logging.info(f"Original error: {original_response[:200]}...")
        logging.info(f"Detected quantity: {quantity} {coin_symbol}")
        logging.info(f"Cleaned signal: {cleaned_signal}")

        try:
            # Update the structured signal to remove the quantity prefix
            supabase.from_("trades").update({
                "binance_response": "",
                "status": "PENDING",
                "structured": cleaned_signal
            }).eq("id", trade_id).execute()

            # Construct the signal payload from the database row
            signal_payload = {
                "timestamp": trade.get("timestamp"),
                "content": trade.get("content"),
                "discord_id": trade.get("discord_id"),
                "trader": trade.get("trader"),
                "structured": cleaned_signal,  # Use the cleaned signal
            }

            # Validate required fields
            if not all([signal_payload["content"], signal_payload["discord_id"], signal_payload["trader"]]):
                logging.error(f"Skipping trade {trade_id} - missing required fields")
                continue

            logging.info(f"Retrying initial signal for trade {trade_id} with cleaned format...")
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
    """Main function to run the memecoin quantity retry script."""
    await retry_failed_trades()
    logging.info("\n--- Memecoin Quantity Retry Script Complete ---")

if __name__ == "__main__":
    asyncio.run(main())