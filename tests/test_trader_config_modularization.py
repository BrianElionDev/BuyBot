"""
Test Trader Configuration Modularization

This test verifies that the trader configuration system works correctly
with database-driven configuration instead of hardcoded values.
"""

import pytest
import asyncio
import sys
import os
from unittest.mock import AsyncMock, MagicMock, patch

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.services.trader_config_service import (
    TraderConfigService, ExchangeType, TraderConfig, trader_config_service
)
from src.bot.signal_router import SignalRouter
from src.services.active_futures_sync_service import ActiveFuturesSyncService


class TestTraderConfigService:
    """Test the trader configuration service."""

    @pytest.fixture
    def mock_runtime_config(self):
        """Mock runtime config for testing."""
        mock_config = MagicMock()
        mock_config.supabase = MagicMock()
        return mock_config

    @pytest.fixture
    def trader_service(self, mock_runtime_config):
        """Create trader config service with mocked dependencies."""
        with patch('src.services.trader_config_service.runtime_config', mock_runtime_config):
            service = TraderConfigService(cache_ttl_seconds=1)  # Short cache for testing
            return service

    @pytest.mark.asyncio
    async def test_get_trader_config_success(self, trader_service, mock_runtime_config):
        """Test successful trader config retrieval."""
        # Mock database response
        mock_response = MagicMock()
        mock_response.data = [{
            "trader_id": "@Johnny",
            "exchange": "binance",
            "leverage": 10,
            "created_at": "2024-01-01T00:00:00Z",
            "updated_at": "2024-01-01T00:00:00Z",
            "updated_by": "admin"
        }]
        mock_runtime_config.supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = mock_response

        # Test
        config = await trader_service.get_trader_config("@Johnny")

        # Assertions
        assert config is not None
        assert config.trader_id == "@Johnny"
        assert config.exchange == ExchangeType.BINANCE
        assert config.leverage == 10

    @pytest.mark.asyncio
    async def test_get_trader_config_not_found(self, trader_service, mock_runtime_config):
        """Test trader config not found."""
        # Mock empty database response
        mock_response = MagicMock()
        mock_response.data = []
        mock_runtime_config.supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = mock_response

        # Test
        config = await trader_service.get_trader_config("@Unknown")

        # Assertions
        assert config is None

    @pytest.mark.asyncio
    async def test_get_exchange_for_trader_with_config(self, trader_service, mock_runtime_config):
        """Test getting exchange for trader with valid config."""
        # Mock database response
        mock_response = MagicMock()
        mock_response.data = [{
            "trader_id": "@Tareeq",
            "exchange": "kucoin",
            "leverage": 5
        }]
        mock_runtime_config.supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = mock_response

        # Test
        exchange = await trader_service.get_exchange_for_trader("@Tareeq")

        # Assertions
        assert exchange == ExchangeType.KUCOIN

    @pytest.mark.asyncio
    async def test_get_exchange_for_trader_fallback(self, trader_service, mock_runtime_config):
        """Test getting exchange for trader with fallback to default."""
        # Mock empty database response
        mock_response = MagicMock()
        mock_response.data = []
        mock_runtime_config.supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = mock_response

        # Test
        exchange = await trader_service.get_exchange_for_trader("@Unknown")

        # Assertions
        assert exchange == ExchangeType.BINANCE  # Default fallback

    @pytest.mark.asyncio
    async def test_is_trader_supported(self, trader_service, mock_runtime_config):
        """Test trader support check."""
        # Mock database response
        mock_response = MagicMock()
        mock_response.data = [{
            "trader_id": "@Johnny",
            "exchange": "binance",
            "leverage": 10
        }]
        mock_runtime_config.supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = mock_response

        # Test
        is_supported = await trader_service.is_trader_supported("@Johnny")

        # Assertions
        assert is_supported is True

    @pytest.mark.asyncio
    async def test_get_supported_traders(self, trader_service, mock_runtime_config):
        """Test getting all supported traders."""
        # Mock database response
        mock_response = MagicMock()
        mock_response.data = [
            {"trader_id": "@Johnny"},
            {"trader_id": "@Tareeq"}
        ]
        mock_runtime_config.supabase.table.return_value.select.return_value.execute.return_value = mock_response

        # Test
        traders = await trader_service.get_supported_traders()

        # Assertions
        assert len(traders) == 2
        assert "@Johnny" in traders
        assert "@Tareeq" in traders

    @pytest.mark.asyncio
    async def test_add_trader_config(self, trader_service, mock_runtime_config):
        """Test adding trader configuration."""
        # Mock successful upsert
        mock_response = MagicMock()
        mock_response.data = [{"id": "123"}]
        mock_runtime_config.supabase.table.return_value.upsert.return_value.execute.return_value = mock_response

        # Test
        success = await trader_service.add_trader_config(
            "@NewTrader", ExchangeType.BINANCE, 20, "admin"
        )

        # Assertions
        assert success is True

    @pytest.mark.asyncio
    async def test_remove_trader_config(self, trader_service, mock_runtime_config):
        """Test removing trader configuration."""
        # Mock successful delete
        mock_response = MagicMock()
        mock_response.data = []
        mock_runtime_config.supabase.table.return_value.delete.return_value.eq.return_value.execute.return_value = mock_response

        # Test
        success = await trader_service.remove_trader_config("@Johnny")

        # Assertions
        assert success is True

    @pytest.mark.asyncio
    async def test_cache_functionality(self, trader_service, mock_runtime_config):
        """Test caching functionality."""
        # Mock database response
        mock_response = MagicMock()
        mock_response.data = [{
            "trader_id": "@Johnny",
            "exchange": "binance",
            "leverage": 10
        }]
        mock_runtime_config.supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = mock_response

        # First call - should hit database
        config1 = await trader_service.get_trader_config("@Johnny")

        # Second call - should hit cache
        config2 = await trader_service.get_trader_config("@Johnny")

        # Assertions
        assert config1 is not None
        assert config2 is not None
        assert config1.trader_id == config2.trader_id

        # Verify database was called only once (cached on second call)
        assert mock_runtime_config.supabase.table.call_count == 1


