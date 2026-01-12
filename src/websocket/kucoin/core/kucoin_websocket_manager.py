"""
Main WebSocket manager for KuCoin futures API.
Coordinates token management, connection establishment, and event handling.
"""

import asyncio
import json
import logging
import time
import uuid
from typing import Dict, List, Optional, Callable, Any
from datetime import datetime, timedelta
import aiohttp

from .kucoin_websocket_config import KucoinWebSocketConfig
from .kucoin_connection_manager import KucoinConnectionManager
from src.websocket.core.event_dispatcher import EventDispatcher, WebSocketEvent
from src.exchange.kucoin.kucoin_auth import KucoinAuth

logger = logging.getLogger(__name__)

class KucoinWebSocketManager:
    """
    Main WebSocket manager for KuCoin futures API.

    Features:
    - Token-based authentication
    - Automatic token refresh
    - Channel subscription management
    - Rate limiting compliance
    - Automatic reconnection
    - Ping/pong heartbeat handling
    """

    def __init__(self, api_key: str, api_secret: str, api_passphrase: str,
                 is_testnet: bool = False, db_manager=None):
        """
        Initialize WebSocket manager.

        Args:
            api_key: KuCoin API key
            api_secret: KuCoin API secret
            api_passphrase: KuCoin API passphrase
            is_testnet: Whether to use testnet
            db_manager: Database manager for real-time sync (optional)
        """
        self.api_key = api_key
        self.api_secret = api_secret
        self.api_passphrase = api_passphrase
        self.config = KucoinWebSocketConfig(is_testnet)
        self.db_manager = db_manager

        self.auth = KucoinAuth(api_key, api_secret, api_passphrase)
        self.connection_manager = KucoinConnectionManager(self.config)
        self.event_dispatcher = EventDispatcher()

        self.token: Optional[str] = None
        self.token_expiry: Optional[datetime] = None
        self.ws_endpoint: Optional[str] = None
        self.ping_interval: int = self.config.PING_INTERVAL_DEFAULT

        self.is_connected = False
        self.reconnect_attempts = 0
        self.consecutive_errors = 0
        self.rate_limit_counter = {'messages': 0, 'window_start': time.time()}

        self.tasks: List[asyncio.Task] = []
        self.running = False
        self.subscribed_symbols: List[str] = []

        logger.info(f"[KC-WS] Manager initialized for {'testnet' if is_testnet else 'mainnet'}")

    async def start(self):
        """Start WebSocket connections and background tasks."""
        if self.running:
            logger.warning("[KC-WS] Manager is already running")
            return

        self.running = True
        self.connection_manager.start()
        self.event_dispatcher.start()

        try:
            self.tasks = [
                asyncio.create_task(self._manage_token_refresh()),
                asyncio.create_task(self._rate_limit_monitor()),
                asyncio.create_task(self._heartbeat_monitor())
            ]

            await self._establish_connections()

            logger.info("[KC-WS] Manager started successfully")

        except Exception as e:
            logger.error(f"[KC-WS] Failed to start manager: {e}")
            await self.stop()
            raise

    async def stop(self):
        """Stop WebSocket connections and cleanup."""
        if not self.running:
            return

        self.running = False
        logger.info("[KC-WS] Stopping manager...")

        self.connection_manager.stop()
        self.event_dispatcher.stop()

        for task in self.tasks:
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        await self.connection_manager.close_all_connections()

        self.is_connected = False
        logger.info("[KC-WS] Manager stopped")

    async def _get_connection_token(self):
        """Get a new connection token from KuCoin."""
        try:
            endpoint = "/api/v1/bullet-private"
            request_body = json.dumps({})
            headers = self.auth.get_futures_headers("POST", endpoint, body=request_body)

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.config.get_bullet_private_url(),
                    headers=headers,
                    data=request_body,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data.get('code') == '200000':
                            token_data = data.get('data', {})
                            self.token = token_data.get('token')
                            instance_servers = token_data.get('instanceServers', [])
                            if instance_servers:
                                server = instance_servers[0]
                                self.ws_endpoint = server.get('endpoint')
                                ping_interval_ms = server.get('pingInterval', 18000)
                                self.ping_interval = ping_interval_ms / 1000
                            self.token_expiry = datetime.now() + timedelta(minutes=60)
                            logger.info(f"[KC-WS] Obtained new token, ping interval: {self.ping_interval}s")
                        else:
                            raise Exception(f"Failed to get token: {data.get('msg', 'Unknown error')}")
                    else:
                        text = await response.text()
                        raise Exception(f"Failed to get token: {response.status} - {text}")

        except Exception as e:
            logger.error(f"[KC-WS] Error getting token: {e}")
            raise

    async def _establish_connections(self):
        """Establish WebSocket connection."""
        try:
            await self._get_connection_token()

            if not self.token or not self.ws_endpoint:
                raise Exception("Failed to obtain token or endpoint")

            success = await self.connection_manager.create_connection(
                "kucoin_user_data",
                self.ws_endpoint,
                self.token,
                self._handle_message,
                self.ping_interval
            )

            if success:
                self.is_connected = True
                logger.info("[KC-WS] Connection established")
            else:
                raise Exception("Failed to establish connection")

        except Exception as e:
            logger.error(f"[KC-WS] Failed to establish connections: {e}")
            raise

    async def _handle_message(self, message: str, connection_id: str):
        """
        Handle messages from WebSocket.

        Args:
            message: Raw message from WebSocket
            connection_id: Connection identifier
        """
        try:
            self.rate_limit_counter['messages'] += 1

            if isinstance(message, str):
                data = json.loads(message)
            else:
                data = message

            msg_type = data.get('type')
            if msg_type == 'welcome':
                logger.info("[KC-WS] Received welcome message")
                return
            elif msg_type == 'ack':
                logger.debug(f"[KC-WS] Received ack: {data.get('id')}")
                return
            elif msg_type == 'pong':
                return

            topic = data.get('topic', '')
            subject = data.get('subject', '')

            if topic.startswith('/contractMarket/execution'):
                event_type = 'kucoin:execution'
            elif topic.startswith('/contractMarket/orderChange'):
                event_type = 'kucoin:orderChange'
            else:
                event_type = 'kucoin:unknown'

            event = WebSocketEvent(
                event_type=event_type,
                data=data,
                timestamp=datetime.now().timestamp(),
                connection_id=connection_id
            )

            await self.event_dispatcher.dispatch_event(event)

        except json.JSONDecodeError as e:
            logger.error(f"[KC-WS] Failed to parse message: {e}")
        except Exception as e:
            logger.error(f"[KC-WS] Error handling message: {e}")
            self.consecutive_errors += 1

    async def subscribe_to_symbol(self, symbol: str):
        """
        Subscribe to order execution and lifecycle events for a symbol.

        Args:
            symbol: Trading symbol (e.g., 'XBTUSDTM')
        """
        try:
            if symbol in self.subscribed_symbols:
                logger.debug(f"[KC-WS] Already subscribed to {symbol}")
                return

            topics = [
                f"/contractMarket/execution:{symbol}",
                f"/contractMarket/orderChange:{symbol}"
            ]

            for topic in topics:
                subscribe_msg = {
                    "id": str(int(time.time() * 1000)),
                    "type": "subscribe",
                    "topic": topic,
                    "privateChannel": True,
                    "response": True
                }

                success = await self.connection_manager.send_message(
                    "kucoin_user_data",
                    json.dumps(subscribe_msg)
                )

                if success:
                    logger.info(f"[KC-WS] Subscribed to {topic}")
                else:
                    logger.error(f"[KC-WS] Failed to subscribe to {topic}")

            self.subscribed_symbols.append(symbol)

        except Exception as e:
            logger.error(f"[KC-WS] Error subscribing to {symbol}: {e}")

    async def subscribe_to_coin_symbol(self, coin_symbol: str):
        """
        Subscribe to order events for a coin symbol (converts to KuCoin format).

        Args:
            coin_symbol: Coin symbol (e.g., 'BTC', 'ETH') - will be converted to KuCoin format
        """
        try:
            from src.exchange.kucoin.kucoin_symbol_converter import symbol_converter

            kucoin_symbol = symbol_converter.convert_bot_to_kucoin_futures(coin_symbol)
            await self.subscribe_to_symbol(kucoin_symbol)

        except Exception as e:
            logger.error(f"[KC-WS] Error subscribing to coin symbol {coin_symbol}: {e}")

    async def _manage_token_refresh(self):
        """Background task to manage token refresh."""
        while self.running:
            try:
                if self.token_expiry:
                    time_until_expiry = (self.token_expiry - datetime.now()).total_seconds()

                    if time_until_expiry <= 600:
                        logger.info("[KC-WS] Refreshing token...")
                        await self._get_connection_token()

                        if self.is_connected:
                            await self.connection_manager.close_connection("kucoin_user_data")
                            await self._establish_connections()

                            for symbol in self.subscribed_symbols:
                                await self.subscribe_to_symbol(symbol)

                await asyncio.sleep(60)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[KC-WS] Error in token refresh: {e}")
                await asyncio.sleep(60)

    async def _heartbeat_monitor(self):
        """Background task to monitor connection health."""
        while self.running:
            try:
                if not self.connection_manager.is_connected("kucoin_user_data"):
                    logger.warning("[KC-WS] Connection lost, attempting reconnection")
                    await self._establish_connections()

                    for symbol in self.subscribed_symbols:
                        await self.subscribe_to_symbol(symbol)

                await asyncio.sleep(30)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[KC-WS] Error in heartbeat monitor: {e}")
                await asyncio.sleep(30)

    async def _rate_limit_monitor(self):
        """Background task to monitor rate limits."""
        while self.running:
            try:
                current_time = time.time()
                window_start = self.rate_limit_counter['window_start']

                if current_time - window_start >= 10:
                    messages_in_window = self.rate_limit_counter['messages']
                    if messages_in_window > self.config.RATE_LIMIT_MESSAGES_PER_10SEC:
                        logger.warning(f"[KC-WS] Rate limit warning: {messages_in_window} messages in 10s")
                    self.rate_limit_counter = {'messages': 0, 'window_start': current_time}

                await asyncio.sleep(1)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[KC-WS] Error in rate limit monitor: {e}")
                await asyncio.sleep(1)

    def register_handler(self, event_type: str, handler: Callable):
        """
        Register a handler for a specific event type.

        Args:
            event_type: Type of event to handle (e.g., 'kucoin:execution')
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
            'token': self.token is not None,
            'token_expiry': self.token_expiry.isoformat() if self.token_expiry else None,
            'connection_states': self.connection_manager.get_all_connection_states(),
            'registered_handlers': self.event_dispatcher.get_registered_handlers(),
            'subscribed_symbols': self.subscribed_symbols.copy(),
            'rate_limit_counter': self.rate_limit_counter.copy(),
            'consecutive_errors': self.consecutive_errors
        }
