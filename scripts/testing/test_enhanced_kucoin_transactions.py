#!/usr/bin/env python3
"""
Test script for enhanced KuCoin transaction history functionality.
This script tests the comprehensive transaction history fetching from KuCoin
to ensure parity with Binance transaction data.
"""

import os
import sys
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any

# Add the project root to Python path
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(script_dir))
sys.path.insert(0, project_root)

from config import settings
from src.exchange.kucoin.kucoin_exchange import KucoinExchange
from src.exchange.kucoin.kucoin_transaction_fetcher import KucoinTransactionFetcher

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class KuCoinTransactionTester:
    """Test class for enhanced KuCoin transaction functionality."""

    def __init__(self):
        self.kucoin_exchange = None
        self.transaction_fetcher = None

    async def initialize(self):
        """Initialize KuCoin exchange and transaction fetcher."""
        try:
            # Initialize KuCoin exchange
            self.kucoin_exchange = KucoinExchange(
                api_key=settings.KUCOIN_API_KEY,
                api_secret=settings.KUCOIN_API_SECRET,
                api_passphrase=settings.KUCOIN_API_PASSPHRASE,
                is_testnet=settings.KUCOIN_TESTNET
            )

            # Initialize transaction fetcher
            self.transaction_fetcher = KucoinTransactionFetcher(self.kucoin_exchange)

            logger.info("✅ KuCoin exchange and transaction fetcher initialized")
            return True

        except Exception as e:
            logger.error(f"❌ Failed to initialize KuCoin: {e}")
            return False

    async def test_account_ledgers(self):
        """Test account ledgers functionality."""
        try:
            logger.info("🧪 Testing account ledgers...")

            # Test regular account ledgers
            end_time = int(datetime.now(timezone.utc).timestamp() * 1000)
            start_time = int((datetime.now(timezone.utc) - timedelta(days=1)).timestamp() * 1000)

            ledgers = await self.kucoin_exchange.get_account_ledgers(
                start_time=start_time,
                end_time=end_time,
                limit=100
            )

            logger.info(f"📊 Retrieved {len(ledgers)} account ledger records")

            # Test futures account ledgers
            futures_ledgers = await self.kucoin_exchange.get_futures_account_ledgers(
                start_time=start_time,
                end_time=end_time,
                limit=100
            )

            logger.info(f"📊 Retrieved {len(futures_ledgers)} futures account ledger records")

            # Analyze ledger types
            self._analyze_ledger_types(ledgers, "Account Ledgers")
            self._analyze_ledger_types(futures_ledgers, "Futures Account Ledgers")

            return True

        except Exception as e:
            logger.error(f"❌ Account ledgers test failed: {e}")
            return False

    async def test_comprehensive_transaction_history(self):
        """Test comprehensive transaction history fetching."""
        try:
            logger.info("🧪 Testing comprehensive transaction history...")

            # Calculate time range (last 24 hours)
            end_time = int(datetime.now(timezone.utc).timestamp() * 1000)
            start_time = int((datetime.now(timezone.utc) - timedelta(hours=24)).timestamp() * 1000)

            # Fetch comprehensive transaction history
            transactions = await self.transaction_fetcher.fetch_transaction_history(
                symbol="",  # All symbols
                start_time=start_time,
                end_time=end_time,
                limit=1000
            )

            logger.info(f"📊 Retrieved {len(transactions)} comprehensive transaction records")

            # Analyze transaction types
            self._analyze_transaction_types(transactions)

            # Show sample transactions
            self._show_sample_transactions(transactions)

            return True

        except Exception as e:
            logger.error(f"❌ Comprehensive transaction history test failed: {e}")
            return False

    async def test_symbol_specific_transactions(self):
        """Test symbol-specific transaction fetching."""
        try:
            logger.info("🧪 Testing symbol-specific transaction history...")

            # Test with common symbols
            test_symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]

            for symbol in test_symbols:
                logger.info(f"Testing symbol: {symbol}")

                end_time = int(datetime.now(timezone.utc).timestamp() * 1000)
                start_time = int((datetime.now(timezone.utc) - timedelta(hours=24)).timestamp() * 1000)

                transactions = await self.transaction_fetcher.fetch_transaction_history(
                    symbol=symbol,
                    start_time=start_time,
                    end_time=end_time,
                    limit=100
                )

                logger.info(f"📊 {symbol}: {len(transactions)} transactions")

                if transactions:
                    self._analyze_transaction_types(transactions, f" for {symbol}")

            return True

        except Exception as e:
            logger.error(f"❌ Symbol-specific transaction test failed: {e}")
            return False

    def _analyze_ledger_types(self, ledgers: List[Dict[str, Any]], source: str):
        """Analyze and log ledger types."""
        if not ledgers:
            logger.info(f"📋 {source}: No ledgers found")
            return

        biz_types = {}
        directions = {}

        for ledger in ledgers:
            biz_type = ledger.get('bizType', 'Unknown')
            direction = ledger.get('direction', 'Unknown')

            biz_types[biz_type] = biz_types.get(biz_type, 0) + 1
            directions[direction] = directions.get(direction, 0) + 1

        logger.info(f"📋 {source} Analysis:")
        logger.info(f"   Business Types: {dict(sorted(biz_types.items(), key=lambda x: x[1], reverse=True))}")
        logger.info(f"   Directions: {dict(sorted(directions.items(), key=lambda x: x[1], reverse=True))}")

    def _analyze_transaction_types(self, transactions: List[Dict[str, Any]], suffix: str = ""):
        """Analyze and log transaction types."""
        if not transactions:
            logger.info(f"📋 Transaction Types{suffix}: No transactions found")
            return

        types = {}
        assets = {}
        exchanges = {}

        for transaction in transactions:
            trans_type = transaction.get('type', 'Unknown')
            asset = transaction.get('asset', 'Unknown')
            exchange = transaction.get('exchange', 'Unknown')

            types[trans_type] = types.get(trans_type, 0) + 1
            assets[asset] = assets.get(asset, 0) + 1
            exchanges[exchange] = exchanges.get(exchange, 0) + 1

        logger.info(f"📋 Transaction Types{suffix} Analysis:")
        logger.info(f"   Types: {dict(sorted(types.items(), key=lambda x: x[1], reverse=True))}")
        logger.info(f"   Assets: {dict(sorted(assets.items(), key=lambda x: x[1], reverse=True))}")
        logger.info(f"   Exchanges: {dict(sorted(exchanges.items(), key=lambda x: x[1], reverse=True))}")

    def _show_sample_transactions(self, transactions: List[Dict[str, Any]], count: int = 5):
        """Show sample transactions."""
        if not transactions:
            logger.info("📋 No sample transactions to show")
            return

        logger.info(f"📋 Sample Transactions (showing {min(count, len(transactions))}):")

        for i, transaction in enumerate(transactions[:count]):
            logger.info(f"   {i+1}. {transaction.get('time', 'N/A')} | "
                       f"{transaction.get('type', 'N/A')} | "
                       f"{transaction.get('amount', 0)} {transaction.get('asset', 'N/A')} | "
                       f"{transaction.get('symbol', 'N/A')} | "
                       f"{transaction.get('exchange', 'N/A')}")

    async def run_all_tests(self):
        """Run all tests."""
        logger.info("🚀 Starting KuCoin transaction history tests...")

        # Initialize
        if not await self.initialize():
            return False

        # Run tests
        tests = [
            ("Account Ledgers", self.test_account_ledgers),
            ("Comprehensive Transaction History", self.test_comprehensive_transaction_history),
            ("Symbol-Specific Transactions", self.test_symbol_specific_transactions),
        ]

        results = {}
        for test_name, test_func in tests:
            logger.info(f"\n{'='*50}")
            logger.info(f"Running test: {test_name}")
            logger.info(f"{'='*50}")

            try:
                result = await test_func()
                results[test_name] = result
                logger.info(f"✅ {test_name}: {'PASSED' if result else 'FAILED'}")
            except Exception as e:
                logger.error(f"❌ {test_name}: FAILED - {e}")
                results[test_name] = False

        # Summary
        logger.info(f"\n{'='*50}")
        logger.info("TEST SUMMARY")
        logger.info(f"{'='*50}")

        passed = sum(1 for result in results.values() if result)
        total = len(results)

        for test_name, result in results.items():
            status = "✅ PASSED" if result else "❌ FAILED"
            logger.info(f"{test_name}: {status}")

        logger.info(f"\nOverall: {passed}/{total} tests passed")

        return passed == total

    async def cleanup(self):
        """Cleanup resources."""
        try:
            if self.kucoin_exchange:
                await self.kucoin_exchange.close_client()
            logger.info("🧹 Cleanup completed")
        except Exception as e:
            logger.error(f"❌ Cleanup error: {e}")


async def main():
    """Main test function."""
    tester = KuCoinTransactionTester()

    try:
        success = await tester.run_all_tests()
        return 0 if success else 1
    except Exception as e:
        logger.error(f"❌ Test execution failed: {e}")
        return 1
    finally:
        await tester.cleanup()


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
