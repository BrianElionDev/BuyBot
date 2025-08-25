#!/usr/bin/env python3
"""
Script to fix case inconsistencies in status values.

Found issue: 190 trades have status='pending' (lowercase) instead of 'PENDING' (uppercase)
This should be standardized to match the status constants.
"""

import asyncio
import logging
from supabase import create_client, Client
import os
from dotenv import load_dotenv
from datetime import datetime, timezone

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class StatusCaseFixer:
    def __init__(self):
        self.supabase_url = os.getenv('SUPABASE_URL')
        self.supabase_key = os.getenv('SUPABASE_KEY')

        if not self.supabase_url or not self.supabase_key:
            raise ValueError("Missing SUPABASE_URL or SUPABASE_KEY environment variables")

        self.supabase: Client = create_client(self.supabase_url, self.supabase_key)

    async def find_case_inconsistencies(self):
        """Find trades with lowercase status values."""
        try:
            # Find trades with lowercase 'pending'
            response = self.supabase.from_("trades").select("*").eq("status", "pending").execute()

            if response.data:
                logger.info(f"Found {len(response.data)} trades with status='pending' (lowercase)")
                return response.data
            else:
                logger.info("No trades found with lowercase status values")
                return []

        except Exception as e:
            logger.error(f"Error finding case inconsistencies: {e}")
            return []

    async def fix_case_inconsistencies(self, trades):
        """Fix case inconsistencies in status values."""
        fixed_count = 0

        for trade in trades:
            try:
                trade_id = trade['id']
                symbol = trade.get('coin_symbol', 'UNKNOWN')
                current_status = trade.get('status', '')

                # Define the correct uppercase mapping
                status_mapping = {
                    'pending': 'PENDING',
                    'open': 'OPEN',
                    'closed': 'CLOSED',
                    'none': 'NONE',
                    'failed': 'FAILED'
                }

                if current_status.lower() in status_mapping:
                    correct_status = status_mapping[current_status.lower()]

                    if current_status != correct_status:
                        # Update the trade
                        updates = {
                            'status': correct_status,
                            'updated_at': datetime.now(timezone.utc).isoformat()
                        }

                        self.supabase.from_("trades").update(updates).eq("id", trade_id).execute()

                        logger.info(f"Fixed trade {trade_id} ({symbol}):")
                        logger.info(f"  Before: status='{current_status}'")
                        logger.info(f"  After:  status='{correct_status}'")

                        fixed_count += 1
                    else:
                        logger.info(f"Trade {trade_id} ({symbol}) already has correct case")

            except Exception as e:
                logger.error(f"Error fixing trade {trade.get('id')}: {e}")
                continue

        return fixed_count

    async def run_fix(self):
        """Run the complete case fix process."""
        logger.info("Starting status case inconsistency fix...")

        # Find case inconsistencies
        inconsistent_trades = await self.find_case_inconsistencies()

        if not inconsistent_trades:
            logger.info("No case inconsistencies found. All good!")
            return

        # Fix the trades
        fixed_count = await self.fix_case_inconsistencies(inconsistent_trades)

        logger.info(f"Case fix completed! Fixed {fixed_count} out of {len(inconsistent_trades)} trades")

async def main():
    """Main function."""
    try:
        fixer = StatusCaseFixer()
        await fixer.run_fix()
    except Exception as e:
        logger.error(f"Error in main: {e}")

if __name__ == "__main__":
    asyncio.run(main())





