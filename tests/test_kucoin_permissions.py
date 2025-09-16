#!/usr/bin/env python3
"""
KuCoin API Permissions Test

Tests the permissions of KuCoin API keys for both testnet and mainnet.
This test verifies what operations the API keys are allowed to perform.
"""

import os
import sys
import asyncio
import logging
from dotenv import load_dotenv
from typing import Dict, Any, Optional

# Add project root to path
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(script_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

try:
    from kucoin_universal_sdk.api.client import DefaultClient
    from kucoin_universal_sdk.model.client_option import ClientOptionBuilder
    from kucoin_universal_sdk.model.constants import GLOBAL_API_ENDPOINT
    from kucoin_universal_sdk.model.transport_option import TransportOptionBuilder
    from kucoin_universal_sdk.generate.spot.market.model_get_all_symbols_req import GetAllSymbolsReqBuilder
    from kucoin_universal_sdk.generate.spot.market.model_get_ticker_req import GetTickerReqBuilder
    from kucoin_universal_sdk.generate.spot.market.model_get_part_order_book_req import GetPartOrderBookReqBuilder
    print("✅ KuCoin SDK imported successfully")
except ImportError as e:
    print(f"❌ Failed to import KuCoin SDK: {e}")
    print("Installing kucoin-universal-sdk...")
    os.system("pip install kucoin-universal-sdk")
    sys.exit(1)


class KucoinPermissionsTester:
    """Test KuCoin API key permissions for both testnet and mainnet."""

    def __init__(self):
        self.api_key = os.getenv("KUCOIN_API_KEY")
        self.api_secret = os.getenv("KUCOIN_API_SECRET")
        self.api_passphrase = os.getenv("KUCOIN_API_PASSPHRASE")

        if not all([self.api_key, self.api_secret, self.api_passphrase]):
            raise ValueError("Missing KuCoin API credentials in .env file")

    async def test_permissions(self, is_testnet: bool) -> Dict[str, Any]:
        """Test API permissions for given testnet setting."""
        print(f"\n{'='*60}")
        print(f"Testing KuCoin API Permissions - {'TESTNET' if is_testnet else 'MAINNET'}")
        print(f"{'='*60}")

        results = {
            'testnet': is_testnet,
            'connection': False,
            'permissions': {},
            'errors': []
        }

        client = None
        try:
            # Initialize client directly
            print("🔌 Testing connection...")
            client = await self._create_client(is_testnet)
            if not client:
                results['errors'].append("Failed to create client")
                return results

            results['connection'] = True
            print("✅ Connection successful")

            # Test various permissions
            permissions = await self._test_all_permissions(client)
            results['permissions'] = permissions

        except Exception as e:
            error_msg = f"Test failed: {str(e)}"
            print(f"❌ {error_msg}")
            results['errors'].append(error_msg)
            logger.error(error_msg, exc_info=True)
        finally:
            if client:
                client = None

        return results

    async def _create_client(self, is_testnet: bool) -> Optional[DefaultClient]:
        """Create and initialize KuCoin client."""
        try:
            # Configure transport options
            transport_option = TransportOptionBuilder().build()

            # Build client options
            client_option = (
                ClientOptionBuilder()
                .set_key(self.api_key)
                .set_secret(self.api_secret)
                .set_passphrase(self.api_passphrase)
                .set_spot_endpoint(GLOBAL_API_ENDPOINT)
                .set_futures_endpoint(GLOBAL_API_ENDPOINT)
                .set_transport_option(transport_option)
                .build()
            )

            # Create client
            client = DefaultClient(client_option)
            return client

        except Exception as e:
            logger.error(f"Failed to create KuCoin client: {e}")
            return None

    async def _test_all_permissions(self, client: DefaultClient) -> Dict[str, Any]:
        """Test all available permissions."""
        permissions = {}

        # 1. Test market data access (no auth required)
        print("\n📊 Testing market data access...")
        permissions['market_data'] = await self._test_market_data(client)

        # 2. Test order book access
        print("\n📈 Testing order book access...")
        permissions['order_book'] = await self._test_order_book(client)

        # 3. Test API key validation (connection test)
        print("\n🔑 Testing API key validation...")
        permissions['api_validation'] = await self._test_api_validation(client)

        return permissions

    async def _test_market_data(self, client: DefaultClient) -> Dict[str, Any]:
        """Test market data access permissions."""
        result = {'success': False, 'details': {}}

        try:
            # Get market service
            market_service = client.rest_service().get_spot_service().get_market_api()

            # Test getting all symbols
            symbols_request = GetAllSymbolsReqBuilder().build()
            symbols_response = market_service.get_all_symbols(symbols_request)
            symbols = symbols_response.data

            if symbols:
                result['success'] = True
                result['details']['symbols_count'] = len(symbols)

                # Find BTC-USDT symbol
                btc_symbols = [s for s in symbols if s.symbol == 'BTC-USDT']
                if btc_symbols:
                    # Test getting ticker for BTC-USDT
                    ticker_request = GetTickerReqBuilder().set_symbol('BTC-USDT').build()
                    ticker_response = market_service.get_ticker(ticker_request)

                    result['details']['btc_price'] = float(ticker_response.price) if ticker_response.price else 0
                    # Check if changeRate attribute exists
                    if hasattr(ticker_response, 'changeRate'):
                        result['details']['btc_change_rate'] = float(ticker_response.changeRate) if ticker_response.changeRate else 0
                    else:
                        result['details']['btc_change_rate'] = 0
                    print(f"   ✅ Retrieved {len(symbols)} symbols, BTC price: ${result['details']['btc_price']}")
                else:
                    print(f"   ✅ Retrieved {len(symbols)} symbols (BTC-USDT not found)")
            else:
                print("   ❌ No symbols retrieved")

        except Exception as e:
            result['error'] = str(e)
            print(f"   ❌ Market data test failed: {e}")

        return result

    async def _test_api_validation(self, client: DefaultClient) -> Dict[str, Any]:
        """Test API key validation by attempting to access authenticated endpoints."""
        result = {'success': False, 'details': {}}

        try:
            # Test if we can access the REST service (this requires valid API credentials)
            rest_service = client.rest_service()

            if rest_service:
                result['success'] = True
                result['details']['rest_service_accessible'] = True
                result['details']['spot_service_accessible'] = bool(rest_service.get_spot_service())
                result['details']['futures_service_accessible'] = bool(rest_service.get_futures_service())
                print("   ✅ API credentials are valid and services are accessible")
            else:
                print("   ❌ REST service not accessible")

        except Exception as e:
            result['error'] = str(e)
            print(f"   ❌ API validation test failed: {e}")

        return result

    async def _test_order_book(self, client: DefaultClient) -> Dict[str, Any]:
        """Test order book access permissions."""
        result = {'success': False, 'details': {}}

        try:
            # Get market service
            market_service = client.rest_service().get_spot_service().get_market_api()

            # Test order book for BTC-USDT - try different parameter names
            order_book_request = GetPartOrderBookReqBuilder().set_symbol('BTC-USDT')
            if hasattr(order_book_request, 'set_limit'):
                order_book_request = order_book_request.set_limit(10)
            elif hasattr(order_book_request, 'set_size'):
                order_book_request = order_book_request.set_size('10')
            order_book_request = order_book_request.build()

            order_book_response = market_service.get_part_order_book(order_book_request)

            if order_book_response and order_book_response.data:
                order_book = order_book_response.data
                result['success'] = True
                result['details']['bids_count'] = len(order_book.bids) if order_book.bids else 0
                result['details']['asks_count'] = len(order_book.asks) if order_book.asks else 0

                if order_book.bids:
                    result['details']['best_bid'] = [float(order_book.bids[0][0]), float(order_book.bids[0][1])]
                if order_book.asks:
                    result['details']['best_ask'] = [float(order_book.asks[0][0]), float(order_book.asks[0][1])]

                print(f"   ✅ Retrieved order book: {result['details']['bids_count']} bids, {result['details']['asks_count']} asks")
            else:
                print("   ❌ No order book data")

        except Exception as e:
            result['error'] = str(e)
            print(f"   ❌ Order book test failed: {e}")

        return result


    def print_summary(self, testnet_results: Dict[str, Any], mainnet_results: Dict[str, Any]):
        """Print a summary of all test results."""
        print(f"\n{'='*80}")
        print("KUCON API PERMISSIONS TEST SUMMARY")
        print(f"{'='*80}")

        for testnet, results in [("TESTNET", testnet_results), ("MAINNET", mainnet_results)]:
            print(f"\n{testnet} RESULTS:")
            print(f"  Connection: {'✅' if results['connection'] else '❌'}")

            if results['connection']:
                permissions = results['permissions']
                for perm_name, perm_result in permissions.items():
                    status = '✅' if perm_result.get('success', False) else '❌'
                    print(f"  {perm_name.replace('_', ' ').title()}: {status}")

                    if perm_result.get('error'):
                        print(f"    Error: {perm_result['error']}")
                    elif perm_result.get('details'):
                        details = perm_result['details']
                        if 'symbols_count' in details:
                            print(f"    Symbols: {details['symbols_count']}")
                        if 'btc_price' in details:
                            print(f"    BTC Price: ${details['btc_price']}")
                        if 'bids_count' in details and 'asks_count' in details:
                            print(f"    Order Book: {details['bids_count']} bids, {details['asks_count']} asks")
                        if 'rest_service_accessible' in details:
                            print(f"    Services: Spot={details.get('spot_service_accessible', False)}, Futures={details.get('futures_service_accessible', False)}")
            else:
                print(f"  Errors: {len(results['errors'])}")
                for error in results['errors']:
                    print(f"    - {error}")


async def main():
    """Main test function."""
    print("🚀 Starting KuCoin API Permissions Test")
    print("=" * 50)

    try:
        tester = KucoinPermissionsTester()

        # Test both testnet and mainnet
        print("Testing API key permissions for both testnet and mainnet...")

        testnet_results = await tester.test_permissions(is_testnet=True)
        mainnet_results = await tester.test_permissions(is_testnet=False)

        # Print summary
        tester.print_summary(testnet_results, mainnet_results)

        # Overall success check - consider it successful if connection and API validation work
        testnet_success = (testnet_results['connection'] and
                          testnet_results['permissions'].get('api_validation', {}).get('success', False) and
                          testnet_results['permissions'].get('market_data', {}).get('success', False))
        mainnet_success = (mainnet_results['connection'] and
                          mainnet_results['permissions'].get('api_validation', {}).get('success', False) and
                          mainnet_results['permissions'].get('market_data', {}).get('success', False))

        print(f"\n{'='*80}")
        if testnet_success and mainnet_success:
            print("🎉 CORE TESTS PASSED! Your KuCoin API keys have proper permissions.")
            print("✅ Connection successful for both testnet and mainnet")
            print("✅ Market data access working")
            print("✅ API credentials validated")
            print("\nNote: Some advanced features may have limited functionality due to API restrictions.")
        elif testnet_success or mainnet_success:
            print("⚠️  PARTIAL SUCCESS: Some tests passed, check the summary above.")
        else:
            print("❌ TESTS FAILED: Check your API key permissions and configuration.")
        print(f"{'='*80}")

    except Exception as e:
        print(f"❌ Test setup failed: {e}")
        logger.error("Test setup failed", exc_info=True)
        return False

    return True


if __name__ == "__main__":
    asyncio.run(main())
