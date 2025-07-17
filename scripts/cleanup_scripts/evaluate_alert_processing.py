import asyncio
import logging
import os
import sys
import json

# Add project root to the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
from supabase import create_client, Client

# --- Setup ---
load_dotenv()

# --- Supabase Client ---
url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_KEY")
if not url or not key:
    print("Supabase URL or Key not found. Please set SUPABASE_URL and SUPABASE_KEY in your .env file.")
    exit(1)

supabase: Client = create_client(url, key)

# --- Logger Setup ---
# Create a logger that writes to a file in the project root
log_file_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'alert_evaluation.log')
file_handler = logging.FileHandler(log_file_path, mode='w')
file_handler.setFormatter(logging.Formatter('%(message)s'))

logger = logging.getLogger('AlertEvaluator')
logger.setLevel(logging.INFO)
logger.addHandler(file_handler)
# Prevent propagation to the root logger to avoid duplicate console output
logger.propagate = False


def format_json_for_log(data):
    """Helper function to pretty-print JSON strings or dicts for logging."""
    if not data:
        return "Not Available"
    try:
        if isinstance(data, str):
            # If it's a string, parse it to a dict first
            parsed_data = json.loads(data)
        else:
            parsed_data = data
        return json.dumps(parsed_data, indent=2)
    except (json.JSONDecodeError, TypeError):
        # If it's not valid JSON, return the original string
        return str(data)


async def evaluate_processed_alerts():
    """
    Iterates over the alerts table to evaluate the binance_response and compares
    it with the corresponding trade data.
    """
    logger.info("--- Starting Evaluation of Processed Alerts ---")
    logger.info(f"Log file generated at: {log_file_path}\n")

    try:
        # 1. Fetch all alerts
        alerts_response = supabase.from_("alerts").select("*").order("id", desc=False).execute()
        if not alerts_response.data:
            logger.info("No alerts found in the database.")
            return

        all_alerts = alerts_response.data
        logger.info(f"Found {len(all_alerts)} total alerts to check.\n")

    except Exception as e:
        logger.error(f"Error fetching alerts from Supabase: {e}", exc_info=True)
        return

    # 2. Process each alert
    processed_count = 0
    for alert in all_alerts:
        alert_binance_response = alert.get('binance_response')

        # Skip alerts without a binance_response
        if not alert_binance_response:
            continue

        processed_count += 1
        trade_discord_id = alert.get('trade')

        logger.info("=" * 60)
        logger.info(f"Found Alert with Response (Alert ID: {alert.get('id')})")
        logger.info(f"  - Alert Discord ID: {alert.get('discord_id')}")
        logger.info(f"  - Alert Content: {alert.get('content')}")
        logger.info(f"  - Linked Trade (Discord ID): {trade_discord_id}")
        logger.info(f"  - Alert's Parsed Data:\n{format_json_for_log(alert.get('parsed_alert'))}")
        logger.info(f"  - Alert's Binance Response:\n{format_json_for_log(alert_binance_response)}")

        if not trade_discord_id:
            logger.warning("  - This alert is not linked to a trade. Cannot fetch trade details.\n")
            continue

        try:
            # 3. Fetch the corresponding trade
            trade_response = (
                supabase.from_("trades")
                .select("binance_response, exchange_order_id, stop_loss_order_id, parsed_signal, position_size")
                .eq("discord_id", trade_discord_id)
                .single() # We expect only one trade per discord_id
                .execute()
            )

            if trade_response.data:
                trade_data = trade_response.data
                logger.info("\n  --- Corresponding Trade Details ---")
                logger.info(f"  - Original Position Size: {trade_data.get('position_size')}")
                logger.info(f"  - Trade's Exchange Order ID: {trade_data.get('exchange_order_id')}")
                logger.info(f"  - Trade's Stop Loss Order ID: {trade_data.get('stop_loss_order_id')}")
                logger.info(f"  - Trade's Initial Parsed Signal:\n{format_json_for_log(trade_data.get('parsed_signal'))}")
                logger.info(f"  - Trade's Initial Binance Response:\n{format_json_for_log(trade_data.get('binance_response'))}")

            else:
                logger.warning(f"\n  - Could not find a corresponding trade with discord_id: {trade_discord_id}")

        except Exception as e:
            logger.error(f"\n  - An error occurred while fetching trade {trade_discord_id}: {e}", exc_info=True)

        logger.info("=" * 60 + "\n")

    logger.info(f"--- Evaluation Complete. Found and logged {processed_count} alerts with a Binance response. ---")
    print(f"Evaluation complete. Please check the log file: {log_file_path}")


async def main():
    await evaluate_processed_alerts()

if __name__ == "__main__":
    asyncio.run(main())