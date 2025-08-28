"""
WebSocket Manager for DiscordBot integration.
Handles real-time database synchronization with Binance WebSocket events.
"""

import logging
from typing import Optional
from datetime import datetime, timezone

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src', 'websocket'))

from src.websocket.binance_websocket_manager import BinanceWebSocketManager
from src.websocket.database_sync_handler import DatabaseSyncHandler
from discord_bot.database import DatabaseManager

logger = logging.getLogger(__name__)

class DiscordBotWebSocketManager:
    """
    WebSocket manager specifically designed for DiscordBot integration.
    Handles real-time database synchronization and provides status monitoring.
    """

    def __init__(self, bot, db_manager: DatabaseManager):
        """
        Initialize WebSocket manager for DiscordBot.

        Args:
            bot: DiscordBot instance
            db_manager: Database manager instance
        """
        self.bot = bot
        self.db_manager = db_manager
        self.ws_manager: Optional[BinanceWebSocketManager] = None
        self.db_sync_handler: Optional[DatabaseSyncHandler] = None
        self.is_running = False
        self.last_sync_time = None
        self.sync_stats = {
            'orders_updated': 0,
            'positions_updated': 0,
            'pnl_updates': 0,
            'errors': 0
        }

        # Initialize WebSocket manager with database sync
        self._initialize_websocket_manager()

    def _initialize_websocket_manager(self):
        """Initialize the Binance WebSocket manager."""
        try:
            # Get credentials from bot
            api_key = self.bot.binance_exchange.api_key
            api_secret = self.bot.binance_exchange.api_secret
            is_testnet = self.bot.binance_exchange.is_testnet

            # Create database sync handler
            self.db_sync_handler = DatabaseSyncHandler(self.db_manager)

            # Create WebSocket manager with database sync
            self.ws_manager = BinanceWebSocketManager(
                api_key=api_key,
                api_secret=api_secret,
                is_testnet=is_testnet,
                db_manager=self.db_manager
            )

            # Register event handlers
            self._register_event_handlers()

            logger.info("WebSocket manager initialized successfully")

        except Exception as e:
            logger.error(f"Failed to initialize WebSocket manager: {e}")
            raise

    def _register_event_handlers(self):
        """Register event handlers for real-time updates."""

        async def handle_execution_report(data):
            """Handle order execution reports."""
            try:
                self.sync_stats['orders_updated'] += 1
                self.last_sync_time = datetime.now(timezone.utc)

                # Debug: Log the full data structure
                logger.info(f"DEBUG: DiscordBotWebSocketManager received data: {data}")

                # Extract data for logging
                order_data = data.get('o', {})
                logger.info(f"DEBUG: order_data extracted: {order_data}")

                order_id = order_data.get('i', 'Unknown')
                symbol = order_data.get('s', 'Unknown')
                status = order_data.get('X', 'Unknown')
                executed_qty = float(order_data.get('z', 0))
                avg_price = float(order_data.get('ap', 0))
                realized_pnl = float(order_data.get('Y', 0))

                logger.info(f"DEBUG: Extracted order_id: {order_id} (type: {type(order_id)})")
                logger.info(f"WebSocket: Order {order_id} ({symbol}) - {status} - Price: {avg_price}")

                # Log important events
                if status == 'FILLED':
                    logger.info(f"WebSocket: ORDER FILLED - {symbol} at {avg_price} - PnL: {realized_pnl}")

                # CRITICAL: Call database sync handler to update database
                if self.ws_manager and self.ws_manager.db_sync_handler:
                    await self.ws_manager.db_sync_handler.handle_execution_report(data)
                    logger.info(f"Database sync called for order {order_id}")

            except Exception as e:
                logger.error(f"Error in execution report handler: {e}")
                self.sync_stats['errors'] += 1

        async def handle_account_position(data):
            """Handle account position updates."""
            try:
                self.sync_stats['positions_updated'] += 1
                self.last_sync_time = datetime.now(timezone.utc)

                logger.info("WebSocket: Account position update received")

                # Log balance changes
                for balance in data.get('B', []):
                    asset = balance.get('a')
                    free = balance.get('f')
                    locked = balance.get('l')
                    if float(free) > 0 or float(locked) > 0:
                        logger.info(f"WebSocket: Balance - {asset}: Free={free}, Locked={locked}")

                # CRITICAL: Call database sync handler to update database
                if self.ws_manager and self.ws_manager.db_sync_handler:
                    await self.ws_manager.db_sync_handler.handle_account_position(data)
                    logger.info("Database sync called for account position update")

            except Exception as e:
                logger.error(f"Error in account position handler: {e}")
                self.sync_stats['errors'] += 1

        async def handle_ticker(data):
            """Handle market ticker updates."""
            try:
                self.sync_stats['pnl_updates'] += 1

                symbol = data.get('s', 'Unknown')
                price = data.get('c', 'Unknown')

                # Log every 100th ticker to avoid spam
                if self.sync_stats['pnl_updates'] % 100 == 0:
                    logger.info(f"WebSocket: Ticker update #{self.sync_stats['pnl_updates']} - {symbol}: {price}")

                # CRITICAL: Call database sync handler to update database
                if self.ws_manager and self.ws_manager.db_sync_handler:
                    await self.ws_manager.db_sync_handler.handle_ticker(data)

            except Exception as e:
                logger.error(f"Error in ticker handler: {e}")
                self.sync_stats['errors'] += 1

        async def handle_connection(data):
            """Handle connection events."""
            stream_type = data.get('type', 'unknown')
            logger.info(f"WebSocket: Connected to {stream_type} stream")

        async def handle_disconnection(data):
            """Handle disconnection events."""
            stream_type = data.get('type', 'unknown')
            logger.warning(f"WebSocket: Disconnected from {stream_type} stream")

        async def handle_error(data):
            """Handle error events."""
            error_msg = data.get('error', 'Unknown error')
            logger.error(f"WebSocket Error: {error_msg}")
            self.sync_stats['errors'] += 1

        # Register handlers
        if self.ws_manager:
            self.ws_manager.add_event_handler('ORDER_TRADE_UPDATE', handle_execution_report)
            self.ws_manager.add_event_handler('ACCOUNT_UPDATE', handle_account_position)
            self.ws_manager.add_event_handler('ticker', handle_ticker)
            self.ws_manager.add_event_handler('connection', handle_connection)
            self.ws_manager.add_event_handler('disconnection', handle_disconnection)
            self.ws_manager.add_event_handler('error', handle_error)

    async def start(self):
        """Start the WebSocket manager."""
        try:
            if not self.ws_manager:
                logger.error("WebSocket manager not initialized")
                return False

            logger.info("Starting WebSocket manager for DiscordBot...")
            await self.ws_manager.start()
            self.is_running = True
            self.last_sync_time = datetime.now(timezone.utc)

            logger.info("WebSocket manager started successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to start WebSocket manager: {e}")
            return False

    async def stop(self):
        """Stop the WebSocket manager."""
        try:
            if self.ws_manager:
                logger.info("Stopping WebSocket manager...")
                await self.ws_manager.stop()
                self.is_running = False
                logger.info("WebSocket manager stopped successfully")

        except Exception as e:
            logger.error(f"Error stopping WebSocket manager: {e}")

    def get_status(self) -> dict:
        """Get WebSocket manager status."""
        if not self.ws_manager:
            return {
                'running': False,
                'initialized': False,
                'error': 'WebSocket manager not initialized'
            }

        ws_status = self.ws_manager.get_connection_status()

        return {
            'running': self.is_running,
            'initialized': True,
            'last_sync_time': self.last_sync_time.isoformat() if self.last_sync_time else None,
            'sync_stats': self.sync_stats.copy(),
            'websocket_status': ws_status
        }

    def reset_stats(self):
        """Reset sync statistics."""
        self.sync_stats = {
            'orders_updated': 0,
            'positions_updated': 0,
            'pnl_updates': 0,
            'errors': 0
        }
        logger.info("WebSocket sync statistics reset")

    async def health_check(self) -> bool:
        """Perform health check on WebSocket connection."""
        try:
            if not self.ws_manager:
                return False

            status = self.ws_manager.get_connection_status()

            # Check if both streams are connected
            user_data_connected = status.get('user_data_connected', False)
            market_data_connected = status.get('market_data_connected', False)

            if user_data_connected and market_data_connected:
                logger.debug("WebSocket health check: OK")
                return True
            else:
                logger.warning(f"WebSocket health check: FAILED - User data: {user_data_connected}, Market data: {market_data_connected}")
                return False

        except Exception as e:
            logger.error(f"WebSocket health check error: {e}")
            return False
