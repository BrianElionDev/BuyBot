"""
Main WebSocket manager for orchestrating connections, events, and handlers.
Coordinates connection management, event dispatching, and handler execution.
"""

import asyncio
import json
import logging
import time
from typing import Dict, List, Optional, Callable, Any, Union
from datetime import datetime, timedelta
import aiohttp
import websockets
from websockets.exceptions import ConnectionClosed

from .websocket_config import WebSocketConfig
from .connection_manager import ConnectionManager
from .event_dispatcher import EventDispatcher, WebSocketEvent

logger = logging.getLogger(__name__)

class WebSocketManager:
    """
    Main WebSocket manager for Binance futures API.

    Features:
    - Automatic reconnection with exponential backoff
    - Rate limiting compliance
    - Listen key management
    - Ping/pong heartbeat handling
    - Error handling and logging
    - User data and market data streams
    """

    def __init__(self, api_key: str, api_secret: str, is_testnet: bool = False, db_manager=None):
        """
        Initialize WebSocket manager.

        Args:
            api_key: Binance API key
            api_secret: Binance API secret
            is_testnet: Whether to use testnet
            db_manager: Database manager for real-time sync (optional)
        """
        self.api_key = api_key
        self.api_secret = api_secret
        self.config = WebSocketConfig(is_testnet)
        self.db_manager = db_manager

        # Initialize core components
        self.connection_manager = ConnectionManager(self.config)
        self.event_dispatcher = EventDispatcher()

        # Connection state
        self.listen_key: Optional[str] = None
        self.listen_key_expiry: Optional[datetime] = None

        # Connection management
        self.is_connected = False
        self.reconnect_attempts = 0
        self.last_ping_time = 0
        self.last_pong_time = 0
        self.consecutive_errors = 0
        self.rate_limit_counter = {'messages': 0, 'ping_pong': 0}
        self.rate_limit_reset_time = time.time()

        # Tasks
        self.tasks: List[asyncio.Task] = []
        self.running = False

        logger.info(f"WebSocket Manager initialized for {'testnet' if is_testnet else 'mainnet'}")

    async def start(self):
        """Start WebSocket connections and background tasks."""
        if self.running:
            logger.warning("WebSocket manager is already running")
            return

        self.running = True
        self.connection_manager.start()
        self.event_dispatcher.start()

        try:
            # Start background tasks
            self.tasks = [
                asyncio.create_task(self._manage_listen_key()),
                asyncio.create_task(self._heartbeat_monitor()),
                asyncio.create_task(self._rate_limit_monitor())
            ]

            # Establish connections
            await self._establish_connections()

            logger.info("WebSocket manager started successfully")

        except Exception as e:
            logger.error(f"Failed to start WebSocket manager: {e}")
            await self.stop()
            raise

    async def stop(self):
        """Stop WebSocket connections and cleanup."""
        if not self.running:
            return

        self.running = False
        logger.info("Stopping WebSocket manager...")

        # Stop core components
        self.connection_manager.stop()
        self.event_dispatcher.stop()

        # Cancel background tasks
        for task in self.tasks:
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        # Close all connections
        await self.connection_manager.close_all_connections()

        # Cleanup listen key
        if self.listen_key:
            await self._delete_listen_key()

        self.is_connected = False
        logger.info("WebSocket manager stopped")

    async def _establish_connections(self):
        """Establish WebSocket connections."""
        try:
            # Get listen key for user data stream
            await self._get_listen_key()

            # Create user data connection
            user_data_url = f"{self.config.user_data_stream_url}/{self.listen_key}"
            success = await self.connection_manager.create_connection(
                "user_data",
                user_data_url,
                self._handle_user_data_message,
                "user_data"
            )

            if success:
                self.is_connected = True
                logger.info("User data connection established")
            else:
                raise Exception("Failed to establish user data connection")

        except Exception as e:
            logger.error(f"Failed to establish connections: {e}")
            raise

    async def _handle_user_data_message(self, message: str, connection_id: str):
        """
        Handle messages from user data stream.

        Args:
            message: Raw message from WebSocket
            connection_id: Connection identifier
        """
        try:
            # Update rate limit counter
            self.rate_limit_counter['messages'] += 1

            # Dispatch message to event dispatcher
            await self.event_dispatcher.dispatch_raw_message(message, connection_id)

        except Exception as e:
            logger.error(f"Error handling user data message: {e}")
            self.consecutive_errors += 1

    async def _get_listen_key(self):
        """Get a new listen key from Binance."""
        try:
            async with aiohttp.ClientSession() as session:
                headers = {'X-MBX-APIKEY': self.api_key}
                async with session.post(
                    self.config.get_listen_key_url(),
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        self.listen_key = data.get('listenKey')
                        self.listen_key_expiry = datetime.now() + timedelta(minutes=60)
                        logger.info("Obtained new listen key")
                    else:
                        raise Exception(f"Failed to get listen key: {response.status}")

        except Exception as e:
            logger.error(f"Error getting listen key: {e}")
            raise

    async def _refresh_listen_key(self):
        """Refresh the current listen key."""
        if not self.listen_key:
            await self._get_listen_key()
            return

        try:
            async with aiohttp.ClientSession() as session:
                headers = {'X-MBX-APIKEY': self.api_key}
                async with session.put(
                    self.config.get_refresh_listen_key_url(),
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status == 200:
                        self.listen_key_expiry = datetime.now() + timedelta(minutes=60)
                        logger.debug("Refreshed listen key")
                    else:
                        logger.warning(f"Failed to refresh listen key: {response.status}")
                        await self._get_listen_key()

        except Exception as e:
            logger.error(f"Error refreshing listen key: {e}")
            await self._get_listen_key()

    async def _delete_listen_key(self):
        """Delete the current listen key."""
        if not self.listen_key:
            return

        try:
            async with aiohttp.ClientSession() as session:
                headers = {'X-MBX-APIKEY': self.api_key}
                async with session.delete(
                    self.config.get_delete_listen_key_url(),
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status == 200:
                        logger.info("Deleted listen key")
                    else:
                        logger.warning(f"Failed to delete listen key: {response.status}")

        except Exception as e:
            logger.error(f"Error deleting listen key: {e}")

    async def _manage_listen_key(self):
        """Background task to manage listen key lifecycle."""
        while self.running:
            try:
                if self.listen_key_expiry:
                    time_until_expiry = (self.listen_key_expiry - datetime.now()).total_seconds()

                    if time_until_expiry <= 300:  # Refresh 5 minutes before expiry
                        await self._refresh_listen_key()

                await asyncio.sleep(60)  # Check every minute

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in listen key management: {e}")
                await asyncio.sleep(60)

    async def _heartbeat_monitor(self):
        """Background task to monitor connection health."""
        while self.running:
            try:
                # Check connection health
                if not self.connection_manager.is_connected("user_data"):
                    logger.warning("User data connection lost, attempting reconnection")
                    await self._establish_connections()

                await asyncio.sleep(30)  # Check every 30 seconds

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in heartbeat monitor: {e}")
                await asyncio.sleep(30)

    async def _rate_limit_monitor(self):
        """Background task to monitor rate limits."""
        while self.running:
            try:
                current_time = time.time()

                # Reset counters every second
                if current_time - self.rate_limit_reset_time >= 1:
                    self.rate_limit_counter = {'messages': 0, 'ping_pong': 0}
                    self.rate_limit_reset_time = current_time

                # Check rate limits
                if not self.config.validate_rate_limits(
                    self.rate_limit_counter['messages'],
                    self.rate_limit_counter['ping_pong']
                ):
                    logger.warning("Rate limit exceeded, throttling messages")

                await asyncio.sleep(1)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in rate limit monitor: {e}")
                await asyncio.sleep(1)

    def register_handler(self, event_type: str, handler: Callable):
        """
        Register a handler for a specific event type.

        Args:
            event_type: Type of event to handle
            handler: Callback function to handle the event
        """
        self.event_dispatcher.register_handler(event_type, handler)

    def unregister_handler(self, event_type: str, handler: Callable):
        """
        Unregister a handler for a specific event type.

        Args:
            event_type: Type of event
            handler: Handler to unregister
        """
        self.event_dispatcher.unregister_handler(event_type, handler)

    def get_connection_status(self) -> Dict[str, Any]:
        """
        Get the current connection status.

        Returns:
            Dict: Connection status information
        """
        return {
            'is_connected': self.is_connected,
            'running': self.running,
            'listen_key': self.listen_key is not None,
            'listen_key_expiry': self.listen_key_expiry.isoformat() if self.listen_key_expiry else None,
            'connection_states': self.connection_manager.get_all_connection_states(),
            'registered_handlers': self.event_dispatcher.get_registered_handlers(),
            'rate_limit_counter': self.rate_limit_counter.copy(),
            'consecutive_errors': self.consecutive_errors
        }

    async def send_message(self, connection_id: str, message: str) -> bool:
        """
        Send a message through a specific connection.

        Args:
            connection_id: Connection identifier
            message: Message to send

        Returns:
            bool: True if message was sent successfully
        """
        return await self.connection_manager.send_message(connection_id, message)
