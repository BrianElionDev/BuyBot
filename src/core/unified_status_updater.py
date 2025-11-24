"""
Unified Status Update System

This module provides a single entry point for all trade status updates,
ensuring consistency between order_status and position status using StatusManager.
"""

import logging
from typing import Optional, Dict, Any, Tuple, List
from datetime import datetime, timezone
from supabase import Client

from src.core.status_manager import StatusManager

logger = logging.getLogger(__name__)


def validate_trade_data_before_update(trade: Dict[str, Any], update_data: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """
    Validate trade data before update to ensure required fields are present.

    Args:
        trade: Current trade data
        update_data: Proposed update data

    Returns:
        Tuple of (is_valid: bool, warnings: List[str])
    """
    warnings = []

    # Check if status is being updated to CLOSED
    new_status = update_data.get('status') or trade.get('status')
    if str(new_status).upper() == 'CLOSED':
        # CLOSED trades should have entry_price
        entry_price = trade.get('entry_price') or update_data.get('entry_price')
        if not entry_price or float(entry_price) == 0:
            warnings.append("CLOSED trade missing entry_price")

        # If PNL exists, exit_price should also exist
        pnl_usd = update_data.get('pnl_usd') or trade.get('pnl_usd')
        exit_price = update_data.get('exit_price') or trade.get('exit_price')

        if pnl_usd and float(pnl_usd) != 0:
            if not exit_price or float(exit_price) == 0:
                warnings.append("Trade has PNL but missing exit_price")

    # Validate status consistency if both status and order_status are being updated
    if 'status' in update_data or 'order_status' in update_data:
        order_status = str(update_data.get('order_status') or trade.get('order_status', 'NEW')).upper().strip()
        position_status = str(update_data.get('status') or trade.get('status', 'PENDING')).upper().strip()

        is_consistent = StatusManager.validate_status_consistency(order_status, position_status)
        if not is_consistent:
            warnings.append(
                f"Status inconsistency detected: order_status={order_status}, "
                f"position_status={position_status}"
            )

    return len(warnings) == 0, warnings


async def update_trade_status_safely(
    supabase: Client,
    trade_id: int,
    trade: Dict[str, Any],
    exchange_status: Optional[str] = None,
    position_size: Optional[float] = None,
    force_closed: bool = False,
    bot: Optional[Any] = None
) -> Tuple[bool, Dict[str, Any]]:
    """
    Unified status update function that ensures consistency between order_status and position status.

    This function:
    1. Queries exchange for order status if missing and force_closed is True
    2. Uses StatusManager to map exchange status to internal statuses
    3. Validates consistency before updating
    4. Validates required fields are present
    5. Updates both status and order_status atomically

    Args:
        supabase: Supabase client
        trade_id: Trade ID to update
        trade: Current trade data from database
        exchange_status: Exchange order status (NEW, FILLED, etc.) - optional
        position_size: Current position size - optional, will be extracted from trade if not provided
        force_closed: If True, will query exchange for order status before closing
        bot: DiscordBot instance (required if force_closed is True)

    Returns:
        Tuple of (success: bool, update_data: dict)
    """
    try:
        current_time = datetime.now(timezone.utc).isoformat()
        update_data: Dict[str, Any] = {
            'updated_at': current_time
        }

        # Get current statuses
        current_order_status = str(trade.get('order_status', 'NEW')).upper().strip()
        current_position_status = str(trade.get('status', 'PENDING')).upper().strip()

        # Get position size from trade if not provided
        if position_size is None:
            pos_size_str = trade.get('position_size')
            if pos_size_str:
                try:
                    position_size = float(pos_size_str)
                except (ValueError, TypeError):
                    position_size = 0.0
            else:
                position_size = 0.0

        # If force_closed is True and we don't have exchange_status, try to query it
        if force_closed and not exchange_status:
            exchange_status = await _query_exchange_order_status(trade, bot)
            if not exchange_status:
                # If we can't get exchange status, use current order_status or default to FILLED for closed positions
                if current_order_status in ['FILLED', 'PARTIALLY_FILLED']:
                    exchange_status = current_order_status
                else:
                    exchange_status = 'FILLED'  # Assume filled if position is closed

        # If we have exchange_status, use StatusManager to map it
        if exchange_status:
            exchange_status = str(exchange_status).upper().strip()
            mapped_order_status, mapped_position_status = StatusManager.map_exchange_to_internal(
                exchange_status, position_size
            )

            # If force_closed, override position status to CLOSED
            if force_closed:
                mapped_position_status = 'CLOSED'
                update_data['is_active'] = False  # Always set is_active to false when closing

            # Validate consistency
            is_consistent = StatusManager.validate_status_consistency(
                mapped_order_status, mapped_position_status
            )

            if not is_consistent:
                # Try to fix inconsistency
                fixed_order_status, fixed_position_status = StatusManager.fix_inconsistent_status(
                    mapped_order_status, mapped_position_status
                )
                logger.warning(
                    f"Status inconsistency detected for trade {trade_id}: "
                    f"order_status={mapped_order_status}, position_status={mapped_position_status}. "
                    f"Fixed to: order_status={fixed_order_status}, position_status={fixed_position_status}"
                )
                mapped_order_status = fixed_order_status
                mapped_position_status = fixed_position_status

            update_data['order_status'] = mapped_order_status
            update_data['status'] = mapped_position_status
        else:
            # No exchange_status provided, but we need to update status
            # If force_closed, set to CLOSED with appropriate order_status
            if force_closed:
                # If position is closed, order should be FILLED
                update_data['order_status'] = 'FILLED'
                update_data['status'] = 'CLOSED'
                update_data['is_active'] = False  # Always set is_active to false when closing
            else:
                # Validate current statuses and fix if needed
                is_consistent = StatusManager.validate_status_consistency(
                    current_order_status, current_position_status
                )

                if not is_consistent:
                    fixed_order_status, fixed_position_status = StatusManager.fix_inconsistent_status(
                        current_order_status, current_position_status
                    )
                    logger.warning(
                        f"Status inconsistency detected for trade {trade_id}: "
                        f"order_status={current_order_status}, position_status={current_position_status}. "
                        f"Fixed to: order_status={fixed_order_status}, position_status={fixed_position_status}"
                    )
                    update_data['order_status'] = fixed_order_status
                    update_data['status'] = fixed_position_status

        # Validate required fields before returning
        is_valid, warnings = validate_trade_data_before_update(trade, update_data)
        if warnings:
            for warning in warnings:
                logger.warning(f"Trade {trade_id} validation warning: {warning}")

        return True, update_data

    except Exception as e:
        logger.error(f"Error in update_trade_status_safely for trade {trade_id}: {e}")
        return False, {}


async def _query_exchange_order_status(trade: Dict[str, Any], bot: Optional[Any]) -> Optional[str]:
    """
    Query exchange for order status if order_id is available.

    Args:
        trade: Trade data from database
        bot: DiscordBot instance with exchange connections

    Returns:
        Exchange order status string or None if unavailable
    """
    if not bot:
        return None

    try:
        exchange_name = str(trade.get('exchange', '')).lower()
        order_id = trade.get('exchange_order_id') or trade.get('kucoin_order_id')

        if not order_id:
            return None

        symbol = trade.get('coin_symbol', '')
        if not symbol:
            return None

        if exchange_name == 'binance' and hasattr(bot, 'binance_exchange') and bot.binance_exchange:
            try:
                symbol_pair = f"{symbol}USDT"
                order_info = await bot.binance_exchange.get_order_status(symbol_pair, str(order_id))
                if order_info and isinstance(order_info, dict):
                    return order_info.get('status', '').upper()
            except Exception as e:
                logger.warning(f"Could not query Binance order status for trade {trade.get('id')}: {e}")

        elif exchange_name == 'kucoin' and hasattr(bot, 'kucoin_exchange') and bot.kucoin_exchange:
            try:
                from src.exchange.kucoin.kucoin_symbol_converter import KucoinSymbolConverter
                symbol_converter = KucoinSymbolConverter()
                kucoin_symbol = symbol_converter.convert_bot_to_kucoin_futures(f"{symbol}-USDT")
                order_info = await bot.kucoin_exchange.get_order_status(kucoin_symbol, str(order_id))
                if order_info and isinstance(order_info, dict):
                    status = order_info.get('status', '')
                    if status:
                        return str(status).upper()
            except Exception as e:
                logger.warning(f"Could not query KuCoin order status for trade {trade.get('id')}: {e}")

    except Exception as e:
        logger.error(f"Error querying exchange order status: {e}")

    return None

