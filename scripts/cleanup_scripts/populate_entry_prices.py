import asyncio
import logging
import os
import sys
import json
from typing import List, Dict, Any, Optional

# Add the project root to the Python path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from dotenv import load_dotenv
from supabase import create_client, Client

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

def extract_entry_price_from_parsed_signal(parsed_signal: Dict[str, Any]) -> Optional[float]:
    """
    Extract entry price from parsed_signal JSON.
    Returns the first entry price from entry_prices array or None if not found.
    """
    if not parsed_signal:
        return None

    try:
        # Check if entry_prices exists and has values
        entry_prices = parsed_signal.get('entry_prices')
        if entry_prices and isinstance(entry_prices, list) and len(entry_prices) > 0:
            entry_price = entry_prices[0]
            if isinstance(entry_price, (int, float)):
                return float(entry_price)

        # Fallback: check for single entry_price field
        entry_price = parsed_signal.get('entry_price')
        if entry_price and isinstance(entry_price, (int, float)):
            return float(entry_price)

    except (ValueError, TypeError) as e:
        logging.warning(f"Failed to extract entry price from parsed_signal: {e}")

    return None

async def populate_entry_prices():
    """
    Populate entry_price column from parsed_signal JSON for records before July 11th.
    """
    logging.info("--- Starting Entry Price Population Script (Before July 11th) ---")

    try:
        # 1. Fetch all trades before July 11th with pagination
        all_trades = []
        page = 0
        page_size = 1000
        cutoff_date = "2025-07-11T00:00:00.000Z"

        while True:
            response = (
                supabase.from_("trades")
                .select("*")
                .gte("createdAt", cutoff_date)
                .range(page * page_size, (page + 1) * page_size - 1)
                .execute()
            )

            if not response.data:
                break

            all_trades.extend(response.data)
            logging.info(f"Fetched page {page + 1}: {len(response.data)} trades")

            # If we got less than page_size, we've reached the end
            if len(response.data) < page_size:
                break

            page += 1

        if not all_trades:
            logging.info("No trades found before July 11th.")
            return

        logging.info(f"Found {len(all_trades)} total trades before July 11th. Processing...")

        # 2. Process trades and extract entry prices
        updates_needed = []
        skipped_count = 0
        error_count = 0

        for trade in all_trades:
            trade_id = trade.get('id')
            discord_id = trade.get('discord_id')
            current_entry_price = trade.get('entry_price')
            parsed_signal = trade.get('parsed_signal')

            # Skip if already has entry_price
            if current_entry_price and current_entry_price > 0:
                skipped_count += 1
                continue

            # Skip if no parsed_signal
            if not parsed_signal:
                skipped_count += 1
                continue

            # Extract entry price from parsed_signal
            entry_price = extract_entry_price_from_parsed_signal(parsed_signal)

            if entry_price and entry_price > 0:
                updates_needed.append({
                    'id': trade_id,
                    'discord_id': discord_id,
                    'entry_price': entry_price,
                    'coin_symbol': parsed_signal.get('coin_symbol', 'Unknown')
                })
                logging.info(f"Will update {discord_id} ({parsed_signal.get('coin_symbol', 'Unknown')}): {entry_price}")
            else:
                error_count += 1
                logging.warning(f"No valid entry price found for {discord_id}")

        logging.info(f"\nProcessing Summary:")
        logging.info(f"Total trades: {len(all_trades)}")
        logging.info(f"Already have entry_price: {skipped_count}")
        logging.info(f"No parsed_signal: {error_count}")
        logging.info(f"Updates needed: {len(updates_needed)}")

        if not updates_needed:
            logging.info("No entry prices to update.")
            return

        # 3. Update the database
        success_count = 0
        failed_count = 0

        for update in updates_needed:
            try:
                response = (
                    supabase.from_("trades")
                    .update({"entry_price": update['entry_price']})
                    .eq("id", update['id'])
                    .execute()
                )

                if response.data:
                    success_count += 1
                    logging.info(f"✓ Updated {update['discord_id']} ({update['coin_symbol']}): {update['entry_price']}")
                else:
                    failed_count += 1
                    logging.error(f"✗ Failed to update {update['discord_id']}")

            except Exception as e:
                failed_count += 1
                logging.error(f"✗ Error updating {update['discord_id']}: {e}")

        # 4. Final summary
        logging.info(f"\n--- Update Summary ---")
        logging.info(f"Successfully updated: {success_count}")
        logging.info(f"Failed to update: {failed_count}")
        logging.info(f"Total processed: {len(updates_needed)}")

    except Exception as e:
        logging.error(f"Error in populate_entry_prices: {e}", exc_info=True)

async def main():
    """Main function to run the entry price population script."""
    await populate_entry_prices()
    logging.info("\n--- Entry Price Population Script Complete ---")

if __name__ == "__main__":
    asyncio.run(main())