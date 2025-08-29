"""
Exchange Configuration

Centralized configuration for all exchange-related settings.
Following Clean Code principles with clear, focused configuration.
"""

from dataclasses import dataclass
from typing import Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)


@dataclass
class ExchangeConfig:
    """
    Configuration for exchange operations.

    Centralizes all exchange-related configuration to avoid
    scattered configuration throughout the codebase.
    """

    # API Configuration
    api_key: str
    api_secret: str
    is_testnet: bool = False

    # Connection Settings
    connection_timeout: int = 30
    request_timeout: int = 10
    max_retries: int = 3
    retry_delay: float = 1.0

    # Rate Limiting
    requests_per_minute: int = 1200
    requests_per_second: int = 20

    # Precision Settings
    default_quantity_precision: int = 3
    default_price_precision: int = 2

    # Order Settings
    default_order_timeout: int = 60
    max_order_retries: int = 3

    # Validation Settings
    enable_symbol_validation: bool = True
    enable_precision_validation: bool = True
    enable_balance_validation: bool = True

    def __post_init__(self):
        """Validate configuration after initialization."""
        if not self.api_key or not self.api_secret:
            raise ValueError("API key and secret are required")

        if self.connection_timeout <= 0:
            raise ValueError("Connection timeout must be positive")

        if self.request_timeout <= 0:
            raise ValueError("Request timeout must be positive")

        if self.max_retries < 0:
            raise ValueError("Max retries cannot be negative")

        if self.retry_delay < 0:
            raise ValueError("Retry delay cannot be negative")

    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary."""
        return {
            'api_key': self.api_key,
            'api_secret': '***' if self.api_secret else None,  # Hide secret
            'is_testnet': self.is_testnet,
            'connection_timeout': self.connection_timeout,
            'request_timeout': self.request_timeout,
            'max_retries': self.max_retries,
            'retry_delay': self.retry_delay,
            'requests_per_minute': self.requests_per_minute,
            'requests_per_second': self.requests_per_second,
            'default_quantity_precision': self.default_quantity_precision,
            'default_price_precision': self.default_price_precision,
            'default_order_timeout': self.default_order_timeout,
            'max_order_retries': self.max_order_retries,
            'enable_symbol_validation': self.enable_symbol_validation,
            'enable_precision_validation': self.enable_precision_validation,
            'enable_balance_validation': self.enable_balance_validation
        }

    def log_config(self) -> None:
        """Log configuration (without sensitive data)."""
        config_dict = self.to_dict()
        logger.info(f"Exchange configuration: {config_dict}")


# Default precision rules for common futures symbols
DEFAULT_PRECISION_RULES = {
    'BTCUSDT': {'quantity': 3, 'price': 2},
    'ETHUSDT': {'quantity': 3, 'price': 2},
    'ADAUSDT': {'quantity': 0, 'price': 5},
    'SOLUSDT': {'quantity': 2, 'price': 3},
    'DOGEUSDT': {'quantity': 0, 'price': 6},
    'XRPUSDT': {'quantity': 1, 'price': 5},
    'DOTUSDT': {'quantity': 2, 'price': 3},
    'LINKUSDT': {'quantity': 2, 'price': 3},
    'AVAXUSDT': {'quantity': 2, 'price': 3},
    'LTCUSDT': {'quantity': 3, 'price': 2},
    'BNBUSDT': {'quantity': 2, 'price': 2},
    'MATICUSDT': {'quantity': 0, 'price': 5},
    'ATOMUSDT': {'quantity': 2, 'price': 3},
    'UNIUSDT': {'quantity': 1, 'price': 4},
    'SUSHIUSDT': {'quantity': 1, 'price': 4},
}


def get_precision_rules() -> Dict[str, Dict[str, int]]:
    """
    Get precision rules for symbols.

    Returns:
        Dict mapping symbol to precision rules
    """
    return DEFAULT_PRECISION_RULES.copy()


def format_value(value: float, step_size: str) -> str:
    """
    Format a value to be a valid multiple of a given step size.

    Uses Decimal for precision to avoid floating point errors.

    Args:
        value: Value to format
        step_size: Step size string

    Returns:
        Formatted value string
    """
    from decimal import Decimal

    value_dec = Decimal(str(value))
    step_dec = Decimal(str(step_size))

    # Perform quantization
    quantized_value = (value_dec // step_dec) * step_dec

    # Format the output string to match the precision of the step_size
    return f"{quantized_value:.{step_dec.normalize().as_tuple().exponent * -1}f}"
