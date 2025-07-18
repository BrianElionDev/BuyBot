import asyncio
import logging
import os
import sys
from typing import List

# Add project root to the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
from supabase import create_client, Client
from discord_bot.discord_bot import DiscordBot

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
bot = DiscordBot()

async def process_july_trades() -> List[str]:
    """
    Fetches and re-processes all trades from July 2024 to apply the latest logic.
    """Activity
    logging.info("--- Starting Historical Trade Processing for July 2024 ---")

    try:
        # 1. Fetch all trades created in July 2024
        response = supabase.from_("trades").select("*").gte(
            "timestamp", "2024-07-01T00:00:00.000Z"
        ).lte(
            "timestamp", "2024-07-31T23:59:59.999Z"
        ).execute()

        if not response.data:
            logging.info("No trades found for July.")
            return []

        july_trades = response.data
        logging.info(f"Found {len(july_trades)} trades from July. Re-processing now...")

    except Exception as e:
        logging.error(f"Error fetching trades from Supabase: {e}")
        return []

    processed_trade_ids = []
    # 2. Process each trade to apply the latest logic
    for trade in july_trades:
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

            # is_historic=True prevents sending new discord messages.
            # trade_id tells the function to UPDATE the existing trade record.
            await bot.process_initial_signal(signal_payload, is_historic=True, trade_id=trade.get("id"))

            processed_trade_ids.append(trade.get("discord_id"))
            logging.info(f"Successfully re-processed trade {trade.get('id')}.")

        except Exception as e:
            logging.error(f"Error processing initial signal for trade {trade.get('id')}: {e}", exc_info=True)

        logging.info("--- Waiting 2 seconds before processing next row ---")
        await asyncio.sleep(2)

    return processed_trade_ids

async def process_follow_up_alerts(processed_trade_ids: List[str]):
    """
    Fetches and processes follow-up alerts for the trades that were just processed.
    """
    logging.info("\n--- Starting Follow-up Alert Processing ---")

    if not processed_trade_ids:
        logging.info("No trades were processed, so no follow-up alerts to check.")
        return

    try:
        # 1. Fetch alerts linked to the processed trades that have NOT been parsed yet.
        response = supabase.from_("alerts").select("*").in_(
            "trade", processed_trade_ids
        ).is_("parsed_alert", "null").execute()

        if not response.data:
            logging.info("No new follow-up alerts to process for the July trades.")
            return

        alerts = response.data
        logging.info(f"Found {len(alerts)} related follow-up alerts. Re-processing now...")

    except Exception as e:
        logging.error(f"Error fetching alerts from Supabase: {e}")
        return

    # 2. Process each alert to apply latest logic
    for alert in alerts:
        logging.info(f"\nProcessing follow-up alert DB ID: {alert.get('id')} for trade Discord ID: {alert.get('trade')}")
        try:
            signal_payload = {
                "timestamp": alert.get("timestamp"),
                "content": alert.get("content"),
                "trade": alert.get("trade"),
                "discord_id": alert.get("discord_id"),
                "trader": alert.get("trader"),
            }

            # Pass the alert's database ID to ensure it UPDATES the existing alert record
            await bot.process_update_signal(signal_payload, is_historic=True, alert_id=alert.get("id"))
            logging.info(f"Successfully re-processed alert {alert.get('id')}")

        except Exception as e:
            logging.error(f"Error processing update signal for alert {alert.get('id')}: {e}", exc_info=True)

        logging.info("--- Waiting 2 seconds before processing next row ---")
        await asyncio.sleep(2)

async def main():
    """Main function to run the historical processing."""
    processed_ids = await process_july_trades()
    await process_follow_up_alerts(processed_ids)
    logging.info("\n--- July Data Processing Complete ---")

if __name__ == "__main__":
    asyncio.run(main())