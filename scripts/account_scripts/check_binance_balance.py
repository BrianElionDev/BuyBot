import os
import sys
import asyncio
import logging


# Add the project root to Python path
# This script is two levels deep (scripts/account_scripts), so we go up two directories from the script's location.
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(script_dir))
sys.path.insert(0, project_root)
from config import settings
from src.exchange.binance_exchange import BinanceExchange

# --- Setup ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

async def check_balance():
    """
    Connects to Binance using the BinanceExchange class (same as main implementation)
    and displays the account balance, including zero balances to determine if testnet has funds.
    """
    api_key = settings.BINANCE_API_KEY
    api_secret = settings.BINANCE_API_SECRET
    is_testnet = settings.BINANCE_TESTNET

    if not api_key or not api_secret:
        logging.error("API Key or Secret not found in .env file.")
        logging.error("Please ensure your .env file is in the root directory and contains:")
        logging.error("BINANCE_API_KEY=your_key")
        logging.error("BINANCE_API_SECRET=your_secret")
        return

    logging.info(f"Connecting to Binance ({'Testnet' if is_testnet else 'Mainnet'})...")

    binance_exchange = None  # Initialize to None
    # --- Initialize BinanceExchange (same as main implementation) ---
    try:
        binance_exchange = BinanceExchange(
            api_key=api_key,
            api_secret=api_secret,
            is_testnet=is_testnet
        )
        logging.info("✅ BinanceExchange initialized successfully")

        # Initialize the client first
        await binance_exchange._init_client()
        client = binance_exchange.client

        if is_testnet:
            TESTNET = "TESTNET"
        else:
            TESTNET = "MAINNET"
        print("\n" + "="*70)
        print(f"          DETAILED BINANCE {TESTNET} ACCOUNT CHECK")
        print("="*70)

        # Get futures account information
        try:
            logging.info("Attempting to get detailed futures account info...")

            if client is None:
                raise Exception("Client not initialized")

            # Get futures account information with retry logic
            max_retries = 3
            futures_account = None
            for attempt in range(max_retries):
                try:
                    futures_account = await client.futures_account()
                    break
                except Exception as e:
                    if "rate limit" in str(e).lower() and attempt < max_retries - 1:
                        wait_time = (2 ** attempt) + 1  # Exponential backoff: 2s, 3s, 5s
                        logging.warning(f"Rate limit hit, waiting {wait_time}s before retry {attempt + 1}/{max_retries}")
                        await asyncio.sleep(wait_time)
                    else:
                        raise e

            if not futures_account or not futures_account.get('assets'):
                print("❌ TESTNET ACCOUNT IS COMPLETELY EMPTY OR BALANCE IS NOT VISIBLE TO API KEY")
                print("\nTo fix:")
                print("1. Add funds using the faucet: https://testnet.binance.vision/")
                print("2. Ensure your API key has 'Enable Futures' permission.")
            else:
                print("📊 FUTURES ACCOUNT BALANCES:")
                print(f"{'Asset':<8} {'Wallet Balance':<18} {'Available Balance':<18} {'Unrealized PnL':<15}")
                print("-"*75)

                total_balance = 0
                for asset in futures_account['assets']:
                    wallet_balance = float(asset.get('walletBalance', '0'))
                    available_balance = float(asset.get('availableBalance', '0'))
                    unrealized_pnl = float(asset.get('unrealizedProfit', '0'))

                    if wallet_balance > 0 or available_balance > 0 or unrealized_pnl != 0:
                        print(f"{asset['asset']:<8} {wallet_balance:<18.8f} {available_balance:<18.8f} {unrealized_pnl:<15.8f}")
                        total_balance += wallet_balance

                if total_balance > 0:
                    print("-"*75)
                    print(f"✅ TOTAL WALLET BALANCE: {total_balance:.8f} USDT")
                else:
                    print("-"*75)
                    print("❌ NO POSITIVE BALANCES FOUND")

        except Exception as e:
            logging.error(f"Failed to get detailed futures account: {e}")

        # Add delay between API calls to respect rate limits
        await asyncio.sleep(1)  # 1 second delay

        # Also try to get spot account information
        try:
            print("\n📊 SPOT ACCOUNT BALANCES:")
            if client is None:
                raise Exception("Client not initialized")

            # Get spot account information with retry logic
            max_retries = 3
            spot_account = None
            for attempt in range(max_retries):
                try:
                    spot_account = await client.get_account()
                    break
                except Exception as e:
                    if "rate limit" in str(e).lower() and attempt < max_retries - 1:
                        wait_time = (2 ** attempt) + 1  # Exponential backoff: 2s, 3s, 5s
                        logging.warning(f"Rate limit hit, waiting {wait_time}s before retry {attempt + 1}/{max_retries}")
                        await asyncio.sleep(wait_time)
                    else:
                        raise e

            if spot_account and spot_account.get('balances'):
                print(f"{'Asset':<8} {'Free':<18} {'Locked':<18}")
                print("-"*50)

                total_spot_balance = 0
                for balance in spot_account['balances']:
                    free = float(balance.get('free', '0'))
                    locked = float(balance.get('locked', '0'))

                    if free > 0 or locked > 0:
                        print(f"{balance['asset']:<8} {free:<18.8f} {locked:<18.8f}")
                        if balance['asset'] == 'USDT':
                            total_spot_balance += free + locked

                if total_spot_balance > 0:
                    print("-"*50)
                    print(f"✅ TOTAL SPOT USDT: {total_spot_balance:.8f}")
                else:
                    print("-"*50)
                    print("❌ NO SPOT BALANCES FOUND")
            else:
                print("❌ Could not retrieve spot account information")

        except Exception as e:
            logging.error(f"Failed to get spot account: {e}")

        # Add delay before closing to ensure all requests are processed
        await asyncio.sleep(0.5)

        print("="*70 + "\n")

        logging.info("Detailed balance check complete.")

    except Exception as e:
        logging.error(f"Failed to initialize BinanceExchange: {e}")
        logging.error("This could mean:")
        logging.error("1. The API Key or Secret is incorrect.")
        logging.error("2. You are trying to use a Mainnet key on the Testnet (or vice-versa).")
        logging.error("3. The bot's IP address is not whitelisted in your Binance API settings.")
        logging.error("4. The API key doesn't have sufficient permissions.")
    finally:
        # Ensure the client connection is always closed
        if binance_exchange:
            await binance_exchange.close()
            logging.info("✅ Binance client connection closed.")

async def main():
    """Main async entry point."""
    await check_balance()

if __name__ == "__main__":
    asyncio.run(main())