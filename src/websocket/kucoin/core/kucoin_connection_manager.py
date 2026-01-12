"""
WebSocket connection manager for KuCoin futures API.
Manages token-based connection lifecycle, ping/pong, and reconnection.
"""

import asyncio
import logging
import time
import uuid
import json
from typing import Optional, Dict, Any, Callable
from datetime import datetime
import websockets
from websockets.exceptions import ConnectionClosed

from .kucoin_websocket_config import KucoinWebSocketConfig

logger = logging.getLogger(__name__)

class KucoinConnectionManager:
    """
    Manages KuCoin WebSocket connections with token-based authentication.
    """

    def __init__(self, config: KucoinWebSocketConfig):
        """
        Initialize connection manager.

        Args:
            config: KuCoin WebSocket configuration
        """
        self.config = config
        self.connections: Dict[str, Any] = {}
        self.connection_states: Dict[str, Dict[str, Any]] = {}
        self.reconnect_tasks: Dict[str, asyncio.Task] = {}
        self.running = False
        self.ping_tasks: Dict[str, asyncio.Task] = {}

    async def create_connection(self, connection_id: str, endpoint: str, token: str,
                              message_handler: Callable, ping_interval: int = 18) -> bool:
        """
        Create a new WebSocket connection with token authentication.

        Args:
            connection_id: Unique identifier for the connection
            endpoint: WebSocket endpoint URL
            token: Connection token
            message_handler: Callback function for handling messages
            ping_interval: Ping interval in seconds (from token response)

        Returns:
            bool: True if connection was established successfully
        """
        try:
            connect_id = str(uuid.uuid4())
            url = f"{endpoint}?token={token}&connectId={connect_id}"

            self.connection_states[connection_id] = {
                'url': url,
                'endpoint': endpoint,
                'token': token,
                'connect_id': connect_id,
                'ping_interval': ping_interval,
                'connected': False,
                'last_ping': 0,
                'last_pong': 0,
                'reconnect_attempts': 0,
                'created_at': datetime.now(),
                'message_handler': message_handler
            }

            websocket = await websockets.connect(url)
            self.connections[connection_id] = websocket
            self.connection_states[connection_id]['connected'] = True
            self.connection_states[connection_id]['reconnect_attempts'] = 0

            asyncio.create_task(self._handle_messages(connection_id, websocket, message_handler))

            ping_task = asyncio.create_task(self._ping_loop(connection_id, ping_interval))
            self.ping_tasks[connection_id] = ping_task

            logger.warning(f"[KC-WS] Connection established: {connection_id}")
            return True

        except Exception as e:
            logger.error(f"[KC-WS] Failed to create connection {connection_id}: {e}")
            return False

    async def _ping_loop(self, connection_id: str, ping_interval: int):
        """
        Send periodic ping messages to keep connection alive.

        Args:
            connection_id: Connection identifier
            ping_interval: Ping interval in seconds
        """
        try:
            while self.running and connection_id in self.connections:
                await asyncio.sleep(ping_interval)

                if not self.is_connected(connection_id):
                    break

                ping_message = json.dumps({
                    "id": str(int(time.time() * 1000)),
                    "type": "ping"
                })

                if await self.send_message(connection_id, ping_message):
                    self.connection_states[connection_id]['last_ping'] = time.time()
                    logger.debug(f"[KC-WS] Sent ping to {connection_id}")

        except asyncio.CancelledError:
            logger.info(f"[KC-WS] Ping loop cancelled for {connection_id}")
        except Exception as e:
            logger.error(f"[KC-WS] Error in ping loop for {connection_id}: {e}")

    async def close_connection(self, connection_id: str) -> bool:
        """
        Close a WebSocket connection.

        Args:
            connection_id: Connection identifier

        Returns:
            bool: True if connection was closed successfully
        """
        try:
            if connection_id in self.ping_tasks:
                self.ping_tasks[connection_id].cancel()
                try:
                    await self.ping_tasks[connection_id]
                except asyncio.CancelledError:
                    pass
                del self.ping_tasks[connection_id]

            if connection_id in self.connections:
                websocket = self.connections[connection_id]
                await websocket.close()
                del self.connections[connection_id]

                if connection_id in self.connection_states:
                    self.connection_states[connection_id]['connected'] = False

                if connection_id in self.reconnect_tasks:
                    self.reconnect_tasks[connection_id].cancel()
                    del self.reconnect_tasks[connection_id]

                logger.info(f"[KC-WS] Closed connection: {connection_id}")
                return True
            return False

        except Exception as e:
            logger.error(f"[KC-WS] Error closing connection {connection_id}: {e}")
            return False

    async def close_all_connections(self):
        """Close all active WebSocket connections."""
        connection_ids = list(self.connections.keys())
        for connection_id in connection_ids:
            await self.close_connection(connection_id)

    async def _handle_messages(self, connection_id: str, websocket, message_handler: Callable):
        """
        Handle incoming messages from WebSocket connection.

        Args:
            connection_id: Connection identifier
            websocket: WebSocket connection
            message_handler: Message handling callback
        """
        try:
            async for message in websocket:
                try:
                    if isinstance(message, str):
                        data = json.loads(message)
                        if data.get('type') == 'pong':
                            self.connection_states[connection_id]['last_pong'] = time.time()
                            logger.debug(f"[KC-WS] Received pong from {connection_id}")
                            continue

                    await message_handler(message, connection_id)

                except json.JSONDecodeError as e:
                    logger.error(f"[KC-WS] Failed to parse message from {connection_id}: {e}")
                except Exception as e:
                    logger.error(f"[KC-WS] Error handling message from {connection_id}: {e}")

        except ConnectionClosed:
            logger.warning(f"[KC-WS] Connection closed for {connection_id}")
            await self._handle_connection_closed(connection_id)
        except Exception as e:
            logger.error(f"[KC-WS] Error in message handling for {connection_id}: {e}")
            await self._handle_connection_closed(connection_id)

    async def _handle_connection_closed(self, connection_id: str):
        """
        Handle connection closure and initiate reconnection if needed.

        Args:
            connection_id: Connection identifier
        """
        if connection_id in self.connection_states:
            self.connection_states[connection_id]['connected'] = False

            if connection_id not in self.reconnect_tasks or self.reconnect_tasks[connection_id].done():
                self.reconnect_tasks[connection_id] = asyncio.create_task(
                    self._reconnect_connection(connection_id)
                )

    async def _reconnect_connection(self, connection_id: str):
        """
        Attempt to reconnect a closed connection.
        Note: Reconnection requires a new token, so this should be handled by the manager.

        Args:
            connection_id: Connection identifier
        """
        logger.warning(f"[KC-WS] Reconnection for {connection_id} requires new token - handled by manager")

    def is_connected(self, connection_id: str) -> bool:
        """
        Check if a connection is currently active.

        Args:
            connection_id: Connection identifier

        Returns:
            bool: True if connection is active
        """
        return (connection_id in self.connections and
                connection_id in self.connection_states and
                self.connection_states[connection_id]['connected'])

    def get_connection_state(self, connection_id: str) -> Optional[Dict[str, Any]]:
        """
        Get the state of a connection.

        Args:
            connection_id: Connection identifier

        Returns:
            Optional[Dict]: Connection state or None if not found
        """
        return self.connection_states.get(connection_id)

    def get_all_connection_states(self) -> Dict[str, Dict[str, Any]]:
        """
        Get states of all connections.

        Returns:
            Dict: All connection states
        """
        return self.connection_states.copy()

    async def send_message(self, connection_id: str, message: str) -> bool:
        """
        Send a message through a specific connection.

        Args:
            connection_id: Connection identifier
            message: Message to send (JSON string)

        Returns:
            bool: True if message was sent successfully
        """
        try:
            if self.is_connected(connection_id):
                websocket = self.connections[connection_id]
                await websocket.send(message)
                return True
            else:
                logger.warning(f"[KC-WS] Cannot send message to disconnected connection: {connection_id}")
                return False

        except Exception as e:
            logger.error(f"[KC-WS] Error sending message to {connection_id}: {e}")
            return False

    def start(self):
        """Start the connection manager."""
        self.running = True
        logger.info("[KC-WS] Connection manager started")

    def stop(self):
        """Stop the connection manager."""
        self.running = False
        logger.info("[KC-WS] Connection manager stopped")
