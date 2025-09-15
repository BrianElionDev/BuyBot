#!/usr/bin/env python3
"""
Fix Executed Trade Status Script

This script fixes trades that have successful binance_response but are still marked as "pending".
It updates the status to "OPEN" and extracts order IDs and position sizes from the binance_response.

Usage:
    python3 scripts/maintenance/cleanup_scripts/fix_executed_trade_status.py
"""

import os
import sys
import json
import logging
from typing import List, Dict, Optional
from datetime import datetime, timezone
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add the project root to Python path
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(script_dir)
sys.path.insert(0, project_root)

from supabase import create_client, Client

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def initialize_supabase() -> Optional[Client]:
    """Initialize Supabase client."""
    try:
        supabase_url = os.getenv("SUPABASE_URL")
        supabase_key = os.getenv("SUPABASE_KEY")

        if not supabase_url or not supabase_key:
            logger.error("Missing Supabase credentials")
            return None

        return create_client(supabase_url, supabase_key)

    except Exception as e:
        logger.error(f"Failed to initialize Supabase: {e}")
        return None

def find_trades_needing_status_fix(supabase: Client) -> List[Dict]:
    """Find trades that have binance_response but status is still 'pending'"""
    try:
        # Query for trades with binance_response but status still 'pending'
        response = supabase.table("trades").select("*").eq("status", "pending").not_.is_("binance_response", "null").execute()

        trades_to_fix = []
        for trade in response.data:
            binance_response = trade.get('binance_response')
            if binance_response:
                try:
                    # Parse the binance_response if it's a string
                    if isinstance(binance_response, str):
                        response_data = json.loads(binance_response)
                    else:
                        response_data = binance_response

                    # Check if it contains successful execution data
                    if isinstance(response_data, dict) and ('order_id' in response_data or 'orderId' in response_data):
                        trades_to_fix.append(trade)
                except json.JSONDecodeError:
                    logger.warning(f"Could not parse binance_response for trade {trade['id']}")
                except Exception as e:
                    logger.warning(f"Error processing trade {trade['id']}: {e}")

        return trades_to_fix

    except Exception as e:
        logger.error(f"Error finding trades needing status fix: {e}")
        return []

def fix_trade_status(supabase: Client, trade: Dict) -> bool:
    """Fix a single trade's status by re-processing its binance_response"""
    trade_id = trade['id']
    binance_response = trade.get('binance_response')

    try:
        logger.info(f"Processing trade {trade_id}...")

        # Parse the binance_response
        if isinstance(binance_response, str):
            response_data = json.loads(binance_response)
        else:
            response_data = binance_response

        # Prepare updates
        updates = {
            'updated_at': datetime.now(timezone.utc).isoformat()
        }

        # Extract exchange_order_id
        if 'order_id' in response_data:
            updates['exchange_order_id'] = str(response_data['order_id'])
            logger.info(f"  - Extracted exchange_order_id: {response_data['order_id']}")
        elif 'orderId' in response_data:
            updates['exchange_order_id'] = str(response_data['orderId'])
            logger.info(f"  - Extracted exchange_order_id: {response_data['orderId']}")

        # Extract stop_loss_order_id
        if 'stop_loss_order_id' in response_data:
            updates['stop_loss_order_id'] = str(response_data['stop_loss_order_id'])
            logger.info(f"  - Extracted stop_loss_order_id: {response_data['stop_loss_order_id']}")

        # Update status
        if 'status' in response_data:
            response_status = response_data['status']
            if response_status == 'OPEN':
                updates['status'] = 'OPEN'
                updates['order_status'] = 'EXECUTED'
                logger.info(f"  - Updated status to OPEN, order_status to EXECUTED")
            elif response_status == 'FILLED':
                updates['status'] = 'CLOSED'
                updates['order_status'] = 'FILLED'
                logger.info(f"  - Updated status to CLOSED, order_status to FILLED")
            elif response_status == 'CANCELED':
                updates['status'] = 'CANCELLED'
                updates['order_status'] = 'CANCELLED'
                logger.info(f"  - Updated status to CANCELLED, order_status to CANCELLED")

        # Extract position size from tp_sl_orders
        if 'tp_sl_orders' in response_data:
            tp_sl_orders = response_data['tp_sl_orders']
            if isinstance(tp_sl_orders, list) and len(tp_sl_orders) > 0:
                first_order = tp_sl_orders[0]
                if 'origQty' in first_order:
                    try:
                        position_size = float(first_order['origQty'])
                        updates['position_size'] = position_size
                        logger.info(f"  - Extracted position_size: {position_size}")
                    except (ValueError, TypeError):
                        logger.warning(f"  - Could not parse position_size from tp_sl_orders")

        # Apply the updates
        try:
            supabase.table("trades").update(updates).eq("id", trade_id).execute()
            logger.info(f"✅ Successfully updated trade {trade_id}")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to update trade {trade_id}: {e}")
            return False

    except Exception as e:
        logger.error(f"Error fixing trade {trade_id}: {e}")
        return False


def run_status_fix():
    """Main execution method"""
    logger.info("=== Executed Trade Status Fix Script ===")

    # Initialize Supabase
    supabase = initialize_supabase()
    if not supabase:
        logger.error("Failed to initialize Supabase. Exiting.")
        return

    logger.info("Finding trades that need status fixes...")

    # Find trades needing fixes
    trades_to_fix = find_trades_needing_status_fix(supabase)
    logger.info(f"Found {len(trades_to_fix)} trades that need status fixes")

    if not trades_to_fix:
        logger.info("No trades found that need fixing. Exiting.")
        return

    # Process each trade
    fixed_count = 0
    failed_count = 0

    for trade in trades_to_fix:
        logger.info(f"\n--- Processing Trade ID: {trade['id']} ---")
        logger.info(f"Discord ID: {trade.get('discord_id')}")
        logger.info(f"Current Status: {trade.get('status')}")
        logger.info(f"Coin: {trade.get('coin_symbol')}")

        success = fix_trade_status(supabase, trade)
        if success:
            fixed_count += 1
        else:
            failed_count += 1

    # Summary
    logger.info("\n=== Summary ===")
    logger.info(f"Total trades processed: {len(trades_to_fix)}")
    logger.info(f"Successfully fixed: {fixed_count}")
    logger.info(f"Failed to fix: {failed_count}")

    if fixed_count > 0:
        logger.info("✅ Status fix completed successfully!")
    else:
        logger.info("ℹ️  No trades were fixed.")


def main():
    """Main entry point"""
    run_status_fix()


if __name__ == "__main__":
    main()
