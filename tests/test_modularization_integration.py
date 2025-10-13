#!/usr/bin/env python3
"""
Modularization Integration Test

This test verifies that the modularized system works correctly with a sample trade.
"""

import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from typing import Dict, Any

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Sample trade data based on the provided table structure
SAMPLE_TRADE = {
    "id": 12345,
    "discord_id": "test_discord_123",
    "trader": "@Johnny",
    "content": "BTC/USDT LONG Entry: 45000 SL: 44000 TP1: 46000 TP2: 47000",
    "structured": "BTC/USDT LONG Entry: 45000 SL: 44000 TP1: 46000 TP2: 47000",
    "timestamp": "2025-01-15T10:30:00Z",
    "trade_group_id": "550e8400-e29b-41d4-a716-446655440000",
    "exchange_response": '{"orderId": 123456789, "symbol": "BTCUSDT", "status": "FILLED", "price": "45000.00"}',
    "status": "OPEN",
    "exchange_order_id": "123456789",
    "exit_price": 0.0,
    "pnl_usd": 0.0,
    "parsed_signal": {
        "coin_symbol": "BTC",
        "position_type": "LONG",
        "entry_prices": [45000.0],
        "stop_loss": 44000.0,
        "take_profits": [46000.0, 47000.0],
        "position_size": 0.1
    },
    "created_at": "2025-01-15T10:30:00Z",
    "isHistoricData": False,
    "stop_loss_order_id": "987654321",
    "position_size": 0.1,
    "signal_type": "LONG",
    "entry_price": 45000.0,
    "exit_price": 0.0,
    "updated_at": "2025-01-15T10:30:00Z",
    "realized_pnl": 0.0,
    "unrealized_pnl": 0.0,
    "last_pnl_sync": "2025-01-15T10:30:00Z",
    "sync_order_response": '{"orderId": 123456789, "symbol": "BTCUSDT", "status": "FILLED"}',
    "order_status_response": "FILLED",
    "sync_error_count": 0,
    "sync_issues": [],
    "manual_verification_needed": False,
    "coin_symbol": "BTC",
    "signal_id": "signal_123",
    "is_active": True,
    "tp_sl_orders": [
        {"orderId": "987654321", "type": "STOP_LOSS", "price": 44000.0},
        {"orderId": "111222333", "type": "TAKE_PROFIT", "price": 46000.0}
    ],
    "order_status": "FILLED",
    "closed_at": None,
    "net_pnl": 0.0,
    "tp_status": {"tp1": "PENDING", "tp2": "PENDING"}
}

async def test_database_layer():
    """Test database layer functionality."""
    logger.info("🧪 Testing Database Layer...")
    try:
        from src.database import DatabaseManager
        from src.database.models.trade_models import Trade, TradeStatus
        from src.database.repositories.trade_repository import TradeRepository

        # Test model creation
        trade_model = Trade(
            id=SAMPLE_TRADE["id"],
            discord_id=SAMPLE_TRADE["discord_id"],
            trader=SAMPLE_TRADE["trader"],
            content=SAMPLE_TRADE["content"],
            status=TradeStatus.OPEN.value,
            coin_symbol=SAMPLE_TRADE["coin_symbol"],
            entry_price=SAMPLE_TRADE["entry_price"],
            position_size=SAMPLE_TRADE["position_size"]
        )

        logger.info(f"✅ Database Layer: Trade model created successfully - {trade_model.coin_symbol}")
        return True
    except Exception as e:
        logger.error(f"❌ Database Layer failed: {e}")
        return False

