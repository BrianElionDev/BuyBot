import asyncio
import logging
import os
import sys
from dotenv import load_dotenv
from supabase import create_client, Client
from typing import Optional

# Add project root to the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from discord_bot.discord_bot import DiscordBot

# --- Setup ---
load_dotenv()
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- Initialize Clients ---
def initialize_clients() -> tuple[Optional[DiscordBot], Optional[Client]]:
    """Initializes and returns the Supabase and DiscordBot clients."""
    logging.info("Initializing clients...")
    try:
        url = os.environ.get("SUPABASE_URL")
        key = os.environ.get("SUPABASE_KEY")
        if not url or not key:
            raise ValueError("Supabase URL or key not found in .env file.")

        supabase: Client = create_client(url, key)
        bot = DiscordBot()
        logging.info("✅ Clients initialized successfully.")
        return bot, supabase
    except Exception as e:
        logging.error(f"❌ Failed to initialize clients: {e}")
        return None, None

async def process_single_trade(bot: DiscordBot, supabase: Client, discord_id: str):
    """
    Processes a single trade by discord_id.
    Fetches the trade, re-processes its initial signal, and any associated alerts.
    """
    logging.info(f"--- Processing Discord ID: {discord_id} ---")

    # 2. Fetch the original trade from the database
    trade = None
    try:
        logging.info(f"Fetching trade with discord_id: {discord_id}")
        response = supabase.from_("trades").select("*").eq("discord_id", discord_id).single().execute()
        trade = response.data
        if not trade:
            logging.error(f"❌ No trade found with discord_id: {discord_id}")
            return
        logging.info(f"✅ Found trade. Group ID: {trade.get('trade_group_id')}")
    except Exception as e:
        logging.error(f"Failed to fetch trade from Supabase: {e}")
        return

    # 3. Re-process the initial trade signal
    logging.info("--- (1/2) Re-processing initial trade signal ---")
    initial_signal_data = {
        "timestamp": trade.get("timestamp"),
        "content": trade.get("content"),
        "discord_id": trade.get("discord_id"),
        "trader": trade.get("trader"),
        "structured": trade.get("structured"),
    }

    if not all(initial_signal_data.values()):
        logging.error(f"Skipping initial signal for trade ID {trade.get('id')} due to missing data.")
    else:
        try:
            # Override the price check threshold to allow retrying trades
            initial_signal_data['price_threshold_override'] = 99999  # Effectively disables the check
            # Do NOT set client_order_id here; let the bot generate a new UUID
            from discord_bot.models import InitialDiscordSignal
            signal_model = InitialDiscordSignal(**initial_signal_data)  # type: ignore
            result = await bot.process_initial_signal(signal_model)
            if result.get("status") == "success":
                logging.info(f"✅ Successfully re-processed initial signal.")
            else:
                logging.error(f"❌ Failed to re-process initial signal. Reason: {result.get('message')}")
        except Exception as e:
            logging.error(f"An unexpected error occurred while re-processing the initial signal: {e}", exc_info=True)

    # 4. Fetch and process any corresponding alerts
    logging.info(f"--- (2/2) Searching for alerts associated with trade {discord_id} ---")
    try:
        alert_response = supabase.from_("alerts").select("*").eq("trade", discord_id).execute()
        alerts = alert_response.data
        if not alerts:
            logging.info("✅ No corresponding alerts found for this trade.")
        else:
            logging.info(f"Found {len(alerts)} alert(s) to process.")
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
                    result = await bot.process_update_signal(alert_signal_data)
                    if result.get("status") == "success":
                        logging.info(f"✅ Successfully re-processed alert ID {alert_id}.")
                    else:
                        logging.error(f"❌ Failed to re-process alert ID {alert_id}. Reason: {result.get('message')}")
                except Exception as e:
                    logging.error(f"An unexpected error occurred while processing alert ID {alert_id}: {e}", exc_info=True)
    except Exception as e:
        logging.error(f"Failed to fetch or process alerts: {e}")

async def manual_retry(bot: DiscordBot, supabase: Client):
    """Main loop to manually retry trades by discord_id."""
    try:
        while True:
            discord_id = await asyncio.to_thread(
                input, "\nPlease enter the discord_id of the trade to retry (or type 'exit' to quit): "
            )
            discord_id = discord_id.strip()

            if discord_id.lower() == 'exit':
                break
            if not discord_id.isdigit():
                logging.warning("Invalid input. Please enter a numerical discord_id.")
                continue

            await process_single_trade(bot, supabase, discord_id)
            logging.info(f"--- Finished processing for {discord_id}. Ready for next ID. ---")

    except (KeyboardInterrupt, EOFError):
        logging.info("\nUser interrupted. Exiting...")
    finally:
        if bot and bot.binance_exchange:
            await bot.binance_exchange.close()
            logging.info("Binance client connection closed.")
        logging.info("--- Manual Retry Script Finished ---")

async def main():
    """Sets up logging and runs the manual retry loop."""
    logging.info("--- Manual Trade Retry Script ---")
    bot, supabase = initialize_clients()
    if not bot or not supabase:
        return

    await manual_retry(bot, supabase)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass