import os
import sys
import asyncio
import logging
from dotenv import load_dotenv

# Add the project root to Python path
# This script is two levels deep (scripts/account_scripts), so we go up two directories from the script's location.
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(script_dir))
sys.path.insert(0, project_root)

from src.exchange.binance_exchange import BinanceExchange

# --- Setup ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

async def check_balance():
    """
    Connects to Binance using the BinanceExchange class (same as main implementation)
    and displays the account balance, including zero balances to determine if testnet has funds.
    """
    # --- Load Environment Variables ---
    load_dotenv()

    api_key = os.getenv("BINANCE_API_KEY")
    api_secret = os.getenv("BINANCE_API_SECRET")
    is_testnet = True  # Set to True for testnet, False for mainnet

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

        # --- Check if we can access the client directly for more detailed info ---
        try:
            # Access the underlying client to get raw account data
            client = binance_exchange.client

            print("\n" + "="*70)
            print("          DETAILED BINANCE TESTNET ACCOUNT CHECK")
            print("="*70)

            # Try to get futures account info directly
            try:
                logging.info("Attempting to get detailed futures account info...")
                futures_account_balances = await binance_exchange.get_account_balances()

                # The get_account_balances function already filters for non-zero balances.
                # We'll display what we get back.

                if not futures_account_balances:
                    print("❌ TESTNET ACCOUNT IS COMPLETELY EMPTY OR BALANCE IS NOT VISIBLE TO API KEY")
                    print("\nTo fix:")
                    print("1. Add funds using the faucet: https://testnet.binance.vision/")
                    print("2. Ensure your API key has 'Enable Futures' permission.")

                else:
                    print(f"{'Asset':<8} {'Wallet Balance':<18}")
                    print("-"*70)
                    for asset, balance in futures_account_balances.items():
                        print(f"{asset:<8} {balance:<18.8f}")
                    print("-"*70)
                    print("✅ TESTNET ACCOUNT HAS A VISIBLE BALANCE.")

            except Exception as e:
                logging.error(f"Failed to get detailed futures account: {e}")

            print("="*70 + "\n")

        except Exception as e:
            logging.error(f"Failed to access account details: {e}")

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