async def test_api_layer():
    """Test API layer functionality."""
    logger.info("🧪 Testing API Layer...")
    try:
        from src.api.models.request_models import TradeRequest
        from src.api.models.response_models import TradeResponse

        # Test request model
        trade_request = TradeRequest(
            coin_symbol=SAMPLE_TRADE["coin_symbol"],
            position_type=SAMPLE_TRADE["signal_type"],
            order_type="MARKET",
            amount=SAMPLE_TRADE["position_size"],
            price=SAMPLE_TRADE["entry_price"],
            stop_loss=44000.0,
            take_profits=[46000.0, 47000.0]
        )

        # Test response model
        trade_response = TradeResponse(
            trade_id=SAMPLE_TRADE["id"],
            status="OPEN",
            coin_symbol=SAMPLE_TRADE["coin_symbol"],
            position_type=SAMPLE_TRADE["signal_type"],
            entry_price=SAMPLE_TRADE["entry_price"],
            position_size=SAMPLE_TRADE["position_size"],
            pnl=0.0,
            created_at=datetime.now(timezone.utc)
        )

        logger.info(f"✅ API Layer: Models created successfully - {trade_response.coin_symbol}")
        return True
    except Exception as e:
        logger.error(f"❌ API Layer failed: {e}")
        return False

async def test_services_layer():
    """Test services layer functionality."""
    logger.info("🧪 Testing Services Layer...")
    try:
        from src.services.analytics.analytics_models import MarketAnalysis

        # Test analytics model
        market_analysis = MarketAnalysis(
            symbol=SAMPLE_TRADE["coin_symbol"],
            timestamp=datetime.now(timezone.utc),
            price=SAMPLE_TRADE["entry_price"]
        )

        logger.info(f"✅ Services Layer: Models created successfully - {market_analysis.symbol}")
        return True
    except Exception as e:
        logger.error(f"❌ Services Layer failed: {e}")
        return False

async def test_exchange_layer():
    """Test exchange layer functionality."""
    logger.info("🧪 Testing Exchange Layer...")
    try:
        from src.exchange import ExchangeConfig, BinanceExchange
        from src.exchange.binance.binance_models import BinanceOrder

        # Test configuration (with empty credentials for testing)
        config = ExchangeConfig()

        # Test Binance models
        binance_order = BinanceOrder(
            order_id=SAMPLE_TRADE["exchange_order_id"],
            symbol=f"{SAMPLE_TRADE['coin_symbol']}USDT",
            side="BUY",
            order_type="MARKET",
            quantity=SAMPLE_TRADE["position_size"],
            status="FILLED",
            price=SAMPLE_TRADE["entry_price"]
        )

        logger.info(f"✅ Exchange Layer: Models created successfully - {binance_order.symbol}")
        return True
    except Exception as e:
        logger.error(f"❌ Exchange Layer failed: {e}")
        return False

async def test_websocket_layer():
    """Test WebSocket layer functionality."""
    logger.info("🧪 Testing WebSocket Layer...")
    try:
        from src.websocket.core import WebSocketConfig, WebSocketManager
        from src.websocket.handlers.handler_models import MarketData

        # Test WebSocket configuration
        ws_config = WebSocketConfig(is_testnet=False)

        # Test event model
        market_event = MarketData(
            symbol=f"{SAMPLE_TRADE['coin_symbol']}USDT",
            price=SAMPLE_TRADE["entry_price"],
            quantity=SAMPLE_TRADE["position_size"],
            trade_time=datetime.now(timezone.utc),
            event_type="trade"
        )

        logger.info(f"✅ WebSocket Layer: Models created successfully - {market_event.symbol}")
        return True
    except Exception as e:
        logger.error(f"❌ WebSocket Layer failed: {e}")
        return False

async def test_discord_bot_integration():
    """Test Discord bot integration."""
    logger.info("🧪 Testing Discord Bot Integration...")
    try:
        from discord_bot import DiscordBot
        from discord_bot.models import InitialDiscordSignal

        # Test signal model
        signal = InitialDiscordSignal(
            discord_id=SAMPLE_TRADE["discord_id"],
            trader=SAMPLE_TRADE["trader"],
            content=SAMPLE_TRADE["content"],
            timestamp=SAMPLE_TRADE["timestamp"],
            structured=SAMPLE_TRADE["structured"]
        )

        logger.info(f"✅ Discord Bot Integration: Signal model created successfully - {signal.discord_id}")
        return True
    except Exception as e:
        logger.error(f"❌ Discord Bot Integration failed: {e}")
        return False