class TestSignalRouterIntegration:
    """Test signal router integration with trader config service."""

    @pytest.fixture
    def mock_trading_engines(self):
        """Mock trading engines."""
        binance_engine = MagicMock()
        kucoin_engine = MagicMock()
        return binance_engine, kucoin_engine

    @pytest.fixture
    def signal_router(self, mock_trading_engines):
        """Create signal router with mocked dependencies."""
        binance_engine, kucoin_engine = mock_trading_engines
        return SignalRouter(binance_engine, kucoin_engine)

    @pytest.mark.asyncio
    async def test_signal_router_trader_validation(self, signal_router):
        """Test signal router trader validation."""
        with patch('src.services.trader_config_service.trader_config_service') as mock_service:
            # Mock trader support check
            mock_service.is_trader_supported.return_value = True
            mock_service.get_exchange_for_trader.return_value = ExchangeType.BINANCE

            # Test
            is_supported = await signal_router.is_trader_supported("@Johnny")
            exchange = await signal_router.get_exchange_for_trader("@Johnny")

            # Assertions
            assert is_supported is True
            assert exchange == ExchangeType.BINANCE

    @pytest.mark.asyncio
    async def test_signal_router_unsupported_trader(self, signal_router):
        """Test signal router with unsupported trader."""
        with patch('src.services.trader_config_service.trader_config_service') as mock_service:
            # Mock unsupported trader
            mock_service.is_trader_supported.return_value = False
            mock_service.get_exchange_for_trader.return_value = ExchangeType.BINANCE

            # Test
            is_supported = await signal_router.is_trader_supported("@Unknown")
            exchange = await signal_router.get_exchange_for_trader("@Unknown")

            # Assertions
            assert is_supported is False
            assert exchange == ExchangeType.BINANCE  # Fallback to default


class TestActiveFuturesSyncServiceIntegration:
    """Test active futures sync service integration."""

    @pytest.fixture
    def mock_db_manager(self):
        """Mock database manager."""
        return MagicMock()

    @pytest.fixture
    def sync_service(self, mock_db_manager):
        """Create sync service with mocked dependencies."""
        return ActiveFuturesSyncService(mock_db_manager)

    @pytest.mark.asyncio
    async def test_sync_service_initialization(self, sync_service, mock_db_manager):
        """Test sync service initialization with database traders."""
        with patch('src.services.trader_config_service.trader_config_service') as mock_service:
            # Mock database initialization
            mock_db_manager.initialize.return_value = None

            # Mock trader config service
            mock_service.get_supported_traders.return_value = ["@Johnny", "@Tareeq"]

            # Test
            success = await sync_service.initialize()

            # Assertions
            assert success is True
            assert sync_service.target_traders == ["@Johnny", "@Tareeq"]

    @pytest.mark.asyncio
    async def test_sync_service_fallback_initialization(self, sync_service, mock_db_manager):
        """Test sync service initialization with fallback traders."""
        with patch('src.services.trader_config_service.trader_config_service') as mock_service:
            # Mock database initialization
            mock_db_manager.initialize.return_value = None

            # Mock trader config service failure
            mock_service.get_supported_traders.side_effect = Exception("Database error")

            # Test
            success = await sync_service.initialize()

            # Assertions
            assert success is True
            assert sync_service.target_traders == sync_service.fallback_traders


class TestConvenienceFunctions:
    """Test convenience functions for backward compatibility."""

    @pytest.mark.asyncio
    async def test_get_exchange_for_trader_function(self):
        """Test convenience function for getting exchange."""
        with patch('src.services.trader_config_service.trader_config_service') as mock_service:
            mock_service.get_exchange_for_trader.return_value = ExchangeType.KUCOIN

            from src.services.trader_config_service import get_exchange_for_trader

            exchange = await get_exchange_for_trader("@Tareeq")
            assert exchange == ExchangeType.KUCOIN

    @pytest.mark.asyncio
    async def test_is_trader_supported_function(self):
        """Test convenience function for trader support check."""
        with patch('src.services.trader_config_service.trader_config_service') as mock_service:
            mock_service.is_trader_supported.return_value = True

            from src.services.trader_config_service import is_trader_supported

            is_supported = await is_trader_supported("@Johnny")
            assert is_supported is True


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v"])
