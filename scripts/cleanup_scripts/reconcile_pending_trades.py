import asyncio
import logging
import os
import sys
from dotenv import load_dotenv
from supabase import create_client, Client

# Add project root to the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.exchange.binance_exchange import BinanceExchange

# --- Setup ---
load_dotenv()
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- Initialize Clients ---
def initialize_clients():
    """Initializes and returns Supabase and Binance clients."""
    # Supabase
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    if not url or not key:
        logging.error("Supabase URL or Key not found in .env file.")
        raise ValueError("Supabase credentials not found.")
    supabase: Client = create_client(url, key)

    # Binance
    api_key = os.getenv("BINANCE_API_KEY")
    api_secret = os.getenv("BINANCE_API_SECRET")
    is_testnet = os.getenv("BINANCE_TESTNET", "true").lower() == "true"
    if not api_key or not api_secret:
        logging.error("Binance API Key or Secret not found in .env file.")
        raise ValueError("Binance credentials not found.")
    binance = BinanceExchange(api_key=api_key, api_secret=api_secret, is_testnet=is_testnet)

    return supabase, binance

async def reconcile_pending_trades():
    """
    Finds trades stuck in a 'pending' state and checks Binance for a matching
    live order using the clientOrderId tag. If found, updates the database.
    """
    logging.info("--- Starting Trade Reconciliation ---")

    start_date = '2025-06-15T00:00:00.000Z'
    end_date = '2025-07-31T23:59:59.999Z'

    try:
        supabase, binance = initialize_clients()
    except ValueError as e:
        logging.error(f"Failed to initialize clients: {e}")
        return

    # 1. Fetch all 'pending' trades from the database
    logging.info(f"Searching for pending trades between {start_date} and {end_date}.")

    # 2. Fetch all open orders from Binance (do this once)
    open_orders = await binance.get_all_open_futures_orders()
    if not open_orders:
        logging.info("No open orders found on Binance. No reconciliation needed.")
        return

    # 3. Create a map of clientOrderId -> order for efficient lookup
    orders_by_client_id = {order['clientOrderId']: order for order in open_orders if 'clientOrderId' in order}
    logging.info(f"Found {len(orders_by_client_id)} open orders with client IDs on Binance.")

    # 4. Fetch and process pending trades in batches
    PAGE_SIZE = 100
    page = 0
    total_reconciled_count = 0

    while True:
        try:
            start_index = page * PAGE_SIZE
            end_index = start_index + PAGE_SIZE - 1
            logging.info(f"Fetching pending trades batch {page + 1} (rows {start_index} to {end_index})...")
            # where parsed_signal or binance_response is null
            response = (
                supabase.from_("trades")
                .select("*")
                .is_("parsed_signal", None)
                .is_("binance_response", None)
                .gte("timestamp", start_date)
                .lte("timestamp", end_date)
                .range(start_index, end_index)
                .execute()
            )

            if not response.data:
                logging.info("No more pending trades found in the date range.")
                break

            pending_trades_batch = response.data
            logging.info(f"Found {len(pending_trades_batch)} pending trade(s) in this batch.")

            # 5. Iterate through the batch of pending trades and reconcile
            for trade in pending_trades_batch:
                discord_id = trade.get('discord_id')
                if not discord_id:
                    continue

                if discord_id in orders_by_client_id:
                    binance_order = orders_by_client_id[discord_id]
                    logging.warning(f"Found orphaned order for trade ID {trade['id']} (Discord ID: {discord_id}). Reconciling...")

                    updates = {
                        "status": "OPEN",
                        "exchange_order_id": str(binance_order.get('orderId')),
                        "position_size": float(binance_order.get('origQty', 0.0)),
                        "binance_response": binance_order
                    }

                    try:
                        supabase.from_("trades").update(updates).eq("id", trade['id']).execute()
                        logging.info(f"✅ Successfully reconciled trade ID {trade['id']}.")
                        total_reconciled_count += 1
                    except Exception as e_update:
                        logging.error(f"❌ Failed to update trade ID {trade['id']} in Supabase: {e_update}")

            if len(pending_trades_batch) < PAGE_SIZE:
                logging.info("Last page of trades reached.")
                break

            page += 1

        except Exception as e_fetch:
            logging.error(f"Failed to fetch or process trades batch: {e_fetch}")
            break

    logging.info(f"--- Reconciliation Complete. {total_reconciled_count} trade(s) were updated in total. ---")

if __name__ == "__main__":
    asyncio.run(reconcile_pending_trades())