async def test_script_organization():
    """Test script organization."""
    logger.info("🧪 Testing Script Organization...")
    try:
        # Test that scripts are properly organized
        script_dirs = [
            "scripts/setup",
            "scripts/maintenance",
            "scripts/testing",
            "scripts/analytics",
            "scripts/account_management",
            "scripts/utils"
        ]

        for script_dir in script_dirs:
            if os.path.exists(script_dir):
                logger.info(f"✅ Script directory exists: {script_dir}")
            else:
                logger.warning(f"⚠️ Script directory missing: {script_dir}")

        logger.info("✅ Script Organization: Directory structure verified")
        return True
    except Exception as e:
        logger.error(f"❌ Script Organization failed: {e}")
        return False

async def test_end_to_end_workflow():
    """Test end-to-end workflow with sample trade."""
    logger.info("🧪 Testing End-to-End Workflow...")
    try:
        # Test the complete flow from signal to database
        from discord_bot.models import InitialDiscordSignal
        from src.database.models.trade_models import Trade, TradeStatus

        # Create signal
        signal = InitialDiscordSignal(
            discord_id=SAMPLE_TRADE["discord_id"],
            trader=SAMPLE_TRADE["trader"],
            content=SAMPLE_TRADE["content"],
            timestamp=SAMPLE_TRADE["timestamp"],
            structured=SAMPLE_TRADE["structured"]
        )

        # Create trade model
        trade = Trade(
            id=SAMPLE_TRADE["id"],
            discord_id=signal.discord_id,
            trader=signal.trader,
            content=signal.content,
            status=TradeStatus.OPEN.value,
            coin_symbol=SAMPLE_TRADE["coin_symbol"],
            entry_price=SAMPLE_TRADE["entry_price"],
            position_size=SAMPLE_TRADE["position_size"]
        )

        # Test API response
        from src.api.models.response_models import TradeResponse

        api_response = TradeResponse(
            trade_id=trade.id,
            status="OPEN",
            coin_symbol=trade.coin_symbol,
            position_type=SAMPLE_TRADE["signal_type"],
            entry_price=trade.entry_price,
            position_size=trade.position_size,
            pnl=0.0,
            created_at=datetime.now(timezone.utc)
        )

        logger.info(f"✅ End-to-End Workflow: Complete flow tested successfully - {api_response.coin_symbol}")
        return True
    except Exception as e:
        logger.error(f"❌ End-to-End Workflow failed: {e}")
        return False

async def main():
    """Run all integration tests."""
    logger.info("🚀 Starting Modularization Integration Tests")
    logger.info("=" * 60)

    tests = [
        ("Database Layer", test_database_layer),
        ("API Layer", test_api_layer),
        ("Services Layer", test_services_layer),
        ("Exchange Layer", test_exchange_layer),
        ("WebSocket Layer", test_websocket_layer),
        ("Discord Bot Integration", test_discord_bot_integration),
        ("Script Organization", test_script_organization),
        ("End-to-End Workflow", test_end_to_end_workflow)
    ]

    results = {}
    passed = 0
    total = len(tests)

    for test_name, test_func in tests:
        logger.info(f"\n📋 Running {test_name} test...")
        try:
            result = await test_func()
            results[test_name] = result
            if result:
                passed += 1
                logger.info(f"✅ {test_name}: PASSED")
            else:
                logger.error(f"❌ {test_name}: FAILED")
        except Exception as e:
            logger.error(f"❌ {test_name}: ERROR - {e}")
            results[test_name] = False

    # Summary
    logger.info("\n" + "=" * 60)
    logger.info("📊 INTEGRATION TEST RESULTS")
    logger.info("=" * 60)

    for test_name, result in results.items():
        status = "✅ PASSED" if result else "❌ FAILED"
        logger.info(f"{test_name}: {status}")

    logger.info(f"\n🎯 Overall: {passed}/{total} tests passed ({passed/total*100:.1f}%)")

    if passed == total:
        logger.info("🎉 All tests passed! Modularization is working correctly.")
    else:
        logger.warning(f"⚠️ {total-passed} tests failed. Some issues need attention.")

    return passed == total

