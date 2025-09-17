"""
KuCoin Client Wrapper

Wrapper around the KuCoin Universal SDK for simplified usage.
Following Clean Code principles with clear client abstraction.
"""

import logging
from typing import Optional
from kucoin_universal_sdk.api.client import DefaultClient
from kucoin_universal_sdk.model.client_option import ClientOptionBuilder
from kucoin_universal_sdk.model.constants import GLOBAL_API_ENDPOINT, GLOBAL_FUTURES_API_ENDPOINT
from kucoin_universal_sdk.model.transport_option import TransportOptionBuilder

from .kucoin_auth import KucoinAuth

logger = logging.getLogger(__name__)


class KucoinClient:
    """
    KuCoin client wrapper.

    Provides a simplified interface to the KuCoin Universal SDK
    with proper error handling and logging.
    """

    def __init__(self, api_key: str, api_secret: str, api_passphrase: str, is_testnet: bool = False):
        """
        Initialize KuCoin client.

        Args:
            api_key: KuCoin API key
            api_secret: KuCoin API secret
            api_passphrase: KuCoin API passphrase
            is_testnet: Whether to use testnet
        """
        self.api_key = api_key
        self.api_secret = api_secret
        self.api_passphrase = api_passphrase
        self.is_testnet = is_testnet
        self.client: Optional[DefaultClient] = None
        self.auth = KucoinAuth(api_key, api_secret, api_passphrase)

        logger.info(f"KucoinClient initialized for testnet: {self.is_testnet}")

    async def initialize(self) -> bool:
        """
        Initialize the KuCoin client connection.

        Returns:
            True if initialization successful, False otherwise
        """
        try:
            if not self.auth.validate_credentials():
                logger.error("Invalid KuCoin credentials")
                return False

            # Choose endpoints based on testnet setting
            spot_endpoint = GLOBAL_API_ENDPOINT if self.is_testnet else GLOBAL_API_ENDPOINT
            futures_endpoint = GLOBAL_FUTURES_API_ENDPOINT if self.is_testnet else GLOBAL_FUTURES_API_ENDPOINT

            # Configure transport options
            transport_option = TransportOptionBuilder().build()

            # Build client options
            client_option = (
                ClientOptionBuilder()
                .set_key(self.api_key)
                .set_secret(self.api_secret)
                .set_passphrase(self.api_passphrase)
                .set_spot_endpoint(spot_endpoint)
                .set_futures_endpoint(futures_endpoint)
                .set_transport_option(transport_option)
                .build()
            )

            # Create client
            self.client = DefaultClient(client_option)

            logger.info(f"KuCoin client initialized successfully for {'testnet' if self.is_testnet else 'mainnet'}")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize KuCoin client: {e}")
            return False

    async def close(self) -> None:
        """Close the KuCoin client connection."""
        try:
            if self.client:
                # Close any active connections
                if hasattr(self.client, 'close'):
                    await self.client.close()
                self.client = None
                logger.info("KuCoin client connection closed")
        except Exception as e:
            logger.error(f"Error closing KuCoin client: {e}")

    def get_spot_service(self):
        """Get spot trading service."""
        if not self.client:
            raise RuntimeError("KuCoin client not initialized")
        return self.client.rest_service().get_spot_service()

    def get_futures_service(self):
        """Get futures trading service."""
        if not self.client:
            raise RuntimeError("KuCoin client not initialized")
        return self.client.rest_service().get_futures_service()

    def get_market_service(self):
        """Get market data service (uses spot service for market data)."""
        if not self.client:
            raise RuntimeError("KuCoin client not initialized")
        return self.client.rest_service().get_spot_service()

    async def test_connection(self) -> bool:
        """
        Test the KuCoin API connection.

        Returns:
            True if connection is working, False otherwise
        """
        try:
            if not self.client:
                logger.error("KuCoin client not initialized")
                return False

            market_api = self.get_market_service().get_market_api()

            logger.info("KuCoin connection test successful")
            return True

        except Exception as e:
            logger.error(f"KuCoin connection test failed: {e}")
            return False
