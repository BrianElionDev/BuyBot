"""
Comprehensive Order Status Monitoring System

Monitors orders after creation to:
- Track order status changes
- Handle cancellations and expirations
- Detect fills and update positions
- Recreate dependent orders (TP/SL) when needed
"""

import logging
import asyncio
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone, timedelta
from supabase import Client

logger = logging.getLogger(__name__)


class OrderMonitor:
    """
    Comprehensive order status monitoring system.

    Monitors orders after creation to ensure they're properly tracked,
    handles cancellations, detects fills, and manages dependent orders.
    """

    def __init__(self, db_manager, exchange):
        """
        Initialize the order monitor.

        Args:
            db_manager: Database manager instance
            exchange: Exchange instance (Binance/KuCoin)
        """
        self.db_manager = db_manager
        self.exchange = exchange
        self.monitoring_interval = 60  # Check every 60 seconds
        self.max_monitoring_duration = 3600  # Monitor for up to 1 hour
        self.supabase = db_manager.supabase if hasattr(db_manager, 'supabase') else None

    async def monitor_order(self, trade_id: int, order_id: str, trading_pair: str,
                          max_duration: Optional[int] = None) -> Dict[str, Any]:
        """
        Monitor an order until it's filled, cancelled, or timeout.

        Args:
            trade_id: Trade ID in database
            order_id: Exchange order ID
            trading_pair: Trading pair symbol
            max_duration: Maximum monitoring duration in seconds (default: 1 hour)

        Returns:
            Dict with monitoring results
        """
        max_duration = max_duration or self.max_monitoring_duration
        start_time = datetime.now(timezone.utc)
        check_count = 0

        logger.info(f"Starting order monitoring for trade {trade_id}, order {order_id}")

        while True:
            try:
                elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()

                if elapsed > max_duration:
                    logger.warning(f"Order monitoring timeout for trade {trade_id} after {elapsed}s")
                    return {
                        'status': 'timeout',
                        'message': f'Monitoring timeout after {max_duration}s',
                        'checks_performed': check_count
                    }

                # Get order status from exchange
                order_status = await self.exchange.get_order_status(trading_pair, order_id)

                if not order_status:
                    logger.warning(f"Could not retrieve order status for {order_id}")
                    await asyncio.sleep(self.monitoring_interval)
                    check_count += 1
                    continue

                status = order_status.get('status', '').upper()
                check_count += 1

                logger.debug(f"Order {order_id} status check #{check_count}: {status}")

                # Handle different order statuses
                if status in ['FILLED', 'DONE']:
                    logger.info(f"✅ Order {order_id} filled for trade {trade_id}")
                    await self._handle_order_filled(trade_id, order_id, order_status)
                    return {
                        'status': 'filled',
                        'order_status': order_status,
                        'checks_performed': check_count,
                        'duration': elapsed
                    }

                elif status in ['CANCELED', 'CANCELLED', 'REJECTED', 'EXPIRED']:
                    logger.warning(f"⚠️ Order {order_id} {status.lower()} for trade {trade_id}")
                    await self._handle_order_cancelled(trade_id, order_id, order_status, status)
                    return {
                        'status': 'cancelled',
                        'order_status': order_status,
                        'cancellation_reason': status,
                        'checks_performed': check_count,
                        'duration': elapsed
                    }

                elif status in ['NEW', 'PARTIALLY_FILLED', 'PENDING']:
                    # Order still active, continue monitoring
                    logger.debug(f"Order {order_id} still {status.lower()}, continuing monitoring")
                    await asyncio.sleep(self.monitoring_interval)
                    continue

                else:
                    logger.warning(f"Unknown order status: {status} for order {order_id}")
                    await asyncio.sleep(self.monitoring_interval)
                    continue

            except Exception as e:
                logger.error(f"Error monitoring order {order_id}: {e}")
                await asyncio.sleep(self.monitoring_interval)
                check_count += 1

    async def _handle_order_filled(self, trade_id: int, order_id: str, order_status: Dict[str, Any]):
        """Handle order fill event."""
        try:
            # Update trade with fill information
            updates = {
                'order_status': 'FILLED',
                'status': 'OPEN',
                'updated_at': datetime.now(timezone.utc).isoformat()
            }

            # Extract fill data (convert to strings for database)
            if 'avgPrice' in order_status:
                updates['entry_price'] = f"{float(order_status['avgPrice']):.8f}"
            if 'executedQty' in order_status:
                updates['position_size'] = f"{float(order_status['executedQty']):.8f}"
            elif 'filledSize' in order_status:
                updates['position_size'] = f"{float(order_status['filledSize']):.8f}"

            await self.db_manager.update_existing_trade(trade_id, updates)
            logger.info(f"Updated trade {trade_id} with fill information")

        except Exception as e:
            logger.error(f"Error handling order fill for trade {trade_id}: {e}")

    async def _handle_order_cancelled(self, trade_id: int, order_id: str,
                                     order_status: Dict[str, Any], cancellation_reason: str):
        """Handle order cancellation event."""
        try:
            # Check if this is a main order or TP/SL order
            trade = await self.db_manager.trade_ops.get_trade_by_id(trade_id)
            if not trade:
                return

            is_main_order = trade.get('exchange_order_id') == order_id
            is_stop_loss = trade.get('stop_loss_order_id') == order_id

            updates = {
                'order_status': cancellation_reason,
                'updated_at': datetime.now(timezone.utc).isoformat()
            }

            # If main order cancelled, mark trade as failed
            if is_main_order:
                updates['status'] = 'FAILED'
                logger.warning(f"Main order {order_id} cancelled for trade {trade_id}")
            elif is_stop_loss:
                # Stop loss cancellation is handled by database_sync.py
                logger.info(f"Stop loss order {order_id} cancelled for trade {trade_id}")
                updates['stop_loss_order_id'] = None

            await self.db_manager.update_existing_trade(trade_id, updates)

        except Exception as e:
            logger.error(f"Error handling order cancellation for trade {trade_id}: {e}")

    async def monitor_pending_orders(self, max_age_minutes: int = 30) -> Dict[str, Any]:
        """
        Monitor all pending orders in the database.

        Args:
            max_age_minutes: Only monitor orders created within this time window

        Returns:
            Dict with monitoring statistics
        """
        try:
            cutoff_time = datetime.now(timezone.utc) - timedelta(minutes=max_age_minutes)
            cutoff_iso = cutoff_time.isoformat()

            # Get pending orders
            if not self.supabase:
                logger.error("Supabase client not available for order monitoring")
                return {'error': 'Supabase client not available'}

            response = self.supabase.from_("trades").select("*").in_(
                "status", ["PENDING", "OPEN"]
            ).gte("created_at", cutoff_iso).execute()

            pending_trades = response.data or []
            stats = {
                'total_checked': 0,
                'filled': 0,
                'cancelled': 0,
                'still_pending': 0,
                'errors': 0
            }

            logger.info(f"Monitoring {len(pending_trades)} pending orders")

            for trade in pending_trades:
                try:
                    trade_id = trade.get('id')
                    order_id = trade.get('exchange_order_id')
                    coin_symbol = trade.get('coin_symbol')
                    exchange_name = trade.get('exchange', '').lower()

                    if not order_id or not coin_symbol:
                        continue

                    # Get trading pair
                    if exchange_name == 'binance':
                        trading_pair = f"{coin_symbol.upper()}USDT"
                    elif exchange_name == 'kucoin':
                        from src.exchange.kucoin.kucoin_symbol_converter import symbol_converter
                        trading_pair = f"{coin_symbol.upper()}-USDT"
                        trading_pair = symbol_converter.convert_bot_to_kucoin_futures(trading_pair)
                    else:
                        continue

                    # Check order status
                    try:
                        order_status = await self.exchange.get_order_status(trading_pair, order_id)
                        stats['total_checked'] += 1

                        if not order_status:
                            continue

                        status = order_status.get('status', '').upper()

                        if status in ['FILLED', 'DONE']:
                            await self._handle_order_filled(trade_id, order_id, order_status)
                            stats['filled'] += 1
                        elif status in ['CANCELED', 'CANCELLED', 'REJECTED', 'EXPIRED']:
                            await self._handle_order_cancelled(trade_id, order_id, order_status, status)
                            stats['cancelled'] += 1
                        else:
                            stats['still_pending'] += 1
                    except Exception as order_error:
                        logger.warning(f"Error checking order status for {order_id}: {order_error}")
                        stats['errors'] += 1
                        continue

                except Exception as e:
                    logger.error(f"Error monitoring trade {trade.get('id')}: {e}")
                    stats['errors'] += 1

            logger.info(f"Order monitoring completed: {stats}")
            return stats

        except Exception as e:
            logger.error(f"Error in monitor_pending_orders: {e}")
            return {'error': str(e)}

