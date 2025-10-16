#!/usr/bin/env python3
"""
Comprehensive test to verify leverage flow from signal processing to order creation.
This test simulates the complete leverage resolution path to ensure it uses the
trader_exchange_config table with minimal fallback to 1x leverage.
"""

import asyncio
import pytest
import sys
import os
from unittest.mock import Mock, AsyncMock, patch
from typing import Dict, Any

# Add src to path
sys.path.append('src')

from src.services.trader_config_service import TraderConfigService, TraderConfig, ExchangeType
from src.bot.signal_processor.initial_signal_processor import InitialSignalProcessor
from src.bot.trading_engine import TradingEngine
from src.exchange.binance.binance_exchange import BinanceExchange
from src.exchange.kucoin.kucoin_exchange import KucoinExchange


class TestLeverageFlowVerification:
    """Test class to verify complete leverage flow."""

    def setup_method(self):
        """Set up test fixtures."""
        self.trader_config_service = TraderConfigService()

        # Mock database responses
        self.mock_configs = {
            "johnny": TraderConfig(
                trader_id="johnny",
                exchange=ExchangeType.BINANCE,
                leverage=20
            ),
            "woods": TraderConfig(
                trader_id="woods",
                exchange=ExchangeType.KUCOIN,
                leverage=50
            ),
            "test_trader": TraderConfig(
                trader_id="test_trader",
                exchange=ExchangeType.BINANCE,
                leverage=10
            )
        }

    @pytest.mark.asyncio
    async def test_trader_config_service_leverage_resolution(self):
        """Test TraderConfigService leverage resolution with various trader IDs."""

        # Mock the runtime_config and supabase calls
        with patch('src.services.trader_config_service.runtime_config') as mock_runtime:
            mock_supabase = Mock()
            mock_runtime.supabase = mock_supabase

            # Test case 1: Exact match
            mock_supabase.table.return_value.select.return_value.in_.return_value.execute.return_value.data = [
                {
                    "trader_id": "johnny",
                    "exchange": "binance",
                    "leverage": 20,
                    "created_at": "2025-01-01T00:00:00Z",
                    "updated_at": "2025-01-01T00:00:00Z",
                    "updated_by": "system"
                }
            ]

            config = await self.trader_config_service.get_trader_config("johnny")
            assert config is not None
            assert config.trader_id == "johnny"
            assert config.exchange == ExchangeType.BINANCE
            assert config.leverage == 20

            # Test case 2: Variant matching (@ prefix)
            mock_supabase.table.return_value.select.return_value.in_.return_value.execute.return_value.data = [
                {
                    "trader_id": "woods",
                    "exchange": "kucoin",
                    "leverage": 50,
                    "created_at": "2025-01-01T00:00:00Z",
                    "updated_at": "2025-01-01T00:00:00Z",
                    "updated_by": "system"
                }
            ]

            config = await self.trader_config_service.get_trader_config("@woods")
            assert config is not None
            assert config.leverage == 50

            # Test case 3: No match - should return None
            mock_supabase.table.return_value.select.return_value.in_.return_value.execute.return_value.data = []
            mock_supabase.table.return_value.select.return_value.ilike.return_value.execute.return_value.data = []

            config = await self.trader_config_service.get_trader_config("unknown_trader")
            assert config is None

    @pytest.mark.asyncio
    async def test_leverage_fallback_mechanisms(self):
        """Test leverage fallback mechanisms to ensure minimal fallback to 1x."""

        with patch('src.services.trader_config_service.runtime_config') as mock_runtime:
            mock_supabase = Mock()
            mock_runtime.supabase = mock_supabase

            # Test case 1: Database error - should return None, leading to 1x fallback
            mock_supabase.table.side_effect = Exception("Database connection failed")

            config = await self.trader_config_service.get_trader_config("johnny")
            assert config is None

            # Test case 2: Empty trader_id - should return None
            config = await self.trader_config_service.get_trader_config("")
            assert config is None

            config = await self.trader_config_service.get_trader_config(None)
            assert config is None

    @pytest.mark.asyncio
    async def test_initial_signal_processor_leverage_flow(self):
        """Test complete leverage flow in InitialSignalProcessor."""

        # Mock dependencies
        mock_trading_engine = Mock()
        mock_trading_engine.trader_id = "johnny"
        mock_trading_engine.config = Mock()
        mock_trading_engine.config.TRADE_AMOUNT = 100.0

        mock_exchange = Mock()
        mock_exchange.__class__.__name__ = "BinanceExchange"
        mock_exchange.calculate_min_max_market_order_quantity = AsyncMock(return_value=(0.001, 1000.0))
        mock_exchange.get_futures_symbol_filters = AsyncMock(return_value={
            'LOT_SIZE': {'stepSize': '0.001', 'minQty': '0.001', 'maxQty': '1000.0'}
        })
        mock_exchange.create_futures_order = AsyncMock(return_value={'success': True, 'orderId': '12345'})
        mock_exchange.set_futures_leverage = AsyncMock(return_value=True)

        processor = InitialSignalProcessor(mock_trading_engine)
        processor.exchange = mock_exchange

        # Mock TraderConfigService
        with patch('src.services.trader_config_service.trader_config_service') as mock_service:
            mock_service.get_trader_config = AsyncMock(return_value=TraderConfig(
                trader_id="johnny",
                exchange=ExchangeType.BINANCE,
                leverage=20
            ))

            # Test the _execute_trade method
            result = await processor._execute_trade(
                trading_pair="ETHUSDT",
                coin_symbol="ETH",
                signal_price=2000.0,
                position_type="LONG",
                order_type="MARKET",
                trade_amount=0.1,
                stop_loss=None,
                take_profits=None,
                entry_prices=None,
                is_futures=True
            )

            # Verify leverage was resolved and applied
            assert result[0] is True  # Success

            # Verify set_futures_leverage was called with correct leverage
            mock_exchange.set_futures_leverage.assert_called_once_with("ETHUSDT", 20)

            # Verify create_futures_order was called with leverage parameter
            mock_exchange.create_futures_order.assert_called_once()
            call_args = mock_exchange.create_futures_order.call_args
            assert call_args[1]['leverage'] == 20

    @pytest.mark.asyncio
    async def test_kucoin_leverage_application(self):
        """Test KuCoin specific leverage application."""

        mock_trading_engine = Mock()
        mock_trading_engine.trader_id = "woods"
        mock_trading_engine.config = Mock()
        mock_trading_engine.config.TRADE_AMOUNT = 100.0

        mock_exchange = Mock()
        mock_exchange.__class__.__name__ = "KucoinExchange"
        mock_exchange.calculate_min_max_market_order_quantity = AsyncMock(return_value=(0.001, 1000.0))
        mock_exchange.get_futures_symbol_filters = AsyncMock(return_value={
            'LOT_SIZE': {'stepSize': '0.001', 'minQty': '0.001', 'maxQty': '1000.0'}
        })
        mock_exchange.create_futures_order = AsyncMock(return_value={'success': True, 'orderId': '67890'})

        processor = InitialSignalProcessor(mock_trading_engine)
        processor.exchange = mock_exchange

        # Mock TraderConfigService for KuCoin
        with patch('src.services.trader_config_service.trader_config_service') as mock_service:
            mock_service.get_trader_config = AsyncMock(return_value=TraderConfig(
                trader_id="woods",
                exchange=ExchangeType.KUCOIN,
                leverage=50
            ))

            result = await processor._execute_trade(
                trading_pair="ETHUSDTM",
                coin_symbol="ETH",
                signal_price=2000.0,
                position_type="LONG",
                order_type="MARKET",
                trade_amount=0.1,
                stop_loss=None,
                take_profits=None,
                entry_prices=None,
                is_futures=True
            )

            assert result[0] is True

            # Verify create_futures_order was called with leverage parameter for KuCoin
            mock_exchange.create_futures_order.assert_called_once()
            call_args = mock_exchange.create_futures_order.call_args
            assert call_args[1]['leverage'] == 50

    @pytest.mark.asyncio
    async def test_leverage_fallback_to_1x(self):
        """Test that leverage falls back to 1x only when absolutely necessary."""

        mock_trading_engine = Mock()
        mock_trading_engine.trader_id = "unknown_trader"
        mock_trading_engine.config = Mock()
        mock_trading_engine.config.TRADE_AMOUNT = 100.0

        mock_exchange = Mock()
        mock_exchange.__class__.__name__ = "BinanceExchange"
        mock_exchange.calculate_min_max_market_order_quantity = AsyncMock(return_value=(0.001, 1000.0))
        mock_exchange.get_futures_symbol_filters = AsyncMock(return_value={
            'LOT_SIZE': {'stepSize': '0.001', 'minQty': '0.001', 'maxQty': '1000.0'}
        })
        mock_exchange.create_futures_order = AsyncMock(return_value={'success': True, 'orderId': '11111'})
        mock_exchange.set_futures_leverage = AsyncMock(return_value=True)

        processor = InitialSignalProcessor(mock_trading_engine)
        processor.exchange = mock_exchange

        # Mock TraderConfigService to return None (no config found)
        with patch('src.services.trader_config_service.trader_config_service') as mock_service:
            mock_service.get_trader_config = AsyncMock(return_value=None)

            # Mock RuntimeConfig fallback to also return None
            with patch('src.config.runtime_config.runtime_config') as mock_runtime_config:
                mock_runtime_config.get_trader_exchange_config = AsyncMock(return_value=None)

                result = await processor._execute_trade(
                    trading_pair="ETHUSDT",
                    coin_symbol="ETH",
                    signal_price=2000.0,
                    position_type="LONG",
                    order_type="MARKET",
                    trade_amount=0.1,
                    stop_loss=None,
                    take_profits=None,
                    entry_prices=None,
                    is_futures=True
                )

                assert result[0] is True

                # Verify leverage falls back to 1x
                mock_exchange.set_futures_leverage.assert_called_once_with("ETHUSDT", 1)
                mock_exchange.create_futures_order.assert_called_once()
                call_args = mock_exchange.create_futures_order.call_args
                assert call_args[1]['leverage'] == 1.0

    def test_trader_id_normalization(self):
        """Test trader ID normalization and variant generation."""

        # Test canonical normalization
        assert self.trader_config_service._canonical("johnny") == "johnny"
        assert self.trader_config_service._canonical("@johnny") == "johnny"
        assert self.trader_config_service._canonical("-johnny") == "johnny"
        assert self.trader_config_service._canonical("@-johnny") == "johnny"
        assert self.trader_config_service._canonical("JOHNNY") == "johnny"

        # Test variant generation
        variants = self.trader_config_service._variants("johnny")
        expected_variants = ["johnny", "JOHNNY", "@johnny", "@JOHNNY", "-johnny", "-JOHNNY"]
        for variant in expected_variants:
            assert variant in variants


if __name__ == "__main__":
    # Run the tests
    pytest.main([__file__, "-v"])