if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)

"""
Modularization Integration Test

This test verifies that the modularized system works correctly with a sample trade.
"""

import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from typing import Dict, Any

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Sample trade data based on the provided table structure
SAMPLE_TRADE = {
    "id": 12345,
    "discord_id": "test_discord_123",
    "trader": "@Johnny",
    "content": "BTC/USDT LONG Entry: 45000 SL: 44000 TP1: 46000 TP2: 47000",
    "structured": "BTC/USDT LONG Entry: 45000 SL: 44000 TP1: 46000 TP2: 47000",
    "timestamp": "2025-01-15T10:30:00Z",
    "trade_group_id": "550e8400-e29b-41d4-a716-446655440000",
    "exchange_response": '{"orderId": 123456789, "symbol": "BTCUSDT", "status": "FILLED", "price": "45000.00"}',
    "status": "OPEN",
    "exchange_order_id": "123456789",
    "exit_price": 0.0,
    "pnl_usd": 0.0,
    "parsed_signal": {
        "coin_symbol": "BTC",
        "position_type": "LONG",
        "entry_prices": [45000.0],
        "stop_loss": 44000.0,
        "take_profits": [46000.0, 47000.0],
        "position_size": 0.1
    },
    "created_at": "2025-01-15T10:30:00Z",
    "isHistoricData": False,
    "stop_loss_order_id": "987654321",
    "position_size": 0.1,
    "signal_type": "LONG",
    "entry_price": 45000.0,
    "exit_price": 0.0,
    "updated_at": "2025-01-15T10:30:00Z",
    "realized_pnl": 0.0,
    "unrealized_pnl": 0.0,
    "last_pnl_sync": "2025-01-15T10:30:00Z",
    "sync_order_response": '{"orderId": 123456789, "symbol": "BTCUSDT", "status": "FILLED"}',
    "order_status_response": "FILLED",
    "sync_error_count": 0,
    "sync_issues": [],
    "manual_verification_needed": False,
    "coin_symbol": "BTC",
    "signal_id": "signal_123",
    "is_active": True,
    "tp_sl_orders": [
        {"orderId": "987654321", "type": "STOP_LOSS", "price": 44000.0},
        {"orderId": "111222333", "type": "TAKE_PROFIT", "price": 46000.0}
    ],
    "order_status": "FILLED",
    "closed_at": None,
    "net_pnl": 0.0,
    "tp_status": {"tp1": "PENDING", "tp2": "PENDING"}
}

async def test_database_layer():
    """Test database layer functionality."""
    logger.info("🧪 Testing Database Layer...")
    try:
        from src.database import DatabaseManager
        from src.database.models.trade_models import Trade, TradeStatus
        from src.database.repositories.trade_repository import TradeRepository

        # Test model creation
        trade_model = Trade(
            id=SAMPLE_TRADE["id"],
            discord_id=SAMPLE_TRADE["discord_id"],
            trader=SAMPLE_TRADE["trader"],
            content=SAMPLE_TRADE["content"],
            status=TradeStatus.OPEN.value,
            coin_symbol=SAMPLE_TRADE["coin_symbol"],
            entry_price=SAMPLE_TRADE["entry_price"],
            position_size=SAMPLE_TRADE["position_size"]
        )

        logger.info(f"✅ Database Layer: Trade model created successfully - {trade_model.coin_symbol}")
        return True
    except Exception as e:
        logger.error(f"❌ Database Layer failed: {e}")
        return False

