"""
KuCoin Precision Configuration

KuCoin-specific precision and validation utilities.
Following Clean Code principles with clear precision handling.
"""

import json
import os
from typing import Dict, Optional, Any
import logging

logger = logging.getLogger(__name__)


class KucoinPrecision:
    """
    KuCoin precision and validation handler.

    Provides precision validation and formatting for KuCoin trading operations.
    """

    def __init__(self):
        """Initialize KuCoin precision handler."""
        self.precision_data: Dict[str, Any] = {}
        self._load_precision_data()

    def _load_precision_data(self):
        """Load precision data from JSON file."""
        try:
            current_dir = os.path.dirname(os.path.abspath(__file__))
            precision_file = os.path.join(current_dir, "kucoin_precision.json")

            if os.path.exists(precision_file):
                with open(precision_file, 'r') as f:
                    self.precision_data = json.load(f)
                logger.info("KuCoin precision data loaded successfully")
            else:
                logger.warning("KuCoin precision file not found, using defaults")
                self.precision_data = {"symbols": {}}

        except Exception as e:
            logger.error(f"Failed to load KuCoin precision data: {e}")
            self.precision_data = {"symbols": {}}

    def get_symbol_info(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Get symbol precision information.

        Args:
            symbol: Trading pair symbol (e.g., "BTC-USDT")

        Returns:
            Symbol information dict or None if not found
        """
        return self.precision_data.get("symbols", {}).get(symbol)

    def validate_quantity(self, symbol: str, quantity: float) -> bool:
        """
        Validate quantity against symbol precision rules.

        Args:
            symbol: Trading pair symbol
            quantity: Quantity to validate

        Returns:
            True if valid, False otherwise
        """
        try:
            symbol_info = self.get_symbol_info(symbol)
            if not symbol_info:
                logger.warning(f"No precision data for symbol {symbol}")
                return True  # Allow if no data available

            min_size = float(symbol_info.get("baseMinSize", 0))
            max_size = float(symbol_info.get("baseMaxSize", float('inf')))
            increment = float(symbol_info.get("baseIncrement", 0.00001))

            if quantity < min_size:
                logger.warning(f"Quantity {quantity} below minimum {min_size} for {symbol}")
                return False

            if quantity > max_size:
                logger.warning(f"Quantity {quantity} above maximum {max_size} for {symbol}")
                return False

            # Check increment precision
            if increment > 0:
                remainder = quantity % increment
                if remainder > 1e-10:  # Allow for floating point precision
                    logger.warning(f"Quantity {quantity} not aligned with increment {increment} for {symbol}")
                    return False

            return True

        except Exception as e:
            logger.error(f"Error validating quantity for {symbol}: {e}")
            return False

    def validate_price(self, symbol: str, price: float) -> bool:
        """
        Validate price against symbol precision rules.

        Args:
            symbol: Trading pair symbol
            price: Price to validate

        Returns:
            True if valid, False otherwise
        """
        try:
            symbol_info = self.get_symbol_info(symbol)
            if not symbol_info:
                logger.warning(f"No precision data for symbol {symbol}")
                return True  # Allow if no data available

            min_size = float(symbol_info.get("quoteMinSize", 0))
            increment = float(symbol_info.get("priceIncrement", 0.01))

            if price < min_size:
                logger.warning(f"Price {price} below minimum {min_size} for {symbol}")
                return False

            # Check increment precision
            if increment > 0:
                remainder = price % increment
                if remainder > 1e-10:  # Allow for floating point precision
                    logger.warning(f"Price {price} not aligned with increment {increment} for {symbol}")
                    return False

            return True

        except Exception as e:
            logger.error(f"Error validating price for {symbol}: {e}")
            return False

    def format_quantity(self, symbol: str, quantity: float) -> str:
        """
        Format quantity according to symbol precision rules.

        Args:
            symbol: Trading pair symbol
            quantity: Quantity to format

        Returns:
            Formatted quantity string
        """
        try:
            symbol_info = self.get_symbol_info(symbol)
            if not symbol_info:
                return str(quantity)

            increment = float(symbol_info.get("baseIncrement", 0.00001))

            if increment > 0:
                # Round to nearest increment
                formatted = round(quantity / increment) * increment
                # Determine decimal places based on increment
                decimal_places = len(str(increment).split('.')[-1]) if '.' in str(increment) else 0
                return f"{formatted:.{decimal_places}f}"

            return str(quantity)

        except Exception as e:
            logger.error(f"Error formatting quantity for {symbol}: {e}")
            return str(quantity)

    def format_price(self, symbol: str, price: float) -> str:
        """
        Format price according to symbol precision rules.

        Args:
            symbol: Trading pair symbol
            price: Price to format

        Returns:
            Formatted price string
        """
        try:
            symbol_info = self.get_symbol_info(symbol)
            if not symbol_info:
                return str(price)

            increment = float(symbol_info.get("priceIncrement", 0.01))

            if increment > 0:
                # Round to nearest increment
                formatted = round(price / increment) * increment
                # Determine decimal places based on increment
                decimal_places = len(str(increment).split('.')[-1]) if '.' in str(increment) else 0
                return f"{formatted:.{decimal_places}f}"

            return str(price)

        except Exception as e:
            logger.error(f"Error formatting price for {symbol}: {e}")
            return str(price)

    def is_symbol_supported(self, symbol: str) -> bool:
        """
        Check if symbol is supported for trading.

        Args:
            symbol: Trading pair symbol

        Returns:
            True if supported, False otherwise
        """
        symbol_info = self.get_symbol_info(symbol)
        if not symbol_info:
            return False

        return symbol_info.get("enableTrading", False)


# Global instance
kucoin_precision = KucoinPrecision()


def is_symbol_supported(symbol: str) -> bool:
    """
    Check if KuCoin symbol is supported.

    Args:
        symbol: Trading pair symbol

    Returns:
        True if supported, False otherwise
    """
    return kucoin_precision.is_symbol_supported(symbol)


def validate_quantity(symbol: str, quantity: float) -> bool:
    """
    Validate KuCoin quantity.

    Args:
        symbol: Trading pair symbol
        quantity: Quantity to validate

    Returns:
        True if valid, False otherwise
    """
    return kucoin_precision.validate_quantity(symbol, quantity)


def validate_price(symbol: str, price: float) -> bool:
    """
    Validate KuCoin price.

    Args:
        symbol: Trading pair symbol
        price: Price to validate

    Returns:
        True if valid, False otherwise
    """
    return kucoin_precision.validate_price(symbol, price)


def format_quantity(symbol: str, quantity: float) -> str:
    """
    Format KuCoin quantity.

    Args:
        symbol: Trading pair symbol
        quantity: Quantity to format

    Returns:
        Formatted quantity string
    """
    return kucoin_precision.format_quantity(symbol, quantity)


def format_price(symbol: str, price: float) -> str:
    """
    Format KuCoin price.

    Args:
        symbol: Trading pair symbol
        price: Price to format

    Returns:
        Formatted price string
    """
    return kucoin_precision.format_price(symbol, price)
