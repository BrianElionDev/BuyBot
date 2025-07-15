#!/usr/bin/env python3
"""
Example script demonstrating how to switch between different Binance credential sets.
This shows how to reload credentials without restarting your application.
"""

import os
import sys
import asyncio
import logging

# Add the project root to Python path
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(script_dir)
sys.path.insert(0, project_root)

from src.bot.trading_engine import TradingEngine
from config import settings as config

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

async def main():
    """Demonstrate credential switching."""
    print("="*70)
    print("           CREDENTIAL SWITCHING EXAMPLE")
    print("="*70)

    # Initialize trading engine with current credentials
    trading_engine = TradingEngine(
        api_key=config.BINANCE_API_KEY,
        api_secret=config.BINANCE_API_SECRET,
        is_testnet=config.BINANCE_TESTNET
    )

    print(f"📊 Initial credentials loaded:")
    print(f"   API Key: {config.BINANCE_API_KEY[:10]}...{config.BINANCE_API_KEY[-5:] if config.BINANCE_API_KEY else 'None'}")
    print(f"   Testnet: {config.BINANCE_TESTNET}")

    # Test initial credentials
    print("\n🔍 Testing initial credentials...")
    try:
        balances = await trading_engine.binance_exchange.get_spot_balance()
        print(f"✅ Initial credentials working - Found {len(balances)} assets with balance")
    except Exception as e:
        print(f"❌ Initial credentials failed: {e}")

    print("\n" + "="*70)
    print("🔄 Now modify your .env file to switch credentials...")
    print("   1. Comment out the current BINANCE_API_KEY and BINANCE_API_SECRET")
    print("   2. Uncomment the next set of credentials you want to use")
    print("   3. Press Enter when ready to reload...")
    print("="*70)

    input("Press Enter to continue after updating .env file...")

    # Reload credentials
    print("\n🔄 Reloading credentials...")
    success = await trading_engine.reload_credentials()

    if success:
        print("\n✅ Credentials successfully switched!")

        # Test new credentials
        print("\n🔍 Testing new credentials...")
        try:
            balances = await trading_engine.binance_exchange.get_spot_balance()
            print(f"✅ New credentials working - Found {len(balances)} assets with balance")

            # Show some balance info if available
            if balances:
                print("\n📊 Account balances:")
                for asset, balance in list(balances.items())[:5]:  # Show first 5
                    print(f"   {asset.upper()}: {balance}")
                if len(balances) > 5:
                    print(f"   ... and {len(balances) - 5} more assets")
            else:
                print("   No assets with positive balance found")

        except Exception as e:
            print(f"❌ New credentials test failed: {e}")

    else:
        print("\n❌ Failed to switch credentials - check your .env file")

    # Cleanup
    await trading_engine.close()
    print("\n🎉 Demo complete!")

if __name__ == "__main__":
    asyncio.run(main())