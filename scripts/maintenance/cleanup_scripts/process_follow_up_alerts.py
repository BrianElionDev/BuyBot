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
        # Fetch a recent window of alerts; we'll filter in Python to be exchange-agnostic
        response = (
            supabase
            .table("alerts")
            .select("*")
            .eq("discord_id", "1434787278106132525")
            .execute()
        )

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

                # Skip already processed alerts
                # if alert.get("status") in ("PROCESSED", "SUCCESS"):
                #     logging.info(f"Skipping already processed alert ID {alert_id}")
                #     continue
                # if alert.get("exchange_response") or alert.get("binance_response") or alert.get("kucoin_response"):
                #     logging.info(f"Skipping alert ID {alert_id} with existing exchange response")
                #     continue

                # Construct the signal payload and delegate parsing/routing to the bot
                signal_payload = {
                    "timestamp": alert.get("timestamp"),
                    "content": alert.get("content"),
                    "trade": alert.get("trade"),  # Original trade discord_id
                    "discord_id": alert.get("discord_id"),  # The alert message id
                    "trader": alert.get("trader"),
                    "structured": alert.get("structured"),
                }

                result = await bot.process_update_signal(signal_payload)

                # Normalize result fields
                status_ok = str(result.get("status", "")).lower() in ("success", "ok", "processed", "true") or bool(result.get("success"))
                message = result.get("message") or result.get("error") or ""
                parsed_alert = result.get("parsed_alert")
                exchange_resp = result.get("exchange_response") or result.get("result") or {"message": message}

                if status_ok:
                    logging.info(f"✅ Successfully processed alert ID {alert_id}. Message: {message}")
                    try:
                        update_fields = {
                            "status": "SUCCESS",
                            "exchange_response": exchange_resp,
                        }
                        if parsed_alert:
                            update_fields["parsed_alert"] = parsed_alert
                        supabase.table("alerts").update(update_fields).eq("id", alert_id).execute()
                    except Exception as e:
                        logging.error(f"Could not update alert status: {e}")
                else:
                    logging.error(f"❌ Failed to process alert ID {alert_id}. Reason: {message}")
                    try:
                        supabase.table("alerts").update({
                            "status": "ERROR",
                            "exchange_response": {"error": message}
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

            logging.info("--- Waiting 3 seconds before next alert ---")
            await asyncio.sleep(3)

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