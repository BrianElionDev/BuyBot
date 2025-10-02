#!/usr/bin/env python3
"""
KuCoin Transaction History Filler

This script fetches transaction history from KuCoin and stores it in the database.
Similar to the Binance transaction history filler but for KuCoin exchange.
"""

import asyncio
import logging
import sys
import os
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any, Optional

# Add the project root to the Python path
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)

from discord_bot.discord_bot import DiscordBot
from discord_bot.database.database_manager import DatabaseManager
from src.exchange.kucoin.kucoin_transaction_fetcher import KucoinTransactionFetcher

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class KucoinTransactionHistoryFiller:
    """Fills transaction history from KuCoin exchange."""

    def __init__(self):
        """Initialize the KuCoin transaction history filler."""
        self.bot = DiscordBot()
        self.db_manager = DatabaseManager(self.bot.supabase)
        self.kucoin_fetcher = KucoinTransactionFetcher(self.bot.kucoin_exchange)

    async def fetch_kucoin_transactions(self, symbol: str = "", start_time: int = 0, end_time: int = 0,
                                      limit: int = 1000) -> List[Dict[str, Any]]:
        """
        Fetch transaction data from KuCoin API.

        Args:
            symbol: Trading pair symbol (e.g., 'BTCUSDT') - if empty, fetches all symbols
            start_time: Start time in milliseconds
            end_time: End time in milliseconds
            limit: Number of records to retrieve

        Returns:
            List of transaction records
        """
        try:
            logger.info(f"Fetching KuCoin transaction data for {symbol or 'ALL SYMBOLS'}")

            # Get the last sync time to avoid re-syncing existing transactions
            last_sync_time = await self.db_manager.get_last_transaction_sync_time()

            # If we have existing transactions, start from the last one + 1ms
            if last_sync_time and last_sync_time > 0 and start_time < last_sync_time:
                start_time = last_sync_time + 1
                logger.info(f"Starting sync from last transaction time: {start_time} ({datetime.fromtimestamp(start_time/1000, tz=timezone.utc)})")

            # Fetch transactions from KuCoin
            transactions = await self.kucoin_fetcher.fetch_transaction_history(
                symbol=symbol,
                start_time=start_time,
                end_time=end_time,
                limit=limit
            )

            logger.info(f"Fetched {len(transactions)} KuCoin transaction records for {symbol or 'ALL SYMBOLS'}")
            return transactions

        except Exception as e:
            logger.error(f"Error fetching KuCoin transaction data: {e}")
            return []

    def transform_kucoin_to_transaction(self, transaction_record: Dict[str, Any]) -> Dict[str, Any]:
        """
        Transform KuCoin transaction record to database format.

        Args:
            transaction_record: KuCoin transaction record

        Returns:
            Transaction record formatted for database
        """
        try:
            # The fetcher already formats the data correctly, just ensure exchange is set
            transaction_record['exchange'] = 'kucoin'
            return transaction_record

        except Exception as e:
            logger.error(f"Error transforming KuCoin transaction: {e}")
            return {}

    async def fill_single_symbol(self, symbol: str, days: int = 7) -> bool:
        """
        Fill transaction history for a single symbol.

        Args:
            symbol: Trading pair symbol (e.g., 'BTCUSDT')
            days: Number of days to fetch

        Returns:
            True if successful, False otherwise
        """
        try:
            logger.info(f"Filling KuCoin transaction history for {symbol} (last {days} days)")

            # Calculate time range
            end_time = int(datetime.now(timezone.utc).timestamp() * 1000)
            start_time = int((datetime.now(timezone.utc) - timedelta(days=days)).timestamp() * 1000)

            # Fetch transactions
            transactions = await self.fetch_kucoin_transactions(
                symbol=symbol,
                start_time=start_time,
                end_time=end_time,
                limit=1000
            )

            if not transactions:
                logger.info(f"No KuCoin transactions found for {symbol}")
                return True

            # Transform transactions
            transformed_transactions = []
            for transaction in transactions:
                transformed = self.transform_kucoin_to_transaction(transaction)
                if transformed:
                    transformed_transactions.append(transformed)

            if not transformed_transactions:
                logger.info(f"No valid KuCoin transactions to insert for {symbol}")
                return True

            # Insert transactions in batches
            batch_size = 100
            success_count = 0

            for i in range(0, len(transformed_transactions), batch_size):
                batch = transformed_transactions[i:i + batch_size]

                # Check for duplicates before inserting
                filtered_batch = []
                for transaction in batch:
                    exists = await self.db_manager.check_transaction_exists(
                        time=transaction.get('time', ''),
                        type=transaction.get('type', ''),
                        amount=transaction.get('amount', 0),
                        asset=transaction.get('asset', ''),
                        symbol=transaction.get('symbol', '')
                    )
                    if not exists:
                        filtered_batch.append(transaction)

                if filtered_batch:
                    success = await self.db_manager.insert_transaction_history_batch(filtered_batch)
                    if success:
                        success_count += len(filtered_batch)
                        logger.info(f"Inserted batch of {len(filtered_batch)} KuCoin transactions for {symbol}")
                    else:
                        logger.error(f"Failed to insert batch for {symbol}")
                else:
                    logger.info(f"All transactions in batch already exist for {symbol}")

            logger.info(f"Successfully processed {success_count} KuCoin transactions for {symbol}")
            return True

        except Exception as e:
            logger.error(f"Error filling KuCoin transaction history for {symbol}: {e}")
            return False

    async def fill_all_symbols(self, days: int = 7) -> bool:
        """
        Fill transaction history for all supported symbols.

        Args:
            days: Number of days to fetch

        Returns:
            True if successful, False otherwise
        """
        try:
            logger.info(f"Filling KuCoin transaction history for all symbols (last {days} days)")

            # Get supported symbols
            symbols = self.kucoin_fetcher.get_supported_symbols()
            logger.info(f"Processing {len(symbols)} KuCoin symbols: {symbols}")

            success_count = 0
            total_symbols = len(symbols)

            for i, symbol in enumerate(symbols, 1):
                logger.info(f"Processing symbol {i}/{total_symbols}: {symbol}")

                success = await self.fill_single_symbol(symbol, days)
                if success:
                    success_count += 1
                    logger.info(f"✅ Successfully processed {symbol}")
                else:
                    logger.error(f"❌ Failed to process {symbol}")

                # Add delay between symbols to avoid rate limiting
                await asyncio.sleep(1)

            logger.info(f"Completed KuCoin transaction history fill: {success_count}/{total_symbols} symbols processed successfully")
            return success_count == total_symbols

        except Exception as e:
            logger.error(f"Error filling KuCoin transaction history for all symbols: {e}")
            return False

    async def get_statistics(self) -> Dict[str, Any]:
        """
        Get statistics about KuCoin transaction history in the database.

        Returns:
            Dictionary with statistics
        """
        try:
            # Get total count
            total_count = await self.db_manager.get_transaction_count_by_exchange('kucoin')

            # Get count by symbol
            symbols = self.kucoin_fetcher.get_supported_symbols()
            symbol_counts = {}

            for symbol in symbols:
                count = await self.db_manager.get_transaction_count_by_symbol_and_exchange(symbol, 'kucoin')
                if count > 0:
                    symbol_counts[symbol] = count

            # Get latest transaction time
            latest_time = await self.db_manager.get_latest_transaction_time_by_exchange('kucoin')

            return {
                'total_kucoin_transactions': total_count,
                'symbol_counts': symbol_counts,
                'latest_transaction_time': latest_time,
                'supported_symbols': len(symbols)
            }

        except Exception as e:
            logger.error(f"Error getting KuCoin transaction statistics: {e}")
            return {}


