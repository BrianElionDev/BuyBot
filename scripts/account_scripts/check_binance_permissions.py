import os
import logging
from dotenv import load_dotenv
from binance.client import Client
from binance.exceptions import BinanceAPIException

# --- Setup ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def check_permissions():
    """
    Connects to Binance using API credentials from the .env file
    and checks the permissions of the key.
    """
    # --- Load Environment Variables ---
    load_dotenv()

    api_key = os.getenv("BINANCE_API_KEY")
    api_secret = os.getenv("BINANCE_API_SECRET")
    is_testnet = True

    if not api_key or not api_secret:
        logging.error("API Key or Secret not found in .env file.")
        logging.error("Please ensure your .env file is in the root directory and contains:")
        logging.error("BINANCE_API_KEY=your_key")
        logging.error("BINANCE_API_SECRET=your_secret")
        return

    logging.info(f"Connecting to Binance ({'Testnet' if is_testnet else 'Mainnet'})...")

    # --- Initialize Client ---
    try:
        client = Client(api_key, api_secret, testnet=is_testnet)

        # --- Fetch API Permissions ---
        logging.info("Fetching API key permissions...")
        permissions = client.get_account_api_permissions()

        # --- Display Results ---
        print("\n" + "="*40)
        print("      Binance API Key Permissions")
        print("="*40)

        # General Info
        print(f"Key for User ID:              {permissions['tradingAuthority'] if 'tradingAuthority' in permissions else 'N/A'}")
        print(f"IP Address Restrictions:      {'Yes' if permissions['ipRestrict'] else 'No'}")
        print(f"Created At:                   {permissions.get('createTime', 'N/A')}") # Timestamp may not be present

        print("-"*40)

        # Permissions
        print(f"Enable Reading:               {'✅ Enabled' if permissions['enableReading'] else '❌ Disabled'}")
        print(f"Enable Spot & Margin Trading: {'✅ Enabled' if permissions['enableSpotAndMarginTrading'] else '❌ Disabled'}")
        print(f"Enable Withdrawals:           {'✅ Enabled' if permissions['enableWithdrawals'] else '❌ Disabled'}")
        print(f"Enable Futures:               {'✅ Enabled' if permissions['enableFutures'] else '❌ Disabled'}")
        print(f"Enable Vanilla Options:       {'✅ Enabled' if permissions['enableVanillaOptions'] else '❌ Disabled'}")

        print("="*40 + "\n")
        logging.info("Permission check complete.")

    except BinanceAPIException as e:
        logging.error(f"Binance API Error (Code: {e.code}): {e.message}")
        logging.error("This could mean:")
        logging.error("1. The API Key or Secret is incorrect.")
        logging.error("2. You are trying to use a Mainnet key on the Testnet (or vice-versa). Check BINANCE_TESTNET in your .env file.")
        logging.error("3. The bot's IP address is not whitelisted in your Binance API settings.")
    except Exception as e:
        logging.error(f"An unexpected error occurred: {e}")

if __name__ == "__main__":
    check_permissions()