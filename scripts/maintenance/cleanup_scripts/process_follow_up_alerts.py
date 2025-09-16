import os
import sys
import asyncio
import logging
from dotenv import load_dotenv
from supabase import Client, create_client

# Add the project root to Python path
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(os.path.dirname(script_dir)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from discord_bot.discord_bot import DiscordBot

# --- Setup ---
load_dotenv()
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- Supabase & Bot Initialization ---
supabase: Client
bot: DiscordBot

async def process_alerts():
    """
    Fetches unprocessed alerts, sends them to the DiscordBot for processing,
    and logs the outcome.
    """
    global supabase, bot
    logging.info("--- Starting Follow-Up Alert Processing ---")

    try:
        # Fetch all alerts that haven't been processed yet
        response = supabase.table("alerts").select("*").is_("binance_response", None).eq("trade", "1416231183850668192").execute()

        if not hasattr(response, 'data') or not response.data:
            logging.info("No unprocessed alerts found.")
            return

        alerts = response.data
        logging.info(f"Found {len(alerts)} unprocessed alerts.")

        for alert in alerts:
            logging.info(f"\nProcessing alert ID {alert['id']}: {alert['content']}")

            try:
                alert_id = alert.get("id")
                if not alert_id:
                    logging.error(f"Alert is missing an 'id'. Raw alert data: {alert}")
                    continue

                # Parse alert content for action and details
                content = alert.get("content", "").lower()
                details = {}
                action = None
                # Enhanced parsing logic for the specific alert formats
                if "tp1" in content or "take profit 1" in content:
                    action = "take_profit_1"
                    details["close_percentage"] = 50
                elif "tp2" in content or "take profit 2" in content:
                    action = "take_profit_2"
                    details["close_percentage"] = 25
                elif "tp3" in content or "take profit 3" in content:
                    action = "take_profit_3"
                    details["close_percentage"] = 25
                elif "stops moved to be" in content or "moved to be" in content or "stops moved to be" in content:
                    action = "break_even"
                    details["stop_price"] = "BE"
                elif "stopped be" in content or "stopped out" in content or "stop loss hit" in content:
                    action = "stop_loss_hit"
                elif "close" in content:
                    action = "position_closed"
                    details["close_percentage"] = 100
                else:
                    action = None

                # Extract coin symbol from content for enhanced processing
                coin_symbol = None
                content_upper = alert.get("content", "").upper()
                import re
                coin_match = re.search(r'^([A-Z]{2,5})\s*[🚀|]', content_upper)
                if coin_match:
                    coin_symbol = coin_match.group(1)

                # Reconstruct the signal payload from the alert row
                signal_payload = {
                    "timestamp": alert.get("timestamp"),
                    "content": alert.get("content"),
                    "trade": alert.get("trade"),
                    "discord_id": alert.get("discord_id"),
                    "trader": alert.get("trader"),
                    "structured": alert.get("structured"),
                    "coin_symbol": coin_symbol,  # Add coin symbol for enhanced processing
                }

                # Log what is being attempted
                logging.info(f"Attempting action: {action} with details: {details}")

                # Pass action and details to process_update_signal
                if action:
                    signal_payload["action"] = action
                    signal_payload["details"] = details
                result = await bot.process_update_signal(signal_payload)

                if result.get("status") == "success":
                    logging.info(f"✅ Successfully processed alert ID {alert_id}. Action: {action}. Message: {result.get('message')}")
                    # Update alert status to SUCCESS
                    try:
                        supabase.table("alerts").update({
                            "status": "SUCCESS",
                            "binance_response": {"message": result.get('message')}
                        }).eq("id", alert_id).execute()
                    except Exception as e:
                        logging.error(f"Could not update alert status: {e}")
                else:
                    logging.error(f"❌ Failed to process alert ID {alert_id}. Action: {action}. Reason: {result.get('message')}")
                    # Update alert status to ERROR
                    try:
                        supabase.table("alerts").update({
                            "status": "ERROR",
                            "binance_response": {"error": result.get('message')}
                        }).eq("id", alert_id).execute()
                    except Exception as e:
                        logging.error(f"Could not update alert status: {e}")

            except Exception as e:
                logging.error(f"An unexpected error occurred while processing alert ID {alert.get('id')}: {e}", exc_info=True)
                if alert_id := alert.get("id"):
                    try:
                        error_info = {"success": False, "reason": f"script_error: {str(e)}"}
                        supabase.table("alerts").update({
                            "parsed_alert": error_info,
                            "binance_response": {"error": f"Script error: {str(e)}"},
                            "status": "ERROR"
                        }).eq("id", alert_id).execute()
                    except Exception as db_e:
                        logging.error(f"Could not even log the error to the database for alert {alert_id}: {db_e}")

            logging.info("--- Waiting 10 seconds before next alert ---")
            await asyncio.sleep(10)

    except Exception as e:
        logging.error(f"An error occurred in the main processing loop: {e}", exc_info=True)

async def main():
    """Initializes connections and runs the main processing loop."""
    global supabase, bot

    supabase_url = os.environ.get("SUPABASE_URL")
    supabase_key = os.environ.get("SUPABASE_KEY")

    if not supabase_url or not supabase_key:
        logging.critical("SUPABASE_URL and SUPABASE_KEY must be set.")
        return

    try:
        supabase = create_client(supabase_url, supabase_key)
        logging.info("Successfully connected to Supabase.")
        bot = DiscordBot()
        await process_alerts()
    except Exception as e:
        logging.critical(f"Failed to initialize resources: {e}", exc_info=True)
    finally:
        if 'bot' in globals() and bot:
            await bot.close()
            logging.info("Bot resources have been closed.")


if __name__ == "__main__":
    asyncio.run(main())