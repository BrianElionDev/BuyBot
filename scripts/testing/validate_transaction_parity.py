#!/usr/bin/env python3
"""
Validation script to ensure KuCoin transaction history achieves parity with Binance.
This script compares transaction types and data structures between both exchanges.
"""

import os
import sys
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any, Set

# Add the project root to Python path
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(script_dir))
sys.path.insert(0, project_root)

from config import settings
from src.exchange.binance.binance_exchange import BinanceExchange
from src.exchange.kucoin.kucoin_exchange import KucoinExchange
from src.exchange.kucoin.kucoin_transaction_fetcher import KucoinTransactionFetcher
from scripts.maintenance.cleanup_scripts.autofill_transaction_history import AutoTransactionHistoryFiller

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class TransactionParityValidator:
    """Validator to ensure KuCoin and Binance transaction parity."""

    def __init__(self):
        self.binance_exchange = None
        self.kucoin_exchange = None
        self.kucoin_fetcher = None
        self.binance_autofiller = None

    async def initialize(self):
        """Initialize both exchanges."""
        try:
            # Initialize Binance exchange
            self.binance_exchange = BinanceExchange(
                api_key=settings.BINANCE_API_KEY,
                api_secret=settings.BINANCE_API_SECRET,
                is_testnet=settings.BINANCE_TESTNET
            )

            # Initialize KuCoin exchange
            self.kucoin_exchange = KucoinExchange(
                api_key=settings.KUCOIN_API_KEY,
                api_secret=settings.KUCOIN_API_SECRET,
                api_passphrase=settings.KUCOIN_API_PASSPHRASE,
                is_testnet=settings.KUCOIN_TESTNET
            )

            # Initialize KuCoin transaction fetcher
            self.kucoin_fetcher = KucoinTransactionFetcher(self.kucoin_exchange)

            # Initialize Binance autofiller
            self.binance_autofiller = AutoTransactionHistoryFiller()
            if hasattr(self.binance_autofiller, 'binance_exchange'):
                self.binance_autofiller.binance_exchange = self.binance_exchange

            logger.info("✅ Both exchanges initialized successfully")
            return True

        except Exception as e:
            logger.error(f"❌ Failed to initialize exchanges: {e}")
            return False

    async def fetch_binance_transactions(self, days: int = 7) -> List[Dict[str, Any]]:
        """Fetch Binance transaction history."""
        try:
            logger.info(f"📊 Fetching Binance transactions for last {days} days...")

            # Calculate time range
            end_time = int(datetime.now(timezone.utc).timestamp() * 1000)
            start_time = int((datetime.now(timezone.utc) - timedelta(days=days)).timestamp() * 1000)

            # Fetch income history (primary source for Binance transactions)
            income_records = await self.binance_exchange.get_income_history(
                start_time=start_time,
                end_time=end_time,
                limit=1000
            )

            # Transform to transaction format
            transactions = []
            for income in income_records:
                if isinstance(income, dict):
                    time_ms = int(income.get('time', 0))
                    dt = datetime.fromtimestamp(time_ms / 1000, tz=timezone.utc)
                    time_timestampz = dt.isoformat()

                    transaction = {
                        'time': time_timestampz,
                        'type': income.get('incomeType', income.get('type', '')),
                        'amount': float(income.get('income', 0.0)),
                        'asset': income.get('asset', ''),
                        'symbol': income.get('symbol', ''),
                        'exchange': 'binance'
                    }
                    transactions.append(transaction)

            logger.info(f"📊 Retrieved {len(transactions)} Binance transactions")
            return transactions

        except Exception as e:
            logger.error(f"❌ Failed to fetch Binance transactions: {e}")
            return []

    async def fetch_kucoin_transactions(self, days: int = 7) -> List[Dict[str, Any]]:
        """Fetch KuCoin transaction history."""
        try:
            logger.info(f"📊 Fetching KuCoin transactions for last {days} days...")

            # Calculate time range
            end_time = int(datetime.now(timezone.utc).timestamp() * 1000)
            start_time = int((datetime.now(timezone.utc) - timedelta(days=days)).timestamp() * 1000)

            # Fetch comprehensive transaction history
            transactions = await self.kucoin_fetcher.fetch_transaction_history(
                symbol="",  # All symbols
                start_time=start_time,
                end_time=end_time,
                limit=1000
            )

            logger.info(f"📊 Retrieved {len(transactions)} KuCoin transactions")
            return transactions

        except Exception as e:
            logger.error(f"❌ Failed to fetch KuCoin transactions: {e}")
            return []

    def analyze_transaction_types(self, transactions: List[Dict[str, Any]], exchange: str) -> Dict[str, Any]:
        """Analyze transaction types for an exchange."""
        if not transactions:
            return {
                'total_count': 0,
                'types': {},
                'assets': {},
                'symbols': {},
                'type_coverage': set()
            }

        types = {}
        assets = {}
        symbols = {}
        type_coverage = set()

        for transaction in transactions:
            trans_type = transaction.get('type', 'Unknown')
            asset = transaction.get('asset', 'Unknown')
            symbol = transaction.get('symbol', 'Unknown')

            types[trans_type] = types.get(trans_type, 0) + 1
            assets[asset] = assets.get(asset, 0) + 1
            symbols[symbol] = symbols.get(symbol, 0) + 1
            type_coverage.add(trans_type)

        return {
            'total_count': len(transactions),
            'types': types,
            'assets': assets,
            'symbols': symbols,
            'type_coverage': type_coverage
        }

    def compare_transaction_parity(self, binance_data: Dict[str, Any], kucoin_data: Dict[str, Any]) -> Dict[str, Any]:
        """Compare transaction parity between exchanges."""

        # Expected transaction types (from Binance)
        expected_types = {
            'REALIZED_PNL', 'COMMISSION', 'FUNDING_FEE', 'TRANSFER',
            'WELCOME_BONUS', 'INSURANCE_CLEAR'
        }

        binance_types = binance_data['type_coverage']
        kucoin_types = kucoin_data['type_coverage']

        # Find missing types in KuCoin
        missing_in_kucoin = expected_types - kucoin_types
        missing_in_binance = expected_types - binance_types

        # Find extra types in KuCoin
        extra_in_kucoin = kucoin_types - expected_types
        extra_in_binance = binance_types - expected_types

        # Calculate coverage percentage
        kucoin_coverage = len(kucoin_types & expected_types) / len(expected_types) * 100
        binance_coverage = len(binance_types & expected_types) / len(expected_types) * 100

        return {
            'expected_types': expected_types,
            'binance_types': binance_types,
            'kucoin_types': kucoin_types,
            'missing_in_kucoin': missing_in_kucoin,
            'missing_in_binance': missing_in_binance,
            'extra_in_kucoin': extra_in_kucoin,
            'extra_in_binance': extra_in_binance,
            'kucoin_coverage_percentage': kucoin_coverage,
            'binance_coverage_percentage': binance_coverage,
            'parity_achieved': len(missing_in_kucoin) == 0 and kucoin_coverage >= 80
        }

    def print_analysis_report(self, binance_data: Dict[str, Any], kucoin_data: Dict[str, Any], comparison: Dict[str, Any]):
        """Print comprehensive analysis report."""

        logger.info(f"\n{'='*80}")
        logger.info("TRANSACTION PARITY ANALYSIS REPORT")
        logger.info(f"{'='*80}")

        # Exchange summaries
        logger.info(f"\n📊 EXCHANGE SUMMARIES:")
        logger.info(f"   Binance: {binance_data['total_count']} transactions")
        logger.info(f"   KuCoin:  {kucoin_data['total_count']} transactions")

        # Transaction types comparison
        logger.info(f"\n📋 TRANSACTION TYPES COMPARISON:")
        logger.info(f"   Expected Types: {sorted(comparison['expected_types'])}")
        logger.info(f"   Binance Types:  {sorted(comparison['binance_types'])}")
        logger.info(f"   KuCoin Types:   {sorted(comparison['kucoin_types'])}")

        # Coverage analysis
        logger.info(f"\n📈 COVERAGE ANALYSIS:")
        logger.info(f"   Binance Coverage: {comparison['binance_coverage_percentage']:.1f}%")
        logger.info(f"   KuCoin Coverage:  {comparison['kucoin_coverage_percentage']:.1f}%")

        # Missing types
        if comparison['missing_in_kucoin']:
            logger.warning(f"\n⚠️  MISSING IN KUCOIN: {sorted(comparison['missing_in_kucoin'])}")
        else:
            logger.info(f"\n✅ KUCOIN HAS ALL EXPECTED TYPES")

        if comparison['missing_in_binance']:
            logger.warning(f"\n⚠️  MISSING IN BINANCE: {sorted(comparison['missing_in_binance'])}")
        else:
            logger.info(f"\n✅ BINANCE HAS ALL EXPECTED TYPES")

        # Extra types
        if comparison['extra_in_kucoin']:
            logger.info(f"\n➕ EXTRA IN KUCOIN: {sorted(comparison['extra_in_kucoin'])}")

        if comparison['extra_in_binance']:
            logger.info(f"\n➕ EXTRA IN BINANCE: {sorted(comparison['extra_in_binance'])}")

        # Detailed type breakdown
        logger.info(f"\n📊 DETAILED TYPE BREAKDOWN:")
        logger.info(f"   {'Type':<20} {'Binance':<10} {'KuCoin':<10} {'Status':<10}")
        logger.info(f"   {'-'*20} {'-'*10} {'-'*10} {'-'*10}")

        all_types = comparison['expected_types'] | comparison['binance_types'] | comparison['kucoin_types']
        for trans_type in sorted(all_types):
            binance_count = binance_data['types'].get(trans_type, 0)
            kucoin_count = kucoin_data['types'].get(trans_type, 0)

            if trans_type in comparison['expected_types']:
                if trans_type in comparison['kucoin_types']:
                    status = "✅ PARITY"
                else:
                    status = "❌ MISSING"
            else:
                status = "➕ EXTRA"

            logger.info(f"   {trans_type:<20} {binance_count:<10} {kucoin_count:<10} {status:<10}")

        # Final verdict
        logger.info(f"\n🎯 FINAL VERDICT:")
        if comparison['parity_achieved']:
            logger.info(f"   ✅ PARITY ACHIEVED: KuCoin successfully captures all expected transaction types")
        else:
            logger.info(f"   ❌ PARITY NOT ACHIEVED: KuCoin is missing {len(comparison['missing_in_kucoin'])} expected types")

        logger.info(f"   📊 KuCoin Coverage: {comparison['kucoin_coverage_percentage']:.1f}% of expected types")

    async def run_validation(self, days: int = 7):
        """Run complete validation."""
        logger.info("🚀 Starting transaction parity validation...")

        # Initialize
        if not await self.initialize():
            return False

        try:
            # Fetch transaction data from both exchanges
            binance_transactions = await self.fetch_binance_transactions(days)
            kucoin_transactions = await self.fetch_kucoin_transactions(days)

            # Analyze transaction types
            binance_data = self.analyze_transaction_types(binance_transactions, 'binance')
            kucoin_data = self.analyze_transaction_types(kucoin_transactions, 'kucoin')

            # Compare parity
            comparison = self.compare_transaction_parity(binance_data, kucoin_data)

            # Print comprehensive report
            self.print_analysis_report(binance_data, kucoin_data, comparison)

            return comparison['parity_achieved']

        except Exception as e:
            logger.error(f"❌ Validation failed: {e}")
            return False

    async def cleanup(self):
        """Cleanup resources."""
        try:
            if self.binance_exchange:
                await self.binance_exchange.close_client()
            if self.kucoin_exchange:
                await self.kucoin_exchange.close_client()
            logger.info("🧹 Cleanup completed")
        except Exception as e:
            logger.error(f"❌ Cleanup error: {e}")


async def main():
    """Main validation function."""
    validator = TransactionParityValidator()

    try:
        success = await validator.run_validation(days=7)
        return 0 if success else 1
    except Exception as e:
        logger.error(f"❌ Validation execution failed: {e}")
        return 1
    finally:
        await validator.cleanup()


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
