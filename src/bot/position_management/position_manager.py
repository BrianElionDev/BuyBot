"""
Position Management System

Handles position aggregation, conflict detection, and trade management
to ensure database consistency with exchange behavior.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class PositionConflictAction(Enum):
    """Actions to take when a position conflict is detected."""
    MERGE = "merge"  # Merge new trade into existing position
    REJECT = "reject"  # Reject new trade
    REPLACE = "replace"  # Replace existing position
    COOLDOWN = "cooldown"  # Apply cooldown and reject


@dataclass
class PositionInfo:
    """Information about an active position."""
    symbol: str
    side: str  # LONG or SHORT
    size: float
    entry_price: float
    mark_price: float
    unrealized_pnl: float
    trade_ids: List[int]  # List of trade IDs that make up this position
    primary_trade_id: int  # The main trade ID for this position
    created_at: datetime
    updated_at: datetime


@dataclass
class TradeConflict:
    """Information about a trade conflict."""
    new_trade_id: int
    existing_position: PositionInfo
    conflict_type: str
    suggested_action: PositionConflictAction
    reason: str


class PositionManager:
    """
    Manages position aggregation and conflict resolution.

    This class ensures that the database accurately reflects the exchange's
    position aggregation behavior, preventing orphaned orders and database inconsistencies.
    """

    def __init__(self, db_manager, exchange):
        self.db_manager = db_manager
        self.exchange = exchange
        self.position_cache = {}  # Cache for active positions
        self.last_cache_update = None
        self.cache_ttl = 30  # Cache TTL in seconds

    async def get_active_positions(self, force_refresh: bool = False) -> Dict[str, PositionInfo]:
        """
        Get all active positions from the database.

        Args:
            force_refresh: Force refresh of position cache

        Returns:
            Dict mapping symbol to PositionInfo
        """
        current_time = datetime.now(timezone.utc)

        # Check if cache is still valid
        if (not force_refresh and
            self.last_cache_update and
            (current_time - self.last_cache_update).seconds < self.cache_ttl):
            return self.position_cache

        try:
            # Get all active trades from database
            active_trades = await self.db_manager.get_active_trades()

            # Group trades by symbol and side
            positions_by_symbol = {}

            for trade in active_trades:
                symbol = trade.get('coin_symbol')
                if not symbol:
                    continue

                # Create position key (symbol + side)
                side = self._determine_position_side(trade)
                position_key = f"{symbol}_{side}"

                if position_key not in positions_by_symbol:
                    positions_by_symbol[position_key] = {
                        'trades': [],
                        'total_size': 0.0,
                        'weighted_entry': 0.0,
                        'total_entry_value': 0.0
                    }

                # Add trade to position
                trade_size = float(trade.get('position_size', 0))
                entry_price = float(trade.get('entry_price', 0))

                if trade_size > 0 and entry_price > 0:
                    positions_by_symbol[position_key]['trades'].append(trade)
                    positions_by_symbol[position_key]['total_size'] += trade_size
                    positions_by_symbol[position_key]['total_entry_value'] += trade_size * entry_price

            # Convert to PositionInfo objects
            self.position_cache = {}

            for position_key, pos_data in positions_by_symbol.items():
                if not pos_data['trades']:
                    continue

                symbol, side = position_key.split('_', 1)

                # Calculate weighted average entry price
                if pos_data['total_size'] > 0:
                    weighted_entry = pos_data['total_entry_value'] / pos_data['total_size']
                else:
                    weighted_entry = 0.0

                # Get the primary trade (oldest or largest)
                primary_trade = min(pos_data['trades'],
                                  key=lambda t: (t.get('created_at', ''), -float(t.get('position_size', 0))))

                # Get current mark price from exchange
                mark_price = await self._get_mark_price(symbol)
                unrealized_pnl = await self._calculate_unrealized_pnl(
                    pos_data['total_size'], weighted_entry, mark_price, side
                )

                try:
                    import asyncio
                    from src.services.notifications.trade_notification_service import trade_notification_service, PnLUpdateData
                    from datetime import datetime, timezone

                    if hasattr(self, '_last_pnl_cache'):
                        last_pnl = self._last_pnl_cache.get(position_key, 0)
                        pnl_change = abs(unrealized_pnl - last_pnl)
                        if pnl_change > 1.0:
                            # Determine exchange name from exchange object
                            exchange_name = "Binance" if "Binance" in self.exchange.__class__.__name__ else "Kucoin"

                            notification_data = PnLUpdateData(
                                symbol=symbol,
                                position_type=side,
                                entry_price=weighted_entry,
                                current_price=mark_price,
                                quantity=pos_data['total_size'],
                                unrealized_pnl=unrealized_pnl,
                                exchange=exchange_name,
                                timestamp=datetime.now(timezone.utc)
                            )

                            asyncio.create_task(trade_notification_service.notify_pnl_update(notification_data))

                    if not hasattr(self, '_last_pnl_cache'):
                        self._last_pnl_cache = {}
                    self._last_pnl_cache[position_key] = unrealized_pnl

                except Exception as e:
                    logger.error(f"Failed to send PnL update notification: {e}")

                position_info = PositionInfo(
                    symbol=symbol,
                    side=side,
                    size=pos_data['total_size'],
                    entry_price=weighted_entry,
                    mark_price=mark_price,
                    unrealized_pnl=unrealized_pnl,
                    trade_ids=[t['id'] for t in pos_data['trades']],
                    primary_trade_id=primary_trade['id'],
                    created_at=min(t.get('created_at', current_time) for t in pos_data['trades']),
                    updated_at=current_time
                )

                self.position_cache[position_key] = position_info

            self.last_cache_update = current_time
            logger.info(f"Updated position cache with {len(self.position_cache)} active positions")

            return self.position_cache

        except Exception as e:
            logger.error(f"Error getting active positions: {e}")
            return {}

    async def check_position_conflict(self, symbol: str, side: str,
                                    new_trade_id: int) -> Optional[TradeConflict]:
        """
        Check if a new trade conflicts with existing positions.

        Args:
            symbol: Trading symbol
            side: Position side (LONG/SHORT)
            new_trade_id: ID of the new trade

        Returns:
            TradeConflict if conflict exists, None otherwise
        """
        try:
            # Get active positions
            positions = await self.get_active_positions()

            # Check for same-side position
            same_side_key = f"{symbol}_{side}"
            if same_side_key in positions:
                existing_position = positions[same_side_key]

                return TradeConflict(
                    new_trade_id=new_trade_id,
                    existing_position=existing_position,
                    conflict_type="same_side",
                    suggested_action=PositionConflictAction.MERGE,
                    reason=f"Existing {side} position for {symbol} with size {existing_position.size}"
                )

            # Check for opposite-side position
            opposite_side = "SHORT" if side == "LONG" else "LONG"
            opposite_side_key = f"{symbol}_{opposite_side}"
            if opposite_side_key in positions:
                existing_position = positions[opposite_side_key]

                return TradeConflict(
                    new_trade_id=new_trade_id,
                    existing_position=existing_position,
                    conflict_type="opposite_side",
                    suggested_action=PositionConflictAction.REJECT,
                    reason=f"Conflicting {opposite_side} position exists for {symbol}"
                )

            return None

        except Exception as e:
            logger.error(f"Error checking position conflict: {e}")
            return None

    async def handle_position_conflict(self, conflict: TradeConflict,
                                     new_trade_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle a position conflict based on the suggested action.

        Args:
            conflict: The detected conflict
            new_trade_data: Data for the new trade

        Returns:
            Result of the conflict resolution
        """
        try:
            if conflict.suggested_action == PositionConflictAction.MERGE:
                return await self._merge_trade_into_position(conflict, new_trade_data)
            elif conflict.suggested_action == PositionConflictAction.REJECT:
                return await self._reject_trade(conflict, new_trade_data)
            elif conflict.suggested_action == PositionConflictAction.REPLACE:
                return await self._replace_position(conflict, new_trade_data)
            elif conflict.suggested_action == PositionConflictAction.COOLDOWN:
                return await self._apply_cooldown_and_reject(conflict, new_trade_data)
            else:
                return {
                    'success': False,
                    'error': f"Unknown conflict action: {conflict.suggested_action}"
                }

        except Exception as e:
            logger.error(f"Error handling position conflict: {e}")
            return {
                'success': False,
                'error': f"Error handling conflict: {str(e)}"
            }

    async def _merge_trade_into_position(self, conflict: TradeConflict,
                                       new_trade_data: Dict[str, Any]) -> Dict[str, Any]:
        """Merge a new trade into an existing position."""
        try:
            # Update the primary trade with new position size
            new_size = float(new_trade_data.get('position_size', 0))
            new_entry_price = float(new_trade_data.get('entry_price', 0))

            if new_size <= 0 or new_entry_price <= 0:
                return {
                    'success': False,
                    'error': 'Invalid trade size or entry price for merging'
                }

            # Calculate new weighted average entry price
            existing_position = conflict.existing_position
            total_size = existing_position.size + new_size
            total_value = (existing_position.size * existing_position.entry_price +
                          new_size * new_entry_price)
            new_weighted_entry = total_value / total_size if total_size > 0 else 0

            # Update primary trade
            update_data = {
                'position_size': total_size,
                'entry_price': new_weighted_entry,
                'updated_at': datetime.now(timezone.utc).isoformat()
            }

            await self.db_manager.update_trade(conflict.existing_position.primary_trade_id, update_data)

            # Mark new trade as merged
            merge_data = {
                'status': 'MERGED',
                'merged_into_trade_id': conflict.existing_position.primary_trade_id,
                'updated_at': datetime.now(timezone.utc).isoformat()
            }

            await self.db_manager.update_trade(conflict.new_trade_id, merge_data)

            # Invalidate position cache
            self.position_cache = {}

            logger.info(f"Merged trade {conflict.new_trade_id} into position {conflict.existing_position.primary_trade_id}")

            return {
                'success': True,
                'action': 'merged',
                'primary_trade_id': conflict.existing_position.primary_trade_id,
                'new_position_size': total_size,
                'new_entry_price': new_weighted_entry
            }

        except Exception as e:
            logger.error(f"Error merging trade: {e}")
            return {
                'success': False,
                'error': f"Error merging trade: {str(e)}"
            }

    async def _reject_trade(self, conflict: TradeConflict,
                          new_trade_data: Dict[str, Any]) -> Dict[str, Any]:
        """Reject a trade due to position conflict."""
        try:
            # Mark trade as rejected
            reject_data = {
                'status': 'REJECTED',
                'rejection_reason': conflict.reason,
                'updated_at': datetime.now(timezone.utc).isoformat()
            }

            await self.db_manager.update_trade(conflict.new_trade_id, reject_data)

            logger.info(f"Rejected trade {conflict.new_trade_id}: {conflict.reason}")

            return {
                'success': False,
                'action': 'rejected',
                'reason': conflict.reason
            }

        except Exception as e:
            logger.error(f"Error rejecting trade: {e}")
            return {
                'success': False,
                'error': f"Error rejecting trade: {str(e)}"
            }

    async def _replace_position(self, conflict: TradeConflict,
                              new_trade_data: Dict[str, Any]) -> Dict[str, Any]:
        """Replace existing position with new trade."""
        try:
            # Close existing position
            for trade_id in conflict.existing_position.trade_ids:
                close_data = {
                    'status': 'CLOSED',
                    'closed_at': datetime.now(timezone.utc).isoformat(),
                    'updated_at': datetime.now(timezone.utc).isoformat()
                }
                await self.db_manager.update_trade(trade_id, close_data)

            # Mark new trade as primary
            new_trade_data['status'] = 'OPEN'
            await self.db_manager.update_trade(conflict.new_trade_id, new_trade_data)

            # Invalidate position cache
            self.position_cache = {}

            logger.info(f"Replaced position with trade {conflict.new_trade_id}")

            return {
                'success': True,
                'action': 'replaced',
                'closed_trades': conflict.existing_position.trade_ids,
                'new_primary_trade_id': conflict.new_trade_id
            }

        except Exception as e:
            logger.error(f"Error replacing position: {e}")
            return {
                'success': False,
                'error': f"Error replacing position: {str(e)}"
            }

    async def _apply_cooldown_and_reject(self, conflict: TradeConflict,
                                       new_trade_data: Dict[str, Any]) -> Dict[str, Any]:
        """Apply cooldown and reject the trade."""
        try:
            # Mark trade as cooldown rejected
            cooldown_data = {
                'status': 'COOLDOWN_REJECTED',
                'rejection_reason': f"Cooldown active for {conflict.existing_position.symbol}",
                'updated_at': datetime.now(timezone.utc).isoformat()
            }

            await self.db_manager.update_trade(conflict.new_trade_id, cooldown_data)

            logger.info(f"Applied cooldown and rejected trade {conflict.new_trade_id}")

            return {
                'success': False,
                'action': 'cooldown_rejected',
                'reason': f"Cooldown active for {conflict.existing_position.symbol}"
            }

        except Exception as e:
            logger.error(f"Error applying cooldown: {e}")
            return {
                'success': False,
                'error': f"Error applying cooldown: {str(e)}"
            }

    def _determine_position_side(self, trade: Dict[str, Any]) -> str:
        """Determine position side from trade data."""
        signal_type = trade.get('signal_type', '').upper()
        if signal_type in ['LONG', 'SHORT']:
            return signal_type

        # Fallback to parsed signal
        parsed_signal = trade.get('parsed_signal')
        if isinstance(parsed_signal, dict):
            position_type = parsed_signal.get('position_type', '').upper()
            if position_type in ['LONG', 'SHORT']:
                return position_type

        # Default to LONG if unclear
        return 'LONG'

    async def _get_mark_price(self, symbol: str) -> float:
        """Get current mark price for symbol."""
        try:
            if hasattr(self.exchange, 'get_mark_price'):
                price = await self.exchange.get_mark_price(symbol)
                return float(price) if price else 0.0
            else:
                # Fallback to current price
                prices = await self.exchange.get_current_prices([symbol])
                return float(prices.get(symbol, 0))
        except Exception as e:
            logger.warning(f"Could not get mark price for {symbol}: {e}")
            return 0.0

    async def _calculate_unrealized_pnl(self, size: float, entry_price: float,
                                      mark_price: float, side: str) -> float:
        """Calculate unrealized PnL for a position."""
        try:
            if size <= 0 or entry_price <= 0 or mark_price <= 0:
                return 0.0

            if side == 'LONG':
                return size * (mark_price - entry_price)
            else:  # SHORT
                return size * (entry_price - mark_price)
        except Exception as e:
            logger.warning(f"Error calculating unrealized PnL: {e}")
            return 0.0

    async def get_position_summary(self) -> Dict[str, Any]:
        """Get a summary of all active positions."""
        try:
            positions = await self.get_active_positions()

            summary = {
                'total_positions': len(positions),
                'total_unrealized_pnl': 0.0,
                'positions': []
            }

            for position in positions.values():
                summary['total_unrealized_pnl'] += position.unrealized_pnl
                summary['positions'].append({
                    'symbol': position.symbol,
                    'side': position.side,
                    'size': position.size,
                    'entry_price': position.entry_price,
                    'mark_price': position.mark_price,
                    'unrealized_pnl': position.unrealized_pnl,
                    'trade_count': len(position.trade_ids),
                    'primary_trade_id': position.primary_trade_id
                })

            return summary

        except Exception as e:
            logger.error(f"Error getting position summary: {e}")
            return {'error': str(e)}
