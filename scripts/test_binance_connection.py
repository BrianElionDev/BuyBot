import os
import sys
import asyncio
import logging
from dotenv import load_dotenv
from binance.client import Client
from binance.exceptions import BinanceAPIException

# Add the project root to Python path
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(script_dir)
sys.path.insert(0, project_root)

# --- Setup ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

async def test_binance_connection():
    """Test basic Binance testnet connection and what endpoints work."""

    # --- Load Environment Variables ---
    load_dotenv()

    api_key = os.getenv("BINANCE_API_KEY")
    api_secret = os.getenv("BINANCE_API_SECRET")
    is_testnet = True

    if not api_key or not api_secret:
        logging.error("API Key or Secret not found in .env file.")
        return

    logging.info("Testing Binance Testnet Connection...")

    # Initialize client
    client = Client(api_key, api_secret, testnet=is_testnet, tld='com')

    print("\n" + "="*70)
    print("                BINANCE TESTNET CONNECTION TEST")
    print("="*70)

    # Test 1: Server time (no auth required)
    try:
        server_time = client.get_server_time()
        print(f"✅ Server Time: {server_time}")
    except Exception as e:
        print(f"❌ Server Time Failed: {e}")

    # Test 2: Exchange info (no auth required)
    try:
        exchange_info = client.get_exchange_info()
        print(f"✅ Exchange Info: Found {len(exchange_info['symbols'])} trading pairs")
    except Exception as e:
        print(f"❌ Exchange Info Failed: {e}")

    # Test 3: API key permissions
    # try:
    #     api_permissions = client.get_api_key_permissions()
    #     print(f"✅ API Permissions: {api_permissions}")
    # except BinanceAPIException as e:
    #     print(f"❌ API Permissions Failed: {e}")

    # Test 4: Account status (requires auth)
    try:
        account_status = client.get_account_status()
        print(f"✅ Account Status: {account_status}")
    except BinanceAPIException as e:
        print(f"❌ Account Status Failed: {e}")

    # Test 5: Spot account (most basic authenticated call)
    try:
        account = client.get_account()
        print(f"✅ Spot Account Access: Success")
        print(f"   Account Type: {account.get('accountType')}")
        print(f"   Can Trade: {account.get('canTrade')}")
        print(f"   Can Withdraw: {account.get('canWithdraw')}")
        print(f"   Can Deposit: {account.get('canDeposit')}")
    except BinanceAPIException as e:
        print(f"❌ Spot Account Failed: {e}")

    # Test 6: Futures account (what we're actually trying to access)
    try:
        futures_account = client.futures_account()
        print(f"✅ Futures Account Access: Success")
        print(f"   Total Wallet Balance: {futures_account.get('totalWalletBalance')} USDT")
        print(f"   Can Trade: {futures_account.get('canTrade')}")
        print(f"   Can Withdraw: {futures_account.get('canWithdraw')}")
        print(f"   Can Deposit: {futures_account.get('canDeposit')}")
    except BinanceAPIException as e:
        print(f"❌ Futures Account Failed: {e}")
        print(f"   Error Code: {e.code}")
        print(f"   Error Message: {e.message}")

    # Test 7: Try futures account balance (lighter call)
    try:
        futures_balance = client.futures_account_balance()
        print(f"✅ Futures Balance Access: Success")
        usdt_balance = next((b for b in futures_balance if b['asset'] == 'USDT'), None)
        if usdt_balance:
            print(f"   USDT Balance: {usdt_balance['balance']}")
    except BinanceAPIException as e:
        print(f"❌ Futures Balance Failed: {e}")
        print(f"   Error Code: {e.code}")
        print(f"   Error Message: {e.message}")

    # Test 8: Try COIN-M futures (alternative)
    try:
        coin_futures_balance = client.futures_coin_account_balance()
        print(f"✅ COIN-M Futures Balance Access: Success")
    except BinanceAPIException as e:
        print(f"❌ COIN-M Futures Balance Failed: {e}")
        print(f"   Error Code: {e.code}")

    print("="*70)
    print("\nDiagnostic Summary:")
    print("- If server time and exchange info work: Basic connection is OK")
    print("- If API permissions fail: API key configuration issue")
    print("- If spot works but futures fails: Futures-specific permission issue")
    print("- If nothing works: API key or network issue")
    print("="*70 + "\n")

if __name__ == "__main__":
    asyncio.run(test_binance_connection())