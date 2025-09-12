"""
Discord Signal Validator

This module handles signal validation and sanitization for Discord trading signals.
"""

import logging
import re
from typing import Dict, Any, Optional, Tuple, List

logger = logging.getLogger(__name__)


class SignalValidator:
    """
    Validates and sanitizes Discord trading signals.

    Responsibilities:
    - Validate signal structure and content
    - Sanitize signal data
    - Extract coin symbols from content
    - Validate position types and prices
    """

    def __init__(self):
        """Initialize the signal validator."""
        self.supported_order_types = ['LIMIT', 'MARKET', 'SPOT']
        self.supported_position_types = ['LONG', 'SHORT']

    def _extract_coin_symbol_from_content(self, content: str) -> Optional[str]:
        """
        Extract coin symbol from alert content using regex patterns.

        Args:
            content: The alert content to parse

        Returns:
            Extracted coin symbol or None if not found
        """
        if not content:
            return None

        # Common coin symbol patterns
        patterns = [
            r'\b(BTC|ETH|SOL|ADA|DOT|LINK|UNI|AAVE|MATIC|AVAX|NEAR|FTM|ALGO|ATOM|XRP)\b',
            r'\b(DOGE|SHIB|PEPE|BONK|WIF|FLOKI|TOSHI|TURBO|HYPE|FARTCOIN)\b',
            r'\b([A-Z]{2,10})\b'  # Generic 2-10 letter uppercase pattern
        ]

        for pattern in patterns:
            match = re.search(pattern, content.upper())
            if match:
                symbol = match.group(1)
                logger.info(f"Extracted coin symbol: {symbol}")
                return symbol

        logger.warning(f"No coin symbol found in content: {content}")
        return None

    def validate_parsed_signal(self, parsed_signal: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """
        Validate a parsed signal structure.

        Args:
            parsed_signal: The parsed signal to validate

        Returns:
            Tuple of (is_valid, error_message)
        """
        if not parsed_signal:
            return False, "Parsed signal is empty"

        # Check required fields
        required_fields = ['coin_symbol', 'position_type', 'entry_prices']
        for field in required_fields:
            if field not in parsed_signal:
                return False, f"Missing required field: {field}"

        # Validate coin symbol
        coin_symbol = parsed_signal.get('coin_symbol', '').upper()
        if not coin_symbol or len(coin_symbol) < 2:
            return False, f"Invalid coin symbol: {coin_symbol}"

        # Validate position type
        position_type = parsed_signal.get('position_type', '').upper()
        if position_type not in self.supported_position_types:
            return False, f"Invalid position type: {position_type}"

        # Validate entry prices
        entry_prices = parsed_signal.get('entry_prices')
        if not entry_prices or not isinstance(entry_prices, list):
            return False, "Entry prices must be a non-empty list"

        for price in entry_prices:
            if not isinstance(price, (int, float)) or price <= 0:
                return False, f"Invalid entry price: {price}"

        # Validate order type if present
        order_type = parsed_signal.get('order_type', 'LIMIT').upper()
        if order_type not in self.supported_order_types:
            return False, f"Invalid order type: {order_type}"

        # Validate stop loss if present
        stop_loss = parsed_signal.get('stop_loss')
        if stop_loss is not None:
            if isinstance(stop_loss, (int, float)) and stop_loss <= 0:
                return False, f"Invalid stop loss price: {stop_loss}"

        # Validate take profits if present
        take_profits = parsed_signal.get('take_profits')
        if take_profits is not None:
            if not isinstance(take_profits, list):
                return False, "Take profits must be a list"
            for tp in take_profits:
                if not isinstance(tp, (int, float)) or tp <= 0:
                    return False, f"Invalid take profit price: {tp}"

        return True, None

    def sanitize_signal_content(self, content: str) -> str:
        """
        Sanitize signal content by removing problematic characters and formatting.

        Args:
            content: Raw signal content

        Returns:
            Sanitized content
        """
        if not content:
            return ""

        # Remove or replace problematic characters
        sanitized = content.replace('"', '"').replace('"', '"')  # Smart quotes to regular quotes
        sanitized = sanitized.replace(''', "'").replace(''', "'")  # Smart apostrophes to regular apostrophes
        sanitized = sanitized.replace('–', '-').replace('—', '-')  # Em dashes to regular dashes
        sanitized = sanitized.replace('…', '...')  # Ellipsis to three dots

        zero_width_chars = [
            '\u200B',  # Zero Width Space
            '\u200C',  # Zero Width Non-Joiner
            '\u200D',  # Zero Width Joiner
            '\u200E',  # Left-to-Right Mark
            '\u200F',  # Right-to-Left Mark
            '\u2060',  # Word Joiner
            '\u2061',  # Function Application
            '\u2062',  # Invisible Times
            '\u2063',  # Invisible Separator
            '\u2064',  # Invisible Plus
            '\u2066',  # Left-to-Right Isolate
            '\u2067',  # Right-to-Left Isolate
            '\u2068',  # First Strong Isolate
            '\u2069',  # Pop Directional Isolate
            '\uFEFF',  # Zero Width No-Break Space (BOM)
        ]

        for char in zero_width_chars:
            sanitized = sanitized.replace(char, '')

        # Remove any other non-ASCII characters that might cause issues
        sanitized = ''.join(char for char in sanitized if ord(char) < 128)

        return sanitized.strip()

    def validate_alert_content(self, content: str) -> Tuple[bool, Optional[str]]:
        """
        Validate alert content structure.

        Args:
            content: Alert content to validate

        Returns:
            Tuple of (is_valid, error_message)
        """
        if not content or not isinstance(content, str):
            return False, "Alert content must be a non-empty string"

        if len(content.strip()) < 5:
            return False, "Alert content too short"

        # Check for basic structure indicators
        has_coin_symbol = self._extract_coin_symbol_from_content(content) is not None
        if not has_coin_symbol:
            return False, "No coin symbol found in alert content"

        return True, None

    def extract_action_from_alert(self, content: str) -> Dict[str, Any]:
        """
        Extract action information from alert content.

        Args:
            content: Alert content to parse

        Returns:
            Dictionary containing action information
        """
        content_lower = content.lower()
        coin_symbol = self._extract_coin_symbol_from_content(content)

        # Define regex patterns for different action types
        patterns = {
            'liquidation': r'liquidated|liquidation',
            'partial_fill': r'partial\s+fill',
            'tp1and_sl_to_be': r'tp1\s*&\s*stops?\s+moved\s+to\s+be|tp1\s*&\s*stops?\s+to\s+be',
            'stop_loss_hit': r'stopped\s+out|closed\s+in\s+profits|closed\s+in\s+loss|closed\s+be/in\s+slight\s+loss',
            'leverage_update': r'leverage\s*to\s*(\d+x)',
            'trailing_stop_loss': r'trailing\s+sl\s+at\s+(\d+\.?\d*%)',
            'position_size_adjustment': r'(double|increase|decrease)\s+position\s+size',
            'stop_loss_update': r'stoploss\s+moved\s+to\s+([-+]?\d*\.?\d+)',
            'stops_to_be': r'\b(stops?|sl)\b.*\bbe\b|stopped\s+be',
            'stops_to_price': r'\b(stop\w*|sl)\b.*\bto\b\s*(-?\d+(\.\d+)?)',
            'dca_to_entry': r'\bdca\b.*\bentry\b.*?(\d+\.?\d+)(?:\s|$)',
            'take_profit_1': r'tp1\b',
            'take_profit_2': r'tp2\b',
            'limit_order_cancelled': r'limit\s+order\s+cancelled?',
            'limit_order_filled': r'limit\s+order\s+filled',
            'position_closed': r'closed\s+be|closed\s+in\s+profits?|closed\s+in\s+loss'
        }

        # Check each pattern and return the first match
        for action_type, pattern in patterns.items():
            match = re.search(pattern, content_lower)
            if match:
                action_data = {
                    'action_type': action_type,
                    'coin_symbol': coin_symbol,
                    'content': content
                }

                # Extract additional data for specific action types
                if action_type == 'leverage_update':
                    action_data['leverage'] = int(match.group(1).replace('x', ''))
                elif action_type == 'trailing_stop_loss':
                    action_data['trailing_percentage'] = float(match.group(1).replace('%', ''))
                elif action_type == 'stop_loss_update':
                    action_data['stop_loss_price'] = float(match.group(1))
                elif action_type == 'stops_to_price':
                    action_data['stop_loss_price'] = float(match.group(2))
                elif action_type == 'dca_to_entry':
                    action_data['entry_price'] = float(match.group(1))

                # Add action descriptions and binance actions for new types
                if action_type == 'take_profit_1':
                    action_data['action_description'] = f'Take Profit 1 hit for {coin_symbol}'
                    action_data['binance_action'] = 'PARTIAL_SELL'
                    action_data['position_status'] = 'PARTIALLY_CLOSED'
                    action_data['reason'] = 'TP1 target reached'
                elif action_type == 'take_profit_2':
                    action_data['action_description'] = f'Take Profit 2 hit for {coin_symbol}'
                    action_data['binance_action'] = 'PARTIAL_SELL'
                    action_data['position_status'] = 'PARTIALLY_CLOSED'
                    action_data['reason'] = 'TP2 target reached'
                elif action_type == 'limit_order_cancelled':
                    action_data['action_description'] = f'Limit order cancelled for {coin_symbol}'
                    action_data['binance_action'] = 'CANCEL_ORDER'
                    action_data['position_status'] = 'CLOSED'
                    action_data['reason'] = 'Cancel limit order'
                elif action_type == 'position_closed':
                    action_data['action_description'] = f'Position closed for {coin_symbol}'
                    action_data['binance_action'] = 'MARKET_SELL'
                    action_data['position_status'] = 'CLOSED'
                    action_data['reason'] = 'Position closed'
                elif action_type == 'stops_to_be':
                    action_data['action_description'] = f'Stop loss moved to break even for {coin_symbol}'
                    action_data['binance_action'] = 'UPDATE_STOP_ORDER'
                    action_data['position_status'] = 'OPEN'
                    action_data['stop_loss'] = 'BE'
                    action_data['reason'] = 'Risk management - move to break even'
                elif action_type == 'tp1and_sl_to_be':
                    action_data['action_description'] = f'TP1 hit and stop loss moved to break even for {coin_symbol}'
                    action_data['binance_action'] = 'PARTIAL_SELL_AND_UPDATE_STOP_ORDER'
                    action_data['position_status'] = 'PARTIALLY_CLOSED'
                    action_data['stop_loss'] = 'BE'
                    action_data['reason'] = 'TP1 hit and risk management - move to break even'
                elif action_type == 'limit_order_filled':
                    action_data['action_description'] = f'Limit order filled for {coin_symbol}'
                    action_data['binance_action'] = 'NO_ACTION'
                    action_data['position_status'] = 'OPEN'
                    action_data['reason'] = 'Limit order filled - position now open'
                elif action_type == 'stop_loss_hit':
                    action_data['action_description'] = f'Position closed for {coin_symbol}'
                    action_data['binance_action'] = 'MARKET_SELL'
                    action_data['position_status'] = 'CLOSED'
                    action_data['reason'] = 'Position closed'

                return action_data

        # Default action if no specific pattern matches
        return {
            'action_type': 'unknown',
            'coin_symbol': coin_symbol,
            'content': content
        }
