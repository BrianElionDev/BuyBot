"""
Trader Configuration Service

This service manages trader-to-exchange configurations from the database,
providing a centralized way to handle trader configurations dynamically.
"""

import logging
import time
import unicodedata
from typing import Dict, List, Optional, Set
from dataclasses import dataclass
from enum import Enum

from src.config.runtime_config import init_runtime_config, runtime_config as _runtime_config
runtime_config = _runtime_config

logger = logging.getLogger(__name__)


class ExchangeType(Enum):
    """Supported exchange types"""
    BINANCE = "binance"
    KUCOIN = "kucoin"


@dataclass
class TraderConfig:
    """Represents a trader's exchange configuration"""
    trader_id: str
    exchange: ExchangeType
    leverage: int
    position_size: float
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    updated_by: Optional[str] = None


class TraderConfigService:
    """
    Service for managing trader-to-exchange configurations from the database.
    Provides caching and fallback mechanisms for robust operation.
    """

    def __init__(self, cache_ttl_seconds: int = 300):
        """
        Initialize the trader config service.

        Args:
            cache_ttl_seconds: Cache TTL in seconds (default: 5 minutes)
        """
        self.cache_ttl = cache_ttl_seconds
        self._config_cache: Dict[str, TraderConfig] = {}
        self._cache_timestamps: Dict[str, float] = {}
        self._supported_traders_cache: Optional[Set[str]] = None
        self._supported_traders_timestamp: Optional[float] = None
        # Ensure runtime_config is initialized if possible
        try:
            from config.settings import SUPABASE_URL, SUPABASE_KEY
            if SUPABASE_URL and SUPABASE_KEY and _runtime_config is None:
                init_runtime_config(SUPABASE_URL, SUPABASE_KEY)
                from src.config.runtime_config import runtime_config as _rc
                globals()['runtime_config'] = _rc
        except Exception:
            # Defer to callers; logs will show if still missing
            pass

    def _is_cache_valid(self, cache_key: str) -> bool:
        """Check if cache entry is still valid."""
        if cache_key not in self._cache_timestamps:
            return False
        return time.time() - self._cache_timestamps[cache_key] < self.cache_ttl

    def _get_cache_key(self, trader_id: str) -> str:
        """Generate cache key for trader."""
        return f"trader_config:{trader_id}"

    def _canonical(self, trader_id: str) -> str:
        """Return a canonical, case-insensitive trader id without leading @ or -.

        This method aggressively normalizes Unicode to avoid subtle mismatches caused
        by zero-width or formatting characters occasionally present in Discord names.
        """
        try:
            s = trader_id or ""
            s = unicodedata.normalize("NFKC", s)
            s = "".join(
                ch
                for ch in s
                if unicodedata.category(ch) not in ("Cf", "Cc", "Cs")
            )
            return s.strip().lstrip("@-").lower()
        except Exception:
            return ""

    def _variants(self, trader_id: str) -> List[str]:
        """Generate common variants of a trader id for robust lookups."""
        original = (trader_id or "").strip()
        base = self._canonical(original)

        candidates = {
            original,
            original.lstrip("@-"),
            original.lower(),
            base,
            base.capitalize(),
            f"@{base}",
            f"@-{base}",
            f"-{base}",
        }

        return [c for c in candidates if c]

    async def get_trader_config(self, trader_id: str) -> Optional[TraderConfig]:
        """
        Get trader configuration from database with caching.

        Args:
            trader_id: The trader identifier

        Returns:
            TraderConfig or None if not found
        """
        if not trader_id:
            logger.warning("Empty trader_id provided")
            return None

        cache_key = self._get_cache_key(trader_id)

        # Check cache first
        if cache_key in self._config_cache and self._is_cache_valid(cache_key):
            logger.debug(f"Using cached config for trader {trader_id}")
            return self._config_cache[cache_key]

        # Fetch from database
        try:
            if not runtime_config:
                logger.error("Runtime config not initialized")
                return None

            # First, try exact/variant matching using IN
            variants = self._variants(trader_id)
            response = runtime_config.supabase.table("trader_exchange_config").select(
                "trader_id, exchange, leverage, position_size, created_at, updated_at, updated_by"
            ).in_("trader_id", variants).execute()

            data = getattr(response, 'data', None)

            # Fallback: case-insensitive match on normalized value if no direct hit
            if not data:
                canon = self._canonical(trader_id)
                if canon:
                    response = runtime_config.supabase.table("trader_exchange_config").select(
                        "trader_id, exchange, leverage, position_size, created_at, updated_at, updated_by"
                    ).ilike("trader_id", canon).execute()
                    data = getattr(response, 'data', None)

            if data:
                config_data = response.data[0]
                config = TraderConfig(
                    trader_id=config_data["trader_id"],
                    exchange=ExchangeType(config_data["exchange"]),
                    leverage=config_data["leverage"],
                    position_size=float(config_data.get("position_size", 100.0)),
                    created_at=config_data.get("created_at"),
                    updated_at=config_data.get("updated_at"),
                    updated_by=config_data.get("updated_by")
                )

                # Cache the result
                self._config_cache[cache_key] = config
                self._cache_timestamps[cache_key] = time.time()

                logger.info(f"Loaded config for trader {trader_id}: {config.exchange.value} @ {config.leverage}x, position_size=${config.position_size}")
                return config
            else:
                logger.warning(f"No configuration found for trader {trader_id}")
                return None

        except Exception as e:
            logger.error(f"Error fetching trader config for {trader_id}: {e}")
            return None

    async def get_exchange_for_trader(self, trader_id: str) -> ExchangeType:
        """
        Get the exchange type for a given trader.

        Args:
            trader_id: The trader identifier

        Returns:
            ExchangeType: The exchange that should handle this trader's signals
        """
        config = await self.get_trader_config(trader_id)
        if config:
            return config.exchange

        # Fallback 1: legacy static mapping (src.config.trader_config)
        try:
            from src.config.trader_config import TraderConfig as LegacyTraderConfig

            if LegacyTraderConfig.is_trader_supported(trader_id):
                legacy_exchange = LegacyTraderConfig.get_exchange_for_trader(trader_id)
                if legacy_exchange and isinstance(legacy_exchange.value, str):
                    logger.warning(
                        f"No DB config for trader {trader_id}, using legacy mapping: "
                        f"{legacy_exchange.value}"
                    )
                    return ExchangeType(legacy_exchange.value)
        except Exception as e:
            logger.warning(f"Legacy trader_config fallback failed for {trader_id}: {e}")

        # Fallback 2: hard default
        logger.warning(f"No config found for trader {trader_id}, using default exchange")
        return ExchangeType.BINANCE

    async def get_leverage_for_trader(self, trader_id: str, exchange: str) -> int:
        """
        Get leverage for a specific trader and exchange.

        Args:
            trader_id: The trader identifier
            exchange: The exchange name

        Returns:
            int: Leverage value (default: 1)
        """
        config = await self.get_trader_config(trader_id)
        if config and config.exchange.value == exchange:
            return config.leverage

        # Fallback to default leverage
        logger.warning(f"No leverage config found for {trader_id} on {exchange}, using 1x")
        return 1

    async def is_trader_supported(self, trader_id: str) -> bool:
        """
        Check if a trader is supported (has configuration in database).

        Args:
            trader_id: The trader identifier

        Returns:
            bool: True if trader is supported, False otherwise
        """
        if not trader_id:
            return False

        config = await self.get_trader_config(trader_id)
        return config is not None

    async def get_supported_traders(self) -> List[str]:
        """
        Get list of all supported traders from database.

        Returns:
            List[str]: List of supported trader identifiers
        """
        # Check cache first
        if (self._supported_traders_cache is not None and
            self._supported_traders_timestamp is not None and
            time.time() - self._supported_traders_timestamp < self.cache_ttl):
            return list(self._supported_traders_cache)

        try:
            if not runtime_config:
                logger.error("Runtime config not initialized")
                return []

            response = runtime_config.supabase.table("trader_exchange_config").select(
                "trader_id"
            ).execute()

            if response.data:
                traders = [config["trader_id"] for config in response.data]

                # Cache the result
                self._supported_traders_cache = set(traders)
                self._supported_traders_timestamp = time.time()

                logger.info(f"Loaded {len(traders)} supported traders from database")
                return traders
            else:
                logger.warning("No supported traders found in database")
                return []

        except Exception as e:
            logger.error(f"Error fetching supported traders: {e}")
            return []

    async def get_traders_for_exchange(self, exchange: ExchangeType) -> List[str]:
        """
        Get list of traders that use a specific exchange.

        Args:
            exchange: The exchange type

        Returns:
            List[str]: List of trader identifiers using this exchange
        """
        try:
            if not runtime_config:
                logger.error("Runtime config not initialized")
                return []

            response = runtime_config.supabase.table("trader_exchange_config").select(
                "trader_id"
            ).eq("exchange", exchange.value).execute()

            if response.data:
                traders = [config["trader_id"] for config in response.data]
                logger.info(f"Found {len(traders)} traders for {exchange.value} exchange")
                return traders
            else:
                logger.warning(f"No traders found for {exchange.value} exchange")
                return []

        except Exception as e:
            logger.error(f"Error fetching traders for {exchange.value}: {e}")
            return []

    async def add_trader_config(self, trader_id: str, exchange: ExchangeType,
                              leverage: int, updated_by: Optional[str] = None) -> bool:
        """
        Add a new trader configuration.

        Args:
            trader_id: The trader identifier
            exchange: The exchange type
            leverage: The leverage value
            updated_by: Who made the update

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            if not runtime_config:
                logger.error("Runtime config not initialized")
                return False

            config_data = {
                "trader_id": trader_id,
                "exchange": exchange.value,
                "leverage": leverage,
                "updated_by": updated_by
            }

            response = runtime_config.supabase.table("trader_exchange_config").upsert(
                config_data
            ).execute()

            if response.data:
                # Clear cache for this trader
                cache_key = self._get_cache_key(trader_id)
                self._config_cache.pop(cache_key, None)
                self._cache_timestamps.pop(cache_key, None)

                # Clear supported traders cache
                self._supported_traders_cache = None
                self._supported_traders_timestamp = None

                logger.info(f"Added/updated config for trader {trader_id}: {exchange.value} @ {leverage}x")
                return True
            else:
                logger.error(f"Failed to add config for trader {trader_id}")
                return False

        except Exception as e:
            logger.error(f"Error adding trader config for {trader_id}: {e}")
            return False

    async def remove_trader_config(self, trader_id: str) -> bool:
        """
        Remove a trader configuration.

        Args:
            trader_id: The trader identifier

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            if not runtime_config:
                logger.error("Runtime config not initialized")
                return False

            # Delete using variants, with case-insensitive fallback
            variants = self._variants(trader_id)
            response = runtime_config.supabase.table("trader_exchange_config").delete().in_(
                "trader_id", variants
            ).execute()

            if not getattr(response, 'data', None):
                canon = self._canonical(trader_id)
                if canon:
                    runtime_config.supabase.table("trader_exchange_config").delete().ilike(
                        "trader_id", canon
                    ).execute()

            # Clear cache for this trader
            cache_key = self._get_cache_key(trader_id)
            self._config_cache.pop(cache_key, None)
            self._cache_timestamps.pop(cache_key, None)

            # Clear supported traders cache
            self._supported_traders_cache = None
            self._supported_traders_timestamp = None

            logger.info(f"Removed config for trader {trader_id}")
            return True

        except Exception as e:
            logger.error(f"Error removing trader config for {trader_id}: {e}")
            return False

    def clear_cache(self, trader_id: Optional[str] = None):
        """
        Clear configuration cache.

        Args:
            trader_id: Specific trader to clear cache for, or None to clear all
        """
        if trader_id:
            cache_key = self._get_cache_key(trader_id)
            self._config_cache.pop(cache_key, None)
            self._cache_timestamps.pop(cache_key, None)
            logger.debug(f"Cleared cache for trader {trader_id}")
        else:
            self._config_cache.clear()
            self._cache_timestamps.clear()
            self._supported_traders_cache = None
            self._supported_traders_timestamp = None
            logger.debug("Cleared all trader config cache")


# Global instance
trader_config_service = TraderConfigService()


# Convenience functions for backward compatibility
async def get_exchange_for_trader(trader_id: str) -> ExchangeType:
    """Get exchange for trader using the service."""
    return await trader_config_service.get_exchange_for_trader(trader_id)


async def is_trader_supported(trader_id: str) -> bool:
    """Check if trader is supported using the service."""
    return await trader_config_service.is_trader_supported(trader_id)


async def get_supported_traders() -> List[str]:
    """Get supported traders using the service."""
    return await trader_config_service.get_supported_traders()


async def get_traders_for_exchange(exchange: ExchangeType) -> List[str]:
    """Get traders for exchange using the service."""
    return await trader_config_service.get_traders_for_exchange(exchange)
