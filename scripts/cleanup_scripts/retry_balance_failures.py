import asyncio
import logging
import os
import sys
from dotenv import load_dotenv
from supabase import create_client, Client

# Add project root to the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from discord_bot.discord_bot import DiscordBot

from src.exchange.binance_exchange import BinanceExchange

# --- Setup ---
load_dotenv()
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- Initialize Clients ---
def initialize_clients():
    """Initializes and returns Supabase client and DiscordBot instance."""
    # Supabase
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    if not url or not key:
        raise ValueError("Supabase credentials not found.")
    supabase: Client = create_client(url, key)

    bot = DiscordBot()

    return supabase, bot

async def retry_balance_check_failures():
    """
    Finds and retries trades that failed due to the 'Failed to get account balances' error.
    """
    logging.info("--- Starting Retry Script for Balance Check Failures ---")

    try:
        supabase, bot = initialize_clients()
    except ValueError as e:
        logging.error(f"Failed to initialize clients: {e}")
        return

    balance_error_pattern = "%Failed to get account balances from Binance Futures%"

    try:
        logging.info(f"Searching for trades with binance_response matching: '{balance_error_pattern}'")
        # parsed_alert is empty
        response = supabase.from_("trades").select("*").eq("status", "FAILED").gte("timestamp", "2025-07-15T13:26:38.192Z").execute()

        if not response.data:
            logging.info("✅ No trades found that failed due to the balance check error.")
            return

        failed_trades = response.data
        logging.warning(f"Found {len(failed_trades)} trade(s) to retry.")

        for trade in failed_trades:
            trade_id = trade.get('id')
            discord_id = trade.get('discord_id')
            logging.info(f"--- Retrying trade ID: {trade_id} (Discord ID: {discord_id}) ---")

            # Reconstruct the original signal payload
            signal_data = {
                "timestamp": trade.get("timestamp"),
                "content": trade.get("content"),
                "discord_id": discord_id,
                "trader": trade.get("trader"),
                "structured": trade.get("structured"),
            }

            if not all(signal_data.values()):
                logging.error(f"Skipping trade ID {trade_id} due to missing data.")
                continue

            try:
                # --- 1. Re-process the initial signal ---
                logging.info(f"--- (1/2) Re-processing initial signal for trade {trade_id} ---")
                result = await bot.process_initial_signal(signal_data)
                if result.get("status") == "success":
                    logging.info(f"✅ Successfully re-processed initial signal for trade ID {trade_id}.")
                else:
                    logging.error(f"❌ Failed to re-process initial signal for trade ID {trade_id}. Reason: {result.get('message')}")

                # --- 2. Fetch and process associated alerts ---
                logging.info(f"--- (2/2) Searching for alerts associated with trade {discord_id} ---")
                alert_response = supabase.from_("alerts").select("*").eq("trade", discord_id).execute()
                alerts = alert_response.data

                if not alerts:
                    logging.info("✅ No corresponding alerts found for this trade.")
                else:
                    logging.info(f"Found {len(alerts)} alert(s) to process.")
                    # Sort alerts by timestamp to process them in chronological order
                    for alert in sorted(alerts, key=lambda x: x.get('timestamp') or ''):
                        alert_id = alert.get('id')
                        logging.info(f"--- Processing Alert ID: {alert_id} ---")

                        alert_signal_data = {
                            "timestamp": alert.get("timestamp"),
                            "content": alert.get("content"),
                            "discord_id": alert.get("discord_id"),
                            "trader": alert.get("trader"),
                            "trade": alert.get("trade"),
                        }

                        if not all(alert_signal_data.values()):
                            logging.warning(f"Skipping alert ID {alert_id} due to missing data.")
                            continue

                        try:
                            alert_result = await bot.process_update_signal(alert_signal_data)
                            if alert_result.get("status") == "success":
                                logging.info(f"✅ Successfully re-processed alert ID {alert_id}.")
                            else:
                                logging.error(f"❌ Failed to re-process alert ID {alert_id}. Reason: {alert_result.get('message')}")
                        except Exception as e_alert:
                            logging.error(f"An unexpected error occurred while processing alert ID {alert_id}: {e_alert}", exc_info=True)

            except Exception as e_retry:
                logging.error(f"An unexpected error occurred while retrying trade ID {trade_id}: {e_retry}", exc_info=True)

            logging.info(f"--- Finished processing for trade ID: {trade_id} ---")

    except Exception as e_fetch:
        logging.error(f"An error occurred while fetching failed trades: {e_fetch}", exc_info=True)

    logging.info("--- Retry Script Finished ---")

if __name__ == "__main__":
    asyncio.run(retry_balance_check_failures())