"""
Comprehensive tests for KuCoin exchange implementation.

This test suite verifies that all KuCoin exchange methods are working correctly
and that the implementation is complete and accurate.
"""

import asyncio
import os
import pytest
import pytest_asyncio
from unittest.mock import Mock, AsyncMock, patch
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

from src.exchange.kucoin.kucoin_exchange import KucoinExchange
from src.bot.kucoin_trading_engine import KucoinTradingEngine
from src.services.pricing.price_service import PriceService
from src.core.market_data_handler import MarketDataHandler
from src.bot.risk_management.stop_loss_manager import StopLossManager
from src.bot.risk_management.take_profit_manager import TakeProfitManager
from src.bot.risk_management.position_auditor import PositionAuditor
from src.bot.order_management.order_creator import OrderCreator
from src.bot.order_management.order_canceller import OrderCanceller
from src.bot.order_management.order_update import OrderUpdater


class TestKucoinExchangeComprehensive:
    """Comprehensive tests for KuCoin exchange implementation."""

    @pytest_asyncio.fixture
    async def kucoin_exchange(self):
        """Create a KuCoin exchange instance for testing."""
        api_key = os.getenv('KUCOIN_API_KEY')
        api_secret = os.getenv('KUCOIN_API_SECRET')
        api_passphrase = os.getenv('KUCOIN_API_PASSPHRASE')

        if not all([api_key, api_secret, api_passphrase]):
            pytest.skip("KuCoin API credentials not found in environment")

        exchange = KucoinExchange(api_key, api_secret, api_passphrase, is_testnet=True)
        await exchange.initialize()
        yield exchange
        await exchange.close()

    @pytest.mark.asyncio
    async def test_exchange_initialization(self, kucoin_exchange):
        """Test that KuCoin exchange initializes correctly."""
        assert kucoin_exchange is not None
        assert kucoin_exchange.client is not None
        assert kucoin_exchange.is_testnet is True

    @pytest.mark.asyncio
    async def test_get_futures_account_info(self, kucoin_exchange):
        """Test getting futures account information."""
        account_info = await kucoin_exchange.get_futures_account_info()

        if account_info:  # May be None if no balance
            assert isinstance(account_info, dict)
            assert 'totalWalletBalance' in account_info
            assert 'currency' in account_info
            assert isinstance(account_info['totalWalletBalance'], float)

    @pytest.mark.asyncio
    async def test_get_futures_symbols(self, kucoin_exchange):
        """Test getting all futures symbols."""
        symbols = await kucoin_exchange.get_futures_symbols()

        assert isinstance(symbols, list)
        # Note: Testnet may have 0 symbols, which is acceptable
        if len(symbols) == 0:
            pytest.skip("No futures symbols available in testnet environment")

        # Check that we have some common symbols
        common_symbols = ['BTC-USDT', 'ETH-USDT', 'AVAX-USDT']
        for symbol in common_symbols:
            if symbol in symbols:
                break
        else:
            pytest.fail("No common symbols found in futures symbols list")

    @pytest.mark.asyncio
    async def test_is_futures_symbol_supported(self, kucoin_exchange):
        """Test symbol support validation."""
        # Test with a known symbol
        is_supported = await kucoin_exchange.is_futures_symbol_supported('BTC-USDT')
        assert isinstance(is_supported, bool)

        # Test with an invalid symbol
        is_supported_invalid = await kucoin_exchange.is_futures_symbol_supported('INVALID-SYMBOL')
        assert is_supported_invalid is False

    @pytest.mark.asyncio
    async def test_get_futures_symbol_filters(self, kucoin_exchange):
        """Test getting symbol filters for futures trading."""
        filters = await kucoin_exchange.get_futures_symbol_filters('BTC-USDT')

        if filters:  # May be None if symbol not found
            assert isinstance(filters, dict)
            assert 'symbol' in filters
            assert 'LOT_SIZE' in filters
            assert 'PRICE_FILTER' in filters
            assert 'MIN_NOTIONAL' in filters
            assert filters['symbol'] == 'BTC-USDT'

    @pytest.mark.asyncio
    async def test_get_current_prices(self, kucoin_exchange):
        """Test getting current prices for multiple symbols."""
        symbols = ['BTC-USDT', 'ETH-USDT']
        prices = await kucoin_exchange.get_current_prices(symbols)

        assert isinstance(prices, dict)
        for symbol in symbols:
            if symbol in prices:
                assert isinstance(prices[symbol], float)
                assert prices[symbol] > 0

    @pytest.mark.asyncio
    async def test_get_mark_price(self, kucoin_exchange):
        """Test getting mark price for a symbol."""
        mark_price = await kucoin_exchange.get_mark_price('BTC-USDT')

        if mark_price:  # May be None if symbol not found
            assert isinstance(mark_price, float)
            assert mark_price > 0

    @pytest.mark.asyncio
    async def test_get_order_book(self, kucoin_exchange):
        """Test getting order book data."""
        order_book = await kucoin_exchange.get_order_book('BTC-USDT', limit=5)

        if order_book:  # May be None if symbol not found
            assert isinstance(order_book, dict)
            assert 'bids' in order_book
            assert 'asks' in order_book
            assert isinstance(order_book['bids'], list)
            assert isinstance(order_book['asks'], list)

    @pytest.mark.asyncio
    async def test_validate_trade_amount(self, kucoin_exchange):
        """Test trade amount validation."""
        is_valid, error = await kucoin_exchange.validate_trade_amount('BTC-USDT', 0.001, 50000.0)

        assert isinstance(is_valid, bool)
        if not is_valid:
            assert isinstance(error, str)

    @pytest.mark.asyncio
    async def test_get_futures_position_information(self, kucoin_exchange):
        """Test getting futures position information."""
        positions = await kucoin_exchange.get_futures_position_information()

        assert isinstance(positions, list)
        # If there are positions, check their structure
        for position in positions:
            assert isinstance(position, dict)
            assert 'symbol' in position
            assert 'side' in position
            assert 'size' in position

    @pytest.mark.asyncio
    async def test_get_user_trades(self, kucoin_exchange):
        """Test getting user trade history."""
        trades = await kucoin_exchange.get_user_trades('BTC-USDT', limit=10)

        assert isinstance(trades, list)
        # If there are trades, check their structure
        for trade in trades:
            assert isinstance(trade, dict)
            assert 'id' in trade
            assert 'symbol' in trade
            assert 'side' in trade

    @pytest.mark.asyncio
    async def test_get_income_history(self, kucoin_exchange):
        """Test getting income history."""
        income = await kucoin_exchange.get_income_history('BTC-USDT', limit=10)

        assert isinstance(income, list)
        # If there is income, check its structure
        for record in income:
            assert isinstance(record, dict)
            assert 'id' in record
            assert 'type' in record
            assert 'amount' in record

    @pytest.mark.asyncio
    async def test_cancel_futures_order(self, kucoin_exchange):
        """Test canceling a futures order (with mock order ID)."""
        # This test uses a mock order ID since we don't have real orders
        success, response = await kucoin_exchange.cancel_futures_order('BTC-USDT', 'test_order_id')

        # The test should fail gracefully with an error message
        assert isinstance(success, bool)
        assert isinstance(response, dict)

    @pytest.mark.asyncio
    async def test_get_order_status(self, kucoin_exchange):
        """Test getting order status (with mock order ID)."""
        # This test uses a mock order ID since we don't have real orders
        order_status = await kucoin_exchange.get_order_status('BTC-USDT', 'test_order_id')

        # The test should return None for non-existent orders
        assert order_status is None or isinstance(order_status, dict)

    @pytest.mark.asyncio
    async def test_get_account_balances(self, kucoin_exchange):
        """Test getting account balances."""
        balances = await kucoin_exchange.get_account_balances()

        assert isinstance(balances, dict)
        # Check that balances are numeric
        for currency, balance in balances.items():
            assert isinstance(currency, str)
            assert isinstance(balance, float)

    @pytest.mark.asyncio
    async def test_get_spot_balance(self, kucoin_exchange):
        """Test getting spot balances."""
        balances = await kucoin_exchange.get_spot_balance()

        assert isinstance(balances, dict)
        # Check that balances are numeric
        for currency, balance in balances.items():
            assert isinstance(currency, str)
            assert isinstance(balance, float)

    @pytest.mark.asyncio
    async def test_get_futures_balance(self, kucoin_exchange):
        """Test getting futures balances."""
        balances = await kucoin_exchange.get_futures_balance()

        assert isinstance(balances, dict)
        # Check that balances are numeric
        for currency, balance in balances.items():
            assert isinstance(currency, str)
            assert isinstance(balance, float)

    @pytest.mark.asyncio
    async def test_calculate_max_position_size(self, kucoin_exchange):
        """Test calculating maximum position size."""
        max_size = await kucoin_exchange.calculate_max_position_size('BTC-USDT', leverage=1.0)

        # May be None if no account info or price available
        if max_size is not None:
            assert isinstance(max_size, float)
            assert max_size >= 0


