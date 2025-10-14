#!/usr/bin/env python3
"""
Manual script to fill transaction_history table with data from Binance /income endpoint.
This script allows manual control over the data fetching and insertion process.
"""

import sys
import os
import asyncio
import logging
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional

# Add project root to path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from discord_bot.discord_bot import DiscordBot
from discord_bot.database import DatabaseManager

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class TransactionHistoryFiller:
    def __init__(self):
        self.bot = DiscordBot()
        self.db_manager = DatabaseManager(self.bot.supabase)

    async def fetch_income_data(self, symbol: str = "", start_time: int = 0, end_time: int = 0,
                               income_type: str = "", limit: int = 1000) -> List[Dict[str, Any]]:
        """
        Fetch income data from Binance API.

        Args:
            symbol: Trading pair symbol (e.g., 'BTCUSDT') - if empty, fetches all symbols
            start_time: Start time in milliseconds
            end_time: End time in milliseconds
            income_type: Income type filter (optional)
            limit: Number of records to retrieve

        Returns:
            List of income records
        """
        try:
            # Get the last sync time to avoid re-syncing existing transactions
            last_sync_time = await self.db_manager.get_last_transaction_sync_time()

            # If we have existing transactions, start from the last one + 1ms
            if last_sync_time and last_sync_time > 0 and start_time < last_sync_time:
                start_time = last_sync_time + 1
                logger.info(f"Starting sync from last transaction time: {start_time} ({datetime.fromtimestamp(start_time/1000, tz=timezone.utc)})")

            logger.info(f"Fetching income data for {symbol or 'ALL SYMBOLS'} from {start_time} to {end_time}")

            income_records = await self.bot.binance_exchange.get_income_history(
                symbol=symbol,
                income_type=income_type,
                start_time=start_time,
                end_time=end_time,
                limit=limit
            )

            logger.info(f"Fetched {len(income_records)} income records for {symbol or 'ALL SYMBOLS'}")
            return income_records

        except Exception as e:
            logger.error(f"Error fetching income data: {e}")
            return []

    def transform_income_to_transaction(self, income_record: Dict[str, Any]) -> Dict[str, Any]:
        """
        Transform Binance income record to transaction_history format.

        Args:
            income_record: Raw income record from Binance API

        Returns:
            Transaction record in the required format
        """
        try:
            # Extract fields from income record
            time_ms = int(income_record.get('time', 0))
            income_type = income_record.get('incomeType', income_record.get('type', ''))
            amount = float(income_record.get('income', 0.0))
            asset = income_record.get('asset', '')
            symbol = income_record.get('symbol', '')

            # Convert millisecond timestamp to timestampz format for database
            # Database expects: 2025-09-03 08:00:00+00 (timestamp with timezone)
            from datetime import datetime, timezone
            dt = datetime.fromtimestamp(time_ms / 1000, tz=timezone.utc)
            time_timestampz = dt.isoformat()  # This gives us: 2025-09-05T19:00:00+00:00

            # Create transaction record
            transaction = {
                'time': time_timestampz,  # Use timestampz format instead of milliseconds
                'type': income_type,
                'amount': amount,
                'asset': asset,
                'symbol': symbol,
                'exchange': 'binance'
            }

            return transaction

        except Exception as e:
            logger.error(f"Error transforming income record: {e}")
            return {}

    async def insert_single_transaction(self, transaction: Dict[str, Any]) -> bool:
        """
        Insert a single transaction record with duplicate checking.

        Args:
            transaction: Transaction record to insert

        Returns:
            True if successful, False otherwise
        """
        try:
            # Check if transaction already exists
            exists = await self.db_manager.check_transaction_exists(
                time=transaction['time'],
                type=transaction['type'],
                amount=transaction['amount'],
                asset=transaction['asset'],
                symbol=transaction['symbol']
            )

            if exists:
                logger.info(f"Transaction already exists, skipping: {transaction}")
                return True

            # Insert new transaction
            result = await self.db_manager.insert_transaction_history(transaction)
            return result is not None

        except Exception as e:
            logger.error(f"Error inserting transaction: {e}")
            return False

    async def fill_transaction_history_manual(self, symbol: str = "", days: int = 30,
                                            income_type: str = "", batch_size: int = 100) -> Dict[str, Any]:
        """
        Manually fill transaction_history table with income data using last sync time approach.

        Args:
            symbol: Trading pair symbol (e.g., 'BTCUSDT')
            days: Number of days to look back (only used if no existing transactions)
            income_type: Income type filter (optional)
            batch_size: Number of records to process in each batch

        Returns:
            Summary of the operation
        """
        try:
            # Calculate time range (will be overridden by last sync time if data exists)
            end_time = int(datetime.now(timezone.utc).timestamp() * 1000)
            start_time = int((datetime.now(timezone.utc) - timedelta(days=days)).timestamp() * 1000)

            logger.info(f"Fetching income data for {symbol} from {datetime.fromtimestamp(start_time/1000, tz=timezone.utc)} to {datetime.fromtimestamp(end_time/1000, tz=timezone.utc)}")

            # Fetch income data (this will use last sync time internally)
            income_records = await self.fetch_income_data(
                symbol=symbol,
                start_time=start_time,
                end_time=end_time,
                income_type=income_type,
                limit=1000
            )

            if not income_records:
                logger.warning("No income records found")
                return {
                    'success': False,
                    'message': 'No income records found',
                    'processed': 0,
                    'inserted': 0,
                    'skipped': 0
                }

            # Transform and insert records (no duplicate checking needed since last sync time handles it)
            processed = 0
            inserted = 0
            skipped = 0
            batch = []

            for income in income_records:
                if not isinstance(income, dict):
                    continue

                transaction = self.transform_income_to_transaction(income)
                if not transaction:
                    skipped += 1
                    continue

                # No duplicate checking needed - last sync time ensures we only get new transactions
                batch.append(transaction)
                processed += 1

                # Process batch when it reaches batch_size
                if len(batch) >= batch_size:
                    batch_inserted = await self.db_manager.insert_transaction_history_batch(batch)
                    if batch_inserted:
                        inserted += len(batch)
                    else:
                        skipped += len(batch)
                    batch = []

                    # Rate limiting
                    await asyncio.sleep(0.1)

            # Process remaining records
            if batch:
                batch_inserted = await self.db_manager.insert_transaction_history_batch(batch)
                if batch_inserted:
                    inserted += len(batch)
                else:
                    skipped += len(batch)

            summary = {
                'success': True,
                'message': f'Processed {processed} income records',
                'processed': processed,
                'inserted': inserted,
                'skipped': skipped,
                'symbol': symbol,
                'time_range': f"{datetime.fromtimestamp(start_time/1000, tz=timezone.utc)} to {datetime.fromtimestamp(end_time/1000, tz=timezone.utc)}"
            }

            logger.info(f"Transaction history fill completed: {summary}")
            return summary

        except Exception as e:
            logger.error(f"Error in fill_transaction_history_manual: {e}")
            return {
                'success': False,
                'message': f'Error: {str(e)}',
                'processed': 0,
                'inserted': 0,
                'skipped': 0
            }

    async def fill_from_date(self, start_date: str, symbol: str = "",
                           income_type: str = "", batch_size: int = 100) -> Dict[str, Any]:
        """
        Fill transaction history from a specific date to now.

        Args:
            start_date: Start date in format 'YYYY-MM-DD' (e.g., '2025-08-10')
            symbol: Trading pair symbol (e.g., 'BTCUSDT')
            income_type: Income type filter (optional)
            batch_size: Number of records to process in each batch

        Returns:
            Summary of the operation
        """
        try:
            # Parse start date
            start_dt = datetime.strptime(start_date, '%Y-%m-%d').replace(tzinfo=timezone.utc)
            end_dt = datetime.now(timezone.utc)

            # Convert to milliseconds for Binance API
            start_time = int(start_dt.timestamp() * 1000)
            end_time = int(end_dt.timestamp() * 1000)

            logger.info(f"Filling transaction history from {start_date} to now")
            logger.info(f"Time range: {start_dt} to {end_dt}")

            # Fetch income data
            income_records = await self.fetch_income_data(
                symbol=symbol,
                start_time=start_time,
                end_time=end_time,
                income_type=income_type,
                limit=1000
            )

            if not income_records:
                logger.warning("No income records found")
                return {
                    'success': False,
                    'message': 'No income records found',
                    'processed': 0,
                    'inserted': 0,
                    'skipped': 0
                }

            # Transform and insert records (no duplicate checking needed since last sync time handles it)
            processed = 0
            inserted = 0
            skipped = 0
            batch = []

            for income in income_records:
                if not isinstance(income, dict):
                    continue

                transaction = self.transform_income_to_transaction(income)
                if not transaction:
                    skipped += 1
                    continue

                # No duplicate checking needed - last sync time ensures we only get new transactions
                batch.append(transaction)
                processed += 1

                # Process batch when it reaches batch_size
                if len(batch) >= batch_size:
                    batch_inserted = await self.db_manager.insert_transaction_history_batch(batch)
                    if batch_inserted:
                        inserted += len(batch)
                    else:
                        skipped += len(batch)
                    batch = []

                    # Rate limiting
                    await asyncio.sleep(0.1)

            # Process remaining records
            if batch:
                batch_inserted = await self.db_manager.insert_transaction_history_batch(batch)
                if batch_inserted:
                    inserted += len(batch)
                else:
                    skipped += len(batch)

            summary = {
                'success': True,
                'message': f'Successfully filled transaction history from {start_date}',
                'processed': processed,
                'inserted': inserted,
                'skipped': skipped,
                'symbol': symbol,
                'start_date': start_date,
                'end_date': end_dt.strftime('%Y-%m-%d'),
                'time_range': f"{start_dt} to {end_dt}"
            }

            logger.info(f"Transaction history fill from date completed: {summary}")
            return summary

        except Exception as e:
            logger.error(f"Error in fill_from_date: {e}")
            return {
                'success': False,
                'message': f'Error: {str(e)}',
                'processed': 0,
                'inserted': 0,
                'skipped': 0
            }

    async def fill_all_symbols_manual(self, days: int = 30, income_type: str = "") -> Dict[str, Any]:
        """
        Fill transaction history for all available symbols by fetching without symbol filter.

        Args:
            days: Number of days to look back
            income_type: Income type filter (optional)

        Returns:
            Summary of the operation
        """
        try:
            logger.info("Fetching ALL symbols transaction history")

            # Fetch all symbols at once (empty symbol = all symbols)
            result = await self.fill_transaction_history_manual(
                symbol="",  # Empty symbol fetches all symbols
                days=days,
                income_type=income_type
            )

            summary = {
                'success': result.get('success', False),
                'message': f'Fetched all symbols transaction history',
                'total_processed': result.get('processed', 0),
                'total_inserted': result.get('inserted', 0),
                'total_skipped': result.get('skipped', 0)
            }

            logger.info(f"All symbols processing completed: {summary}")
            return summary

        except Exception as e:
            logger.error(f"Error in fill_all_symbols_manual: {e}")
            return {
                'success': False,
                'message': f'Error: {str(e)}',
                'total_processed': 0,
                'total_inserted': 0,
                'total_skipped': 0
            }


