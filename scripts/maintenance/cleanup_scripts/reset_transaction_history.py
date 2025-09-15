#!/usr/bin/env python3
"""
Simple script to reset transaction history - delete all and add fresh data from Binance.
"""

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List

# Add the project root to the path
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from discord_bot.database import DatabaseManager
from discord_bot.discord_bot import DiscordBot

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class TransactionHistoryResetter:
    def __init__(self):
        self.bot = DiscordBot()
        self.db_manager = DatabaseManager(self.bot.supabase)

    async def delete_all_transactions(self) -> bool:
        """Delete all transaction history records."""
        logger.info("🗑️ Deleting all transaction history records...")
        
        try:
            response = self.db_manager.supabase.from_("transaction_history").delete().neq("id", 0).execute()
            logger.info("✅ All transaction history records deleted successfully")
            return True
        except Exception as e:
            logger.error(f"❌ Error deleting transaction history: {e}")
            return False

    async def verify_empty_database(self) -> bool:
        """Verify that the database is empty."""
        logger.info("🔍 Verifying database is empty...")
        
        try:
            response = self.db_manager.supabase.from_("transaction_history").select("id").limit(1).execute()
            
            if not response.data:
                logger.info("✅ Database is empty - no transaction records found")
                return True
            else:
                logger.warning(f"⚠️ Database still has {len(response.data)} records")
                return False
        except Exception as e:
            logger.error(f"❌ Error checking database: {e}")
            return False

    async def fetch_fresh_data_from_binance(self, start_date: str = "2025-08-08") -> List[Dict]:
        """Fetch fresh transaction data from Binance from a specific start date."""
        logger.info(f"📥 Fetching fresh data from Binance from {start_date}...")
        
        try:
            # Initialize Binance client if needed
            if not self.bot.binance_exchange.client:
                await self.bot.binance_exchange._init_client()

            # Calculate time range from start date
            end_time = int(datetime.now(timezone.utc).timestamp() * 1000)
            start_time = int(datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp() * 1000)

            # Fetch ALL transactions without limiting to specific symbols
            logger.info("Fetching ALL transactions from Binance...")
            
            all_transactions = []
            
            try:
                # Fetch income history for ALL symbols
                income_records = await self.bot.binance_exchange.get_income_history(
                    start_time=start_time,
                    end_time=end_time,
                    limit=1000
                )

                # Transform to transaction format
                for income in income_records:
                    if isinstance(income, dict):
                        transaction = {
                            'time': int(income.get('time', 0)),
                            'type': income.get('incomeType', income.get('type', '')),
                            'amount': float(income.get('income', 0.0)),
                            'asset': income.get('asset', ''),
                            'symbol': income.get('symbol', '')
                        }
                        all_transactions.append(transaction)

                logger.info(f"Fetched {len(income_records)} income records from Binance")

            except Exception as e:
                logger.error(f"Error fetching data from Binance: {e}")
                return []

            logger.info(f"✅ Fetched {len(all_transactions)} transactions from Binance") 
            return all_transactions

        except Exception as e:
            logger.error(f"❌ Error fetching fresh data: {e}")
            return []

    async def insert_fresh_data(self, transactions: List[Dict]) -> bool:
        """Insert fresh transaction data into database."""
        logger.info(f"📝 Inserting {len(transactions)} fresh transactions...")
        
        try:
            if not transactions:
                logger.warning("No transactions to insert")
                return True

            # Insert in batches
            batch_size = 100
            inserted_count = 0

            for i in range(0, len(transactions), batch_size):
                batch = transactions[i:i + batch_size]
                
                success = await self.db_manager.insert_transaction_history_batch(batch)
                if success:
                    inserted_count += len(batch)
                    logger.info(f"Inserted batch {i//batch_size + 1}: {len(batch)} transactions")
                else:
                    logger.error(f"Failed to insert batch {i//batch_size + 1}")

                # Rate limiting
                await asyncio.sleep(0.1)

            logger.info(f"✅ Successfully inserted {inserted_count} transactions")
            return True

        except Exception as e:
            logger.error(f"❌ Error inserting fresh data: {e}")
            return False

    async def verify_fresh_data(self) -> bool:
        """Verify that fresh data was inserted correctly."""
        logger.info("🔍 Verifying fresh data...")
        
        try:
            response = self.db_manager.supabase.from_("transaction_history").select("id").execute()
            
            if response.data:
                logger.info(f"✅ Database now has {len(response.data)} transaction records")
                
                # Show some sample data
                sample_response = self.db_manager.supabase.from_("transaction_history").select("*").order("time", desc=True).limit(5).execute()
                if sample_response.data:
                    logger.info("📋 Sample transactions:")
                    for i, tx in enumerate(sample_response.data, 1):
                        logger.info(f"  {i}. {tx['type']} - {tx['symbol']} - {tx['amount']} {tx['asset']}")
                
                return True
            else:
                logger.error("❌ No transaction records found after insertion")
                return False

        except Exception as e:
            logger.error(f"❌ Error verifying fresh data: {e}")
            return False

    async def reset_transaction_history(self, start_date: str = "2025-08-10") -> bool:
        """Reset transaction history - delete all and add fresh data from a specific start date."""
        logger.info("🚀 Starting transaction history reset...")
        
        try:
            # Step 1: Delete all transactions
            if not await self.delete_all_transactions():
                return False

            # Step 2: Verify database is empty
            if not await self.verify_empty_database():
                return False

            # Step 3: Fetch fresh data from Binance
            transactions = await self.fetch_fresh_data_from_binance(start_date)
            if not transactions:
                logger.warning("No transactions fetched from Binance")
                return True  # Not necessarily an error

            # Step 4: Insert fresh data
            if not await self.insert_fresh_data(transactions):
                return False

            # Step 5: Verify fresh data
            if not await self.verify_fresh_data():
                return False

            logger.info("🎉 Transaction history reset completed successfully!")
            return True

        except Exception as e:
            logger.error(f"❌ Transaction history reset failed: {e}", exc_info=True)
            return False


async def main():
    """Main function."""
    resetter = TransactionHistoryResetter()
    
    print("🔄 Transaction History Reset")
    print("This will:")
    print("1. Delete ALL existing transaction history")
    print("2. Fetch ALL transactions from Binance from a specific start date")
    print("3. Insert the fresh data")
    print()
    
    start_date = input("Enter start date (YYYY-MM-DD, default 2025-08-08): ").strip()
    if not start_date:
        start_date = "2025-08-08"
    
    confirmation = input(f"This will DELETE ALL transaction history and fetch ALL transactions from {start_date}! Continue? (y/N): ")
    if confirmation.lower() != 'y':
        print("Reset cancelled.")
        return
    
    success = await resetter.reset_transaction_history(start_date)
    
    if success:
        print("\n🎉 Transaction history reset completed successfully!")
    else:
        print("\n❌ Transaction history reset failed. Check the logs above.")


if __name__ == "__main__":
    asyncio.run(main())
