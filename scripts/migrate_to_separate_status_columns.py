#!/usr/bin/env python3
"""
Migration script to separate order status and position status.
This script updates existing trades to use the new order_status and position_status columns.
"""

import os
import sys
import logging
from datetime import datetime, timezone
from dotenv import load_dotenv

# Add the project root to Python path
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(script_dir)
sys.path.insert(0, project_root)

from supabase import create_client, Client
from discord_bot.status_constants import map_binance_order_status, determine_position_status_from_order
from config import settings

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def initialize_supabase() -> Client:
    """Initialize Supabase client."""
    try:
        supabase_url = settings.SUPABASE_URL
        supabase_key = settings.SUPABASE_KEY

        if not supabase_url or not supabase_key:
            logger.error("Missing Supabase credentials")
            return None

        return create_client(supabase_url, supabase_key)

    except Exception as e:
        logger.error(f"Failed to initialize Supabase: {e}")
        return None

def migrate_trade_statuses(supabase: Client):
    """Migrate existing trades to use separate order_status and position_status columns."""
    try:
        logger.info("Starting migration of trade statuses...")

        # Get all trades that need migration
        response = supabase.from_("trades").select("*").execute()
        trades = response.data or []

        logger.info(f"Found {len(trades)} trades to migrate")

        migrated_count = 0
        for trade in trades:
            try:
                trade_id = trade['id']
                current_status = trade.get('status', 'PENDING')
                binance_response = trade.get('binance_response', '')
                order_status_response = trade.get('order_status_response', '')

                # Determine order_status and position_status based on current data
                order_status = 'PENDING'
                position_status = 'NONE'

                # Parse binance_response if available
                if binance_response:
                    try:
                        import json
                        binance_data = json.loads(binance_response) if isinstance(binance_response, str) else binance_response

                        if 'orderId' in binance_data and 'error' not in binance_data:
                            # Order was created successfully
                            order_status = 'FILLED'  # Assume filled if we have orderId
                            position_status = 'OPEN'  # Assume position is open
                        elif 'error' in binance_data:
                            # Order failed
                            order_status = 'REJECTED'
                            position_status = 'NONE'
                    except (json.JSONDecodeError, TypeError):
                        pass

                # Parse order_status_response if available
                if order_status_response:
                    try:
                        import json
                        status_data = json.loads(order_status_response) if isinstance(order_status_response, str) else order_status_response

                        binance_status = status_data.get('status', '').upper()
                        order_status = map_binance_order_status(binance_status)

                        # Determine position status based on order status
                        position_size = float(trade.get('position_size', 0))
                        position_status = determine_position_status_from_order(order_status, position_size)
                    except (json.JSONDecodeError, TypeError):
                        pass

                # Map current status to new columns if no other data available
                if order_status == 'PENDING' and position_status == 'NONE':
                    if current_status in ['PENDING', 'FAILED']:
                        order_status = current_status
                        position_status = 'NONE'
                    elif current_status in ['OPEN', 'CLOSED', 'PARTIALLY_CLOSED']:
                        order_status = 'FILLED'
                        position_status = current_status

                # Update the trade
                updates = {
                    'order_status': order_status,
                    'status': position_status,  # status column now holds position status
                    'updated_at': datetime.now(timezone.utc).isoformat()
                }

                supabase.table("trades").update(updates).eq("id", trade_id).execute()
                migrated_count += 1

                if migrated_count % 100 == 0:
                    logger.info(f"Migrated {migrated_count} trades...")

            except Exception as e:
                logger.error(f"Error migrating trade {trade.get('id')}: {e}")
                continue

        logger.info(f"Migration completed! Migrated {migrated_count} trades")

        # Show summary
        response = supabase.from_("trades").select("order_status, status").execute()
        trades = response.data or []

        order_status_counts = {}
        position_status_counts = {}

        for trade in trades:
            order_status = trade.get('order_status', 'UNKNOWN')
            position_status = trade.get('status', 'UNKNOWN')

            order_status_counts[order_status] = order_status_counts.get(order_status, 0) + 1
            position_status_counts[position_status] = position_status_counts.get(position_status, 0) + 1

        logger.info("Order Status Summary:")
        for status, count in order_status_counts.items():
            logger.info(f"  {status}: {count}")

        logger.info("Position Status Summary:")
        for status, count in position_status_counts.items():
            logger.info(f"  {status}: {count}")

    except Exception as e:
        logger.error(f"Error during migration: {e}")

def main():
    """Main migration function."""
    logger.info("Starting trade status migration...")

    supabase = initialize_supabase()
    if not supabase:
        logger.error("Failed to initialize Supabase client")
        return

    migrate_trade_statuses(supabase)
    logger.info("Migration completed!")

if __name__ == "__main__":
    main()