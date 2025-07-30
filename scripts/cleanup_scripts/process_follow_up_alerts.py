import os
import sys
import asyncio
import logging
from dotenv import load_dotenv
from supabase import Client, create_client

# Add the project root to the Python path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
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
        response = supabase.table("alerts").select("*").is_("binance_response", None).gte("timestamp", "2025-07-23T12:43:40.221Z").execute()

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
                # Example parsing logic (customize as needed for your alert format)
                if "tp1" in content or "take profit 1" in content:
                    action = "take_profit_1"
                    # Extract TP1 price and/or close % if present
                    # (You may want to use regex or a parser for more robust extraction)
                    if "close" in content and "%" in content:
                        try:
                            pct = int(content.split("close")[-1].split("%")[-2].split()[-1])
                            details["close_percentage"] = pct
                        except Exception:
                            details["close_percentage"] = 50
                    else:
                        details["close_percentage"] = 50
                    # Optionally extract TP price
                elif "tp2" in content or "take profit 2" in content:
                    action = "take_profit_2"
                    details["close_percentage"] = 25
                elif "tp3" in content or "take profit 3" in content:
                    action = "take_profit_3"
                    details["close_percentage"] = 25
                elif "move stop" in content or "sl to be" in content or "stop to be" in content:
                    action = "stop_loss_update"
                    details["stop_price"] = "BE"
                elif "stopped out" in content or "stop loss hit" in content:
                    action = "stop_loss_hit"
                elif "close" in content:
                    action = "position_closed"
                    # Try to extract close %
                    if "%" in content:
                        try:
                            pct = int(content.split("close")[-1].split("%")[-2].split()[-1])
                            details["close_percentage"] = pct
                        except Exception:
                            details["close_percentage"] = 100
                    else:
                        details["close_percentage"] = 100
                else:
                    action = None

                # Reconstruct the signal payload from the alert row
                signal_payload = {
                    "timestamp": alert.get("timestamp"),
                    "content": alert.get("content"),
                    "trade": alert.get("trade"),
                    "discord_id": alert.get("discord_id"),
                    "trader": alert.get("trader"),
                    "structured": alert.get("structured"),
                }

                # Log what is being attempted
                logging.info(f"Attempting action: {action} with details: {details}")

                # Pass action and details to process_update_signal
                if action:
                    signal_payload["action"] = action
                    signal_payload["details"] = details
                result = await bot.process_update_signal(signal_payload, alert_id=alert_id)

                if result.get("status") == "success":
                    logging.info(f"✅ Successfully processed alert ID {alert_id}. Action: {action}. Message: {result.get('message')}")
                else:
                    logging.error(f"❌ Failed to process alert ID {alert_id}. Action: {action}. Reason: {result.get('message')}")

            except Exception as e:
                logging.error(f"An unexpected error occurred while processing alert ID {alert.get('id')}: {e}", exc_info=True)
                if alert_id := alert.get("id"):
                    try:
                        error_info = {"success": False, "reason": f"script_error: {str(e)}"}
                        supabase.table("alerts").update({
                            "parsed_alert": error_info,
                            "binance_response": {"error": f"Script error: {str(e)}"}
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