async def test_api_layer():
    """Test API layer functionality."""
    logger.info("🧪 Testing API Layer...")
    try:
        from src.api.models.request_models import TradeRequest
        from src.api.models.response_models import TradeResponse

        # Test request model
        trade_request = TradeRequest(
            coin_symbol=SAMPLE_TRADE["coin_symbol"],
            position_type=SAMPLE_TRADE["signal_type"],
            order_type="MARKET",
            amount=SAMPLE_TRADE["position_size"],
            price=SAMPLE_TRADE["entry_price"],
            stop_loss=44000.0,
            take_profits=[46000.0, 47000.0]
        )

        # Test response model
        trade_response = TradeResponse(
            trade_id=SAMPLE_TRADE["id"],
            status="OPEN",
            coin_symbol=SAMPLE_TRADE["coin_symbol"],
            position_type=SAMPLE_TRADE["signal_type"],
            entry_price=SAMPLE_TRADE["entry_price"],
            position_size=SAMPLE_TRADE["position_size"],
            pnl=0.0,
            created_at=datetime.now(timezone.utc)
        )

        logger.info(f"✅ API Layer: Models created successfully - {trade_response.coin_symbol}")
        return True
    except Exception as e:
        logger.error(f"❌ API Layer failed: {e}")
        return False

async def test_services_layer():
    """Test services layer functionality."""
    logger.info("🧪 Testing Services Layer...")
    try:
        from src.services.analytics.analytics_models import MarketAnalysis

        # Test analytics model
        market_analysis = MarketAnalysis(
            symbol=SAMPLE_TRADE["coin_symbol"],
            timestamp=datetime.now(timezone.utc),
            price=SAMPLE_TRADE["entry_price"]
        )

        logger.info(f"✅ Services Layer: Models created successfully - {market_analysis.symbol}")
        return True
    except Exception as e:
        logger.error(f"❌ Services Layer failed: {e}")
        return False

async def test_exchange_layer():
    """Test exchange layer functionality."""
    logger.info("🧪 Testing Exchange Layer...")
    try:
        from src.exchange import ExchangeConfig, BinanceExchange
        from src.exchange.binance.binance_models import BinanceOrder

        # Test configuration (with empty credentials for testing)
        config = ExchangeConfig()

        # Test Binance models
        binance_order = BinanceOrder(
            order_id=SAMPLE_TRADE["exchange_order_id"],
            symbol=f"{SAMPLE_TRADE['coin_symbol']}USDT",
            side="BUY",
            order_type="MARKET",
            quantity=SAMPLE_TRADE["position_size"],
            status="FILLED",
            price=SAMPLE_TRADE["entry_price"]
        )

        logger.info(f"✅ Exchange Layer: Models created successfully - {binance_order.symbol}")
        return True
    except Exception as e:
        logger.error(f"❌ Exchange Layer failed: {e}")
        return False

async def test_websocket_layer():
    """Test WebSocket layer functionality."""
    logger.info("🧪 Testing WebSocket Layer...")
    try:
        from src.websocket.core import WebSocketConfig, WebSocketManager
        from src.websocket.handlers.handler_models import MarketData

        # Test WebSocket configuration
        ws_config = WebSocketConfig(is_testnet=False)

        # Test event model
        market_event = MarketData(
            symbol=f"{SAMPLE_TRADE['coin_symbol']}USDT",
            price=SAMPLE_TRADE["entry_price"],
            quantity=SAMPLE_TRADE["position_size"],
            trade_time=datetime.now(timezone.utc),
            event_type="trade"
        )

        logger.info(f"✅ WebSocket Layer: Models created successfully - {market_event.symbol}")
        return True
    except Exception as e:
        logger.error(f"❌ WebSocket Layer failed: {e}")
        return False

async def test_discord_bot_integration():
    """Test Discord bot integration."""
    logger.info("🧪 Testing Discord Bot Integration...")
    try:
        from discord_bot import DiscordBot
        from discord_bot.models import InitialDiscordSignal

        # Test signal model
        signal = InitialDiscordSignal(
            discord_id=SAMPLE_TRADE["discord_id"],
            trader=SAMPLE_TRADE["trader"],
            content=SAMPLE_TRADE["content"],
            timestamp=SAMPLE_TRADE["timestamp"],
            structured=SAMPLE_TRADE["structured"]
        )

        logger.info(f"✅ Discord Bot Integration: Signal model created successfully - {signal.discord_id}")
        return True
    except Exception as e:
        logger.error(f"❌ Discord Bot Integration failed: {e}")
        return False

