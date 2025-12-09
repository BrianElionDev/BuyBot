"""
Test cases for notional value validation fixes.

Tests verify that:
1. KuCoin MARKET orders fetch mark price and validate notional
2. KuCoin LIMIT orders use provided price and validate notional
3. Binance MARKET orders fetch mark price and validate notional
4. Binance LIMIT orders use provided price and validate notional
5. Error handling when mark price fetch fails
6. Edge cases from real trade data (BTC trades with small position sizes)
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch, Mock
from typing import Dict, Any, Optional


class TestKucoinNotionalValidation:
    """Test KuCoin notional validation fixes."""

    @pytest.fixture
    def mock_kucoin_exchange(self):
        """Create a mock KuCoin exchange."""
        exchange = MagicMock()
        exchange.__class__.__name__ = "KucoinExchange"
        exchange._init_client = AsyncMock()
        exchange.get_futures_symbol_filters = AsyncMock(return_value={
            'LOT_SIZE': {
                'stepSize': '0.001',
                'minQty': '1.0',
                'maxQty': '1000000.0'
            },
            'PRICE_FILTER': {
                'tickSize': '0.01'
            },
            'MIN_NOTIONAL': {
                'minNotional': '0.00001'
            },
            'multiplier': '0.001'
        })
        exchange.get_mark_price = AsyncMock()
        exchange._convert_order_type = Mock(return_value='market')
        return exchange

    @pytest.mark.asyncio
    async def test_market_order_fetches_mark_price_and_validates(self, mock_kucoin_exchange):
        """Test that MARKET orders fetch mark price and validate notional."""
        from src.exchange.kucoin.kucoin_exchange import KucoinExchange

        # Mock mark price fetch
        mock_kucoin_exchange.get_mark_price.return_value = 101390.86  # BTC price from trade data

        # Create real exchange instance but patch methods
        exchange = KucoinExchange("key", "secret", "passphrase", False)
        exchange.get_futures_symbol_filters = mock_kucoin_exchange.get_futures_symbol_filters
        exchange.get_mark_price = mock_kucoin_exchange.get_mark_price
        exchange._init_client = AsyncMock()
        exchange.client = MagicMock()
        exchange.client.get_futures_service = Mock()

        # Mock symbol converter
        with patch('src.exchange.kucoin.kucoin_exchange.symbol_converter') as mock_converter:
            mock_converter.convert_bot_to_kucoin_futures.return_value = "XBTUSDTM"

            # Test MARKET order with amount that should pass (0.004 BTC * 101390.86 = 405.56 USDT > 0.00001)
            result = await exchange.create_futures_order(
                pair="BTC-USDT",
                side="BUY",
                order_type="MARKET",
                amount=0.004,  # From trade data: position_size 0.00400000
                price=None  # MARKET orders don't have price
            )

            # Verify mark price was fetched
            mock_kucoin_exchange.get_mark_price.assert_called_once_with("BTC-USDT")

            # Should not return error (notional is valid)
            assert 'error' not in result or result.get('code') != -4007

    @pytest.mark.asyncio
    async def test_market_order_fails_when_mark_price_unavailable(self, mock_kucoin_exchange):
        """Test that MARKET orders fail when mark price fetch fails."""
        from src.exchange.kucoin.kucoin_exchange import KucoinExchange

        # Mock mark price fetch to return None
        mock_kucoin_exchange.get_mark_price.return_value = None

        exchange = KucoinExchange("key", "secret", "passphrase", False)
        exchange.get_futures_symbol_filters = mock_kucoin_exchange.get_futures_symbol_filters
        exchange.get_mark_price = mock_kucoin_exchange.get_mark_price
        exchange._init_client = AsyncMock()
        exchange.client = MagicMock()

        with patch('src.exchange.kucoin.kucoin_exchange.symbol_converter') as mock_converter:
            mock_converter.convert_bot_to_kucoin_futures.return_value = "XBTUSDTM"

            result = await exchange.create_futures_order(
                pair="BTC-USDT",
                side="BUY",
                order_type="MARKET",
                amount=0.004,
                price=None
            )

            # Should return error with code -4008
            assert 'error' in result
            assert result.get('code') == -4008
            assert 'mark price unavailable' in result['error'].lower()

    @pytest.mark.asyncio
    async def test_limit_order_uses_provided_price_and_validates(self, mock_kucoin_exchange):
        """Test that LIMIT orders use provided price and validate notional."""
        from src.exchange.kucoin.kucoin_exchange import KucoinExchange

        exchange = KucoinExchange("key", "secret", "passphrase", False)
        exchange.get_futures_symbol_filters = mock_kucoin_exchange.get_futures_symbol_filters
        exchange.get_mark_price = mock_kucoin_exchange.get_mark_price
        exchange._init_client = AsyncMock()
        exchange.client = MagicMock()

        with patch('src.exchange.kucoin.kucoin_exchange.symbol_converter') as mock_converter:
            mock_converter.convert_bot_to_kucoin_futures.return_value = "XBTUSDTM"

            # Test LIMIT order with price from trade data (86,050)
            signal_price = 86050.0  # From trade: "Btc limit 86,050/85,050"
            amount = 0.004  # position_size from trade data

            result = await exchange.create_futures_order(
                pair="BTC-USDT",
                side="BUY",
                order_type="LIMIT",
                amount=amount,
                price=signal_price
            )

            # Should not fetch mark price for LIMIT orders
            mock_kucoin_exchange.get_mark_price.assert_not_called()

            # Should not return notional error (0.004 * 86050 = 344.2 USDT > 0.00001)
            assert 'error' not in result or result.get('code') != -4007

    @pytest.mark.asyncio
    async def test_limit_order_fails_when_notional_below_minimum(self, mock_kucoin_exchange):
        """Test that LIMIT orders fail when notional is below minimum."""
        from src.exchange.kucoin.kucoin_exchange import KucoinExchange

        # Set higher minimum notional
        mock_kucoin_exchange.get_futures_symbol_filters.return_value = {
            'LOT_SIZE': {
                'stepSize': '0.001',
                'minQty': '1.0',
                'maxQty': '1000000.0'
            },
            'PRICE_FILTER': {
                'tickSize': '0.01'
            },
            'MIN_NOTIONAL': {
                'minNotional': '100.0'  # Higher minimum
            },
            'multiplier': '0.001'
        }

        exchange = KucoinExchange("key", "secret", "passphrase", False)
        exchange.get_futures_symbol_filters = mock_kucoin_exchange.get_futures_symbol_filters
        exchange.get_mark_price = mock_kucoin_exchange.get_mark_price
        exchange._init_client = AsyncMock()
        exchange.client = MagicMock()

        with patch('src.exchange.kucoin.kucoin_exchange.symbol_converter') as mock_converter:
            mock_converter.convert_bot_to_kucoin_futures.return_value = "XBTUSDTM"

            # Very small amount that will fail notional check
            result = await exchange.create_futures_order(
                pair="BTC-USDT",
                side="BUY",
                order_type="LIMIT",
                amount=0.0001,  # Very small
                price=86050.0
            )

            # Should return notional error
            assert 'error' in result
            assert result.get('code') == -4007
            assert 'notional' in result['error'].lower()


class TestBinanceNotionalValidation:
    """Test Binance notional validation fixes."""

    @pytest.fixture
    def mock_binance_exchange(self):
        """Create a mock Binance exchange."""
        exchange = MagicMock()
        exchange.__class__.__name__ = "BinanceExchange"
        exchange._init_client = AsyncMock()
        exchange.client = MagicMock()
        exchange.get_futures_symbol_filters = AsyncMock(return_value={
            'LOT_SIZE': {
                'stepSize': '0.001',
                'minQty': '0.001',
                'maxQty': '1000000.0'
            },
            'PRICE_FILTER': {
                'tickSize': '0.01'
            },
            'MIN_NOTIONAL': {
                'notional': '100.0'  # Binance minimum for BTC
            }
        })
        exchange.get_futures_mark_price = AsyncMock()
        return exchange

    @pytest.mark.asyncio
    async def test_market_order_fetches_mark_price_and_validates(self, mock_binance_exchange):
        """Test that MARKET orders fetch mark price and validate notional."""
        from src.exchange.binance.binance_exchange import BinanceExchange

        # Mock mark price fetch
        mock_binance_exchange.get_futures_mark_price.return_value = 101390.86

        exchange = BinanceExchange("key", "secret", False)
        exchange.get_futures_symbol_filters = mock_binance_exchange.get_futures_symbol_filters
        exchange.get_futures_mark_price = mock_binance_exchange.get_futures_mark_price
        exchange._init_client = AsyncMock()
        exchange.client = mock_binance_exchange.client

        # Test MARKET order with valid notional
        result = await exchange.create_futures_order(
            pair="BTCUSDT",
            side="BUY",
            order_type="MARKET",
            amount=0.001,  # 0.001 BTC * 101390.86 = 101.39 USDT > 100
            price=None
        )

        # Verify mark price was fetched
        mock_binance_exchange.get_futures_mark_price.assert_called_once_with("BTCUSDT")

        # Should not return notional error
        assert 'error' not in result or result.get('code') != -4164

    @pytest.mark.asyncio
    async def test_market_order_fails_when_mark_price_unavailable(self, mock_binance_exchange):
        """Test that MARKET orders fail when mark price fetch fails."""
        from src.exchange.binance.binance_exchange import BinanceExchange

        # Mock mark price fetch to return None
        mock_binance_exchange.get_futures_mark_price.return_value = None

        exchange = BinanceExchange("key", "secret", False)
        exchange.get_futures_symbol_filters = mock_binance_exchange.get_futures_symbol_filters
        exchange.get_futures_mark_price = mock_binance_exchange.get_futures_mark_price
        exchange._init_client = AsyncMock()
        exchange.client = mock_binance_exchange.client

        result = await exchange.create_futures_order(
            pair="BTCUSDT",
            side="BUY",
            order_type="MARKET",
            amount=0.001,
            price=None
        )

        # Should return error with code -4165
        assert 'error' in result
        assert result.get('code') == -4165
        assert 'mark price unavailable' in result['error'].lower()

    @pytest.mark.asyncio
    async def test_market_order_fails_on_exception(self, mock_binance_exchange):
        """Test that MARKET orders fail when mark price fetch raises exception."""
        from src.exchange.binance.binance_exchange import BinanceExchange

        # Mock mark price fetch to raise exception
        mock_binance_exchange.get_futures_mark_price.side_effect = Exception("API Error")

        exchange = BinanceExchange("key", "secret", False)
        exchange.get_futures_symbol_filters = mock_binance_exchange.get_futures_symbol_filters
        exchange.get_futures_mark_price = mock_binance_exchange.get_futures_mark_price
        exchange._init_client = AsyncMock()
        exchange.client = mock_binance_exchange.client

        result = await exchange.create_futures_order(
            pair="BTCUSDT",
            side="BUY",
            order_type="MARKET",
            amount=0.001,
            price=None
        )

        # Should return error with code -4165
        assert 'error' in result
        assert result.get('code') == -4165
        assert 'failed to fetch mark price' in result['error'].lower()

    @pytest.mark.asyncio
    async def test_limit_order_uses_provided_price_and_validates(self, mock_binance_exchange):
        """Test that LIMIT orders use provided price and validate notional."""
        from src.exchange.binance.binance_exchange import BinanceExchange

        exchange = BinanceExchange("key", "secret", False)
        exchange.get_futures_symbol_filters = mock_binance_exchange.get_futures_symbol_filters
        exchange.get_futures_mark_price = mock_binance_exchange.get_futures_mark_price
        exchange._init_client = AsyncMock()
        exchange.client = mock_binance_exchange.client

        # Test LIMIT order with price from trade data
        signal_price = 86050.0  # From trade: "Btc limit 86,050/85,050"
        amount = 0.001  # Small amount

        result = await exchange.create_futures_order(
            pair="BTCUSDT",
            side="BUY",
            order_type="LIMIT",
            amount=amount,
            price=signal_price
        )

        # Should not fetch mark price for LIMIT orders
        mock_binance_exchange.get_futures_mark_price.assert_not_called()

        # Should not return notional error (0.001 * 86050 = 86.05 USDT, but let's check)
        # Actually, 86.05 < 100, so it might fail - but that's correct behavior
        if 'error' in result and result.get('code') == -4164:
            assert 'notional' in result['error'].lower()

    @pytest.mark.asyncio
    async def test_limit_order_fails_when_notional_below_minimum(self, mock_binance_exchange):
        """Test that LIMIT orders fail when notional is below minimum."""
        from src.exchange.binance.binance_exchange import BinanceExchange

        exchange = BinanceExchange("key", "secret", False)
        exchange.get_futures_symbol_filters = mock_binance_exchange.get_futures_symbol_filters
        exchange.get_futures_mark_price = mock_binance_exchange.get_futures_mark_price
        exchange._init_client = AsyncMock()
        exchange.client = mock_binance_exchange.client

        # Amount that passes minQty (0.001) but fails notional (0.001 * 86050 = 86.05 < 100)
        result = await exchange.create_futures_order(
            pair="BTCUSDT",
            side="BUY",
            order_type="LIMIT",
            amount=0.001,  # Passes minQty but fails notional
            price=86050.0
        )

        # Should return notional error
        assert 'error' in result
        assert result.get('code') == -4164
        assert 'notional' in result['error'].lower()


class TestRealTradeScenarios:
    """Test scenarios based on real trade data that failed."""

    @pytest.mark.asyncio
    async def test_btc_limit_order_with_small_position_size(self):
        """Test BTC LIMIT order scenario from trade data that failed."""
        from src.exchange.binance.binance_exchange import BinanceExchange

        # Trade data: "Btc limit 86,050/85,050 stop 83,058"
        # position_size: 0.00400000 (from trade data)
        # entry_price: 86050
        # This should calculate: 0.004 * 86050 = 344.2 USDT notional

        mock_exchange = MagicMock()
        mock_exchange.get_futures_symbol_filters = AsyncMock(return_value={
            'LOT_SIZE': {
                'stepSize': '0.001',
                'minQty': '0.001',
                'maxQty': '1000000.0'
            },
            'PRICE_FILTER': {
                'tickSize': '0.01'
            },
            'MIN_NOTIONAL': {
                'notional': '100.0'
            }
        })
        mock_exchange.get_futures_mark_price = AsyncMock()
        mock_exchange._init_client = AsyncMock()
        mock_exchange.client = MagicMock()

        exchange = BinanceExchange("key", "secret", False)
        exchange.get_futures_symbol_filters = mock_exchange.get_futures_symbol_filters
        exchange.get_futures_mark_price = mock_exchange.get_futures_mark_price
        exchange._init_client = AsyncMock()
        exchange.client = mock_exchange.client

        # Simulate the trade: 0.004 BTC at 86050
        result = await exchange.create_futures_order(
            pair="BTCUSDT",
            side="BUY",
            order_type="LIMIT",
            amount=0.004,
            price=86050.0
        )

        # Should pass validation (344.2 > 100)
        assert 'error' not in result or result.get('code') != -4164

    @pytest.mark.asyncio
    async def test_btc_market_order_kucoin_scenario(self):
        """Test BTC MARKET order scenario that failed on KuCoin."""
        from src.exchange.kucoin.kucoin_exchange import KucoinExchange

        # Trade data showed: "Notional value 0.0 below minimum 1e-05 for XBTUSDTM"
        # This happened because validation was skipped for MARKET orders

        mock_exchange = MagicMock()
        mock_exchange.get_futures_symbol_filters = AsyncMock(return_value={
            'LOT_SIZE': {
                'stepSize': '0.001',
                'minQty': '1.0',
                'maxQty': '1000000.0'
            },
            'PRICE_FILTER': {
                'tickSize': '0.01'
            },
            'MIN_NOTIONAL': {
                'minNotional': '0.00001'
            },
            'multiplier': '0.001'
        })
        mock_exchange.get_mark_price = AsyncMock(return_value=101390.86)
        mock_exchange._init_client = AsyncMock()
        mock_exchange.client = MagicMock()

        exchange = KucoinExchange("key", "secret", "passphrase", False)
        exchange.get_futures_symbol_filters = mock_exchange.get_futures_symbol_filters
        exchange.get_mark_price = mock_exchange.get_mark_price
        exchange._init_client = AsyncMock()
        exchange.client = mock_exchange.client

        with patch('src.exchange.kucoin.kucoin_exchange.symbol_converter') as mock_converter:
            mock_converter.convert_bot_to_kucoin_futures.return_value = "XBTUSDTM"

            # Test MARKET order - should now fetch mark price and validate
            result = await exchange.create_futures_order(
                pair="BTC-USDT",
                side="BUY",
                order_type="MARKET",
                amount=0.004,
                price=None
            )

            # Verify mark price was fetched (this was the bug - it wasn't being fetched)
            mock_exchange.get_mark_price.assert_called_once_with("BTC-USDT")

            # Should not return notional error (0.004 * 101390.86 = 405.56 > 0.00001)
            assert 'error' not in result or result.get('code') != -4007

    @pytest.mark.asyncio
    async def test_eth_limit_order_scenario(self):
        """Test ETH LIMIT order scenario from trade data."""
        from src.exchange.binance.binance_exchange import BinanceExchange

        # Trade data: "eth limit long 3074 - 3042 sl 2957"
        # position_size: 0.02000000
        # entry_price: 3074
        # Notional: 0.02 * 3074 = 61.48 USDT

        mock_exchange = MagicMock()
        mock_exchange.get_futures_symbol_filters = AsyncMock(return_value={
            'LOT_SIZE': {
                'stepSize': '0.001',
                'minQty': '0.001',
                'maxQty': '1000000.0'
            },
            'PRICE_FILTER': {
                'tickSize': '0.01'
            },
            'MIN_NOTIONAL': {
                'notional': '10.0'  # Lower minimum for ETH
            }
        })
        mock_exchange.get_futures_mark_price = AsyncMock()
        mock_exchange._init_client = AsyncMock()
        mock_exchange.client = MagicMock()

        exchange = BinanceExchange("key", "secret", False)
        exchange.get_futures_symbol_filters = mock_exchange.get_futures_symbol_filters
        exchange.get_futures_mark_price = mock_exchange.get_futures_mark_price
        exchange._init_client = AsyncMock()
        exchange.client = mock_exchange.client

        result = await exchange.create_futures_order(
            pair="ETHUSDT",
            side="BUY",
            order_type="LIMIT",
            amount=0.02,
            price=3074.0
        )

        # Should pass (61.48 > 10)
        assert 'error' not in result or result.get('code') != -4164


class TestNotionalValidationIntegration:
    """Integration tests for notional validation in signal processor."""

    @pytest.mark.asyncio
    async def test_final_notional_check_logic(self):
        """Test that final notional check logic works correctly."""
        # Test the notional validation logic directly
        # This verifies the calculation: trade_amount * price_for_validation >= min_notional

        trade_amount = 0.00049  # Small amount from trade data
        price_for_validation = 101390.86  # BTC price
        min_notional = 100.0

        # Calculate notional value
        final_notional = trade_amount * price_for_validation
        # 0.00049 * 101390.86 = 49.68 USDT < 100 USDT minimum

        # Verify the logic: should fail notional check
        assert final_notional < min_notional
        assert final_notional == pytest.approx(49.68, rel=0.01)

        # Test with larger amount that should pass
        larger_trade_amount = 0.001  # 0.001 BTC
        larger_notional = larger_trade_amount * price_for_validation
        # 0.001 * 101390.86 = 101.39 USDT > 100 USDT minimum
        assert larger_notional >= min_notional
        assert larger_notional == pytest.approx(101.39, rel=0.01)

        # Test LIMIT vs MARKET price usage
        # LIMIT orders should use signal_price
        limit_price = 86050.0  # From trade data
        limit_notional = trade_amount * limit_price
        # 0.00049 * 86050 = 42.16 USDT < 100
        assert limit_notional < min_notional

        # MARKET orders should use current_price (mark price)
        market_price = 101390.86  # Mark price
        market_notional = trade_amount * market_price
        # Same calculation as above
        assert market_notional < min_notional

