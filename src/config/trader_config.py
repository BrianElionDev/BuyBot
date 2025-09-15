"""
Trader Configuration Module

This module centralizes trader-to-exchange mapping and provides utilities
for determining which exchange should handle signals from specific traders.
"""

from enum import Enum
import logging

logger = logging.getLogger(__name__)


class ExchangeType(Enum):
    """Supported exchange types"""
    BINANCE = "binance"
    KUCOIN = "kucoin"


class TraderConfig:
    """Configuration for trader-to-exchange mapping"""

    TRADER_EXCHANGE_MAPPING = {
        "@Johnny": ExchangeType.BINANCE,
        "@-Johnny": ExchangeType.BINANCE,
        "@-Tareeq": ExchangeType.KUCOIN,
        "@Tareeq": ExchangeType.KUCOIN,
    }

    DEFAULT_EXCHANGE = ExchangeType.BINANCE

    @classmethod
    def get_exchange_for_trader(cls, trader: str) -> ExchangeType:
        """
        Get the exchange type for a given trader.

        Args:
            trader: The trader identifier (e.g., "@Johnny", "@-Tareeq")

        Returns:
            ExchangeType: The exchange that should handle this trader's signals
        """
        if not trader:
            logger.warning("Empty trader provided, using default exchange")
            return cls.DEFAULT_EXCHANGE

        normalized_trader = trader.strip()

        if normalized_trader in cls.TRADER_EXCHANGE_MAPPING:
            exchange = cls.TRADER_EXCHANGE_MAPPING[normalized_trader]
            logger.info(f"Trader {trader} mapped to {exchange.value} exchange")
            return exchange

        # Check for partial matches
        for mapped_trader, exchange in cls.TRADER_EXCHANGE_MAPPING.items():
            if normalized_trader in mapped_trader or mapped_trader in normalized_trader:
                logger.info(f"Trader {trader} partially matched to {mapped_trader}, using {exchange.value} exchange")
                return exchange

        logger.warning(f"Unknown trader {trader}, using default exchange {cls.DEFAULT_EXCHANGE.value}")
        return cls.DEFAULT_EXCHANGE

    @classmethod
    def is_trader_supported(cls, trader: str) -> bool:
        """
        Check if a trader is supported (has a specific exchange mapping).

        Args:
            trader: The trader identifier

        Returns:
            bool: True if trader is supported, False otherwise
        """
        if not trader:
            return False

        normalized_trader = trader.strip()

        if normalized_trader in cls.TRADER_EXCHANGE_MAPPING:
            return True

        for mapped_trader in cls.TRADER_EXCHANGE_MAPPING:
            if normalized_trader in mapped_trader or mapped_trader in normalized_trader:
                return True

        return False

    @classmethod
    def get_supported_traders(cls) -> list:
        """
        Get list of all supported traders.

        Returns:
            list: List of supported trader identifiers
        """
        return list(cls.TRADER_EXCHANGE_MAPPING.keys())

    @classmethod
    def get_traders_for_exchange(cls, exchange: ExchangeType) -> list:
        """
        Get list of traders that use a specific exchange.

        Args:
            exchange: The exchange type

        Returns:
            list: List of trader identifiers using this exchange
        """
        return [
            trader for trader, ex in cls.TRADER_EXCHANGE_MAPPING.items()
            if ex == exchange
        ]

    @classmethod
    def add_trader_mapping(cls, trader: str, exchange: ExchangeType) -> None:
        """
        Add a new trader-to-exchange mapping.

        Args:
            trader: The trader identifier
            exchange: The exchange type
        """
        cls.TRADER_EXCHANGE_MAPPING[trader] = exchange
        logger.info(f"Added trader mapping: {trader} -> {exchange.value}")

    @classmethod
    def remove_trader_mapping(cls, trader: str) -> bool:
        """
        Remove a trader-to-exchange mapping.

        Args:
            trader: The trader identifier

        Returns:
            bool: True if trader was removed, False if not found
        """
        if trader in cls.TRADER_EXCHANGE_MAPPING:
            del cls.TRADER_EXCHANGE_MAPPING[trader]
            logger.info(f"Removed trader mapping: {trader}")
            return True
        return False


def get_exchange_for_trader(trader: str) -> ExchangeType:
    """
    Convenience function to get exchange for a trader.

    Args:
        trader: The trader identifier

    Returns:
        ExchangeType: The exchange that should handle this trader's signals
    """
    return TraderConfig.get_exchange_for_trader(trader)


def is_trader_supported(trader: str) -> bool:
    """
    Convenience function to check if a trader is supported.

    Args:
        trader: The trader identifier

    Returns:
        bool: True if trader is supported, False otherwise
    """
    return TraderConfig.is_trader_supported(trader)
