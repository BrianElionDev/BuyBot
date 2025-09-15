"""
Exchange Factory

Factory for creating exchange instances.
Following Clean Code principles with clear factory pattern.
"""

from typing import Dict, Type
import logging
from .exchange_base import ExchangeBase
from .exchange_config import ExchangeConfig

logger = logging.getLogger(__name__)


class ExchangeFactory:
    """
    Factory for creating exchange instances.

    Centralizes exchange creation logic and provides a clean
    interface for instantiating different exchange types.
    """

    def __init__(self):
        """Initialize the exchange factory."""
        self._exchanges: Dict[str, Type[ExchangeBase]] = {}

    def register_exchange(self, name: str, exchange_class: Type[ExchangeBase]) -> None:
        """
        Register an exchange class with the factory.

        Args:
            name: Exchange name identifier
            exchange_class: Exchange class to register
        """
        if not issubclass(exchange_class, ExchangeBase):
            raise ValueError(f"Exchange class must inherit from ExchangeBase")

        self._exchanges[name.lower()] = exchange_class
        logger.info(f"Registered exchange: {name}")

    def create_exchange(self, name: str, config: ExchangeConfig) -> ExchangeBase:
        """
        Create an exchange instance.

        Args:
            name: Exchange name identifier
            config: Exchange configuration

        Returns:
            Exchange instance

        Raises:
            ValueError: If exchange name is not registered
        """
        exchange_name = name.lower()

        if exchange_name not in self._exchanges:
            available = list(self._exchanges.keys())
            raise ValueError(f"Exchange '{name}' not found. Available: {available}")

        exchange_class = self._exchanges[exchange_name]
        exchange = exchange_class(config.api_key, config.api_secret, config.is_testnet)

        logger.info(f"Created exchange instance: {name}")
        return exchange

    def get_available_exchanges(self) -> list[str]:
        """
        Get list of available exchange names.

        Returns:
            List of registered exchange names
        """
        return list(self._exchanges.keys())

    def is_exchange_available(self, name: str) -> bool:
        """
        Check if an exchange is available.

        Args:
            name: Exchange name to check

        Returns:
            True if exchange is available, False otherwise
        """
        return name.lower() in self._exchanges


# Global factory instance
_exchange_factory = ExchangeFactory()


def get_exchange_factory() -> ExchangeFactory:
    """
    Get the global exchange factory instance.

    Returns:
        Global exchange factory
    """
    return _exchange_factory


def register_exchange(name: str, exchange_class: Type[ExchangeBase]) -> None:
    """
    Register an exchange with the global factory.

    Args:
        name: Exchange name identifier
        exchange_class: Exchange class to register
    """
    _exchange_factory.register_exchange(name, exchange_class)


def create_exchange(name: str, config: ExchangeConfig) -> ExchangeBase:
    """
    Create an exchange using the global factory.

    Args:
        name: Exchange name identifier
        config: Exchange configuration

    Returns:
        Exchange instance
    """
    return _exchange_factory.create_exchange(name, config)
