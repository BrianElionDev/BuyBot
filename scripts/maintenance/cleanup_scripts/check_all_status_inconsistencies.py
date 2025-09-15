#!/usr/bin/env python3
"""
Comprehensive script to check for all possible status inconsistencies in the database.

This script identifies various types of status inconsistencies:
1. status=OPEN but order_status=PENDING (logically impossible)
2. status=CLOSED but order_status=PENDING (logically impossible)
3. status=NONE but order_status=FILLED (logically impossible)
4. status=OPEN but order_status=CANCELED/EXPIRED/REJECTED (logically impossible)
5. Missing order_status or status values
"""

import asyncio
import json
import logging
from typing import Dict, List, Tuple
from supabase import create_client, Client
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class StatusInconsistencyChecker:
    def __init__(self):
        self.supabase_url = os.getenv('SUPABASE_URL')
        self.supabase_key = os.getenv('SUPABASE_KEY')

        if not self.supabase_url or not self.supabase_key:
            raise ValueError("Missing SUPABASE_URL or SUPABASE_KEY environment variables")

        self.supabase: Client = create_client(self.supabase_url, self.supabase_key)

    async def check_all_inconsistencies(self):
        """Check for all possible status inconsistencies."""
        logger.info("Starting comprehensive status inconsistency check...")

        # Define all possible inconsistencies
        inconsistencies = [
            {
                'name': 'OPEN status with PENDING order_status',
                'query': {'status': 'OPEN', 'order_status': 'PENDING'},
                'description': 'Position is open but order is pending (impossible)'
            },
            {
                'name': 'CLOSED status with PENDING order_status',
                'query': {'status': 'CLOSED', 'order_status': 'PENDING'},
                'description': 'Position is closed but order is pending (impossible)'
            },
            {
                'name': 'NONE status with FILLED order_status',
                'query': {'status': 'NONE', 'order_status': 'FILLED'},
                'description': 'No position but order is filled (impossible)'
            },
            {
                'name': 'OPEN status with CANCELED order_status',
                'query': {'status': 'OPEN', 'order_status': 'CANCELED'},
                'description': 'Position is open but order was canceled (impossible)'
            },
            {
                'name': 'OPEN status with EXPIRED order_status',
                'query': {'status': 'OPEN', 'order_status': 'EXPIRED'},
                'description': 'Position is open but order expired (impossible)'
            },
            {
                'name': 'OPEN status with REJECTED order_status',
                'query': {'status': 'OPEN', 'order_status': 'REJECTED'},
                'description': 'Position is open but order was rejected (impossible)'
            },
            {
                'name': 'Missing order_status',
                'query': {'order_status': 'is.null'},
                'description': 'Trades missing order_status value'
            },
            {
                'name': 'Missing status',
                'query': {'status': 'is.null'},
                'description': 'Trades missing status value'
            }
        ]

        total_issues = 0

        for inconsistency in inconsistencies:
            try:
                trades = await self._query_inconsistency(inconsistency['query'])

                if trades:
                    logger.warning(f"❌ {inconsistency['name']}: {len(trades)} trades")
                    logger.warning(f"   Description: {inconsistency['description']}")

                    # Show first few examples
                    for i, trade in enumerate(trades[:3]):
                        logger.warning(f"   Example {i+1}: Trade ID {trade['id']} ({trade.get('coin_symbol', 'UNKNOWN')})")
                        logger.warning(f"     status: {trade.get('status')}, order_status: {trade.get('order_status')}")

                    if len(trades) > 3:
                        logger.warning(f"   ... and {len(trades) - 3} more")

                    total_issues += len(trades)
                else:
                    logger.info(f"✅ {inconsistency['name']}: No issues found")

            except Exception as e:
                logger.error(f"Error checking {inconsistency['name']}: {e}")

        # Summary
        logger.info("=" * 60)
        if total_issues == 0:
            logger.info("🎉 All status checks passed! No inconsistencies found.")
        else:
            logger.warning(f"⚠️  Found {total_issues} total status inconsistencies")
            logger.warning("Run the fix scripts to resolve these issues.")

        return total_issues

    async def _query_inconsistency(self, query_params: Dict) -> List[Dict]:
        """Query for specific inconsistency."""
        try:
            # Build the query
            query = self.supabase.from_("trades").select("*")

            for key, value in query_params.items():
                if value == 'is.null':
                    query = query.is_(key, 'null')
                else:
                    query = query.eq(key, value)

            response = query.execute()
            return response.data or []

        except Exception as e:
            logger.error(f"Error querying inconsistency: {e}")
            return []

    async def get_status_summary(self):
        """Get a summary of all status combinations."""
        logger.info("Getting status summary...")

        try:
            # Get all trades
            response = self.supabase.from_("trades").select("status,order_status").execute()
            trades = response.data or []

            # Count combinations
            status_counts = {}
            for trade in trades:
                status = trade.get('status', 'NULL')
                order_status = trade.get('order_status', 'NULL')
                key = f"{status} | {order_status}"
                status_counts[key] = status_counts.get(key, 0) + 1

            # Display summary
            logger.info("Status combination summary:")
            for combination, count in sorted(status_counts.items()):
                logger.info(f"  {combination}: {count} trades")

        except Exception as e:
            logger.error(f"Error getting status summary: {e}")

async def main():
    """Main function."""
    try:
        checker = StatusInconsistencyChecker()

        # Check all inconsistencies
        await checker.check_all_inconsistencies()

        # Get status summary
        await checker.get_status_summary()

    except Exception as e:
        logger.error(f"Error in main: {e}")

if __name__ == "__main__":
    asyncio.run(main())





