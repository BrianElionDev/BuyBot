#!/usr/bin/env python3
"""
Timestamp Manager for Trade Lifecycle

This module ensures that created_at and closed_at timestamps are accurately
set at the exact moments when trades are created and closed, with validation
and WebSocket monitoring.
"""

from datetime import datetime, timezone
from typing import Dict, Optional, Any
import logging
from supabase import Client

logger = logging.getLogger(__name__)


class TimestampManager:
    """Manages accurate timestamp setting for trade lifecycle events."""

    def __init__(self, supabase: Client):
        self.supabase = supabase

    def validate_created_at(self, trade_data: Dict[str, Any]) -> bool:
        """
        Validate that created_at is only set once when trade is first created.

        Args:
            trade_data: Trade data dict

        Returns:
            bool: True if created_at is valid/can be set
        """
        try:
            # If trade already has created_at, don't allow changes
            if trade_data.get('created_at'):
                logger.warning(f"Trade already has created_at: {trade_data.get('created_at')}")
                return False

            return True

        except Exception as e:
            logger.error(f"Error validating created_at: {e}")
            return False

    def validate_closed_at(self, trade_data: Dict[str, Any], new_status: str) -> bool:
        """
        Validate that closed_at can only be set when position is actually closed.

        Args:
            trade_data: Trade data dict
            new_status: New status being set

        Returns:
            bool: True if closed_at can be set
        """
        try:
            # Only allow closed_at to be set when status is CLOSED
            if new_status != 'CLOSED':
                return False

            # Allow setting closed_at even if it already exists (for fixing missing timestamps)
            # The database update function will handle the logic of when to actually set it
            return True

        except Exception as e:
            logger.error(f"Error validating closed_at: {e}")
            return False

    def set_created_at(self, trade_id: int, binance_order_time: Optional[int] = None) -> bool:
        """
        Set created_at timestamp when trade is first created.
        Uses Binance order timestamp if available, otherwise current time.

        Args:
            trade_id: Database trade ID
            binance_order_time: Binance order timestamp in milliseconds

        Returns:
            bool: Success status
        """
        try:
            # Get current trade data
            response = self.supabase.from_("trades").select("*").eq("id", trade_id).execute()
            trade = response.data[0] if response.data else None

            if not trade:
                logger.error(f"Trade {trade_id} not found")
                return False

            # Validate that created_at can be set
            if not self.validate_created_at(trade):
                return False

            # Use Binance order time if available, otherwise current time
            if binance_order_time:
                created_at = datetime.fromtimestamp(binance_order_time / 1000, tz=timezone.utc).isoformat()
                logger.info(f"Setting created_at from Binance order time: {created_at}")
            else:
                created_at = datetime.now(timezone.utc).isoformat()
                logger.info(f"Setting created_at to current time: {created_at}")

            # Update database
            update_data = {
                'created_at': created_at,
                'updated_at': datetime.now(timezone.utc).isoformat()
            }

            self.supabase.from_("trades").update(update_data).eq("id", trade_id).execute()
            logger.info(f"✅ Set created_at for trade {trade_id}: {created_at}")

            return True

        except Exception as e:
            logger.error(f"Error setting created_at for trade {trade_id}: {e}")
            return False

    def set_closed_at(self, trade_id: int, binance_fill_time: Optional[int] = None) -> bool:
        """
        Set closed_at timestamp when position is actually closed.
        Uses Binance fill timestamp if available, otherwise current time.

        Args:
            trade_id: Database trade ID
            binance_fill_time: Binance fill timestamp in milliseconds

        Returns:
            bool: Success status
        """
        try:
            # Get current trade data
            response = self.supabase.from_("trades").select("*").eq("id", trade_id).execute()
            trade = response.data[0] if response.data else None

            if not trade:
                logger.error(f"Trade {trade_id} not found")
                return False

            # Validate that closed_at can be set
            if not self.validate_closed_at(trade, 'CLOSED'):
                return False

            # Use Binance fill time if available, otherwise current time
            if binance_fill_time:
                closed_at = datetime.fromtimestamp(binance_fill_time / 1000, tz=timezone.utc).isoformat()
                logger.info(f"Setting closed_at from Binance fill time: {closed_at}")
            else:
                closed_at = datetime.now(timezone.utc).isoformat()
                logger.info(f"Setting closed_at to current time: {closed_at}")

            # Update database with closed_at and status
            # Use Binance execution time for updated_at if available (for accurate PnL calculations)
            if binance_fill_time:
                updated_at = datetime.fromtimestamp(binance_fill_time / 1000, tz=timezone.utc).isoformat()
                logger.info(f"Using Binance execution time for updated_at: {updated_at}")
            else:
                updated_at = datetime.now(timezone.utc).isoformat()

            update_data = {
                'closed_at': closed_at,
                'status': 'CLOSED',
                'updated_at': updated_at
            }

            self.supabase.from_("trades").update(update_data).eq("id", trade_id).execute()
            logger.info(f"✅ Set closed_at for trade {trade_id}: {closed_at}")

            return True

        except Exception as e:
            logger.error(f"Error setting closed_at for trade {trade_id}: {e}")
            return False

    def fix_missing_timestamps(self, trade_id: int) -> bool:
        """
        Fix missing timestamps for existing trades (one-time backfill only).
        This should only be used for historical data cleanup.

        Args:
            trade_id: Database trade ID

        Returns:
            bool: Success status
        """
        try:
            # Get trade data
            response = self.supabase.from_("trades").select("*").eq("id", trade_id).execute()
            trade = response.data[0] if response.data else None

            if not trade:
                logger.error(f"Trade {trade_id} not found")
                return False

            update_data = {}

            # Fix missing created_at (only if missing)
            if not trade.get('created_at'):
                # Use updated_at as fallback, or current time
                fallback_time = trade.get('updated_at') or datetime.now(timezone.utc).isoformat()
                update_data['created_at'] = fallback_time
                logger.info(f"Backfilling created_at for trade {trade_id}: {fallback_time}")

            # Fix missing closed_at for CLOSED trades (only if missing)
            if trade.get('status') == 'CLOSED' and not trade.get('closed_at'):
                # Use updated_at as fallback
                fallback_time = trade.get('updated_at') or datetime.now(timezone.utc).isoformat()
                update_data['closed_at'] = fallback_time
                logger.info(f"Backfilling closed_at for trade {trade_id}: {fallback_time}")

            # Update database if needed
            if update_data:
                update_data['updated_at'] = datetime.now(timezone.utc).isoformat()
                self.supabase.from_("trades").update(update_data).eq("id", trade_id).execute()
                logger.info(f"✅ Fixed missing timestamps for trade {trade_id}")
                return True
            else:
                logger.info(f"Trade {trade_id} timestamps are already correct")
                return True

        except Exception as e:
            logger.error(f"Error fixing timestamps for trade {trade_id}: {e}")
            return False


