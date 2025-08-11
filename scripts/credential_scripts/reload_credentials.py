#!/usr/bin/env python3
"""
Script to reload environment variables after switching Binance API credentials.
Run this after you modify your .env file to switch between credential sets.
"""

import os
import sys
import logging
from dotenv import load_dotenv

# Add the project root to Python path
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(script_dir))
sys.path.insert(0, project_root)

from config.settings import reload_env
from binance.client import Client
from binance.exceptions import BinanceAPIException

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def test_credentials():
    """Test the reloaded credentials with a simple API call."""
    try:
        # Reload environment variables
        reload_env()

        # Import the updated settings
        from config import settings

        if not settings.BINANCE_API_KEY or not settings.BINANCE_API_SECRET:
            logging.error("❌ No Binance API credentials found in environment")
            return False

        # Test the credentials
        logging.info("🔄 Testing Binance API credentials...")
        client = Client(
            settings.BINANCE_API_KEY,
            settings.BINANCE_API_SECRET,
            testnet=settings.BINANCE_TESTNET
        )

        # Simple test - get server time
        server_time = client.get_server_time()
        logging.info(f"✅ Server connection successful: {server_time}")

        # Test account access
        try:
            account = client.get_account()
            logging.info(f"✅ Account access successful")
            logging.info(f"   Can Trade: {account.get('canTrade', 'Unknown')}")
            logging.info(f"   Can Withdraw: {account.get('canWithdraw', 'Unknown')}")
            logging.info(f"   Can Deposit: {account.get('canDeposit', 'Unknown')}")

        except BinanceAPIException as e:
            if e.code == -2015:  # Invalid API key
                logging.error("❌ Invalid API key or insufficient permissions")
                return False
            else:
                logging.warning(f"⚠️ Account access limited: {e.message}")

        # Test futures access if on testnet
        if settings.BINANCE_TESTNET:
            try:
                futures_account = client.futures_account()
                logging.info(f"✅ Futures account access successful")
                logging.info(f"   Total Wallet Balance: {futures_account.get('totalWalletBalance', 'N/A')} USDT")

            except BinanceAPIException as e:
                logging.warning(f"⚠️ Futures access limited: {e.message}")

        logging.info("🎉 Credentials successfully reloaded and tested!")
        return True

    except BinanceAPIException as e:
        logging.error(f"❌ Binance API Error: {e.message}")
        return False
    except Exception as e:
        logging.error(f"❌ Unexpected error: {e}")
        return False

def main():
    """Main function to reload and test credentials."""
    print("="*60)
    print("   BINANCE CREDENTIALS RELOAD & TEST UTILITY")
    print("="*60)

    if test_credentials():
        print("\n✅ SUCCESS: Credentials reloaded and working!")
        print("Your application will now use the updated credentials.")
    else:
        print("\n❌ FAILED: There was an issue with the credentials.")
        print("Please check your .env file and ensure the credentials are correct.")

    print("="*60)

if __name__ == "__main__":
    main()