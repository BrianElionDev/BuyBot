import asyncio
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Dict, Any, List

# Add project root to the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
from supabase import create_client, Client

# It's better to import the bot instance directly if it's designed to be a singleton
from discord_bot.discord_bot import discord_bot
from discord_bot.models import InitialDiscordSignal, DiscordUpdateSignal

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

async def process_june_trades():
    """
    Fetches and processes all trades from June 2025.
    """
    logging.info("--- Starting Historical Trade Processing for June 2025 ---")

    # 1. Fetch all trades from June
    start_date = '2025-07-01T00:00:00.000Z'
    end_date = '2025-07-31T23:59:59.999Z'

    try:
        response = supabase.from_("trades").select("*").gte("timestamp", start_date).lte("timestamp", end_date).execute()
        if not response.data:
            logging.info("No trades found for June 2025.")
            return []

        june_trades = response.data
        logging.info(f"Found {len(june_trades)} trades from June.")

    except Exception as e:
        logging.error(f"Error fetching trades from Supabase: {e}")
        return []

    # 2. Process each trade as an initial signal
    for trade in june_trades:
        logging.info(f"\nProcessing initial signal for trade ID: {trade.get('id')}, Discord ID: {trade.get('discord_id')}")
        try:
            # We only process if it hasn't been processed already (e.g., status is PENDING or NULL)
            if trade.get('status', 'pending') not in ['pending', None]:
                 logging.info(f"Skipping trade {trade.get('id')} with status '{trade.get('status')}'")
                 continue

            # Construct the signal payload from the database row
            signal_payload = {
                "timestamp": trade.get("timestamp"),
                "content": trade.get("content"),
                "discord_id": trade.get("discord_id"),
                "trader": trade.get("trader"),
                "structured": trade.get("structured"),
            }

            result = await discord_bot.process_initial_signal(signal_payload)
            logging.info(f"Result for trade {trade.get('id')}: {result.get('message')}")

        except Exception as e:
            logging.error(f"Error processing initial signal for trade {trade.get('id')}: {e}", exc_info=True)

        logging.info("--- Waiting 15 seconds before processing next row ---")
        await asyncio.sleep(15)

    return [trade['discord_id'] for trade in june_trades]


async def process_follow_up_alerts(processed_trade_ids: List[str]):
    """
    Fetches and processes all follow-up alerts for the specified trades.
    """
    if not processed_trade_ids:
        logging.info("No trades were processed, so no follow-up alerts to process.")
        return

    logging.info("\n--- Starting Follow-up Alert Processing ---")

    # 1. Fetch all alerts related to the trades we just processed that have not been parsed yet
    try:
        response = supabase.from_("alerts").select("*").in_("trade", processed_trade_ids).is_("parsed_alert", "null").execute()
        if not response.data:
            logging.info("No new/unprocessed follow-up alerts found for the processed trades.")
            return

        alerts = response.data
        logging.info(f"Found {len(alerts)} related follow-up alerts.")

    except Exception as e:
        logging.error(f"Error fetching alerts from Supabase: {e}")
        return

    # 2. Process each alert
    for alert in alerts:
        logging.info(f"\nProcessing follow-up alert for trade Discord ID: {alert.get('trade')}")
        try:
            # Construct the signal payload
            signal_payload = {
                "timestamp": alert.get("timestamp"),
                "content": alert.get("content"),
                "trade": alert.get("trade"), # This is the discord_id of the original trade
                "discord_id": alert.get("discord_id"), # This is the discord_id of the alert message itself
                "trader": alert.get("trader"),
                "structured": alert.get("structured"),
            }

                        # Pass the alert's database ID to the processing function
            result = await discord_bot.process_update_signal(signal_payload)
            logging.info(f"Result for alert {alert.get('id')}: {result.get('message')}")

        except Exception as e:
            logging.error(f"Error processing update signal for alert {alert.get('id')}: {e}", exc_info=True)

        logging.info("--- Waiting 15 seconds before processing next row ---")
        await asyncio.sleep(15)


async def main():
    processed_trade_ids = await process_june_trades()
    await process_follow_up_alerts(processed_trade_ids)
    logging.info("\n--- Historical Data Processing Complete ---")

if __name__ == "__main__":
    asyncio.run(main())