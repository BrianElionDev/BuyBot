import os
import logging
import httpx
import time
from dotenv import load_dotenv
from supabase import create_client, Client

# --- Setup ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- Configuration ---
load_dotenv()
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
BOT_API_URL = "http://0.0.0.0:8001/api/v1/discord/signal"

def get_unparsed_trades(supabase: Client) -> list:
    """
    Queries the 'trades' table for rows where 'parsed_signal' is NULL.
    """
    try:
        logging.info("Querying for trades with a NULL 'parsed_signal'...")
        response = supabase.from_("trades").select("*").execute()

        if response.data:
            logging.info(f"Found {len(response.data)} unparsed trades.")
            return response.data
        else:
            logging.info("No unparsed trades found.")
            return []

    except Exception as e:
        logging.error(f"An error occurred while querying Supabase: {e}")
        return []

def send_signal_to_bot(trade: dict):
    """
    Constructs a JSON payload from the trade data and sends it to the bot's API endpoint.
    """
    # Construct the payload from the trade data.
    # Ensure the column names ('timestamp', 'content', 'structured') match your table.
    payload = {
        "timestamp": trade.get("timestamp"),
        "content": trade.get("content"),
        "structured": trade.get("structured") # Corrected from structured_signal
    }

    # Validate that essential data is present
    if not all([payload["timestamp"], payload["content"], payload["structured"]]):
        logging.warning(f"Skipping trade ID {trade.get('id')} due to missing data.")
        return

    logging.info(f"Sending signal for trade ID: {trade.get('id')}, content: '{payload['content'][:50]}...'")

    try:
        with httpx.Client() as client:
            response = client.post(BOT_API_URL, json=payload, timeout=30.0)
            response.raise_for_status()  # Raise an exception for bad status codes (4xx or 5xx)

            logging.info(f"Successfully sent signal for trade ID {trade.get('id')}. Response: {response.json()}")

    except httpx.HTTPStatusError as e:
        logging.error(f"HTTP error for trade ID {trade.get('id')}: {e.response.status_code} - {e.response.text}")
    except httpx.RequestError as e:
        logging.error(f"Request failed for trade ID {trade.get('id')}: {e}")
    except Exception as e:
        logging.error(f"An unexpected error occurred while sending signal for trade ID {trade.get('id')}: {e}")
    finally:
        # Add a delay between requests to avoid overwhelming the endpoint
        logging.info("--- Waiting 5 seconds before next request ---")
        time.sleep(10)


def main():
    """
    Main function to orchestrate the process.
    """
    # --- Check for Supabase Credentials ---
    if not SUPABASE_URL or not SUPABASE_KEY:
        logging.error("Supabase URL or Key not found in environment variables.")
        logging.error("Please ensure your .env file contains SUPABASE_URL and SUPABASE_KEY.")
        return

    # --- Initialize Supabase Client ---
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        logging.info("Successfully connected to Supabase.")
    except Exception as e:
        logging.error(f"Failed to connect to Supabase: {e}")
        return

    # --- Process Trades ---
    unparsed_trades = get_unparsed_trades(supabase)

    if unparsed_trades:
        for trade in unparsed_trades:
            send_signal_to_bot(trade)

    logging.info("Script finished.")


if __name__ == "__main__":
    main()