"""
WebSocket Manager for KuCoin integration with DiscordBot.
Handles real-time database synchronization with KuCoin WebSocket events.
"""

import logging
from typing import Optional
from datetime import datetime, timezone

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src', 'websocket'))

from src.websocket.kucoin import KucoinWebSocketManager, KucoinSyncManager
from discord_bot.database import DatabaseManager

logger = logging.getLogger(__name__)

class DiscordBotKucoinWebSocketManager:
    """
    KuCoin WebSocket manager specifically designed for DiscordBot integration.
    Handles real-time database synchronization and provides status monitoring.
    """

    def __init__(self, bot, db_manager: DatabaseManager):
        """
        Initialize KuCoin WebSocket manager for DiscordBot.

        Args:
            bot: DiscordBot instance
            db_manager: Database manager instance
        """
        self.bot = bot
        self.db_manager = db_manager
        self.ws_manager: Optional[KucoinWebSocketManager] = None
        self.sync_manager: Optional[KucoinSyncManager] = None
        self.is_running = False
        self.last_sync_time = None
        self.sync_stats = {
            'orders_updated': 0,
            'order_changes': 0,
            'errors': 0
        }

        if hasattr(bot, 'kucoin_exchange') and bot.kucoin_exchange:
            self._initialize_websocket_manager()
        else:
            logger.warning("[KC-WS] KuCoin exchange not available, skipping websocket initialization")

    def _initialize_websocket_manager(self):
        """Initialize the KuCoin WebSocket manager."""
        try:
            api_key = self.bot.kucoin_exchange.api_key
            api_secret = self.bot.kucoin_exchange.api_secret
            api_passphrase = self.bot.kucoin_exchange.api_passphrase
            is_testnet = self.bot.kucoin_exchange.is_testnet

            self.sync_manager = KucoinSyncManager(self.db_manager)

            self.ws_manager = KucoinWebSocketManager(
                api_key=api_key,
                api_secret=api_secret,
                api_passphrase=api_passphrase,
                is_testnet=is_testnet,
                db_manager=self.db_manager
            )

            self._register_event_handlers()

            logger.info("[KC-WS] WebSocket manager initialized successfully")

        except Exception as e:
            logger.error(f"[KC-WS] Failed to initialize WebSocket manager: {e}")
            raise

    def _register_event_handlers(self):
        """Register event handlers for real-time updates."""

        async def handle_execution_report(event):
            """Handle order execution reports."""
            try:
                self.sync_stats['orders_updated'] += 1
                self.last_sync_time = datetime.now(timezone.utc)

                if hasattr(event, 'data') and event.data:
                    data = event.data
                else:
                    data = event

                order_data = data.get('data', {})
                order_id = order_data.get('orderId', 'Unknown')
                symbol = order_data.get('symbol', 'Unknown')
                match_price = float(order_data.get('matchPrice', 0))
                match_size = float(order_data.get('matchSize', 0))

                if match_size > 0:
                    logger.warning(f"[KC-WS] ORDER FILLED - {symbol} {order_id} at {match_price} - Size: {match_size}")

                if self.sync_manager:
                    await self.sync_manager.handle_execution_report(data)
                    logger.warning(f"[KC-WS] Database sync completed for order {order_id}")

            except Exception as e:
                logger.error(f"[KC-WS] Error in execution report handler: {e}")
                self.sync_stats['errors'] += 1

        async def handle_order_change(event):
            """Handle order lifecycle changes."""
            try:
                self.sync_stats['order_changes'] += 1
                self.last_sync_time = datetime.now(timezone.utc)

                if hasattr(event, 'data') and event.data:
                    data = event.data
                else:
                    data = event

                order_data = data.get('data', {})
                order_id = order_data.get('orderId', 'Unknown')
                symbol = order_data.get('symbol', 'Unknown')
                change_type = order_data.get('type', 'Unknown')
                status = order_data.get('status', 'Unknown')

                if change_type in ['filled', 'canceled']:
                    logger.warning(f"[KC-WS] Order {order_id} ({symbol}) - {change_type} ({status})")

                if self.sync_manager:
                    await self.sync_manager.handle_order_change(data)
                    logger.info(f"[KC-WS] Database sync completed for order change {order_id}")

            except Exception as e:
                logger.error(f"[KC-WS] Error in order change handler: {e}")
                self.sync_stats['errors'] += 1

        if self.ws_manager:
            self.ws_manager.register_handler('kucoin:execution', handle_execution_report)
            self.ws_manager.register_handler('kucoin:orderChange', handle_order_change)

    async def start(self):
        """Start the WebSocket manager."""
        try:
            if not self.ws_manager:
                logger.error("[KC-WS] WebSocket manager not initialized")
                return False

            logger.info("[KC-WS] Starting WebSocket manager for DiscordBot...")
            await self.ws_manager.start()
            self.is_running = True
            self.last_sync_time = datetime.now(timezone.utc)

            logger.info("[KC-WS] WebSocket manager started successfully")
            return True

        except Exception as e:
            logger.error(f"[KC-WS] Failed to start WebSocket manager: {e}")
            return False

    async def stop(self):
        """Stop the WebSocket manager."""
        try:
            if self.ws_manager:
                logger.info("[KC-WS] Stopping WebSocket manager...")
                await self.ws_manager.stop()
                self.is_running = False
                logger.info("[KC-WS] WebSocket manager stopped successfully")

        except Exception as e:
            logger.error(f"[KC-WS] Error stopping WebSocket manager: {e}")

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
            'order_changes': 0,
            'errors': 0
        }
        logger.info("[KC-WS] WebSocket sync statistics reset")

    async def health_check(self) -> bool:
        """Perform health check on WebSocket connection."""
        try:
            if not self.ws_manager:
                return False

            status = self.ws_manager.get_connection_status()

            if status.get('is_connected', False):
                logger.info("[KC-WS] Health check: OK")
                return True
            else:
                logger.warning("[KC-WS] Health check: FAILED - Not connected")
                return False

        except Exception as e:
            logger.error(f"[KC-WS] Health check error: {e}")
            return False