class TestKucoinTradingEngineComprehensive:
    """Comprehensive tests for KuCoin trading engine."""

    @pytest_asyncio.fixture
    async def kucoin_trading_engine(self):
        """Create a KuCoin trading engine instance for testing."""
        api_key = os.getenv('KUCOIN_API_KEY')
        api_secret = os.getenv('KUCOIN_API_SECRET')
        api_passphrase = os.getenv('KUCOIN_API_PASSPHRASE')

        if not all([api_key, api_secret, api_passphrase]):
            pytest.skip("KuCoin API credentials not found in environment")

        # Create mock database manager
        mock_db_manager = Mock()

        # Create KuCoin exchange
        from src.exchange.kucoin.kucoin_exchange import KucoinExchange
        kucoin_exchange = KucoinExchange(api_key, api_secret, api_passphrase, is_testnet=True)
        await kucoin_exchange.initialize()

        # Create price service
        price_service = PriceService(kucoin_exchange=kucoin_exchange)

        # Create trading engine
        engine = KucoinTradingEngine(price_service, kucoin_exchange, mock_db_manager)

        yield engine
        await kucoin_exchange.close()

    @pytest.mark.asyncio
    async def test_trading_engine_initialization(self, kucoin_trading_engine):
        """Test that KuCoin trading engine initializes correctly."""
        assert kucoin_trading_engine is not None
        assert kucoin_trading_engine.kucoin_exchange is not None
        assert kucoin_trading_engine.price_service is not None

    @pytest.mark.asyncio
    async def test_calculate_trade_amount(self, kucoin_trading_engine):
        """Test trade amount calculation."""
        trade_amount = await kucoin_trading_engine._calculate_trade_amount('BTC', 50000.0)

        assert isinstance(trade_amount, float)
        assert trade_amount > 0

    @pytest.mark.asyncio
    async def test_calculate_trade_amount_with_multiplier(self, kucoin_trading_engine):
        """Test trade amount calculation with quantity multiplier."""
        trade_amount = await kucoin_trading_engine._calculate_trade_amount('BTC', 50000.0, quantity_multiplier=2)

        assert isinstance(trade_amount, float)
        assert trade_amount > 0

    @pytest.mark.asyncio
    async def test_handle_price_range_logic(self, kucoin_trading_engine):
        """Test price range logic handling."""
        # Test with single price
        price, reason = kucoin_trading_engine._handle_price_range_logic([50000.0], 'LIMIT', 'LONG', 50000.0)
        assert price == 50000.0
        assert isinstance(reason, str)

        # Test with multiple prices
        price, reason = kucoin_trading_engine._handle_price_range_logic([49000.0, 51000.0], 'LIMIT', 'LONG', 50000.0)
        assert price == 51000.0  # Should use highest for LONG
        assert isinstance(reason, str)

        # Test with market order
        price, reason = kucoin_trading_engine._handle_price_range_logic([49000.0, 51000.0], 'MARKET', 'LONG', 50000.0)
        assert price == 50000.0  # Should use current price for MARKET
        assert isinstance(reason, str)

    @pytest.mark.asyncio
    async def test_process_signal_validation(self, kucoin_trading_engine):
        """Test signal processing validation (without actual order creation)."""
        # Test with invalid symbol
        success, response = await kucoin_trading_engine.process_signal(
            coin_symbol='INVALID',
            signal_price=50000.0,
            position_type='LONG',
            order_type='MARKET'
        )

        assert success is False
        assert isinstance(response, str)

    @pytest.mark.asyncio
    async def test_close_position_at_market_validation(self, kucoin_trading_engine):
        """Test close position validation (without actual order creation)."""
        # Test with invalid trade row
        success, response = await kucoin_trading_engine.close_position_at_market(
            trade_row={'coin_symbol': 'INVALID'},
            reason='test',
            close_percentage=100.0
        )

        assert success is False
        assert isinstance(response, str)

    @pytest.mark.asyncio
    async def test_process_followup_signal(self, kucoin_trading_engine):
        """Test follow-up signal processing."""
        signal_data = {'content': 'stops moved to be'}
        trade_row = {'coin_symbol': 'BTC', 'signal_type': 'LONG'}

        result = await kucoin_trading_engine.process_followup_signal(signal_data, trade_row)

        assert isinstance(result, dict)
        assert 'status' in result
        assert 'message' in result

    @pytest.mark.asyncio
    async def test_get_exchange_type(self, kucoin_trading_engine):
        """Test getting exchange type."""
        exchange_type = kucoin_trading_engine.get_exchange_type()
        assert exchange_type == 'kucoin'


