import os
import sys
import asyncio
import logging
from dotenv import load_dotenv

# Add the project root to Python path
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(script_dir)
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
                futures_account = client.futures_account()

                print(f"Total Wallet Balance:    {futures_account.get('totalWalletBalance', 'N/A')} USDT")
                print(f"Total Unrealized PnL:    {futures_account.get('totalUnrealizedProfit', 'N/A')} USDT")
                print(f"Total Margin Balance:    {futures_account.get('totalMarginBalance', 'N/A')} USDT")
                print(f"Available Balance:       {futures_account.get('availableBalance', 'N/A')} USDT")
                print(f"Max Withdraw Amount:     {futures_account.get('maxWithdrawAmount', 'N/A')} USDT")
                print(f"Can Trade:              {futures_account.get('canTrade', False)}")
                print(f"Can Withdraw:           {futures_account.get('canWithdraw', False)}")
                print(f"Can Deposit:            {futures_account.get('canDeposit', False)}")

                print("\n" + "-"*70)
                print("                    ALL ASSETS (INCLUDING ZERO)")
                print("-"*70)
                print(f"{'Asset':<8} {'Wallet Balance':<18} {'Available':<18} {'Cross UnPnL':<15}")
                print("-"*70)

                has_any_balance = False
                if 'assets' in futures_account:
                    for asset in futures_account['assets']:
                        wallet_balance = float(asset.get('walletBalance', 0))
                        available_balance = float(asset.get('availableBalance', 0))
                        cross_unrealized_pnl = float(asset.get('crossUnrealizedProfit', 0))

                        # Show all assets to see if account is completely empty
                        print(f"{asset['asset']:<8} {wallet_balance:<18.8f} {available_balance:<18.8f} {cross_unrealized_pnl:<15.8f}")

                        if wallet_balance > 0 or available_balance > 0 or cross_unrealized_pnl != 0:
                            has_any_balance = True

                print("-"*70)
                if has_any_balance:
                    print("✅ TESTNET HAS SOME BALANCE OR ACTIVITY")
                else:
                    print("❌ TESTNET ACCOUNT IS COMPLETELY EMPTY")
                    print("\nTo get testnet funds:")
                    print("1. Visit: https://testnet.binance.vision/")
                    print("2. Login with your testnet account")
                    print("3. Go to 'Wallet' -> 'Faucet' to get test USDT")
                    print("4. Transfer test USDT to futures wallet if needed")

            except Exception as e:
                logging.error(f"Failed to get detailed futures account: {e}")

                # Fallback: Try basic futures balance
                try:
                    logging.info("Trying basic futures balance check...")
                    futures_balances = await binance_exchange.get_futures_balance()

                    print("\n" + "-"*70)
                    print("                 BASIC FUTURES BALANCE CHECK")
                    print("-"*70)

                    if futures_balances:
                        print("Available balances:")
                        for asset, balance in futures_balances.items():
                            print(f"{asset.upper()}: {balance}")
                    else:
                        print("❌ No balances found - testnet account appears empty")
                        print("\nTo get testnet funds:")
                        print("1. Visit: https://testnet.binance.vision/")
                        print("2. Login with your testnet account")
                        print("3. Go to 'Wallet' -> 'Faucet' to get test USDT")

                except Exception as e2:
                    logging.error(f"Basic balance check also failed: {e2}")

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

async def main():
    """Main async entry point."""
    await check_balance()

if __name__ == "__main__":
    asyncio.run(main())