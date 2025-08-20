#!/usr/bin/env python3
"""
Autofill script to continuously fill transaction_history table with data from Binance /income endpoint.
This script runs automatically and can be scheduled to run periodically.
"""

import sys
import asyncio
import logging
import argparse
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional
import time

sys.path.append(str(Path(__file__).parent.parent))

from discord_bot.discord_bot import DiscordBot
from discord_bot.database import DatabaseManager

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class AutoTransactionHistoryFiller:
    def __init__(self):
        self.bot = DiscordBot()
        self.db_manager = DatabaseManager(self.bot.supabase)
        self.last_sync_time = None

    async def get_last_sync_time(self) -> int:
        """
        Get the timestamp of the last synced transaction to avoid duplicates.
        
        Returns:
            Last sync timestamp in milliseconds
        """
        try:
            # Get the most recent transaction from the database
            recent_transactions = await self.db_manager.get_transaction_history(limit=1)
            
            if recent_transactions:
                last_time = recent_transactions[0].get('time', 0)
                logger.info(f"Last sync time from database: {datetime.fromtimestamp(last_time/1000, tz=timezone.utc)}")
                return last_time
            else:
                # If no transactions exist, start from 30 days ago
                default_time = int((datetime.now(timezone.utc) - timedelta(days=30)).timestamp() * 1000)
                logger.info(f"No existing transactions, starting from: {datetime.fromtimestamp(default_time/1000, tz=timezone.utc)}")
                return default_time

        except Exception as e:
            logger.error(f"Error getting last sync time: {e}")
            # Default to 30 days ago
            default_time = int((datetime.now(timezone.utc) - timedelta(days=30)).timestamp() * 1000)
            return default_time

    async def fetch_income_data_chunked(self, symbol: str = "", start_time: int = 0, end_time: int = 0, 
                                       income_type: str = "", chunk_days: int = 7) -> List[Dict[str, Any]]:
        """
        Fetch income data in chunks to handle large time ranges.
        
        Args:
            symbol: Trading pair symbol
            start_time: Start time in milliseconds
            end_time: End time in milliseconds
            income_type: Income type filter
            chunk_days: Number of days per chunk
            
        Returns:
            List of all income records
        """
        all_records = []
        chunk_start = start_time
        chunk_size_ms = chunk_days * 24 * 60 * 60 * 1000  # Convert days to milliseconds

        while chunk_start < end_time:
            chunk_end = min(chunk_start + chunk_size_ms, end_time)
            
            try:
                logger.info(f"Fetching chunk for {symbol}: {datetime.fromtimestamp(chunk_start/1000, tz=timezone.utc)} to {datetime.fromtimestamp(chunk_end/1000, tz=timezone.utc)}")
                
                income_records = await self.bot.binance_exchange.get_income_history(
                    symbol=symbol,
                    income_type=income_type,
                    start_time=chunk_start,
                    end_time=chunk_end,
                    limit=1000
                )

                if income_records:
                    all_records.extend(income_records if isinstance(income_records, list) else [income_records])
                    logger.info(f"Fetched {len(income_records) if isinstance(income_records, list) else 1} records for chunk")

                # Rate limiting
                await asyncio.sleep(0.5)

            except Exception as e:
                logger.error(f"Error fetching chunk for {symbol}: {e}")

            chunk_start = chunk_end

        logger.info(f"Total records fetched for {symbol}: {len(all_records)}")
        return all_records

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

            # Create transaction record
            transaction = {
                'time': time_ms,
                'type': income_type,
                'amount': amount,
                'asset': asset,
                'symbol': symbol
            }

            return transaction

        except Exception as e:
            logger.error(f"Error transforming income record: {e}")
            return {}

    async def process_symbol_transactions(self, symbol: str, start_time: int, end_time: int, 
                                        income_type: str = "") -> Dict[str, Any]:
        """
        Process transactions for a single symbol.
        
        Args:
            symbol: Trading pair symbol
            start_time: Start time in milliseconds
            end_time: End time in milliseconds
            income_type: Income type filter
            
        Returns:
            Summary of processing results
        """
        try:
            # Fetch income data
            income_records = await self.fetch_income_data_chunked(
                symbol=symbol,
                start_time=start_time,
                end_time=end_time,
                income_type=income_type
            )

            if not income_records:
                return {
                    'symbol': symbol,
                    'processed': 0,
                    'inserted': 0,
                    'skipped': 0,
                    'success': True
                }

            # Transform and filter records
            transactions = []
            for income in income_records:
                if not isinstance(income, dict):
                    continue

                transaction = self.transform_income_to_transaction(income)
                if transaction:
                    transactions.append(transaction)

            if not transactions:
                return {
                    'symbol': symbol,
                    'processed': 0,
                    'inserted': 0,
                    'skipped': 0,
                    'success': True
                }

            # Insert transactions in batches
            batch_size = 100
            inserted = 0
            skipped = 0

            for i in range(0, len(transactions), batch_size):
                batch = transactions[i:i + batch_size]
                
                # Check for duplicates before inserting
                filtered_batch = []
                for transaction in batch:
                    exists = await self.db_manager.check_transaction_exists(
                        time=transaction['time'],
                        type=transaction['type'],
                        amount=transaction['amount'],
                        asset=transaction['asset'],
                        symbol=transaction['symbol']
                    )
                    
                    if not exists:
                        filtered_batch.append(transaction)
                    else:
                        skipped += 1

                if filtered_batch:
                    success = await self.db_manager.insert_transaction_history_batch(filtered_batch)
                    if success:
                        inserted += len(filtered_batch)
                    else:
                        skipped += len(filtered_batch)

                # Rate limiting
                await asyncio.sleep(0.1)

            return {
                'symbol': symbol,
                'processed': len(transactions),
                'inserted': inserted,
                'skipped': skipped,
                'success': True
            }

        except Exception as e:
            logger.error(f"Error processing symbol {symbol}: {e}")
            return {
                'symbol': symbol,
                'processed': 0,
                'inserted': 0,
                'skipped': 0,
                'success': False,
                'error': str(e)
            }

    async def auto_fill_transaction_history(self, symbols: List[str] = None, days_back: int = 7, 
                                          income_type: str = "", continuous: bool = False) -> Dict[str, Any]:
        """
        Automatically fill transaction history for specified symbols.
        
        Args:
            symbols: List of symbols to process (if None, uses default list)
            days_back: Number of days to look back from current time
            income_type: Income type filter
            continuous: Whether to run continuously
            
        Returns:
            Summary of the operation
        """
        try:
            # Initialize Binance client
            if not self.bot.binance_exchange.client:
                await self.bot.binance_exchange._init_client()

            # Use default symbols if none provided
            if symbols is None:
                symbols = [
                    'BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'ADAUSDT', 'SOLUSDT',
                    'DOTUSDT', 'DOGEUSDT', 'AVAXUSDT', 'MATICUSDT', 'LINKUSDT'
                ]

            # Calculate time range
            end_time = int(datetime.now(timezone.utc).timestamp() * 1000)
            start_time = int((datetime.now(timezone.utc) - timedelta(days=days_back)).timestamp() * 1000)

            logger.info(f"Auto-filling transaction history from {datetime.fromtimestamp(start_time/1000, tz=timezone.utc)} to {datetime.fromtimestamp(end_time/1000, tz=timezone.utc)}")

            total_processed = 0
            total_inserted = 0
            total_skipped = 0
            results = []

            for symbol in symbols:
                logger.info(f"Processing symbol: {symbol}")
                
                result = await self.process_symbol_transactions(
                    symbol=symbol,
                    start_time=start_time,
                    end_time=end_time,
                    income_type=income_type
                )

                results.append(result)
                total_processed += result.get('processed', 0)
                total_inserted += result.get('inserted', 0)
                total_skipped += result.get('skipped', 0)

                # Rate limiting between symbols
                await asyncio.sleep(1)

            summary = {
                'success': True,
                'message': f'Auto-fill completed for {len(symbols)} symbols',
                'total_processed': total_processed,
                'total_inserted': total_inserted,
                'total_skipped': total_skipped,
                'symbol_results': results,
                'time_range': f"{datetime.fromtimestamp(start_time/1000, tz=timezone.utc)} to {datetime.fromtimestamp(end_time/1000, tz=timezone.utc)}"
            }

            logger.info(f"Auto-fill completed: {summary}")
            return summary

        except Exception as e:
            logger.error(f"Error in auto_fill_transaction_history: {e}")
            return {
                'success': False,
                'message': f'Error: {str(e)}',
                'total_processed': 0,
                'total_inserted': 0,
                'total_skipped': 0
            }

    async def run_continuous_sync(self, symbols: List[str] = None, sync_interval_hours: int = 6):
        """
        Run continuous synchronization of transaction history.
        
        Args:
            symbols: List of symbols to sync
            sync_interval_hours: Hours between sync runs
        """
        logger.info(f"Starting continuous sync with {sync_interval_hours} hour intervals")
        
        while True:
            try:
                logger.info("Starting sync cycle...")
                
                # Run auto-fill for recent data (last 24 hours)
                result = await self.auto_fill_transaction_history(
                    symbols=symbols,
                    days_back=1,  # Only sync last 24 hours in continuous mode
                    continuous=True
                )
                
                if result.get('success'):
                    logger.info(f"Sync cycle completed: {result.get('total_inserted', 0)} new records")
                else:
                    logger.error(f"Sync cycle failed: {result.get('message', 'Unknown error')}")
                
                # Wait for next sync cycle
                logger.info(f"Waiting {sync_interval_hours} hours until next sync...")
                await asyncio.sleep(sync_interval_hours * 3600)
                
            except KeyboardInterrupt:
                logger.info("Continuous sync interrupted by user")
                break
            except Exception as e:
                logger.error(f"Error in continuous sync: {e}")
                # Wait 1 hour before retrying on error
                await asyncio.sleep(3600)


