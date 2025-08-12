"""
Binance WebSocket Manager for real-time futures data streaming.
Handles user data streams, market data, automatic reconnection, and rate limiting.
"""

import asyncio
import json
import logging
import time
from typing import Dict, List, Optional, Callable, Any, Union
from datetime import datetime, timedelta
from dataclasses import dataclass
import aiohttp
import websockets
from websockets.exceptions import ConnectionClosed

from websocket_config import WebSocketConfig
from database_sync_handler import DatabaseSyncHandler

logger = logging.getLogger(__name__)

@dataclass
class WebSocketEvent:
    """Represents a WebSocket event with metadata."""
    event_type: str
    data: Dict[str, Any]
    timestamp: float
    stream_name: Optional[str] = None

class BinanceWebSocketManager:
    """
    Manages WebSocket connections to Binance futures API.

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

        # Initialize database sync handler if db_manager is provided
        if db_manager:
            self.db_sync_handler = DatabaseSyncHandler(db_manager)
        else:
            self.db_sync_handler = None

        # Connection state
        self.user_data_ws: Optional[Any] = None
        self.market_data_ws: Optional[Any] = None
        self.listen_key: Optional[str] = None
        self.listen_key_expiry: Optional[datetime] = None

        # Event handlers
        self.event_handlers: Dict[str, List[Callable]] = {
            'executionReport': [],
            'outboundAccountPosition': [],
            'balanceUpdate': [],
            'ticker': [],
            'trade': [],
            'depth': [],
            'error': [],
            'connection': [],
            'disconnection': []
        }

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
            logger.warning("WebSocket Manager is already running")
            return

        self.running = True
        logger.info("Starting WebSocket Manager...")

        try:
            # Get listen key for user data stream
            await self._get_listen_key()

            # Start background tasks
            self.tasks = [
                asyncio.create_task(self._manage_user_data_stream()),
                asyncio.create_task(self._manage_market_data_stream()),
                asyncio.create_task(self._manage_listen_key_refresh()),
                asyncio.create_task(self._manage_rate_limiting()),
                asyncio.create_task(self._manage_heartbeat())
            ]

            logger.info("WebSocket Manager started successfully")

        except Exception as e:
            logger.error(f"Failed to start WebSocket Manager: {e}")
            await self.stop()
            raise

    async def stop(self):
        """Stop WebSocket connections and cleanup."""
        if not self.running:
            return

        logger.info("Stopping WebSocket Manager...")
        self.running = False

        # Cancel all tasks
        for task in self.tasks:
            if not task.done():
                task.cancel()

        # Wait for tasks to complete
        if self.tasks:
            await asyncio.gather(*self.tasks, return_exceptions=True)

        # Close WebSocket connections
        await self._close_connections()

        # Delete listen key
        if self.listen_key:
            await self._delete_listen_key()

        logger.info("WebSocket Manager stopped")

    def add_event_handler(self, event_type: str, handler: Callable):
        """Add event handler for specific event type."""
        if event_type in self.event_handlers:
            self.event_handlers[event_type].append(handler)
            logger.debug(f"Added handler for event type: {event_type}")
        else:
            logger.warning(f"Unknown event type: {event_type}")

    def remove_event_handler(self, event_type: str, handler: Callable):
        """Remove event handler."""
        if event_type in self.event_handlers and handler in self.event_handlers[event_type]:
            self.event_handlers[event_type].remove(handler)
            logger.debug(f"Removed handler for event type: {event_type}")

    async def _get_listen_key(self):
        """Get listen key for user data stream."""
        try:
            headers = {'X-MBX-APIKEY': self.api_key}
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.config.get_listen_key_url(),
                    headers=headers
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        self.listen_key = data.get('listenKey')
                        self.listen_key_expiry = datetime.now() + timedelta(minutes=60)
                        logger.info("Listen key obtained successfully")
                    else:
                        error_text = await response.text()
                        raise Exception(f"Failed to get listen key: {response.status} - {error_text}")
        except Exception as e:
            logger.error(f"Error getting listen key: {e}")
            raise

    async def _refresh_listen_key(self):
        """Refresh listen key before expiry."""
        if not self.listen_key:
            await self._get_listen_key()
            return

        try:
            headers = {'X-MBX-APIKEY': self.api_key}
            async with aiohttp.ClientSession() as session:
                async with session.put(
                    self.config.get_refresh_listen_key_url(),
                    headers=headers,
                    params={'listenKey': self.listen_key}
                ) as response:
                    if response.status == 200:
                        self.listen_key_expiry = datetime.now() + timedelta(minutes=60)
                        logger.debug("Listen key refreshed successfully")
                    else:
                        error_text = await response.text()
                        logger.warning(f"Failed to refresh listen key: {response.status} - {error_text}")
                        # Get new listen key
                        await self._get_listen_key()
        except Exception as e:
            logger.error(f"Error refreshing listen key: {e}")
            await self._get_listen_key()

    async def _delete_listen_key(self):
        """Delete listen key."""
        if not self.listen_key:
            return

        try:
            headers = {'X-MBX-APIKEY': self.api_key}
            async with aiohttp.ClientSession() as session:
                async with session.delete(
                    self.config.get_delete_listen_key_url(),
                    headers=headers,
                    params={'listenKey': self.listen_key}
                ) as response:
                    if response.status == 200:
                        logger.info("Listen key deleted successfully")
                    else:
                        logger.warning(f"Failed to delete listen key: {response.status}")
        except Exception as e:
            logger.error(f"Error deleting listen key: {e}")

    async def _manage_user_data_stream(self):
        """Manage user data stream connection."""
        while self.running:
            try:
                if not self.listen_key:
                    await self._get_listen_key()

                url = f"{self.config.user_data_stream_url}/{self.listen_key}"
                logger.info(f"Connecting to user data stream: {url}")

                logger.info(f"Attempting to connect to user data stream...")
                websocket = await websockets.connect(url, ping_interval=None, ping_timeout=None)
                self.user_data_ws = websocket
                self.is_connected = True
                self.reconnect_attempts = 0
                self.consecutive_errors = 0

                logger.info("User data stream connected successfully")
                await self._emit_event('connection', {'type': 'user_data'})

                try:
                    async for message in websocket:
                        if not self.running:
                            break

                        await self._handle_message(message, 'user_data')
                finally:
                    await websocket.close()

            except ConnectionClosed as e:
                logger.warning(f"User data stream connection closed: {e}")
                await self._emit_event('disconnection', {'type': 'user_data'})
            except Exception as e:
                logger.error(f"User data stream error: {e}")
                logger.error(f"Error type: {type(e).__name__}")
                self.consecutive_errors += 1
                await self._emit_event('error', {'type': 'user_data', 'error': str(e)})

            finally:
                self.user_data_ws = None
                self.is_connected = False

            # Reconnection logic
            if self.running:
                await self._handle_reconnection('user_data')

    async def _manage_market_data_stream(self):
        """Manage market data stream connection."""
        # Subscribe to relevant market data streams (reduced to avoid rate limits)
        streams = [
            "btcusdt@ticker",
            "ethusdt@ticker"
            # Removed "!ticker@arr" to reduce message volume
        ]

        while self.running:
            try:
                # Use the correct URL format for combined streams
                # For combined streams, use /stream endpoint, not /ws/stream
                url = f"{self.config.ws_base_url}/stream?streams={'/'.join(streams)}"
                logger.info(f"Connecting to market data stream: {url}")

                logger.info(f"Attempting to connect to market data stream...")
                websocket = await websockets.connect(url, ping_interval=None, ping_timeout=None)
                self.market_data_ws = websocket
                logger.info("Market data stream connected successfully")
                await self._emit_event('connection', {'type': 'market_data'})

                try:
                    async for message in websocket:
                        if not self.running:
                            break

                        await self._handle_message(message, 'market_data')
                finally:
                    await websocket.close()

            except ConnectionClosed as e:
                logger.warning(f"Market data stream connection closed: {e}")
                await self._emit_event('disconnection', {'type': 'market_data'})
            except Exception as e:
                logger.error(f"Market data stream error: {e}")
                logger.error(f"Error type: {type(e).__name__}")
                self.consecutive_errors += 1
                await self._emit_event('error', {'type': 'market_data', 'error': str(e)})

            finally:
                self.market_data_ws = None

            # Reconnection logic
            if self.running:
                await self._handle_reconnection('market_data')

    async def _handle_message(self, message: Union[str, bytes], stream_type: str):
        """Handle incoming WebSocket message."""
        try:
            # Rate limiting check with throttling
            if not self._check_rate_limits():
                # Add small delay when rate limited instead of just skipping
                await asyncio.sleep(0.1)
                return

            # Log all user data stream messages for debugging
            if stream_type == 'user_data':
                logger.info(f"WebSocket {stream_type}: Received message: {message[:200]}...")

            # Convert bytes to string if needed
            if isinstance(message, bytes):
                message_str = message.decode('utf-8')
            else:
                message_str = message

            data = json.loads(message_str)

            # Handle combined stream format
            if 'stream' in data and 'data' in data:
                stream_name = data['stream']
                event_data = data['data']
                # Handle array responses (like !ticker@arr)
                if isinstance(event_data, list):
                    # Process each item in the array
                    for item in event_data:
                        if isinstance(item, dict):
                            item_event_type = item.get('e', 'unknown')
                            await self._emit_event(item_event_type, item)
                    return  # Exit early since we processed the array
                else:
                    event_type = event_data.get('e', 'unknown')
            else:
                # Direct message format
                event_type = data.get('e', 'unknown')
                event_data = data
                stream_name = None

            # Create event object
            event = WebSocketEvent(
                event_type=event_type,
                data=event_data,
                timestamp=time.time(),
                stream_name=stream_name
            )

            # Log message if enabled
            if self.config.LOG_WEBSOCKET_MESSAGES:
                logger.debug(f"Received {stream_type} message: {event_type}")

            # Emit event to handlers
            await self._emit_event(event_type, event_data)

            # Handle database synchronization if enabled
            if self.db_sync_handler:
                await self._handle_database_sync(event_type, event_data)

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse WebSocket message: {e}")
            self.consecutive_errors += 1
        except Exception as e:
            logger.error(f"Error handling WebSocket message: {e}")
            self.consecutive_errors += 1

    async def _emit_event(self, event_type: str, data: Dict[str, Any]):
        """Emit event to registered handlers."""
        if event_type in self.event_handlers:
            for handler in self.event_handlers[event_type]:
                try:
                    if asyncio.iscoroutinefunction(handler):
                        await handler(data)
                    else:
                        handler(data)
                except Exception as e:
                    logger.error(f"Error in event handler for {event_type}: {e}")

    async def _handle_reconnection(self, stream_type: str):
        """Handle reconnection with exponential backoff."""
        if self.consecutive_errors >= self.config.MAX_CONSECUTIVE_ERRORS:
            logger.error(f"Too many consecutive errors for {stream_type}, stopping reconnection")
            return

        self.reconnect_attempts += 1
        delay = self.config.get_reconnect_delay(self.reconnect_attempts)

        logger.info(f"Reconnecting {stream_type} in {delay} seconds (attempt {self.reconnect_attempts})")
        await asyncio.sleep(delay)

    async def _manage_listen_key_refresh(self):
        """Manage listen key refresh."""
        while self.running:
            try:
                await asyncio.sleep(self.config.LISTEN_KEY_REFRESH_INTERVAL)

                if self.listen_key_expiry and datetime.now() >= self.listen_key_expiry - timedelta(minutes=5):
                    logger.info("Refreshing listen key before expiry")
                    await self._refresh_listen_key()

            except Exception as e:
                logger.error(f"Error in listen key refresh: {e}")

    async def _manage_rate_limiting(self):
        """Manage rate limiting counters."""
        while self.running:
            try:
                await asyncio.sleep(1)  # Reset counters every second

                current_time = time.time()
                if current_time - self.rate_limit_reset_time >= 1:
                    self.rate_limit_counter = {'messages': 0, 'ping_pong': 0}
                    self.rate_limit_reset_time = current_time

            except Exception as e:
                logger.error(f"Error in rate limiting management: {e}")

    async def _manage_heartbeat(self):
        """Manage ping/pong heartbeat."""
        while self.running:
            try:
                await asyncio.sleep(self.config.PING_INTERVAL)

                # Check if we need to send ping
                current_time = time.time()
                if current_time - self.last_ping_time >= self.config.PING_INTERVAL:
                    await self._send_ping()

                # Check pong timeout
                if (self.last_pong_time > 0 and
                    current_time - self.last_pong_time > self.config.PONG_TIMEOUT):
                    logger.warning("Pong timeout, reconnecting...")
                    await self._close_connections()

            except Exception as e:
                logger.error(f"Error in heartbeat management: {e}")

    async def _send_ping(self):
        """Send ping to WebSocket connections."""
        try:
            if self.user_data_ws and hasattr(self.user_data_ws, 'closed') and not self.user_data_ws.closed:
                await self.user_data_ws.ping()
                self.last_ping_time = time.time()
                self.rate_limit_counter['ping_pong'] += 1

            if self.market_data_ws and hasattr(self.market_data_ws, 'closed') and not self.market_data_ws.closed:
                await self.market_data_ws.ping()
                self.rate_limit_counter['ping_pong'] += 1

        except Exception as e:
            logger.error(f"Error sending ping: {e}")

    def _check_rate_limits(self) -> bool:
        """Check if we're within rate limits."""
        self.rate_limit_counter['messages'] += 1

        return self.config.validate_rate_limits(
            self.rate_limit_counter['messages'],
            self.rate_limit_counter['ping_pong']
        )

    async def _close_connections(self):
        """Close WebSocket connections."""
        if self.user_data_ws and hasattr(self.user_data_ws, 'closed') and not self.user_data_ws.closed:
            await self.user_data_ws.close()

        if self.market_data_ws and hasattr(self.market_data_ws, 'closed') and not self.market_data_ws.closed:
            await self.market_data_ws.close()

    async def _handle_database_sync(self, event_type: str, event_data: Dict[str, Any]):
        """
        Handle database synchronization for WebSocket events.
        """
        try:
            if self.db_sync_handler:
                if event_type == 'executionReport':
                    await self.db_sync_handler.handle_execution_report(event_data)
                elif event_type == 'outboundAccountPosition':
                    await self.db_sync_handler.handle_account_position(event_data)
                elif event_type == 'ticker':
                    await self.db_sync_handler.handle_ticker(event_data)
        except Exception as e:
            logger.error(f"Error in database sync handler: {e}")

    def get_connection_status(self) -> Dict[str, Any]:
        """Get current connection status."""
        # More robust connection status checking
        def is_websocket_connected(ws) -> bool:
            if ws is None:
                return False
            try:
                # Check if websocket has closed attribute and it's False
                if hasattr(ws, 'closed'):
                    return not ws.closed
                # If no closed attribute, assume it's connected if it exists
                return True
            except Exception:
                return False

        status = {
            'running': self.running,
            'is_connected': self.is_connected,
            'user_data_connected': is_websocket_connected(self.user_data_ws),
            'market_data_connected': is_websocket_connected(self.market_data_ws),
            'listen_key': self.listen_key is not None,
            'listen_key_expiry': self.listen_key_expiry.isoformat() if self.listen_key_expiry else None,
            'reconnect_attempts': self.reconnect_attempts,
            'consecutive_errors': self.consecutive_errors,
            'rate_limit_counter': self.rate_limit_counter.copy()
        }

        # Add database sync stats if available
        if self.db_sync_handler:
            status['db_sync_stats'] = self.db_sync_handler.get_order_id_mapping_stats()

        return status