#!/usr/bin/env python3
"""
Test script to verify transaction_history table functionality.
"""

import sys
import asyncio
import logging
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Dict

sys.path.append(str(Path(__file__).parent.parent))

from discord_bot.discord_bot import DiscordBot
from discord_bot.database import DatabaseManager

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class TransactionHistoryTester:
    def __init__(self):
        self.bot = DiscordBot()
        self.db_manager = DatabaseManager(self.bot.supabase)

    async def test_database_connection(self) -> bool:
        """Test database connection and table access."""
        try:
            # Try to get a single record from transaction_history
            records = await self.db_manager.get_transaction_history(limit=1)
            logger.info("Database connection successful")
            return True
        except Exception as e:
            logger.error(f"Database connection failed: {e}")
            return False

    async def test_insert_single_record(self) -> bool:
        """Test inserting a single transaction record."""
        try:
            # Create a test transaction record
            test_transaction = {
                'time': int(datetime.now(timezone.utc).timestamp() * 1000),
                'type': 'TEST_RECORD',
                'amount': 0.001,
                'asset': 'USDT',
                'symbol': 'TESTUSDT'
            }

            # Insert the record
            result = await self.db_manager.insert_transaction_history(test_transaction)
            
            if result:
                logger.info(f"Successfully inserted test record: {result}")
                return True
            else:
                logger.error("Failed to insert test record")
                return False

        except Exception as e:
            logger.error(f"Error testing single record insert: {e}")
            return False

    async def test_batch_insert(self) -> bool:
        """Test batch insert functionality."""
        try:
            # Create test transaction records
            test_transactions = []
            base_time = int(datetime.now(timezone.utc).timestamp() * 1000)
            
            for i in range(5):
                test_transaction = {
                    'time': base_time + i * 1000,  # 1 second apart
                    'type': f'BATCH_TEST_{i}',
                    'amount': 0.001 + i * 0.001,
                    'asset': 'USDT',
                    'symbol': 'BATCHTESTUSDT'
                }
                test_transactions.append(test_transaction)

            # Insert batch
            success = await self.db_manager.insert_transaction_history_batch(test_transactions)
            
            if success:
                logger.info(f"Successfully inserted {len(test_transactions)} test records in batch")
                return True
            else:
                logger.error("Failed to insert test records in batch")
                return False

        except Exception as e:
            logger.error(f"Error testing batch insert: {e}")
            return False

    async def test_duplicate_checking(self) -> bool:
        """Test duplicate checking functionality."""
        try:
            # Create a test transaction
            test_transaction = {
                'time': int(datetime.now(timezone.utc).timestamp() * 1000),
                'type': 'DUPLICATE_TEST',
                'amount': 0.002,
                'asset': 'USDT',
                'symbol': 'DUPTESTUSDT'
            }

            # Insert the record
            await self.db_manager.insert_transaction_history(test_transaction)
            
            # Check if it exists
            exists = await self.db_manager.check_transaction_exists(
                time=test_transaction['time'],
                type=test_transaction['type'],
                amount=test_transaction['amount'],
                asset=test_transaction['asset'],
                symbol=test_transaction['symbol']
            )
            
            if exists:
                logger.info("Duplicate checking works correctly")
                return True
            else:
                logger.error("Duplicate checking failed")
                return False

        except Exception as e:
            logger.error(f"Error testing duplicate checking: {e}")
            return False

    async def test_fetch_income_data(self) -> bool:
        """Test fetching income data from Binance API."""
        try:
            # Initialize Binance client
            if not self.bot.binance_exchange.client:
                await self.bot.binance_exchange._init_client()

            # Calculate time range (last 24 hours)
            end_time = int(datetime.now(timezone.utc).timestamp() * 1000)
            start_time = int((datetime.now(timezone.utc) - timedelta(days=1)).timestamp() * 1000)

            # Fetch income data for BTCUSDT
            income_records = await self.bot.binance_exchange.get_income_history(
                symbol='BTCUSDT',
                start_time=start_time,
                end_time=end_time,
                limit=10
            )

            if income_records:
                logger.info(f"Successfully fetched {len(income_records)} income records from Binance API")
                return True
            else:
                logger.warning("No income records found (this might be normal if no recent activity)")
                return True  # This is not necessarily an error

        except Exception as e:
            logger.error(f"Error testing income data fetch: {e}")
            return False

    async def test_full_workflow(self) -> bool:
        """Test the complete workflow from income data to database."""
        try:
            # Initialize Binance client
            if not self.bot.binance_exchange.client:
                await self.bot.binance_exchange._init_client()

            # Calculate time range (last 24 hours)
            end_time = int(datetime.now(timezone.utc).timestamp() * 1000)
            start_time = int((datetime.now(timezone.utc) - timedelta(days=1)).timestamp() * 1000)

            # Fetch income data for ETHUSDT
            income_records = await self.bot.binance_exchange.get_income_history(
                symbol='ETHUSDT',
                start_time=start_time,
                end_time=end_time,
                limit=5
            )

            if not income_records:
                logger.warning("No income records found for workflow test")
                return True

            # Transform and insert records
            inserted_count = 0
            for income in income_records:
                if not isinstance(income, dict):
                    continue

                # Transform income record to transaction format
                transaction = {
                    'time': int(income.get('time', 0)),
                    'type': income.get('incomeType', income.get('type', '')),
                    'amount': float(income.get('income', 0.0)),
                    'asset': income.get('asset', ''),
                    'symbol': income.get('symbol', '')
                }

                # Check for duplicates and insert
                exists = await self.db_manager.check_transaction_exists(
                    time=transaction['time'],
                    type=transaction['type'],
                    amount=transaction['amount'],
                    asset=transaction['asset'],
                    symbol=transaction['symbol']
                )

                if not exists:
                    result = await self.db_manager.insert_transaction_history(transaction)
                    if result:
                        inserted_count += 1

            logger.info(f"Workflow test completed: {inserted_count} records inserted")
            return True

        except Exception as e:
            logger.error(f"Error in workflow test: {e}")
            return False

    async def run_all_tests(self) -> Dict[str, bool]:
        """Run all tests and return results."""
        logger.info("Starting transaction history tests...")
        
        results = {}
        
        # Test database connection
        results['database_connection'] = await self.test_database_connection()
        
        # Test single record insert
        results['single_insert'] = await self.test_insert_single_record()
        
        # Test batch insert
        results['batch_insert'] = await self.test_batch_insert()
        
        # Test duplicate checking
        results['duplicate_checking'] = await self.test_duplicate_checking()
        
        # Test income data fetch
        results['income_fetch'] = await self.test_fetch_income_data()
        
        # Test full workflow
        results['full_workflow'] = await self.test_full_workflow()
        
        return results


async def main():
    """Main function for testing transaction history functionality."""
    tester = TransactionHistoryTester()
    
    print("=== Transaction History Table Tests ===")
    
    results = await tester.run_all_tests()
    
    print(f"\n=== Test Results ===")
    for test_name, passed in results.items():
        status = "PASS" if passed else "FAIL"
        print(f"{test_name}: {status}")
    
    # Summary
    passed_tests = sum(results.values())
    total_tests = len(results)
    
    print(f"\n=== Summary ===")
    print(f"Passed: {passed_tests}/{total_tests} tests")
    
    if passed_tests == total_tests:
        print("All tests passed! Transaction history functionality is working correctly.")
    else:
        print("Some tests failed. Please check the logs for details.")


if __name__ == "__main__":
    asyncio.run(main())
