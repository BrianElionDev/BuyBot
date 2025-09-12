"""
WebSocket configuration and constants for Binance futures API.
Based on official Binance documentation with safety measures.
"""

import os
from typing import Optional
from dataclasses import dataclass

@dataclass
class WebSocketConfig:
    """Configuration for Binance WebSocket connections."""

        # Base endpoints
    FUTURES_WS_BASE: str = "wss://fstream.binance.com"
    FUTURES_WS_TESTNET: str = "wss://stream.binancefuture.com"  # Correct testnet WebSocket endpoint

    # REST API endpoints for listen key management
    FUTURES_REST_BASE: str = "https://fapi.binance.com"
    FUTURES_REST_TESTNET: str = "https://testnet.binancefuture.com"

    # Connection settings
    PING_INTERVAL: int = 300  # 5 minutes (reduced ping frequency)
    PONG_TIMEOUT: int = 600   # 10 minutes (must respond within 10 minutes)
    CONNECTION_TIMEOUT: int = 24 * 60 * 60  # 24 hours (connection expires)

    # Rate limiting (conservative limits to avoid hitting Binance limits)
    MAX_MESSAGES_PER_SECOND: int = 6  # Reduced from 9 to be more conservative
    MAX_PING_PONG_PER_SECOND: int = 2  # Reduced from 4 to be more conservative
    MAX_STREAMS_PER_CONNECTION: int = 1024
    MAX_CONNECTIONS_PER_5MIN: int = 290

    # Reconnection settings
    RECONNECT_DELAY: int = 5  # seconds
    MAX_RECONNECT_ATTEMPTS: int = 10
    EXPONENTIAL_BACKOFF_BASE: float = 2.0

    # Listen key management
    LISTEN_KEY_REFRESH_INTERVAL: int = 30 * 60  # 30 minutes (refresh before 60min expiry)

    # Error handling
    MAX_CONSECUTIVE_ERRORS: int = 5
    ERROR_COOLDOWN: int = 60  # seconds

    # Logging
    LOG_LEVEL: str = "INFO"
    LOG_WEBSOCKET_MESSAGES: bool = False # Set to False to reduce logging overhead

    def __init__(self, is_testnet: bool = False):
        """Initialize configuration with testnet flag."""
        self.is_testnet = is_testnet

        # Set appropriate endpoints based on testnet flag
        if is_testnet:
            self.ws_base_url = self.FUTURES_WS_TESTNET
            self.rest_base_url = self.FUTURES_REST_TESTNET
        else:
            self.ws_base_url = self.FUTURES_WS_BASE
            self.rest_base_url = self.FUTURES_REST_BASE

    @property
    def user_data_stream_url(self) -> str:
        """Get user data stream URL (requires listen key)."""
        return f"{self.ws_base_url}/ws"

    @property
    def market_data_stream_url(self) -> str:
        """Get market data stream URL."""
        return f"{self.ws_base_url}/ws"

    def get_listen_key_url(self) -> str:
        """Get REST API URL for obtaining listen key."""
        return f"{self.rest_base_url}/fapi/v1/listenKey"

    def get_refresh_listen_key_url(self) -> str:
        """Get REST API URL for refreshing listen key."""
        return f"{self.rest_base_url}/fapi/v1/listenKey"

    def get_delete_listen_key_url(self) -> str:
        """Get REST API URL for deleting listen key."""
        return f"{self.rest_base_url}/fapi/v1/listenKey"

    def validate_rate_limits(self, messages_per_second: int, ping_pong_per_second: int) -> bool:
        """Validate rate limits according to Binance documentation."""
        if messages_per_second > self.MAX_MESSAGES_PER_SECOND:
            return False
        if ping_pong_per_second > self.MAX_PING_PONG_PER_SECOND:
            return False
        return True

    def get_reconnect_delay(self, attempt: int) -> int:
        """Calculate exponential backoff delay for reconnection."""
        if attempt <= 0:
            return self.RECONNECT_DELAY

        delay = self.RECONNECT_DELAY * (self.EXPONENTIAL_BACKOFF_BASE ** (attempt - 1))
        return min(int(delay), 300)  # Cap at 5 minutes
