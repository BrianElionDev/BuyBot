import asyncio
import logging
import os
import sys

# Add project root to the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
from supabase import create_client, Client

# --- Setup ---
load_dotenv()
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- Supabase Client ---
url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_KEY")
if not url or not key:
    logging.error("Supabase URL or Key not found. Please set SUPABASE_URL and SUPABASE_KEY in your .env file.")
    exit(1)

supabase: Client = create_client(url, key)

async def backfill_signal_type():
    """
    Fetches all trades, extracts the 'position_type' from the 'parsed_signal' JSON,
    and updates the 'signal_type' column.
    """
    logging.info("--- Starting backfill for 'signal_type' column in trades table ---")

    try:
        # 1. Fetch all trades that need updating
        response = supabase.from_("trades").select("id, parsed_signal, signal_type").execute()
        if not response.data:
            logging.info("No trades found in the database.")
            return

        all_trades = response.data
        logging.info(f"Found {len(all_trades)} trades to check.")

    except Exception as e:
        logging.error(f"Error fetching trades from Supabase: {e}", exc_info=True)
        return

    # 2. Process each trade
    updated_count = 0
    for trade in all_trades:
        trade_id = trade.get('id')
        parsed_signal = trade.get('parsed_signal')
        current_signal_type = trade.get('signal_type')

        if not parsed_signal or not isinstance(parsed_signal, dict):
            logging.warning(f"Skipping trade ID {trade_id}: 'parsed_signal' column is empty or invalid.")
            continue

        position_type = parsed_signal.get('position_type')

        if not position_type:
            logging.warning(f"Skipping trade ID {trade_id}: 'position_type' key not found in parsed_signal.")
            continue

        # Only update if the signal_type is not already set correctly
        if str(position_type) != str(current_signal_type):
            try:
                logging.info(f"Updating trade ID {trade_id}: setting signal_type to '{position_type}'.")
                supabase.from_("trades").update({"signal_type": position_type}).eq("id", trade_id).execute()
                updated_count += 1
            except Exception as e:
                logging.error(f"Failed to update trade ID {trade_id}: {e}", exc_info=True)
        else:
            logging.debug(f"Skipping trade ID {trade_id}: 'signal_type' is already set correctly.")

    logging.info(f"--- Backfill complete. Updated {updated_count} trade(s). ---")


async def main():
    await backfill_signal_type()

if __name__ == "__main__":
    asyncio.run(main())