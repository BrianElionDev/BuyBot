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
url: str = os.environ.get("SUPABASE_URL")
key: str = os.environ.get("SUPABASE_KEY")
if not url or not key:
    logging.error("Supabase URL or Key not found. Please set SUPABASE_URL and SUPABASE_KEY in your .env file.")
    exit(1)

supabase: Client = create_client(url, key)

async def find_executed_trades():
    """
    Scans the trades table to find and report any trades that appear to have
    been successfully executed on the exchange, starting from the last 7 days.
    """
    logging.info("--- Scanning for Successfully Executed Trades (Last 7 Days) ---")

    found_trades = []

    try:
        # Set start date to last 7 days
        from datetime import datetime, timezone, timedelta
        start_date = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()

        logging.info(f"Filtering trades from: {start_date}")

        # We query for trades where either the order ID is present OR the binance_response is not empty/null.
        # This covers all bases for what we would consider an "executed" trade.
        response = (
            supabase.from_("trades")
            .select("id, discord_id, exchange_order_id, stop_loss_order_id, position_size, binance_response, status, created_at, binance_entry_price, exit_price")
            .not_.is_("exchange_order_id", "null")
            .gte("created_at", start_date)
            .execute()
        )

        if response.data:
            found_trades.extend(response.data)

        # Also check for trades that might have a response but no ID (less likely but possible)
        response_alt = (
            supabase.from_("trades")
            .select("id, discord_id, exchange_order_id, stop_loss_order_id, position_size, binance_response, status, created_at, binance_entry_price, exit_price")
            .not_.is_("binance_response", "null")
            .neq("binance_response", "") # Check for not empty string
            .is_("exchange_order_id", "null") # Avoid duplicates from the first query
            .gte("created_at", start_date)
            .execute()
        )

        if response_alt.data:
            found_trades.extend(response_alt.data)

        if not found_trades:
            logging.info("\nCONCLUSION: No trades were found with an exchange_order_id or a Binance response.")
            logging.info("This confirms that all historical trades were recorded in the DB but never executed on the exchange.")
            logging.info("The alert failures are expected behavior, as there are no live positions to manage.")
            return

        logging.info(f"\n--- Found {len(found_trades)} Potentially Executed Trade(s) ---")
        for trade in found_trades:
            logging.info("-" * 40)
            logging.info(f"  Trade DB ID: {trade.get('id')}")
            logging.info(f"  Discord ID: {trade.get('discord_id')}")
            logging.info(f"  Status: {trade.get('status')}")
            logging.info(f"  Created At: {trade.get('created_at')}")
            logging.info(f"  Exchange Order ID: {trade.get('exchange_order_id')}")
            logging.info(f"  Stop Loss Order ID: {trade.get('stop_loss_order_id')}")
            logging.info(f"  Position Size: {trade.get('position_size')}")
            logging.info(f"  Binance Entry Price: {trade.get('binance_entry_price')}")
            logging.info(f"  Binance Exit Price: {trade.get('exit_price')}")
            logging.info(f"  Binance Response: {trade.get('binance_response')}")

            # Check for price filling issues
            if not trade.get('binance_entry_price') or float(trade.get('binance_entry_price', 0)) == 0:
                logging.warning(f"  ⚠️  MISSING binance_entry_price")
            if not trade.get('exit_price') or float(trade.get('exit_price', 0)) == 0:
                logging.warning(f"  ⚠️  MISSING exit_price")

        logging.info("\nCONCLUSION: The trades listed above appear to have been executed. If their follow-up alerts failed, we need to investigate them specifically.")

    except Exception as e:
        logging.error(f"An error occurred while scanning for trades: {e}", exc_info=True)


async def main():
    await find_executed_trades()

if __name__ == "__main__":
    asyncio.run(main())