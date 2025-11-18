"""
KuCoin Authentication Handler

Handles KuCoin API authentication using the sophisticated signature system.
Following Clean Code principles with clear authentication logic.
"""

import time
import hmac
import hashlib
import base64
from typing import Dict, Optional
import logging

logger = logging.getLogger(__name__)


class KucoinAuth:
    """
    KuCoin authentication handler.

    Implements KuCoin's sophisticated authentication system with proper
    signature generation and header management.
    """

    def __init__(self, api_key: str, api_secret: str, api_passphrase: str):
        """
        Initialize KuCoin authentication.

        Args:
            api_key: KuCoin API key
            api_secret: KuCoin API secret
            api_passphrase: KuCoin API passphrase
        """
        self.api_key = api_key
        self.api_secret = api_secret
        self.api_passphrase = api_passphrase
        # Server time offset in seconds (server_ms - local_ms) / 1000
        self._time_offset: float = 0.0

    def set_time_offset(self, offset_seconds: float) -> None:
        """
        Set server time offset in seconds.
        Positive value means server time is ahead of local time.
        """
        try:
            self._time_offset = float(offset_seconds)
        except Exception:
            self._time_offset = 0.0

    def _now_ms(self) -> str:
        """
        Current timestamp in milliseconds adjusted by server time offset.
        """
        try:
            return str(int((time.time() + self._time_offset) * 1000))
        except Exception:
            return str(int(time.time() * 1000))

    def generate_signature(self, timestamp: str, method: str, endpoint: str, body: str = "") -> str:
        """
        Generate KuCoin API signature.

        Args:
            timestamp: Request timestamp
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint path
            body: Request body (empty for GET requests)

        Returns:
            Base64 encoded signature
        """
        try:
            # Create the string to sign
            str_to_sign = f"{timestamp}{method}{endpoint}{body}"

            # Create HMAC signature
            signature = hmac.new(
                self.api_secret.encode('utf-8'),
                str_to_sign.encode('utf-8'),
                hashlib.sha256
            ).digest()

            # Base64 encode the signature
            return base64.b64encode(signature).decode('utf-8')

        except Exception as e:
            logger.error(f"Failed to generate KuCoin signature: {e}")
            raise

    def generate_passphrase_signature(self) -> str:
        """
        Generate passphrase signature for KuCoin API.

        Returns:
            Base64 encoded passphrase signature
        """
        try:
            passphrase_signature = hmac.new(
                self.api_secret.encode('utf-8'),
                self.api_passphrase.encode('utf-8'),
                hashlib.sha256
            ).digest()

            return base64.b64encode(passphrase_signature).decode('utf-8')

        except Exception as e:
            logger.error(f"Failed to generate KuCoin passphrase signature: {e}")
            raise

    def get_auth_headers(self, method: str, endpoint: str, body: str = "") -> Dict[str, str]:
        """
        Get authentication headers for KuCoin API request.

        Args:
            method: HTTP method
            endpoint: API endpoint
            body: Request body

        Returns:
            Dictionary of authentication headers
        """
        try:
            timestamp = self._now_ms()
            signature = self.generate_signature(timestamp, method, endpoint, body)
            passphrase_signature = self.generate_passphrase_signature()

            return {
                'KC-API-KEY': self.api_key,
                'KC-API-SIGN': signature,
                'KC-API-TIMESTAMP': timestamp,
                'KC-API-PASSPHRASE': passphrase_signature,
                'KC-API-KEY-VERSION': '2',
                'Content-Type': 'application/json'
            }

        except Exception as e:
            logger.error(f"Failed to generate KuCoin auth headers: {e}")
            raise

    def get_futures_headers(self, method: str, endpoint: str, params: Optional[Dict] = None, body: str = "") -> Dict[str, str]:
        """
        Get authentication headers for KuCoin futures API request.

        Args:
            method: HTTP method
            endpoint: API endpoint
            params: Query parameters
            body: Request body (for POST requests)

        Returns:
            Dictionary of authentication headers
        """
        try:
            from urllib.parse import urlencode

            # Convert params to query string if provided
            query = ""
            if params:
                query = "?" + urlencode(params)

            timestamp = self._now_ms()
            str_to_sign = timestamp + method + endpoint + query + body
            signature = self.generate_signature(timestamp, method, endpoint, query + body)
            passphrase_signature = self.generate_passphrase_signature()

            return {
                'KC-API-KEY': self.api_key,
                'KC-API-SIGN': signature,
                'KC-API-TIMESTAMP': timestamp,
                'KC-API-PASSPHRASE': passphrase_signature,
                'KC-API-KEY-VERSION': '2',
                'Content-Type': 'application/json'
            }

        except Exception as e:
            logger.error(f"Failed to generate KuCoin futures auth headers: {e}")
            raise

    def validate_credentials(self) -> bool:
        """
        Validate KuCoin API credentials.

        Returns:
            True if credentials are valid, False otherwise
        """
        try:
            if not all([self.api_key, self.api_secret, self.api_passphrase]):
                logger.error("KuCoin credentials are incomplete")
                return False

            # Basic format validation
            if len(self.api_key) < 10 or len(self.api_secret) < 10:
                logger.error("KuCoin credentials appear to be invalid format")
                return False

            return True

        except Exception as e:
            logger.error(f"Failed to validate KuCoin credentials: {e}")
            return False
