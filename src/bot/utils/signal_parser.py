"""
Signal parsing utilities for the trading bot.

This module contains utility functions for parsing and handling signal data
from various sources including JSON strings and Binance API responses.
"""

import json
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)


class SignalParser:
    """
    Utility class for parsing signal data from various formats.
    """

    @staticmethod
    def parse_parsed_signal(parsed_signal_data) -> Dict[str, Any]:
        """
        Parse the parsed_signal JSON string into a dictionary.

        Args:
            parsed_signal_data: The signal data to parse (dict, str, or other)

        Returns:
            Dictionary containing the parsed signal data
        """
        if isinstance(parsed_signal_data, dict):
            return parsed_signal_data
        elif isinstance(parsed_signal_data, str):
            try:
                return json.loads(parsed_signal_data)
            except json.JSONDecodeError:
                logger.warning(f"Could not parse parsed_signal JSON: {parsed_signal_data}")
                return {}
        else:
            logger.warning(f"Unexpected parsed_signal type: {type(parsed_signal_data)}")
            return {}

    @staticmethod
    def safe_parse_binance_response(binance_response) -> Dict:
        """
        Safely parse binance_response field which is stored as text but may contain JSON.

        Args:
            binance_response: The Binance API response to parse

        Returns:
            Dictionary containing the parsed response data
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