async def main():
    """Main function for interactive menu."""
    filler = KucoinTransactionHistoryFiller()

    while True:
        print("\n" + "="*60)
        print("KuCoin Transaction History Filler")
        print("="*60)
        print("1. Fill single symbol")
        print("2. Fill all symbols")
        print("3. Show statistics")
        print("4. Exit")
        print("="*60)

        choice = input("Enter your choice (1-4): ").strip()

        if choice == "1":
            symbol = input("Enter symbol (e.g., BTCUSDT): ").strip().upper()
            if not symbol:
                print("❌ Symbol cannot be empty")
                continue

            days = input("Enter number of days (default 7): ").strip()
            try:
                days = int(days) if days else 7
            except ValueError:
                print("❌ Invalid number of days, using default 7")
                days = 7

            print(f"\n🔄 Filling KuCoin transaction history for {symbol} (last {days} days)...")
            success = await filler.fill_single_symbol(symbol, days)

            if success:
                print(f"✅ Successfully filled KuCoin transaction history for {symbol}")
            else:
                print(f"❌ Failed to fill KuCoin transaction history for {symbol}")

        elif choice == "2":
            days = input("Enter number of days (default 7): ").strip()
            try:
                days = int(days) if days else 7
            except ValueError:
                print("❌ Invalid number of days, using default 7")
                days = 7

            print(f"\n🔄 Filling KuCoin transaction history for all symbols (last {days} days)...")
            success = await filler.fill_all_symbols(days)

            if success:
                print("✅ Successfully filled KuCoin transaction history for all symbols")
            else:
                print("❌ Failed to fill KuCoin transaction history for some symbols")

        elif choice == "3":
            print("\n📊 KuCoin Transaction History Statistics:")
            stats = await filler.get_statistics()

            if stats:
                print(f"Total KuCoin transactions: {stats.get('total_kucoin_transactions', 0)}")
                print(f"Supported symbols: {stats.get('supported_symbols', 0)}")
                print(f"Latest transaction time: {stats.get('latest_transaction_time', 'N/A')}")

                symbol_counts = stats.get('symbol_counts', {})
                if symbol_counts:
                    print("\nTransactions by symbol:")
                    for symbol, count in symbol_counts.items():
                        print(f"  {symbol}: {count}")
                else:
                    print("No symbol-specific data available")
            else:
                print("❌ Failed to get statistics")

        elif choice == "4":
            print("👋 Goodbye!")
            break

        else:
            print("❌ Invalid choice. Please enter 1-4.")


if __name__ == "__main__":
    asyncio.run(main())