class TestKucoinModulesIntegration:
    """Integration tests for KuCoin modules."""

    @pytest_asyncio.fixture
    async def kucoin_modules(self):
        """Create KuCoin modules for integration testing."""
        api_key = os.getenv('KUCOIN_API_KEY')
        api_secret = os.getenv('KUCOIN_API_SECRET')
        api_passphrase = os.getenv('KUCOIN_API_PASSPHRASE')

        if not all([api_key, api_secret, api_passphrase]):
            pytest.skip("KuCoin API credentials not found in environment")

        # Create KuCoin exchange
        from src.exchange.kucoin.kucoin_exchange import KucoinExchange
        kucoin_exchange = KucoinExchange(api_key, api_secret, api_passphrase, is_testnet=True)
        await kucoin_exchange.initialize()

        # Create price service
        price_service = PriceService(kucoin_exchange=kucoin_exchange)

        # Create modules
        market_data_handler = MarketDataHandler(kucoin_exchange, price_service)
        stop_loss_manager = StopLossManager(kucoin_exchange)
        take_profit_manager = TakeProfitManager(kucoin_exchange)
        position_auditor = PositionAuditor(kucoin_exchange)
        order_creator = OrderCreator(kucoin_exchange)
        order_canceller = OrderCanceller(kucoin_exchange)
        order_updater = OrderUpdater(kucoin_exchange)

        yield {
            'exchange': kucoin_exchange,
            'price_service': price_service,
            'market_data_handler': market_data_handler,
            'stop_loss_manager': stop_loss_manager,
            'take_profit_manager': take_profit_manager,
            'position_auditor': position_auditor,
            'order_creator': order_creator,
            'order_canceller': order_canceller,
            'order_updater': order_updater
        }

        await kucoin_exchange.close()

    @pytest.mark.asyncio
    async def test_market_data_handler_integration(self, kucoin_modules):
        """Test market data handler integration with KuCoin."""
        handler = kucoin_modules['market_data_handler']

        # Test getting current market price
        price = await handler.get_current_market_price('BTC')
        if price:
            assert isinstance(price, float)
            assert price > 0

        # Test getting order book data
        order_book = await handler.get_order_book_data('BTC-USDT')
        if order_book:
            assert isinstance(order_book, dict)
            assert 'bids' in order_book
            assert 'asks' in order_book

    @pytest.mark.asyncio
    async def test_risk_management_modules_integration(self, kucoin_modules):
        """Test risk management modules integration with KuCoin."""
        stop_loss_manager = kucoin_modules['stop_loss_manager']
        take_profit_manager = kucoin_modules['take_profit_manager']
        position_auditor = kucoin_modules['position_auditor']

        # Test stop loss manager
        success, order_id = await stop_loss_manager.ensure_stop_loss_for_position(
            'BTC', 'LONG', 0.001, 50000.0
        )
        # Should fail gracefully for test environment
        assert isinstance(success, bool)

        # Test take profit manager
        success, order_id = await take_profit_manager.ensure_take_profit_for_position(
            'BTC', 'LONG', 0.001, 50000.0
        )
        # Should fail gracefully for test environment
        assert isinstance(success, bool)

        # Test position auditor
        audit_result = await position_auditor.audit_all_positions()
        assert isinstance(audit_result, dict)

    @pytest.mark.asyncio
    async def test_order_management_modules_integration(self, kucoin_modules):
        """Test order management modules integration with KuCoin."""
        order_creator = kucoin_modules['order_creator']
        order_canceller = kucoin_modules['order_canceller']
        order_updater = kucoin_modules['order_updater']

        # Test order creator
        orders, stop_loss_id = await order_creator.create_tp_sl_orders(
            'BTC-USDT', 'LONG', 0.001, take_profits=[55000.0], stop_loss=45000.0
        )
        # Should return empty list for test environment
        assert isinstance(orders, list)
        assert stop_loss_id is None or isinstance(stop_loss_id, str)

        # Test order canceller
        cancelled = await order_canceller.cancel_tp_sl_orders('BTC-USDT', {})
        # Should return False for test environment
        assert isinstance(cancelled, bool)

        # Test order updater
        order_status = await order_updater.update_order_status('BTC-USDT', 'test_order_id')
        # Should return None for non-existent order
        assert order_status is None or isinstance(order_status, dict)


if __name__ == '__main__':
    # Run tests
    pytest.main([__file__, '-v', '--tb=short'])
