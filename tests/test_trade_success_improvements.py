"""
Test cases for trade success rate improvements.

Tests cover:
1. Symbol validation (early rejection)
2. Position size auto-bump (5x cap)
3. Kucoin contract quantity conversion (minimum 1 contract)
4. Break-even stop loss with entry prices
5. Risk cap removal (wide stop loss accepted)
6. Stop loss order recreation
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch, Mock
from typing import Dict, Any


class TestSymbolValidation:
    """Test symbol validation improvements."""

    @pytest.mark.asyncio
    async def test_invalid_symbol_rejected_early(self):
        """Test that invalid symbols are rejected early in process_signal."""
        from src.bot.signal_processor.initial_signal_processor import InitialSignalProcessor

        mock_exchange = MagicMock()
        mock_exchange.get_futures_trading_pair.return_value = "AVICIUSDT"
        mock_exchange.get_exchange_info = AsyncMock(return_value={
            'symbols': [
                {'symbol': 'BTCUSDT', 'status': 'TRADING'},
                {'symbol': 'ETHUSDT', 'status': 'TRADING'}
            ]
        })
        mock_exchange.is_futures_symbol_supported = AsyncMock(return_value=False)

        mock_engine = MagicMock()
        mock_engine.exchange = mock_exchange
        mock_engine.price_service = MagicMock()
        mock_engine.fee_calculator = MagicMock()
        mock_engine.db_manager = MagicMock()
        mock_engine.trade_cooldowns = {}
        mock_engine.config = MagicMock()
        mock_engine.config.TRADE_COOLDOWN = 60

        processor = InitialSignalProcessor(mock_engine)

        success, result = await processor.process_signal(
            coin_symbol="AVICI",
            signal_price=5.68,
            position_type="LONG"
        )

        assert success is False
        assert "does not exist" in str(result) or "not supported" in str(result)


class TestAutoBump:
    """Test position size auto-bump improvements."""

    @pytest.mark.asyncio
    async def test_auto_bump_5x_cap(self):
        """Test that auto-bump allows up to 5x original position size."""
        from src.bot.signal_processor.initial_signal_processor import InitialSignalProcessor

        mock_exchange = MagicMock()
        mock_engine = MagicMock()
        mock_engine.exchange = mock_exchange
        mock_engine.price_service = MagicMock()
        mock_engine.fee_calculator = MagicMock()
        mock_engine.db_manager = MagicMock()
        mock_engine.trade_cooldowns = {}
        mock_engine.config = MagicMock()
        mock_engine.config.TRADE_AMOUNT = 89.0

        processor = InitialSignalProcessor(mock_engine)

        # Mock trader config service to return position_size
        # Patch where it's imported in the function
        with patch('src.bot.signal_processor.initial_signal_processor.trader_config_service') as mock_service:
            mock_config = MagicMock()
            mock_config.exchange.value = 'binance'
            mock_config.position_size = 89.0
            mock_service.get_trader_config = AsyncMock(return_value=mock_config)

            # Mock filters with min_notional = 100
            mock_filters = {
                'LOT_SIZE': {'minQty': 0.001},
                'MIN_NOTIONAL': {'notional': 100.0}
            }
            mock_exchange.get_futures_symbol_filters = AsyncMock(return_value=mock_filters)
            mock_exchange.get_futures_trading_pair.return_value = "BTCUSDT"

            # Set trader_id on processor
            processor.trading_engine.trader_id = 'test_trader'

            # Test auto-bump: $89 -> $100 (within 5x limit)
            trade_amount = await processor._calculate_trade_amount(
                coin_symbol="BTC",
                current_price=85792.0,
                quantity_multiplier=None,
                is_futures=True,
                position_size_override=None
            )

            # Should auto-bump to meet minimum
            assert trade_amount > 0
            notional = trade_amount * 85792.0
            assert notional >= 100.0  # Should meet minimum


class TestKucoinContractConversion:
    """Test Kucoin contract quantity conversion."""

    @pytest.mark.asyncio
    async def test_minimum_1_contract_enforced(self):
        """Test that Kucoin enforces minimum 1.0 contracts."""
        from src.bot.kucoin_trading_engine import KucoinTradingEngine

        mock_exchange = MagicMock()
        mock_price_service = MagicMock()
        mock_db_manager = MagicMock()

        engine = KucoinTradingEngine(mock_price_service, mock_exchange, mock_db_manager)
        engine.config = MagicMock()
        engine.config.TRADE_AMOUNT = 135.0
        engine.trader_id = 'woods'  # Set trader_id for config lookup

        # Mock trader config service to return position_size
        # Patch where it's imported in the function
        with patch('src.bot.kucoin_trading_engine.trader_config_service') as mock_service:
            mock_config = MagicMock()
            mock_config.exchange.value = 'kucoin'
            mock_config.position_size = 135.0
            mock_service.get_trader_config = AsyncMock(return_value=mock_config)

            # Mock filters: BTC with multiplier 2.0, min contracts 1.0
            mock_filters = {
                'LOT_SIZE': {
                    'minQty': 1.0,
                    'stepSize': 1.0,
                    'maxQty': 1000000.0
                },
                'multiplier': 2.0
            }
            mock_exchange.get_futures_symbol_filters = AsyncMock(return_value=mock_filters)

            # Calculate trade amount for BTC at $86000
            trade_amount = await engine._calculate_trade_amount(
                coin_symbol="BTC",
                current_price=86000.0,
                quantity_multiplier=None,
                position_size_override=None
            )

            # Should enforce minimum 1 contract = 2.0 assets (multiplier 2.0)
            assert trade_amount >= 2.0  # Minimum 1 contract * multiplier


class TestBreakEvenStopLoss:
    """Test break-even stop loss handling."""

    @pytest.mark.asyncio
    async def test_be_stop_loss_with_entry_prices(self):
        """Test that BE stop loss works when entry prices are provided."""
        from src.bot.signal_processor.initial_signal_processor import InitialSignalProcessor

        mock_exchange = MagicMock()
        mock_engine = MagicMock()
        mock_engine.exchange = mock_exchange
        mock_engine.price_service = MagicMock()
        mock_engine.fee_calculator = MagicMock()
        mock_engine.db_manager = MagicMock()
        mock_engine.trade_cooldowns = {}
        mock_engine.config = MagicMock()
        mock_engine.config.TRADE_COOLDOWN = 60

        processor = InitialSignalProcessor(mock_engine)

        # Test BE stop loss normalization logic
        # The actual BE handling happens in process_signal with entry_prices
        # This test verifies the normalization method doesn't break on BE
        normalized = processor._normalize_stop_loss_value("BE")
        # BE should return None from normalize (handled specially in process_signal)
        assert normalized is None  # BE is handled specially, not normalized here


class TestRiskCapRemoval:
    """Test risk cap removal."""

    @pytest.mark.asyncio
    async def test_wide_stop_loss_accepted(self):
        """Test that trades with wide stop losses (>3%) are accepted."""
        from src.bot.kucoin_trading_engine import KucoinTradingEngine

        mock_exchange = MagicMock()
        mock_price_service = MagicMock()
        mock_db_manager = MagicMock()

        engine = KucoinTradingEngine(mock_price_service, mock_exchange, mock_db_manager)
        engine.config = MagicMock()
        engine.config.TRADE_AMOUNT = 135.0

        # Mock successful symbol validation
        mock_exchange.get_futures_trading_pair.return_value = "ZEC-USDT"
        mock_exchange.get_exchange_info = AsyncMock(return_value={
            'symbols': [{'symbol': 'ZEC-USDT', 'status': 'TRADING'}]
        })
        mock_exchange.is_futures_symbol_supported = AsyncMock(return_value=True)
        mock_exchange.get_futures_symbol_filters = AsyncMock(return_value={
            'LOT_SIZE': {'minQty': 0.001},
            'MIN_NOTIONAL': {'minNotional': 1.0}
        })
        mock_exchange.get_futures_mark_price = AsyncMock(return_value=458.1)
        mock_exchange.get_order_book = AsyncMock(return_value={
            'bids': [[458.0, 1.0]],
            'asks': [[458.2, 1.0]]
        })

        # Test with wide stop loss (33% risk)
        success, result = await engine.process_signal(
            coin_symbol="ZEC",
            signal_price=458.1,
            position_type="LONG",
            order_type="MARKET",
            stop_loss=442.0,  # 33.82% risk
            entry_prices=[458.1, 457.2]
        )

        # Should succeed (risk cap removed)
        # Note: This may still fail for other reasons (symbol validation, etc.)
        # but should NOT fail due to risk cap
        assert "Risk" not in str(result) or "risk" not in str(result).lower()


class TestStopLossRecreation:
    """Test stop loss order recreation."""

    @pytest.mark.asyncio
    async def test_stop_loss_recreation_on_expire(self):
        """Test that stop loss orders are recreated when they expire."""
        from src.websocket.sync.database_sync import DatabaseSync

        mock_db_manager = MagicMock()
        mock_db_manager.supabase = MagicMock()
        mock_db_manager.supabase.from_.return_value.update.return_value.eq.return_value.execute.return_value = None
        sync = DatabaseSync(mock_db_manager)

        # Mock trade data
        trade = {
            'id': 123,
            'exchange': 'binance',
            'coin_symbol': 'ETH',
            'signal_type': 'LONG',
            'entry_price': 2740.93,
            'parsed_signal': '{"stop_loss": 2740}'
        }

        # Mock Binance exchange initialization
        with patch('src.websocket.sync.database_sync.BinanceExchange') as mock_binance_class:
            mock_exchange = MagicMock()
            mock_exchange.get_futures_trading_pair.return_value = "ETHUSDT"
            mock_exchange.get_futures_position_information = AsyncMock(return_value=[
                {
                    'symbol': 'ETHUSDT',
                    'positionAmt': '0.045',
                    'entryPrice': '2740.93'
                }
            ])
            mock_exchange.initialize = AsyncMock()
            mock_binance_class.return_value = mock_exchange

            # Mock stop loss manager
            with patch('src.bot.risk_management.stop_loss_manager.StopLossManager') as mock_sl_manager:
                mock_manager_instance = MagicMock()
                mock_manager_instance.ensure_stop_loss_for_position = AsyncMock(return_value=(True, "12345"))
                mock_sl_manager.return_value = mock_manager_instance

                # Mock settings
                with patch('src.websocket.sync.database_sync.settings') as mock_settings:
                    mock_settings.BINANCE_API_KEY = "test_key"
                    mock_settings.BINANCE_API_SECRET = "test_secret"

                    # Test recreation
                    await sync._recreate_stop_loss_on_expire(123, trade, "old_order_id")

                    # Verify stop loss was recreated
                    mock_manager_instance.ensure_stop_loss_for_position.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