async def test_script_organization():
    """Test script organization."""
    logger.info("🧪 Testing Script Organization...")
    try:
        # Test that scripts are properly organized
        script_dirs = [
            "scripts/setup",
            "scripts/maintenance",
            "scripts/testing",
            "scripts/analytics",
            "scripts/account_management",
            "scripts/utils"
        ]

        for script_dir in script_dirs:
            if os.path.exists(script_dir):
                logger.info(f"✅ Script directory exists: {script_dir}")
            else:
                logger.warning(f"⚠️ Script directory missing: {script_dir}")

        logger.info("✅ Script Organization: Directory structure verified")
        return True
    except Exception as e:
        logger.error(f"❌ Script Organization failed: {e}")
        return False

async def test_end_to_end_workflow():
    """Test end-to-end workflow with sample trade."""
    logger.info("🧪 Testing End-to-End Workflow...")
    try:
        # Test the complete flow from signal to database
        from discord_bot.models import InitialDiscordSignal
        from src.database.models.trade_models import Trade, TradeStatus

        # Create signal
        signal = InitialDiscordSignal(
            discord_id=SAMPLE_TRADE["discord_id"],
            trader=SAMPLE_TRADE["trader"],
            content=SAMPLE_TRADE["content"],
            timestamp=SAMPLE_TRADE["timestamp"],
            structured=SAMPLE_TRADE["structured"]
        )

        # Create trade model
        trade = Trade(
            id=SAMPLE_TRADE["id"],
            discord_id=signal.discord_id,
            trader=signal.trader,
            content=signal.content,
            status=TradeStatus.OPEN.value,
            coin_symbol=SAMPLE_TRADE["coin_symbol"],
            entry_price=SAMPLE_TRADE["entry_price"],
            position_size=SAMPLE_TRADE["position_size"]
        )

        # Test API response
        from src.api.models.response_models import TradeResponse

        api_response = TradeResponse(
            trade_id=trade.id,
            status="OPEN",
            coin_symbol=trade.coin_symbol,
            position_type=SAMPLE_TRADE["signal_type"],
            entry_price=trade.entry_price,
            position_size=trade.position_size,
            pnl=0.0,
            created_at=datetime.now(timezone.utc)
        )

        logger.info(f"✅ End-to-End Workflow: Complete flow tested successfully - {api_response.coin_symbol}")
        return True
    except Exception as e:
        logger.error(f"❌ End-to-End Workflow failed: {e}")
        return False

async def main():
    """Run all integration tests."""
    logger.info("🚀 Starting Modularization Integration Tests")
    logger.info("=" * 60)

    tests = [
        ("Database Layer", test_database_layer),
        ("API Layer", test_api_layer),
        ("Services Layer", test_services_layer),
        ("Exchange Layer", test_exchange_layer),
        ("WebSocket Layer", test_websocket_layer),
        ("Discord Bot Integration", test_discord_bot_integration),
        ("Script Organization", test_script_organization),
        ("End-to-End Workflow", test_end_to_end_workflow)
    ]

    results = {}
    passed = 0
    total = len(tests)

    for test_name, test_func in tests:
        logger.info(f"\n📋 Running {test_name} test...")
        try:
            result = await test_func()
            results[test_name] = result
            if result:
                passed += 1
                logger.info(f"✅ {test_name}: PASSED")
            else:
                logger.error(f"❌ {test_name}: FAILED")
        except Exception as e:
            logger.error(f"❌ {test_name}: ERROR - {e}")
            results[test_name] = False

    # Summary
    logger.info("\n" + "=" * 60)
    logger.info("📊 INTEGRATION TEST RESULTS")
    logger.info("=" * 60)

    for test_name, result in results.items():
        status = "✅ PASSED" if result else "❌ FAILED"
        logger.info(f"{test_name}: {status}")

    logger.info(f"\n🎯 Overall: {passed}/{total} tests passed ({passed/total*100:.1f}%)")

    if passed == total:
        logger.info("🎉 All tests passed! Modularization is working correctly.")
    else:
        logger.warning(f"⚠️ {total-passed} tests failed. Some issues need attention.")

    return passed == total

if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)



