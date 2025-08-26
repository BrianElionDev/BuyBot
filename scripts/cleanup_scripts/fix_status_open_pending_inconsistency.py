#!/usr/bin/env python3
"""
Script to fix the specific inconsistency where status is OPEN but order_status is PENDING.

This is a logical inconsistency because:
- If order_status is PENDING, the order hasn't been filled yet
- If status is OPEN, it means there's an active position
- These two states cannot coexist logically

The fix is to determine the correct status based on the actual order state.
"""

import asyncio
import json
import logging
from typing import Dict, List, Tuple
from supabase import create_client, Client
import os
from dotenv import load_dotenv
from datetime import datetime, timezone

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class StatusOpenPendingFixer:
    def __init__(self):
        self.supabase_url = os.getenv('SUPABASE_URL')
        self.supabase_key = os.getenv('SUPABASE_KEY')

        if not self.supabase_url or not self.supabase_key:
            raise ValueError("Missing SUPABASE_URL or SUPABASE_KEY environment variables")

        self.supabase: Client = create_client(self.supabase_url, self.supabase_key)

    async def find_inconsistent_trades(self) -> List[Dict]:
        """Find trades where status is OPEN but order_status is PENDING."""
        try:
            # Query for the specific inconsistency
            response = self.supabase.from_("trades").select("*").eq("status", "OPEN").eq("order_status", "PENDING").execute()

            if response.data:
                logger.info(f"Found {len(response.data)} trades with status=OPEN and order_status=PENDING")
                return response.data
            else:
                logger.info("No trades found with status=OPEN and order_status=PENDING")
                return []

        except Exception as e:
            logger.error(f"Error finding inconsistent trades: {e}")
            return []

    def analyze_trade_data(self, trade: Dict) -> Tuple[str, str, str]:
        """
        Analyze trade data to determine correct order_status and status.

        Returns:
            Tuple of (correct_order_status, correct_status, reason)
        """
        order_status = trade.get('order_status', 'PENDING')
        status = trade.get('status', 'NONE')
        position_size = float(trade.get('position_size', 0))
        realized_pnl = trade.get('realized_pnl')
        binance_response = trade.get('binance_response', '')
        order_status_response = trade.get('order_status_response', '')

        # Check if we have actual order data
        has_order_id = False
        actual_order_status = None

        # Check binance_response for order creation
        if binance_response:
            try:
                if isinstance(binance_response, str):
                    binance_data = json.loads(binance_response)
                else:
                    binance_data = binance_response

                if 'orderId' in binance_data and 'error' not in binance_data:
                    has_order_id = True
                    # Order was created successfully
                    actual_order_status = 'FILLED'  # Assume filled if we have orderId
            except (json.JSONDecodeError, TypeError):
                pass

        # Check order_status_response for actual order status
        if order_status_response:
            try:
                if isinstance(order_status_response, str):
                    status_data = json.loads(order_status_response)
                else:
                    status_data = order_status_response

                actual_order_status = status_data.get('status', '').upper()
                if actual_order_status in ['FILLED', 'PARTIALLY_FILLED', 'NEW', 'CANCELED', 'EXPIRED', 'REJECTED']:
                    has_order_id = True
            except (json.JSONDecodeError, TypeError):
                pass

        # Determine correct statuses
        if has_order_id and actual_order_status:
            if actual_order_status in ['FILLED', 'PARTIALLY_FILLED']:
                if position_size > 0:
                    return 'FILLED', 'OPEN', f"Order was {actual_order_status} and position size > 0"
                else:
                    return 'FILLED', 'CLOSED', f"Order was {actual_order_status} but position size = 0"
            elif actual_order_status == 'NEW':
                return 'PENDING', 'NONE', "Order is NEW (pending) - no position yet"
            elif actual_order_status in ['CANCELED', 'EXPIRED', 'REJECTED']:
                return actual_order_status, 'NONE', f"Order was {actual_order_status}"
            else:
                return 'PENDING', 'NONE', f"Unknown order status: {actual_order_status}"
        else:
            # No order data available - check position size
            if position_size > 0:
                return 'FILLED', 'OPEN', "Position size > 0 but no order data - assuming filled"
            elif realized_pnl is not None:
                return 'FILLED', 'CLOSED', "Has realized PnL - position was closed"
            else:
                return 'PENDING', 'NONE', "No order data and no position - keep as pending"

    async def fix_inconsistent_trades(self, trades: List[Dict]) -> int:
        """Fix the inconsistent trades."""
        fixed_count = 0

        for trade in trades:
            try:
                trade_id = trade['id']
                symbol = trade.get('coin_symbol', 'UNKNOWN')

                # Analyze the trade
                correct_order_status, correct_status, reason = self.analyze_trade_data(trade)

                # Check if fix is needed
                current_order_status = trade.get('order_status', 'PENDING')
                current_status = trade.get('status', 'NONE')

                if current_order_status != correct_order_status or current_status != correct_status:
                    # Update the trade
                    updates = {
                        'order_status': correct_order_status,
                        'status': correct_status,
                        'updated_at': datetime.now(timezone.utc).isoformat()
                    }

                    self.supabase.from_("trades").update(updates).eq("id", trade_id).execute()

                    logger.info(f"Fixed trade {trade_id} ({symbol}):")
                    logger.info(f"  Before: order_status={current_order_status}, status={current_status}")
                    logger.info(f"  After:  order_status={correct_order_status}, status={correct_status}")
                    logger.info(f"  Reason: {reason}")

                    fixed_count += 1
                else:
                    logger.info(f"Trade {trade_id} ({symbol}) is already correct")

            except Exception as e:
                logger.error(f"Error fixing trade {trade.get('id')}: {e}")
                continue

        return fixed_count

    async def run_fix(self):
        """Run the complete fix process."""
        logger.info("Starting status OPEN/PENDING inconsistency fix...")

        # Find inconsistent trades
        inconsistent_trades = await self.find_inconsistent_trades()

        if not inconsistent_trades:
            logger.info("No inconsistent trades found. All good!")
            return

        # Fix the trades
        fixed_count = await self.fix_inconsistent_trades(inconsistent_trades)

        logger.info(f"Fix completed! Fixed {fixed_count} out of {len(inconsistent_trades)} trades")

async def main():
    """Main function."""
    try:
        fixer = StatusOpenPendingFixer()
        await fixer.run_fix()
    except Exception as e:
        logger.error(f"Error in main: {e}")

if __name__ == "__main__":
    asyncio.run(main())





