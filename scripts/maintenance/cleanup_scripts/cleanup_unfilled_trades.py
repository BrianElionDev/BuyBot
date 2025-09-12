import asyncio
import logging
import os
import sys
import json

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

async def cleanup_unfilled_trades():
    """
    Scans the trades table for 'OPEN' trades that were never filled (executedQty is 0)
    and updates their status to 'UNFILLED'.
    """
    logging.info("--- Starting Database Cleanup for Unfilled Trades ---")

    try:
        # Fetch all trades that are currently marked as 'OPEN'
        response = supabase.from_("trades").select("id, binance_response").eq("status", "OPEN").execute()

        if response.data is None:
            logging.warning("Could not fetch trades or no 'OPEN' trades found.")
            return

        open_trades = response.data
        logging.info(f"Found {len(open_trades)} trades with 'OPEN' status. Analyzing now...")

        updated_count = 0
        for trade in open_trades:
            trade_id = trade.get('id')
            binance_response_str = trade.get('binance_response')

            if not binance_response_str or not isinstance(binance_response_str, str):
                continue

            try:
                # Parse the JSON response from Binance
                response_json = json.loads(binance_response_str)

                # Check for executed quantity. It's often a string, so we cast to float.
                executed_qty_str = response_json.get('executedQty')
                if executed_qty_str is not None and float(executed_qty_str) == 0.0:
                    logging.info(f"Trade ID {trade_id} was never filled (executedQty is 0). Updating status to 'UNFILLED'.")

                    # Update the trade status in the database
                    update_response = (
                        supabase.from_("trades")
                        .update({"status": "UNFILLED"})
                        .eq("id", trade_id)
                        .execute()
                    )

                    if len(update_response.data) > 0:
                        updated_count += 1
                    else:
                        logging.error(f"Failed to update status for Trade ID {trade_id}.")

            except (json.JSONDecodeError, TypeError, ValueError):
                # Ignore responses that aren't valid JSON (e.g., simple error strings)
                continue

        logging.info("-" * 20)
        logging.info(f"Cleanup complete. Total trades analyzed: {len(open_trades)}")
        logging.info(f"Total trades updated to 'UNFILLED': {updated_count}")
        logging.info("--- Database Cleanup Finished ---")

    except Exception as e:
        logging.error(f"An unexpected error occurred during the cleanup process: {e}", exc_info=True)


async def main():
    await cleanup_unfilled_trades()

if __name__ == "__main__":
    asyncio.run(main())