async def main():
    """Main function for auto transaction history filling."""
    parser = argparse.ArgumentParser(description='Auto-fill transaction history from Binance income data')
    parser.add_argument('--symbols', nargs='+', help='List of symbols to process (e.g., BTCUSDT ETHUSDT)')
    parser.add_argument('--days', type=int, default=7, help='Number of days to look back (default: 7)')
    parser.add_argument('--income-type', type=str, default='', help='Income type filter (optional)')
    parser.add_argument('--continuous', action='store_true', help='Run continuously with periodic sync')
    parser.add_argument('--sync-interval', type=int, default=6, help='Sync interval in hours for continuous mode (default: 6)')
    
    args = parser.parse_args()

    filler = AutoTransactionHistoryFiller()

    if args.continuous:
        await filler.run_continuous_sync(
            symbols=args.symbols,
            sync_interval_hours=args.sync_interval
        )
    else:
        result = await filler.auto_fill_transaction_history(
            symbols=args.symbols,
            days_back=args.days,
            income_type=args.income_type
        )
        
        # Display results
        print(f"\n=== Auto-fill Results ===")
        print(f"Success: {result.get('success', False)}")
        print(f"Message: {result.get('message', '')}")
        print(f"Total Processed: {result.get('total_processed', 0)}")
        print(f"Total Inserted: {result.get('total_inserted', 0)}")
        print(f"Total Skipped: {result.get('total_skipped', 0)}")
        
        if result.get('symbol_results'):
            print(f"\n=== Symbol Results ===")
            for symbol_result in result['symbol_results']:
                print(f"{symbol_result['symbol']}: {symbol_result['inserted']} inserted, {symbol_result['skipped']} skipped")


if __name__ == "__main__":
    asyncio.run(main())