async def main():
    """Main function for incremental transaction history filling using latest DB timestamp."""
    filler = TransactionHistoryFiller()

    print("=== Incremental Transaction History Filler ===")
    print("🔄 Fetching from Binance using latest timestamp in DB as starting point...")
    
    try:
        # Get current count before
        response = filler.db_manager.supabase.table('transaction_history').select('id').execute()
        before_count = len(response.data) if response.data else 0
        print(f"📊 Current transaction count: {before_count}")
        
        # Fill all symbols using incremental approach (latest timestamp from DB)
        result = await filler.fill_all_symbols_manual(
            days=7,  # Look back 7 days as fallback if no existing data
            income_type=""  # All income types
        )
        
        # Get final count
        response = filler.db_manager.supabase.table('transaction_history').select('id').execute()
        after_count = len(response.data) if response.data else 0
        
        # Display results
        print(f"\n=== Results ===")
        print(f"✅ Success: {result.get('success', False)}")
        print(f"📝 Message: {result.get('message', '')}")
        print(f"📊 Processed: {result.get('total_processed', 0)}")
        print(f"➕ Inserted: {result.get('total_inserted', 0)}")
        print(f"⏭️ Skipped: {result.get('total_skipped', 0)}")
        print(f"📈 Net change: +{after_count - before_count}")
        
        if result.get('success'):
            print(f"🎉 Transaction history updated successfully!")
        else:
            print(f"❌ Error: {result.get('message', 'Unknown error')}")
            
    except Exception as e:
        print(f"❌ Error running incremental fill: {e}")
        return


if __name__ == "__main__":
    asyncio.run(main())