class WebSocketTimestampHandler:
    """Handles timestamp updates from WebSocket events."""

    def __init__(self, timestamp_manager: TimestampManager):
        self.timestamp_manager = timestamp_manager

    async def handle_order_execution(self, order_data: Dict[str, Any]) -> bool:
        """
        Handle order execution events from WebSocket.
        Sets created_at when order is first executed.

        Args:
            order_data: Order execution data from WebSocket

        Returns:
            bool: Success status
        """
        try:
            order_id = order_data.get('i')  # Binance order ID
            status = order_data.get('X')  # Order status
            execution_time = order_data.get('T')  # Transaction time

            if not order_id:
                return False

            # Find trade by exchange_order_id
            response = self.timestamp_manager.supabase.from_("trades").select("*").eq("exchange_order_id", order_id).execute()
            trade = response.data[0] if response.data else None

            if not trade:
                logger.info(f"No trade found for order ID {order_id}")
                return False

            trade_id = trade['id']

            # Set created_at when order is first executed (PARTIALLY_FILLED or FILLED)
            if status in ['PARTIALLY_FILLED', 'FILLED'] and not trade.get('created_at'):
                success = self.timestamp_manager.set_created_at(trade_id, execution_time)
                if success:
                    logger.info(f"Set created_at from WebSocket for trade {trade_id}")

            return True

        except Exception as e:
            logger.error(f"Error handling order execution: {e}")
            return False

    async def handle_position_closure(self, position_data: Dict[str, Any]) -> bool:
        """
        Handle position closure events from WebSocket.
        Sets closed_at when position is fully closed.

        Args:
            position_data: Position data from WebSocket

        Returns:
            bool: Success status
        """
        try:
            symbol = position_data.get('s')  # Symbol
            position_amount = float(position_data.get('pa', 0))  # Position amount
            update_time = position_data.get('T')  # Update time

            # Position is closed when amount becomes 0
            if position_amount != 0:
                return False

            # Find open trades for this symbol
            response = self.timestamp_manager.supabase.from_("trades").select("*").eq("coin_symbol", symbol.replace('USDT', '')).eq("status", "OPEN").execute()
            trades = response.data or []

            for trade in trades:
                trade_id = trade['id']

                # Set closed_at when position is closed
                success = self.timestamp_manager.set_closed_at(trade_id, update_time)
                if success:
                    logger.info(f"Set closed_at from WebSocket for trade {trade_id}")

            return True

        except Exception as e:
            logger.error(f"Error handling position closure: {e}")
            return False


# Integration functions for existing code
async def ensure_created_at(supabase: Client, trade_id: int, binance_order_time: Optional[int] = None) -> bool:
    """
    Ensure created_at is set for a trade. Safe to call multiple times.

    Args:
        supabase: Supabase client
        trade_id: Database trade ID
        binance_order_time: Binance order timestamp in milliseconds

    Returns:
        bool: Success status
    """
    timestamp_manager = TimestampManager(supabase)
    return timestamp_manager.set_created_at(trade_id, binance_order_time)


async def ensure_closed_at(supabase: Client, trade_id: int, binance_fill_time: Optional[int] = None) -> bool:
    """
    Ensure closed_at is set for a trade. Safe to call multiple times.

    Args:
        supabase: Supabase client
        trade_id: Database trade ID
        binance_fill_time: Binance fill timestamp in milliseconds

    Returns:
        bool: Success status
    """
    timestamp_manager = TimestampManager(supabase)
    return timestamp_manager.set_closed_at(trade_id, binance_fill_time)


async def fix_historical_timestamps(supabase: Client, trade_id: int) -> bool:
    """
    Fix missing timestamps for historical trades (backfill only).

    Args:
        supabase: Supabase client
        trade_id: Database trade ID

    Returns:
        bool: Success status
    """
    timestamp_manager = TimestampManager(supabase)
    return timestamp_manager.fix_missing_timestamps(trade_id)
