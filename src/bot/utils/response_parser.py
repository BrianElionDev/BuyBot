"""
Response parsing utilities for the trading bot.

This module contains utility functions for parsing and handling various
API responses from Binance and other services.
"""

import json
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class ResponseParser:
    """
    Utility class for parsing API responses.
    """

    @staticmethod
    def parse_binance_response(binance_response) -> Dict[str, Any]:
        """
        Parse Binance API response safely.

        Args:
            binance_response: The response to parse (dict, str, or other)

        Returns:
            Dictionary containing the parsed response
        """
        if isinstance(binance_response, dict):
            return binance_response
        elif isinstance(binance_response, str):
            # Handle empty or invalid strings
            if not binance_response or binance_response.strip() == '':
                return {}

            # Try to parse as JSON
            try:
                return json.loads(binance_response.strip())
            except (json.JSONDecodeError, ValueError):
                # If it's not valid JSON, treat it as a plain text error message
                return {"error": binance_response.strip()}
        else:
            return {}

    @staticmethod
    def extract_order_id(response: Dict[str, Any]) -> Optional[str]:
        """
        Extract order ID from a Binance response.

        Args:
            response: The Binance API response

        Returns:
            Order ID as string or None if not found
        """
        if not response:
            return None

        # Try different possible field names
        order_id = response.get('orderId') or response.get('order_id') or response.get('id')

        if order_id:
            return str(order_id)

        return None

    @staticmethod
    def extract_error_message(response: Dict[str, Any]) -> Optional[str]:
        """
        Extract error message from a Binance response.

        Args:
            response: The Binance API response

        Returns:
            Error message as string or None if no error
        """
        if not response:
            return None

        # Try different possible field names
        error_msg = (
            response.get('error') or
            response.get('msg') or
            response.get('message') or
            response.get('errorMessage')
        )

        if error_msg:
            return str(error_msg)

        return None

    @staticmethod
    def is_success_response(response: Dict[str, Any]) -> bool:
        """
        Check if a response indicates success.

        Args:
            response: The API response to check

        Returns:
            True if response indicates success, False otherwise
        """
        if not response:
            return False

        # Check for error indicators
        if 'error' in response or 'msg' in response or 'message' in response:
            return False

        # Check for success indicators
        if 'orderId' in response or 'id' in response:
            return True

        # If no clear indicators, assume success if no error
        return 'error' not in response
