#!/usr/bin/env python3
"""
Fix Status Inconsistencies Script

This script fixes inconsistent order_status and position_status combinations
in the trades table by applying the unified status mapping logic.
"""

import os
import sys
import logging
from typing import List, Dict, Any
from datetime import datetime, timezone

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.core.status_manager import StatusManager
from supabase import create_client, Client
from config import settings
# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def get_supabase_client() -> Client:
    """Get Supabase client."""
    url = settings.SUPABASE_URL
    key = settings.SUPABASE_KEY

    if not url or not key:
        raise ValueError("SUPABASE_URL and SUPABASE_ANON_KEY environment variables are required")

    return create_client(url, key)

def find_inconsistent_trades(supabase: Client) -> List[Dict[str, Any]]:
    """Find trades with inconsistent status combinations."""
    logger.info("Finding trades with inconsistent status combinations...")

    # Get all trades
    response = supabase.table('trades').select('*').execute()
    trades = response.data if response.data else []

    inconsistent_trades = []

    for trade in trades:
        order_status = trade.get('order_status', '')
        position_status = trade.get('status', '')

        # Check if status combination is inconsistent
        if not StatusManager.validate_status_consistency(order_status, position_status):
            inconsistent_trades.append(trade)
            logger.warning(f"Trade {trade['id']}: order_status='{order_status}', status='{position_status}' - INCONSISTENT")

    logger.info(f"Found {len(inconsistent_trades)} trades with inconsistent status combinations")
    return inconsistent_trades

def fix_trade_status(trade: Dict[str, Any]) -> Dict[str, Any]:
    """Fix a single trade's status inconsistency."""
    order_status = trade.get('order_status', '')
    position_status = trade.get('status', '')
    position_size = trade.get('position_size', 0) or 0

    # Get corrected statuses
    corrected_order_status, corrected_position_status = StatusManager.fix_inconsistent_status(
        order_status, position_status
    )

    # If still inconsistent, use the unified mapping
    if not StatusManager.validate_status_consistency(corrected_order_status, corrected_position_status):
        corrected_order_status, corrected_position_status = StatusManager.map_exchange_to_internal(
            order_status, position_size
        )

    return {
        'id': trade['id'],
        'order_status': corrected_order_status,
        'status': corrected_position_status,
        'updated_at': datetime.now(timezone.utc).isoformat()
    }

def apply_fixes(supabase: Client, fixes: List[Dict[str, Any]]) -> int:
    """Apply status fixes to the database."""
    if not fixes:
        logger.info("No fixes to apply")
        return 0

    logger.info(f"Applying {len(fixes)} status fixes...")

    success_count = 0
    error_count = 0

    for fix in fixes:
        try:
            # Update the trade
            response = supabase.table('trades').update({
                'order_status': fix['order_status'],
                'status': fix['status'],
                'updated_at': fix['updated_at']
            }).eq('id', fix['id']).execute()

            if response.data:
                success_count += 1
                logger.info(f"Fixed trade {fix['id']}: order_status='{fix['order_status']}', status='{fix['status']}'")
            else:
                error_count += 1
                logger.error(f"Failed to update trade {fix['id']}")

        except Exception as e:
            error_count += 1
            logger.error(f"Error updating trade {fix['id']}: {e}")

    logger.info(f"Applied fixes: {success_count} successful, {error_count} errors")
    return success_count

def generate_sql_fixes(inconsistent_trades: List[Dict[str, Any]]) -> str:
    """Generate SQL statements to fix inconsistencies."""
    sql_statements = []
    sql_statements.append("-- Fix Status Inconsistencies")
    sql_statements.append("-- Generated on: " + datetime.now(timezone.utc).isoformat())
    sql_statements.append("")

    for trade in inconsistent_trades:
        fix = fix_trade_status(trade)
        sql = f"""UPDATE trades
SET order_status = '{fix['order_status']}',
    status = '{fix['status']}',
    updated_at = '{fix['updated_at']}'
WHERE id = {fix['id']};"""
        sql_statements.append(sql)

    return "\n".join(sql_statements)

def main():
    """Main function."""
    try:
        logger.info("Starting status inconsistency fix...")

        # Get Supabase client
        supabase = get_supabase_client()

        # Find inconsistent trades
        inconsistent_trades = find_inconsistent_trades(supabase)

        if not inconsistent_trades:
            logger.info("No inconsistent trades found. Database is clean!")
            return

        # Generate fixes
        fixes = [fix_trade_status(trade) for trade in inconsistent_trades]

        # Apply fixes
        success_count = apply_fixes(supabase, fixes)

        # Generate SQL file for reference
        sql_content = generate_sql_fixes(inconsistent_trades)
        sql_file = f"status_fixes_{datetime.now().strftime('%Y%m%d_%H%M%S')}.sql"

        with open(sql_file, 'w') as f:
            f.write(sql_content)

        logger.info(f"SQL fixes saved to: {sql_file}")
        logger.info(f"Status inconsistency fix completed: {success_count} trades fixed")

    except Exception as e:
        logger.error(f"Error in status inconsistency fix: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
