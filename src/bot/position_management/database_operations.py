"""
Database Operations for Position Management

Handles database operations specific to position management and conflict resolution.
"""

import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)


class PositionDatabaseOperations:
    """
    Database operations for position management.

    Provides methods to interact with the database for position-related
    operations including conflict detection and trade aggregation.
    """

    def __init__(self, db_manager):
        self.db_manager = db_manager

    async def get_active_trades(self, symbol: str = None, trader: str = None) -> List[Dict[str, Any]]:
        """
        Get all active trades, optionally filtered by symbol or trader.

        Args:
            symbol: Optional symbol filter
            trader: Optional trader filter

        Returns:
            List of active trade records
        """
        try:
            # Build query conditions
            conditions = {
                'status': 'OPEN',
                'is_active': True
            }

            if symbol:
                conditions['coin_symbol'] = symbol

            if trader:
                conditions['trader'] = trader

            # Get trades from database using direct Supabase query
            try:
                query = self.db_manager.supabase.table("trades").select("*").eq("status", "OPEN").eq("is_active", True)

                if symbol:
                    query = query.eq("coin_symbol", symbol)
                if trader:
                    query = query.eq("trader", trader)

                response = query.execute()
                trades = response.data if response.data else []
            except Exception as e:
                logger.error(f"Error querying trades: {e}")
                trades = []

            logger.info(f"Retrieved {len(trades)} active trades" +
                       (f" for {symbol}" if symbol else "") +
                       (f" by {trader}" if trader else ""))

            return trades

        except Exception as e:
            logger.error(f"Error getting active trades: {e}")
            return []

    async def get_trades_by_symbol_and_side(self, symbol: str, side: str) -> List[Dict[str, Any]]:
        """
        Get all trades for a specific symbol and side.

        Args:
            symbol: Trading symbol
            side: Position side (LONG/SHORT)

        Returns:
            List of trade records
        """
        try:
            conditions = {
                'coin_symbol': symbol,
                'signal_type': side,
                'status': 'OPEN',
                'is_active': True
            }

            trades = await self.db_manager.get_trades_by_conditions(conditions)

            logger.info(f"Retrieved {len(trades)} {side} trades for {symbol}")
            return trades

        except Exception as e:
            logger.error(f"Error getting trades by symbol and side: {e}")
            return []

    async def get_position_trades(self, symbol: str) -> Dict[str, List[Dict[str, Any]]]:
        """
        Get all trades for a symbol grouped by side.

        Args:
            symbol: Trading symbol

        Returns:
            Dictionary with 'LONG' and 'SHORT' keys containing trade lists
        """
        try:
            long_trades = await self.get_trades_by_symbol_and_side(symbol, 'LONG')
            short_trades = await self.get_trades_by_symbol_and_side(symbol, 'SHORT')

            return {
                'LONG': long_trades,
                'SHORT': short_trades
            }

        except Exception as e:
            logger.error(f"Error getting position trades: {e}")
            return {'LONG': [], 'SHORT': []}

    async def update_trade(self, trade_id: int, updates: Dict[str, Any]) -> bool:
        """
        Update a trade record.

        Args:
            trade_id: Trade ID to update
            updates: Dictionary of fields to update

        Returns:
            True if successful, False otherwise
        """
        try:
            # Add updated_at timestamp
            updates['updated_at'] = datetime.now(timezone.utc).isoformat()

            # Update the trade
            result = await self.db_manager.update_trade(trade_id, updates)

            if result:
                logger.info(f"Updated trade {trade_id}")
            else:
                logger.error(f"Failed to update trade {trade_id}")

            return result

        except Exception as e:
            logger.error(f"Error updating trade {trade_id}: {e}")
            return False

    async def merge_trades(self, primary_trade_id: int, secondary_trade_id: int,
                          merge_data: Dict[str, Any]) -> bool:
        """
        Merge two trades, updating the primary and marking the secondary as merged.

        Args:
            primary_trade_id: ID of the primary trade to keep
            secondary_trade_id: ID of the secondary trade to merge
            merge_data: Data to update the primary trade with

        Returns:
            True if successful, False otherwise
        """
        try:
            # Update primary trade with merged data
            primary_updates = {
                **merge_data,
                'merged_trades_count': merge_data.get('merged_trades_count', 1) + 1,
                'last_merge_at': datetime.now(timezone.utc).isoformat()
            }

            primary_success = await self.update_trade(primary_trade_id, primary_updates)

            if not primary_success:
                return False

            # Mark secondary trade as merged
            secondary_updates = {
                'status': 'MERGED',
                'merged_into_trade_id': primary_trade_id,
                'merge_reason': 'Position aggregation',
                'merged_at': datetime.now(timezone.utc).isoformat()
            }

            secondary_success = await self.update_trade(secondary_trade_id, secondary_updates)

            if not secondary_success:
                # Try to rollback primary trade update
                await self.update_trade(primary_trade_id, {
                    'merged_trades_count': merge_data.get('merged_trades_count', 1),
                    'last_merge_at': None
                })
                return False

            logger.info(f"Merged trade {secondary_trade_id} into {primary_trade_id}")
            return True

        except Exception as e:
            logger.error(f"Error merging trades: {e}")
            return False

    async def close_position_trades(self, symbol: str, side: str,
                                   close_reason: str = "Position closed") -> int:
        """
        Close all trades for a specific symbol and side.

        Args:
            symbol: Trading symbol
            side: Position side (LONG/SHORT)
            close_reason: Reason for closing

        Returns:
            Number of trades closed
        """
        try:
            trades = await self.get_trades_by_symbol_and_side(symbol, side)
            closed_count = 0

            for trade in trades:
                close_data = {
                    'status': 'CLOSED',
                    'closed_at': datetime.now(timezone.utc).isoformat(),
                    'close_reason': close_reason
                }

                if await self.update_trade(trade['id'], close_data):
                    closed_count += 1

            logger.info(f"Closed {closed_count} {side} trades for {symbol}")
            return closed_count

        except Exception as e:
            logger.error(f"Error closing position trades: {e}")
            return 0

    async def get_trade_conflicts(self, symbol: str, side: str,
                                 exclude_trade_id: int = None) -> List[Dict[str, Any]]:
        """
        Get all trades that would conflict with a new trade for the same symbol.

        Args:
            symbol: Trading symbol
            side: Position side (LONG/SHORT)
            exclude_trade_id: Trade ID to exclude from results

        Returns:
            List of conflicting trade records
        """
        try:
            # Get all active trades for the symbol
            all_trades = await self.get_active_trades(symbol)

            # Filter for same side trades
            conflicting_trades = []
            for trade in all_trades:
                if exclude_trade_id and trade['id'] == exclude_trade_id:
                    continue

                trade_side = trade.get('signal_type', '').upper()
                if trade_side == side:
                    conflicting_trades.append(trade)

            logger.info(f"Found {len(conflicting_trades)} conflicting trades for {symbol} {side}")
            return conflicting_trades

        except Exception as e:
            logger.error(f"Error getting trade conflicts: {e}")
            return []

    async def get_position_summary(self, symbol: str = None) -> Dict[str, Any]:
        """
        Get a summary of all positions or a specific symbol.

        Args:
            symbol: Optional symbol to filter by

        Returns:
            Dictionary with position summary
        """
        try:
            if symbol:
                trades = await self.get_active_trades(symbol)
            else:
                trades = await self.get_active_trades()

            # Group trades by symbol and side
            positions = {}

            for trade in trades:
                trade_symbol = trade.get('coin_symbol')
                trade_side = trade.get('signal_type', 'LONG').upper()

                if not trade_symbol:
                    continue

                position_key = f"{trade_symbol}_{trade_side}"

                if position_key not in positions:
                    positions[position_key] = {
                        'symbol': trade_symbol,
                        'side': trade_side,
                        'trades': [],
                        'total_size': 0.0,
                        'total_entry_value': 0.0,
                        'trade_count': 0
                    }

                position_size = float(trade.get('position_size', 0))
                entry_price = float(trade.get('entry_price', 0))

                if position_size > 0 and entry_price > 0:
                    positions[position_key]['trades'].append(trade)
                    positions[position_key]['total_size'] += position_size
                    positions[position_key]['total_entry_value'] += position_size * entry_price
                    positions[position_key]['trade_count'] += 1

            # Calculate weighted average entry prices
            for position in positions.values():
                if position['total_size'] > 0:
                    position['weighted_entry_price'] = (
                        position['total_entry_value'] / position['total_size']
                    )
                else:
                    position['weighted_entry_price'] = 0.0

            summary = {
                'total_positions': len(positions),
                'positions': list(positions.values())
            }

            if symbol:
                summary['filtered_symbol'] = symbol

            return summary

        except Exception as e:
            logger.error(f"Error getting position summary: {e}")
            return {'error': str(e)}

    async def cleanup_merged_trades(self, older_than_days: int = 7) -> int:
        """
        Clean up old merged trades to keep the database clean.

        Args:
            older_than_days: Remove merged trades older than this many days

        Returns:
            Number of trades cleaned up
        """
        try:
            from datetime import timedelta

            cutoff_date = datetime.now(timezone.utc) - timedelta(days=older_than_days)
            cutoff_iso = cutoff_date.isoformat()

            # Get old merged trades
            conditions = {
                'status': 'MERGED',
                'merged_at__lt': cutoff_iso
            }

            old_merged_trades = await self.db_manager.get_trades_by_conditions(conditions)

            # Mark them as inactive instead of deleting
            cleaned_count = 0
            for trade in old_merged_trades:
                if await self.update_trade(trade['id'], {
                    'is_active': False,
                    'cleanup_reason': f'Cleaned up merged trade older than {older_than_days} days'
                }):
                    cleaned_count += 1

            logger.info(f"Cleaned up {cleaned_count} old merged trades")
            return cleaned_count

        except Exception as e:
            logger.error(f"Error cleaning up merged trades: {e}")
            return 0
