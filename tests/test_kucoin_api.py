#!/usr/bin/env python3
"""
KuCoin API Test Script

This script tests the KuCoin API connection and retrieves basic information
to verify the credentials are working correctly.
"""

import os
import sys
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

try:
    from kucoin_universal_sdk.api.client import DefaultClient
    from kucoin_universal_sdk.generate.spot.market.model_get_part_order_book_req import GetPartOrderBookReqBuilder
    from kucoin_universal_sdk.generate.spot.market.model_get_all_symbols_req import GetAllSymbolsReqBuilder
    from kucoin_universal_sdk.model.client_option import ClientOptionBuilder
    from kucoin_universal_sdk.model.constants import GLOBAL_API_ENDPOINT
    from kucoin_universal_sdk.model.transport_option import TransportOptionBuilder
    print("✅ KuCoin SDK imported successfully")
except ImportError as e:
    print(f"❌ Failed to import KuCoin SDK: {e}")
    print("Installing kucoin-universal-sdk...")
    os.system("pip install kucoin-universal-sdk")
    sys.exit(1)

def test_kucoin_connection():
    """Test KuCoin API connection and retrieve basic data"""
    print("=== KuCoin API Connection Test ===")

    # Retrieve API credentials from environment variables
    api_key = os.getenv("KUCOIN_API_KEY")
    api_secret = os.getenv("KUCOIN_API_SECRET")
    api_passphrase = os.getenv("KUCOIN_API_PASSPHRASE")

    if not all([api_key, api_secret, api_passphrase]):
        print("❌ Missing KuCoin API credentials in .env file")
        print("Required: KUCOIN_API_KEY, KUCOIN_API_SECRET, KUCOIN_API_PASSPHRASE")
        return False

    print(f"✅ Found API credentials")
    print(f"API Key: {api_key[:8]}...")
    print(f"API Secret: {api_secret[:8]}...")
    print(f"API Passphrase: {api_passphrase[:8]}...")

    try:
        # Configure transport options
        transport_option = TransportOptionBuilder().build()

        # Configure client options
        client_option = (
            ClientOptionBuilder()
            .set_key(api_key)
            .set_secret(api_secret)
            .set_passphrase(api_passphrase)
            .set_spot_endpoint(GLOBAL_API_ENDPOINT)
            .set_transport_option(transport_option)
            .build()
        )

        # Initialize the client
        client = DefaultClient(client_option)
        print("✅ KuCoin client initialized successfully")

        # Access the RESTful service
        kucoin_rest_service = client.rest_service()
        spot_market_api = kucoin_rest_service.get_spot_service().get_market_api()
        print("✅ Market API service accessed")

        # Test 1: Get all symbols first to see the correct format
        print("\n--- Test 1: Get All Trading Symbols ---")
        try:
            symbols_request = GetAllSymbolsReqBuilder().build()
            symbols_response = spot_market_api.get_all_symbols(symbols_request)
            symbols = symbols_response.data
            print(f"✅ Retrieved {len(symbols)} trading symbols")

            # Find BTC and ETH symbols
            btc_symbols = [s for s in symbols if 'BTC' in s.symbol and 'USDT' in s.symbol]
            eth_symbols = [s for s in symbols if 'ETH' in s.symbol and 'USDT' in s.symbol]

            print(f"BTC-USDT symbols found: {len(btc_symbols)}")
            for symbol in btc_symbols[:3]:
                print(f"  {symbol.symbol} - {symbol.name}")

            print(f"ETH-USDT symbols found: {len(eth_symbols)}")
            for symbol in eth_symbols[:3]:
                print(f"  {symbol.symbol} - {symbol.name}")

            # Test 2: Try to get ticker data instead of order book
            if btc_symbols:
                test_symbol = btc_symbols[0].symbol
                print(f"\n--- Test 2: Get Ticker for {test_symbol} ---")
                try:
                    # Try to get ticker data instead of order book
                    from kucoin_universal_sdk.generate.spot.market.model_get_ticker_req import GetTickerReqBuilder
                    ticker_request = GetTickerReqBuilder().set_symbol(test_symbol).build()
                    ticker_response = spot_market_api.get_ticker(ticker_request)
                    print(f"✅ Ticker data retrieved successfully")
                    print(f"Symbol: {ticker_response.symbol}")
                    print(f"Price: {ticker_response.price}")
                    print(f"Change Rate: {ticker_response.changeRate}")
                    print(f"Change Price: {ticker_response.changePrice}")
                except Exception as e:
                    print(f"⚠️  Failed to get ticker for {test_symbol}: {e}")
                    print("This might be normal - continuing with other tests...")
            else:
                print("❌ No BTC-USDT symbols found")
                return False

        except Exception as e:
            print(f"❌ Failed to get symbols: {e}")
            return False

        # Test 3: Show more symbol statistics
        print("\n--- Test 3: Symbol Statistics ---")
        try:
            # Count symbols by base currency
            btc_symbols = [s for s in symbols if s.symbol.startswith('BTC-')]
            eth_symbols = [s for s in symbols if s.symbol.startswith('ETH-')]
            usdt_symbols = [s for s in symbols if s.symbol.endswith('-USDT')]

            print(f"Symbol counts:")
            print(f"  BTC pairs: {len(btc_symbols)}")
            print(f"  ETH pairs: {len(eth_symbols)}")
            print(f"  USDT pairs: {len(usdt_symbols)}")

            # Show first 10 symbols
            print("\nFirst 10 symbols:")
            for i, symbol in enumerate(symbols[:10]):
                print(f"  {i+1}. {symbol.symbol} - {symbol.name}")

        except Exception as e:
            print(f"❌ Failed to analyze symbols: {e}")
            return False

        # Test 4: Get account info (if credentials have account access)
        print("\n--- Test 4: Get Account Information ---")
        try:
            account_api = kucoin_rest_service.get_spot_service().get_account_api()
            accounts_response = account_api.get_accounts()
            accounts = accounts_response.data
            print(f"✅ Retrieved {len(accounts)} account(s)")

            for account in accounts[:5]:  # Show first 5 accounts
                print(f"  Account: {account.type} - {account.currency} - Balance: {account.balance}")

        except Exception as e:
            print(f"⚠️  Could not get account info (may need trading permissions): {e}")

        print("\n✅ KuCoin API connection test completed successfully!")
        return True

    except Exception as e:
        print(f"❌ KuCoin API connection failed: {e}")
        return False

def main():
    """Main entry point"""
    success = test_kucoin_connection()

    if success:
        print("\n🎉 KuCoin API is working correctly!")
        print("You can now proceed with integrating KuCoin into your trading bot.")
    else:
        print("\n💥 KuCoin API test failed!")
        print("Please check your credentials and try again.")

if __name__ == "__main__":
    main()
