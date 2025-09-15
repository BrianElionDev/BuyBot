"""
Example usage of Binance WebSocket Manager.
Shows how to integrate with existing trading bot for real-time database updates.
"""

import asyncio
import sys
import logging
import os
from datetime import datetime, timezone
from config import settings
from typing import Dict, Any, Optional

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from src.websocket import WebSocketManager

logger = logging.getLogger(__name__)

class WebSocketIntegrationExample:
    """
    Example integration showing how to use WebSocket manager
    to keep database synchronized with real-time Binance data.
    """

    def __init__(self, db_manager, binance_exchange):
        """
        Initialize WebSocket integration.

        Args:
            db_manager: Database manager instance
            binance_exchange: Binance exchange instance
        """
        self.db_manager = db_manager
        self.binance_exchange = binance_exchange

        # Get credentials
        api_key = settings.BINANCE_API_KEY
        api_secret = settings.BINANCE_API_SECRET
        is_testnet = settings.BINANCE_TESTNET

        if not api_key or not api_secret:
            raise ValueError("BINANCE_API_KEY and BINANCE_API_SECRET must be set")

        # Initialize WebSocket manager
        self.ws_manager = WebSocketManager(
            api_key=api_key,
            api_secret=api_secret,
            is_testnet=is_testnet
        )

        # Register event handlers
        self._register_handlers()

    def _register_handlers(self):
        """Register event handlers for real-time database updates."""

        async def handle_execution_report(data):
            """Handle order execution reports - update trade status in database."""
            try:
                # Extract data from ORDER_TRADE_UPDATE event structure
                order_data = data.get('o', {})
                symbol = order_data.get('s')  # Symbol
                order_id = order_data.get('i')  # Order ID
                status = order_data.get('X')  # Order status
                executed_qty = float(order_data.get('z', 0))  # Cumulative filled quantity
                avg_price = float(order_data.get('ap', 0))  # Average price
                realized_pnl = float(order_data.get('Y', 0))  # Realized PnL

                logger.info(f"Order Update: {symbol} {order_id} - {status}")

                # Find trade in database by order ID
                trade = await self._find_trade_by_order_id(order_id)
                if not trade:
                    logger.warning(f"Trade not found for order ID: {order_id}")
                    return

                # Update trade based on order status
                updates: Dict[str, Any] = {
                    'updated_at': datetime.now(timezone.utc).isoformat(),
                    'binance_response': str(data)
                }

                if status == 'FILLED':
                    if executed_qty > 0:
                        updates.update({
                            'status': 'CLOSED',
                            'exit_price': avg_price,
                            'binance_exit_price': avg_price,
                            'pnl_usd': realized_pnl,
                            'position_size': executed_qty  # Update final position size
                        })
                        logger.info(f"Trade {trade['id']} FILLED at {avg_price} - PnL: {realized_pnl}")

                elif status == 'PARTIALLY_FILLED':
                    updates.update({
                        'status': 'PARTIALLY_CLOSED',
                        'exit_price': avg_price,
                        'binance_exit_price': avg_price,
                        'position_size': executed_qty  # Update current position size
                    })
                    logger.info(f"Trade {trade['id']} PARTIALLY_FILLED at {avg_price}")

                elif status in ['CANCELED', 'EXPIRED', 'REJECTED']:
                    updates.update({
                        'status': 'FAILED'
                    })
                    logger.warning(f"Trade {trade['id']} {status}")

                # Update database
                await self.db_manager.update_existing_trade(trade['id'], updates)

            except Exception as e:
                logger.error(f"Error handling execution report: {e}")

        async def handle_account_position(data):
            """Handle account position updates - track position changes."""
            try:
                logger.info("Account position update received")

                # Extract data from ACCOUNT_UPDATE event structure
                account_data = data.get('a', {})

                # Update position information in database
                # This could be used to track unrealized PnL
                for balance in account_data.get('B', []):
                    asset = balance.get('a')
                    free = float(balance.get('f', 0))
                    locked = float(balance.get('l', 0))

                    if asset == 'USDT' and (free > 0 or locked > 0):
                        logger.info(f"USDT Balance - Free: {free}, Locked: {locked}")

            except Exception as e:
                logger.error(f"Error handling account position: {e}")

        async def handle_ticker(data):
            """Handle market ticker updates - calculate unrealized PnL."""
            try:
                symbol = data.get('s')
                current_price = float(data.get('c', 0))

                if current_price > 0:
                    # Find open trades for this symbol
                    open_trades = await self._find_open_trades_by_symbol(symbol)

                    for trade in open_trades:
                        # Calculate unrealized PnL
                        entry_price = float(trade.get('entry_price', 0))
                        position_size = float(trade.get('position_size', 0))
                        position_type = trade.get('signal_type', 'LONG')

                        if entry_price > 0 and position_size > 0:
                            unrealized_pnl = self._calculate_unrealized_pnl(
                                entry_price, current_price, position_size, position_type
                            )

                            # Update unrealized PnL (don't update too frequently)
                            await self.db_manager.update_existing_trade(
                                trade['id'],
                                {'unrealized_pnl': unrealized_pnl}
                            )

            except Exception as e:
                logger.error(f"Error handling ticker: {e}")

        async def handle_connection(data):
            """Handle connection events."""
            stream_type = data.get('type', 'unknown')
            logger.info(f"WebSocket connected to {stream_type} stream")

        async def handle_disconnection(data):
            """Handle disconnection events."""
            stream_type = data.get('type', 'unknown')
            logger.warning(f"WebSocket disconnected from {stream_type} stream")

        async def handle_error(data):
            """Handle error events."""
            error_msg = data.get('error', 'Unknown error')
            logger.error(f"WebSocket error: {error_msg}")

        # Register handlers
        self.ws_manager.register_handler('executionReport', handle_execution_report)
        self.ws_manager.register_handler('outboundAccountPosition', handle_account_position)
        self.ws_manager.register_handler('ticker', handle_ticker)
        self.ws_manager.register_handler('connection', handle_connection)
        self.ws_manager.register_handler('disconnection', handle_disconnection)
        self.ws_manager.register_handler('error', handle_error)

    async def _find_trade_by_order_id(self, order_id: str):
        """Find trade in database by Binance order ID."""
        try:
            # This would be implemented based on your database schema
            # Example implementation:
            response = self.db_manager.supabase.from_("trades").select("*").eq("exchange_order_id", order_id).execute()
            if response.data:
                return response.data[0]
            return None
        except Exception as e:
            logger.error(f"Error finding trade by order ID: {e}")
            return None

    async def _find_open_trades_by_symbol(self, symbol: str):
        """Find open trades for a specific symbol."""
        try:
            # This would be implemented based on your database schema
            # Example implementation:
            response = self.db_manager.supabase.from_("trades").select("*").eq("status", "OPEN").eq("coin_symbol", symbol.replace('USDT', '')).execute()
            return response.data or []
        except Exception as e:
            logger.error(f"Error finding open trades: {e}")
            return []

    def _calculate_unrealized_pnl(self, entry_price: float, current_price: float, position_size: float, position_type: str) -> float:
        """Calculate unrealized PnL."""
        try:
            if position_type.upper() == 'LONG':
                return (current_price - entry_price) * position_size
            else:  # SHORT
                return (entry_price - current_price) * position_size
        except Exception as e:
            logger.error(f"Error calculating unrealized PnL: {e}")
            return 0.0

    async def start(self):
        """Start WebSocket manager."""
        logger.info("Starting WebSocket integration...")
        await self.ws_manager.start()
        logger.info("WebSocket integration started")

    async def stop(self):
        """Stop WebSocket manager."""
        logger.info("Stopping WebSocket integration...")
        await self.ws_manager.stop()
        logger.info("WebSocket integration stopped")

    def get_status(self):
        """Get WebSocket connection status."""
        return self.ws_manager.get_connection_status()

# Example usage in DiscordBot
async def integrate_websocket_with_discord_bot(discord_bot):
    """
    Example of how to integrate WebSocket manager with DiscordBot.

    Usage:
        # In DiscordBot.__init__()
        self.websocket_integration = WebSocketIntegrationExample(
            self.db_manager,
            self.binance_exchange
        )

        # In DiscordBot startup
        await self.websocket_integration.start()

        # In DiscordBot shutdown
        await self.websocket_integration.stop()
    """

    # Create integration instance
    integration = WebSocketIntegrationExample(
        discord_bot.db_manager,
        discord_bot.binance_exchange
    )

    # Start WebSocket manager
    await integration.start()

    # Keep running
    try:
        while True:
            await asyncio.sleep(1)

            # Check status periodically
            status = integration.get_status()
            if not status['is_connected']:
                logger.warning("WebSocket disconnected, attempting reconnection...")

    except KeyboardInterrupt:
        logger.info("Shutting down WebSocket integration...")
        await integration.stop()