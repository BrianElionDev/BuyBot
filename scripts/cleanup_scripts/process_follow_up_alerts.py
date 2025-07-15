import os
import sys
import asyncio
import json
import logging
from dotenv import load_dotenv
from supabase import Client, create_client
from typing import Dict, Any

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

def _create_update_payload(content: str) -> dict:
    """
    Parses the raw alert content and creates a payload dictionary
    for the TradingEngine's process_trade_update method.
    """
    content_lower = content.lower()

    # --- Close Position Logic ---
    # Treat any SL hit, TP, or explicit "closed" signal as a trigger to fully close the position.
    if any(keyword in content_lower for keyword in ["stopped out", "stop loss", "closed", "tp1", "tp2"]):
        return {'close_position': True, 'reason': 'alert_triggered_close'}

    # --- Update Stop Loss to Break-Even Logic ---
    if "stops moved to be" in content_lower or "sl to be" in content_lower:
        return {'update_sl': 'BE'}

    # Return an empty dictionary for unrecognized or unsupported alert types
    return {}

async def process_alerts():
    """
    Fetches unprocessed alerts, creates an action payload, sends it to the
    trading engine for execution, and logs the response.
    """
    global supabase, bot
    logging.info("--- Starting Follow-Up Alert Processing ---")

    try:
        # Fetch all alerts that haven't been processed yet
        response = supabase.table("alerts").select("*").gte("timestamp", "2025-07-09T00:00:00.000Z").is_("parsed_alert", None).execute()

        if not hasattr(response, 'data') or not response.data:
            logging.info("No unprocessed alerts found.")
            return

        alerts = response.data
        logging.info(f"Found {len(alerts)} unprocessed alerts.")

        for alert in alerts:
            logging.info(f"\nProcessing alert ID {alert['id']}: {alert['content']}")
            parsed_alert_update = None
            binance_response_update = None

            try:
                # 1. Find the corresponding active trade in the 'trades' table
                trade_response = supabase.table("trades").select("*").eq("discord_id", alert["trade"]).limit(1).execute()

                if not trade_response.data:
                    parsed_alert_update = {'success': False, 'reason': 'trade_not_found'}
                    binance_response_update = f"Original trade with discord_id {alert['trade']} not found."
                    logging.warning(binance_response_update)
                else:
                    active_trade = trade_response.data[0]

                    # 2. Only process alerts for trades that are still 'OPEN'
                    if active_trade.get('status') != 'OPEN':
                        parsed_alert_update = {'success': False, 'reason': 'trade_not_open'}
                        binance_response_update = f"Trade {active_trade['id']} is not OPEN (status: {active_trade.get('status')}). Skipping alert."
                        logging.info(binance_response_update)
                    else:
                        # 3. Create the action payload from the alert content
                        payload = _create_update_payload(alert['content'])

                        if not payload:
                            parsed_alert_update = {'success': False, 'reason': 'unsupported_alert'}
                            binance_response_update = "Unknown or unsupported alert type."
                            logging.warning(f"Unsupported alert for trade {active_trade['id']}: {alert['content']}")
                        else:
                            # 4. Execute the action using the Trading Engine
                            logging.info(f"Executing action for trade {active_trade['id']} with payload: {payload}")
                            success, response_from_engine = await bot.trading_engine.process_trade_update(payload, active_trade)

                            parsed_alert_update = {'success': success, 'action_payload': payload}
                            binance_response_update = str(response_from_engine)

                            log_level = logging.INFO if success else logging.ERROR
                            logging.log(log_level, f"Engine execution result for trade {active_trade['id']}: {binance_response_update}")

            except Exception as e:
                logging.error(f"An unexpected error occurred while processing alert ID {alert['id']}: {e}", exc_info=True)
                parsed_alert_update = {'success': False, 'reason': 'script_error'}
                binance_response_update = f"Script error: {str(e)}"

            # 5. Log the results to the database
            if parsed_alert_update:
                update_data: Dict[str, Any] = {"parsed_alert": parsed_alert_update}
                if binance_response_update:
                    update_data["binance_response"] = binance_response_update

                supabase.table("alerts").update(update_data).eq("id", alert["id"]).execute()
                logging.info(f"Successfully logged result for alert ID {alert['id']}.")

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