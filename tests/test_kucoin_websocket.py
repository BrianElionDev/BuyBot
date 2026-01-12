"""
Basic tests for KuCoin WebSocket implementation.
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch
from src.websocket.kucoin import KucoinWebSocketManager, KucoinWebSocketConfig
from src.websocket.kucoin.handlers.kucoin_user_data_handler import KucoinUserDataHandler

@pytest.fixture
def mock_db_manager():
    """Create a mock database manager."""
    manager = Mock()
    manager.find_trade_by_order_id = AsyncMock(return_value=None)
    manager.supabase = Mock()
    return manager

@pytest.fixture
def kucoin_config():
    """Create KuCoin websocket config."""
    return KucoinWebSocketConfig(is_testnet=False)

def test_config_initialization(kucoin_config):
    """Test configuration initialization."""
    assert kucoin_config.FUTURES_REST_BASE == "https://api-futures.kucoin.com"
    assert kucoin_config.RATE_LIMIT_MESSAGES_PER_10SEC == 100
    assert kucoin_config.PING_INTERVAL_DEFAULT == 18

def test_handler_initialization():
    """Test handler initialization."""
    handler = KucoinUserDataHandler()
    assert handler.execution_history == []
    assert handler.order_change_history == []

def test_symbol_conversion():
    """Test symbol conversion."""
    handler = KucoinUserDataHandler()
    assert handler.convert_symbol_to_bot_format("XBTUSDTM") == "BTCUSDT"
    assert handler.convert_symbol_to_bot_format("ETHUSDTM") == "ETHUSDT"

def test_status_mapping():
    """Test status mapping."""
    handler = KucoinUserDataHandler()
    order_status, position_status = handler.map_kucoin_status_to_internal("filled")
    assert order_status == "FILLED"
    assert position_status == "CLOSED"

    order_status, position_status = handler.map_kucoin_status_to_internal("canceled")
    assert order_status == "CANCELED"
    assert position_status == "FAILED"

@pytest.mark.asyncio
async def test_execution_report_handling():
    """Test execution report handling."""
    handler = KucoinUserDataHandler()

    event_data = {
        'data': {
            'orderId': '12345',
            'symbol': 'XBTUSDTM',
            'side': 'buy',
            'orderType': 'limit',
            'matchPrice': '45000',
            'matchSize': '1',
            'tradeTime': 1547026473000,
            'fee': '0.001',
            'feeCurrency': 'USDT'
        }
    }

    result = await handler.handle_execution_report(event_data)
    assert result is not None
    assert result.order_id == '12345'
    assert result.match_price == 45000.0
    assert result.match_size == 1.0

@pytest.mark.asyncio
async def test_order_change_handling():
    """Test order change handling."""
    handler = KucoinUserDataHandler()

    event_data = {
        'data': {
            'orderId': '12345',
            'symbol': 'XBTUSDTM',
            'type': 'filled',
            'status': 'filled',
            'filledSize': '1',
            'oldSize': '0',
            'orderType': 'limit',
            'side': 'buy',
            'price': '45000'
        }
    }

    result = await handler.handle_order_change(event_data)
    assert result is not None
    assert result.order_id == '12345'
    assert result.change_type == 'filled'
    assert result.filled_size == 1.0

def test_reconnect_delay_calculation(kucoin_config):
    """Test reconnect delay calculation."""
    delay1 = kucoin_config.get_reconnect_delay(1)
    assert delay1 == 5

    delay2 = kucoin_config.get_reconnect_delay(2)
    assert delay2 == 10

    delay3 = kucoin_config.get_reconnect_delay(3)
    assert delay3 == 20

def test_rate_limit_validation(kucoin_config):
    """Test rate limit validation."""
    assert kucoin_config.validate_rate_limits(50) == True
    assert kucoin_config.validate_rate_limits(100) == True
    assert kucoin_config.validate_rate_limits(101) == False
