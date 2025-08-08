import os
import sys
import asyncio
import logging
from dotenv import load_dotenv
from supabase import create_client, Client

# Add the project root to Python path
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(script_dir))
sys.path.insert(0, project_root)

from src.exchange.binance_exchange import BinanceExchange

# --- Setup ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

async def check_binance_account():
    """
    Connects to Binance and displays open futures positions and orders,
    then correlates them with database records.
    """
    # --- Load Environment Variables ---
    load_dotenv()

    # --- Binance Credentials ---
    api_key = os.getenv("BINANCE_API_KEY")
    api_secret = os.getenv("BINANCE_API_SECRET")
    is_testnet = os.getenv("BINANCE_TESTNET", "true").lower() == "true"

    # --- Supabase Credentials ---
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")

    if not api_key or not api_secret:
        logging.error("Binance API Key or Secret not found in .env file.")
        return
    if not url or not key:
        logging.error("Supabase URL or Key not found in .env file.")
        return

    logging.info(f"Connecting to Binance ({'Testnet' if is_testnet else 'Mainnet'})...")

    # --- Initialize Clients ---
    try:
        exchange = BinanceExchange(
            api_key=api_key,
            api_secret=api_secret,
            is_testnet=is_testnet
        )
        client = exchange.client
        supabase: Client = create_client(url, key)
        logging.info("✅ Binance and Supabase clients initialized successfully")

        # --- Get Open Positions (Futures) ---
        print("\n" + "="*80)
        print(" " * 28 + "OPEN FUTURES POSITIONS")
        print("="*80)
        try:
            positions = await client.futures_position_information()
            open_positions = [p for p in positions if float(p.get('positionAmt', '0')) != 0]

            if not open_positions:
                print("No open positions found.")
            else:
                print(f"{'Symbol':<12} {'Amount':<15} {'Entry Price':<15} {'Mark Price':<15} {'Unrealized PNL':<20}")
                print("-"*80)
                for p in open_positions:
                    print(
                        f"{p['symbol']:<12} {p['positionAmt']:<15} {p['entryPrice']:<15}"
                        f"{p['markPrice']:<15} {p.get('unRealizedProfit', 'N/A'):<20}"
                    )
        except Exception as e:
            logging.error(f"❌ Could not fetch open positions: {e}")

        # --- Get Open Orders (Futures) ---
        print("\n" + "="*95)
        print(" " * 37 + "OPEN FUTURES ORDERS")
        print("="*95)
        open_orders = []
        try:
            open_orders = client.futures_get_open_orders()
            if not open_orders:
                print("No open orders found.")
            else:
                print(f"{'Order ID':<22} {'Symbol':<12} {'Side':<8} {'Type':<20} {'Quantity':<15} {'Price':<15}")
                print("-"*95)
                for o in open_orders:
                    print(
                        f"{o['orderId']:<22} {o['symbol']:<12} {o['side']:<8} {o['type']:<20}"
                        f"{o['origQty']:<15} {o['price']:<15}"
                    )
        except Exception as e:
            logging.error(f"❌ Could not fetch open orders: {e}")

        # --- Correlate Orders with DB records ---
        if open_orders:
            print("\n" + "="*95)
            print(" " * 25 + "ORDER CORRELATION AND ALERT HISTORY")
            print("="*95)

            for order in await open_orders:
                order_id = str(order['orderId'])
                print(f"\n--- Analyzing Order ID: {order_id} ({order['symbol']}) ---")

                # Find matching trade in DB
                try:
                    # Check both regular and stop loss order IDs
                    response = supabase.from_("trades").select("*").or_(
                        f"exchange_order_id.eq.{order_id},stop_loss_order_id.eq.{order_id}"
                    ).execute()

                    if not response.data:
                        print(f"  -> No matching trade found in the database for this order ID.")
                        continue

                    trade = response.data[0]
                    print(f"  -> Found Matching Trade DB ID: {trade.get('id')}, Discord ID: {trade.get('discord_id')}")

                    # Find related alerts for that trade
                    alert_response = supabase.from_("alerts").select("*").eq("trade", trade['discord_id']).execute()

                    if not alert_response.data:
                        print("  -> No alerts found for this trade.")
                    else:
                        print("  -> Associated Alerts:")
                        for alert in alert_response.data:
                            print(f"    - Alert ID: {alert['id']}, Content: \"{alert['content']}\"")
                            if alert.get('binance_response'):
                                print(f"      Response: {alert['binance_response']}")

                except Exception as e:
                    logging.error(f"  -> Error while querying database for order {order_id}: {e}")

    except Exception as e:
        logging.error(f"Failed to initialize clients: {e}")

if __name__ == "__main__":
    asyncio.run(check_binance_account())