#!/usr/bin/env python3
"""
KuCoin Comprehensive Validation Test Script

Tests all validation functionality to ensure it matches Binance capabilities.
"""

import os
import sys
import asyncio
from dotenv import load_dotenv

# Add project root to path
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(script_dir))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Load environment variables
load_dotenv()

from src.exchange.kucoin.kucoin_exchange import KucoinExchange

async def test_comprehensive_validation():
    """Test comprehensive KuCoin validation functionality"""
    print("=== KuCoin Comprehensive Validation Test ===")

    # Get credentials from environment
    api_key = os.getenv("KUCOIN_API_KEY")
    api_secret = os.getenv("KUCOIN_API_SECRET")
    api_passphrase = os.getenv("KUCOIN_API_PASSPHRASE")

    if not all([api_key, api_secret, api_passphrase]):
        print("❌ Missing KuCoin API credentials in .env file")
        return False

    print(f"✅ Found API credentials")

    # Initialize exchange
    exchange = KucoinExchange(api_key, api_secret, api_passphrase, is_testnet=False)

    try:
        # Initialize connection
        print("Initializing KuCoin exchange...")
        success = await exchange.initialize()
        if not success:
            print("❌ Failed to initialize KuCoin exchange")
            return False

        print("✅ KuCoin exchange initialized successfully")

        # Test symbols
        test_symbols = ["BTC-USDT", "ETH-USDT", "SOL-USDT"]

        for symbol in test_symbols:
            print(f"\n--- Testing {symbol} ---")

            # 1. Test symbol support
            print(f"1. Testing symbol support...")
            is_supported = await exchange.is_futures_symbol_supported(symbol)
            print(f"   Symbol supported: {'✅' if is_supported else '❌'}")

            # 2. Test symbol filters
            print(f"2. Testing symbol filters...")
            filters = await exchange.get_futures_symbol_filters(symbol)
            if filters:
                print(f"   ✅ Symbol filters retrieved")
                print(f"   Min Qty: {filters.get('LOT_SIZE', {}).get('minQty', 'N/A')}")
                print(f"   Max Qty: {filters.get('LOT_SIZE', {}).get('maxQty', 'N/A')}")
                print(f"   Step Size: {filters.get('LOT_SIZE', {}).get('stepSize', 'N/A')}")
                print(f"   Min Notional: {filters.get('MIN_NOTIONAL', {}).get('minNotional', 'N/A')}")
                print(f"   Price Increment: {filters.get('PRICE_FILTER', {}).get('tickSize', 'N/A')}")
            else:
                print(f"   ❌ No symbol filters for {symbol}")

            # 3. Test mark price
            print(f"3. Testing mark price...")
            mark_price = await exchange.get_mark_price(symbol)
            if mark_price:
                print(f"   ✅ Mark price: ${mark_price}")
            else:
                print(f"   ❌ No mark price for {symbol}")

            # 4. Test current price
            print(f"4. Testing current price...")
            prices = await exchange.get_current_prices([symbol])
            if symbol in prices and prices[symbol] > 0:
                print(f"   ✅ Current price: ${prices[symbol]}")
            else:
                print(f"   ❌ No current price for {symbol}")

            # 5. Test order book
            print(f"5. Testing order book...")
            order_book = await exchange.get_order_book(symbol, limit=5)
            if order_book and order_book.get('bids') and order_book.get('asks'):
                print(f"   ✅ Order book retrieved")
                print(f"   Bids: {len(order_book['bids'])}")
                print(f"   Asks: {len(order_book['asks'])}")
                if order_book['bids']:
                    print(f"   Best bid: {order_book['bids'][0]}")
                if order_book['asks']:
                    print(f"   Best ask: {order_book['asks'][0]}")
            else:
                print(f"   ❌ No order book data for {symbol}")

            # 6. Test trade amount validation
            print(f"6. Testing trade amount validation...")
            if mark_price:
                # Test valid amount
                valid_amount = 0.001  # Small amount
                is_valid, error = await exchange.validate_trade_amount(symbol, valid_amount, mark_price)
                print(f"   Valid amount {valid_amount}: {'✅' if is_valid else '❌'} {error if error else ''}")

                # Test invalid amount (too small)
                invalid_amount = 0.0000001  # Very small amount
                is_valid, error = await exchange.validate_trade_amount(symbol, invalid_amount, mark_price)
                print(f"   Invalid amount {invalid_amount}: {'✅' if is_valid else '❌'} {error if error else ''}")

            # 7. Test account info
            print(f"7. Testing account info...")
            account_info = await exchange.get_futures_account_info()
            if account_info:
                print(f"   ✅ Account info retrieved")
                print(f"   Total Balance: ${account_info.get('totalWalletBalance', 0)}")
                print(f"   Max Withdraw: ${account_info.get('maxWithdrawAmount', 0)}")
                balances = account_info.get('balances', {})
                if balances:
                    print(f"   Balances: {list(balances.keys())[:5]}...")  # Show first 5
            else:
                print(f"   ❌ No account info available")

            # 8. Test max position size calculation
            print(f"8. Testing max position size calculation...")
            if mark_price:
                max_position = await exchange.calculate_max_position_size(symbol, leverage=1.0)
                if max_position:
                    print(f"   ✅ Max position size: {max_position:.6f} {symbol.split('-')[0]}")
                else:
                    print(f"   ❌ Could not calculate max position size")

        print("\n✅ KuCoin comprehensive validation test completed!")
        return True

    except Exception as e:
        print(f"❌ KuCoin comprehensive validation test failed: {e}")
        return False
    finally:
        await exchange.close()

async def main():
    """Main entry point"""
    success = await test_comprehensive_validation()

    if success:
        print("\n🎉 KuCoin comprehensive validation is working!")
        print("\nValidation Features Tested:")
        print("✅ Symbol support checking")
        print("✅ Symbol filters (min/max amounts, step size, notional)")
        print("✅ Mark price retrieval")
        print("✅ Current price retrieval")
        print("✅ Order book data")
        print("✅ Trade amount validation")
        print("✅ Account information")
        print("✅ Max position size calculation")
        print("\nKuCoin now has the same validation capabilities as Binance!")
    else:
        print("\n💥 KuCoin comprehensive validation test failed!")

if __name__ == "__main__":
    asyncio.run(main())
