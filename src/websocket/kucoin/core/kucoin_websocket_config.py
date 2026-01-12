"""
WebSocket configuration and constants for KuCoin futures API.
Based on official KuCoin documentation with safety measures.
"""

from typing import Optional
from dataclasses import dataclass

@dataclass
class KucoinWebSocketConfig:
    """Configuration for KuCoin WebSocket connections."""

    FUTURES_REST_BASE: str = "https://api-futures.kucoin.com"
    FUTURES_WS_BASE: str = "wss://ws-api.kucoin.com"

    RATE_LIMIT_MESSAGES_PER_10SEC: int = 100
    RATE_LIMIT_CONNECTIONS_PER_USER: int = 50
    RATE_LIMIT_CONNECTIONS_PER_MIN: int = 30
    RATE_LIMIT_TOPICS_PER_BATCH: int = 100
    RATE_LIMIT_TOPICS_PER_CONNECTION: int = 300

    PING_INTERVAL_DEFAULT: int = 18
    PONG_TIMEOUT: int = 30
    TOKEN_REFRESH_INTERVAL: int = 50 * 60
    TOKEN_VALIDITY: int = 60 * 60

    RECONNECT_DELAY: int = 5
    MAX_RECONNECT_ATTEMPTS: int = 10
    EXPONENTIAL_BACKOFF_BASE: float = 2.0

    MAX_CONSECUTIVE_ERRORS: int = 5
    ERROR_COOLDOWN: int = 60

    LOG_LEVEL: str = "INFO"
    LOG_WEBSOCKET_MESSAGES: bool = False

    def __init__(self, is_testnet: bool = False):
        """Initialize configuration with testnet flag."""
        self.is_testnet = is_testnet
        self.rest_base_url = self.FUTURES_REST_BASE
        self.ws_base_url = self.FUTURES_WS_BASE

    def get_bullet_private_url(self) -> str:
        """Get REST API URL for obtaining bullet-private token."""
        return f"{self.rest_base_url}/api/v1/bullet-private"

    def validate_rate_limits(self, messages_in_10sec: int) -> bool:
        """Validate rate limits according to KuCoin documentation."""
        if messages_in_10sec > self.RATE_LIMIT_MESSAGES_PER_10SEC:
            return False
        return True

    def get_reconnect_delay(self, attempt: int) -> int:
        """Calculate exponential backoff delay for reconnection."""
        if attempt <= 0:
            return self.RECONNECT_DELAY

        delay = self.RECONNECT_DELAY * (self.EXPONENTIAL_BACKOFF_BASE ** (attempt - 1))
        return min(int(delay), 300)
