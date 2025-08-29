"""
WebSocket connection manager for handling connection lifecycle.
Manages connection establishment, reconnection, and cleanup.
"""

import asyncio
import logging
import time
from typing import Optional, Dict, Any, Callable
from datetime import datetime, timedelta
import aiohttp
import websockets
from websockets.exceptions import ConnectionClosed

from .websocket_config import WebSocketConfig

logger = logging.getLogger(__name__)

class ConnectionManager:
    """
    Manages WebSocket connections with automatic reconnection and error handling.
    """

    def __init__(self, config: WebSocketConfig):
        """
        Initialize connection manager.

        Args:
            config: WebSocket configuration
        """
        self.config = config
        self.connections: Dict[str, Any] = {}
        self.connection_states: Dict[str, Dict[str, Any]] = {}
        self.reconnect_tasks: Dict[str, asyncio.Task] = {}
        self.running = False

    async def create_connection(self, connection_id: str, url: str, 
                              message_handler: Callable, 
                              connection_type: str = "user_data") -> bool:
        """
        Create a new WebSocket connection.

        Args:
            connection_id: Unique identifier for the connection
            url: WebSocket URL
            message_handler: Callback function for handling messages
            connection_type: Type of connection (user_data, market_data)

        Returns:
            bool: True if connection was established successfully
        """
        try:
            logger.info(f"Creating {connection_type} connection: {connection_id}")
            
            # Create connection state
            self.connection_states[connection_id] = {
                'url': url,
                'type': connection_type,
                'connected': False,
                'last_ping': 0,
                'last_pong': 0,
                'reconnect_attempts': 0,
                'created_at': datetime.now(),
                'message_handler': message_handler
            }

            # Establish connection
            websocket = await websockets.connect(url)
            self.connections[connection_id] = websocket
            self.connection_states[connection_id]['connected'] = True
            self.connection_states[connection_id]['reconnect_attempts'] = 0

            # Start message handling task
            asyncio.create_task(self._handle_messages(connection_id, websocket, message_handler))
            
            logger.info(f"Successfully established {connection_type} connection: {connection_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to create {connection_type} connection {connection_id}: {e}")
            return False

    async def close_connection(self, connection_id: str) -> bool:
        """
        Close a WebSocket connection.

        Args:
            connection_id: Connection identifier

        Returns:
            bool: True if connection was closed successfully
        """
        try:
            if connection_id in self.connections:
                websocket = self.connections[connection_id]
                await websocket.close()
                del self.connections[connection_id]
                
                if connection_id in self.connection_states:
                    self.connection_states[connection_id]['connected'] = False
                
                # Cancel reconnect task if running
                if connection_id in self.reconnect_tasks:
                    self.reconnect_tasks[connection_id].cancel()
                    del self.reconnect_tasks[connection_id]
                
                logger.info(f"Closed connection: {connection_id}")
                return True
            return False

        except Exception as e:
            logger.error(f"Error closing connection {connection_id}: {e}")
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
                    # Update last ping time
                    self.connection_states[connection_id]['last_ping'] = time.time()
                    
                    # Handle message
                    await message_handler(message, connection_id)
                    
                except Exception as e:
                    logger.error(f"Error handling message from {connection_id}: {e}")

        except ConnectionClosed:
            logger.warning(f"Connection closed for {connection_id}")
            await self._handle_connection_closed(connection_id)
        except Exception as e:
            logger.error(f"Error in message handling for {connection_id}: {e}")
            await self._handle_connection_closed(connection_id)

    async def _handle_connection_closed(self, connection_id: str):
        """
        Handle connection closure and initiate reconnection if needed.

        Args:
            connection_id: Connection identifier
        """
        if connection_id in self.connection_states:
            self.connection_states[connection_id]['connected'] = False
            
            # Start reconnection if not already running
            if connection_id not in self.reconnect_tasks or self.reconnect_tasks[connection_id].done():
                self.reconnect_tasks[connection_id] = asyncio.create_task(
                    self._reconnect_connection(connection_id)
                )

    async def _reconnect_connection(self, connection_id: str):
        """
        Attempt to reconnect a closed connection.

        Args:
            connection_id: Connection identifier
        """
        if connection_id not in self.connection_states:
            return

        state = self.connection_states[connection_id]
        max_attempts = self.config.MAX_RECONNECT_ATTEMPTS

        while state['reconnect_attempts'] < max_attempts and self.running:
            try:
                state['reconnect_attempts'] += 1
                delay = self.config.get_reconnect_delay(state['reconnect_attempts'])
                
                logger.info(f"Attempting to reconnect {connection_id} (attempt {state['reconnect_attempts']}/{max_attempts}) in {delay}s")
                
                await asyncio.sleep(delay)
                
                # Attempt reconnection
                websocket = await websockets.connect(state['url'])
                self.connections[connection_id] = websocket
                state['connected'] = True
                state['reconnect_attempts'] = 0
                
                # Restart message handling
                asyncio.create_task(self._handle_messages(connection_id, websocket, state['message_handler']))
                
                logger.info(f"Successfully reconnected {connection_id}")
                return

            except Exception as e:
                logger.error(f"Reconnection attempt {state['reconnect_attempts']} failed for {connection_id}: {e}")

        logger.error(f"Failed to reconnect {connection_id} after {max_attempts} attempts")

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
            message: Message to send

        Returns:
            bool: True if message was sent successfully
        """
        try:
            if self.is_connected(connection_id):
                websocket = self.connections[connection_id]
                await websocket.send(message)
                return True
            else:
                logger.warning(f"Cannot send message to disconnected connection: {connection_id}")
                return False

        except Exception as e:
            logger.error(f"Error sending message to {connection_id}: {e}")
            return False

    def start(self):
        """Start the connection manager."""
        self.running = True
        logger.info("Connection manager started")

    def stop(self):
        """Stop the connection manager."""
        self.running = False
        logger.info("Connection manager stopped")
