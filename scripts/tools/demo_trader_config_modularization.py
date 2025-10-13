#!/usr/bin/env python3
"""
Demo Trader Configuration Modularization

This script demonstrates the new modularized trader configuration system
that uses the database instead of hardcoded values.
"""

import sys
import os
import asyncio
import json
from typing import Dict, Any

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from src.services.trader_config_service import (
    trader_config_service, ExchangeType, TraderConfig
)
from src.bot.signal_router import SignalRouter
from src.services.active_futures_sync_service import ActiveFuturesSyncService


async def demo_trader_config_service():
    """Demonstrate the trader configuration service."""

    print("🎯 Trader Configuration Service Demo")
    print("=" * 50)

    # Initialize runtime config (this would normally be done by the app)
    try:
        from src.config.runtime_config import init_runtime_config
        from config.settings import SUPABASE_URL, SUPABASE_KEY

        if SUPABASE_URL and SUPABASE_KEY:
            init_runtime_config(SUPABASE_URL, SUPABASE_KEY)
            print("✅ Runtime config initialized")
        else:
            print("⚠️  Supabase credentials not found, using mock data")
    except Exception as e:
        print(f"⚠️  Could not initialize runtime config: {e}")

    # Demo 1: Get supported traders
    print("\n1. Getting supported traders from database:")
    try:
        traders = await trader_config_service.get_supported_traders()
        print(f"   Supported traders: {traders}")
        print(f"   Total count: {len(traders)}")
    except Exception as e:
        print(f"   Error: {e}")
        print("   Using fallback traders: ['@Johnny', '@Tareeq']")
        traders = ["@Johnny", "@Tareeq"]

    # Demo 2: Check trader support
    print("\n2. Checking trader support:")
    test_traders = ["@Johnny", "@Tareeq", "@NewTrader", "@Unknown"]
    for trader in test_traders:
        try:
            is_supported = await trader_config_service.is_trader_supported(trader)
            exchange = await trader_config_service.get_exchange_for_trader(trader)
            print(f"   {trader}: {'✅ Supported' if is_supported else '❌ Not supported'} -> {exchange.value}")
        except Exception as e:
            print(f"   {trader}: Error - {e}")

    # Demo 3: Get traders by exchange
    print("\n3. Getting traders by exchange:")
    for exchange in [ExchangeType.BINANCE, ExchangeType.KUCOIN]:
        try:
            exchange_traders = await trader_config_service.get_traders_for_exchange(exchange)
            print(f"   {exchange.value}: {exchange_traders}")
        except Exception as e:
            print(f"   {exchange.value}: Error - {e}")

    # Demo 4: Get leverage for specific trader
    print("\n4. Getting leverage for traders:")
    for trader in traders[:2]:  # Test first 2 traders
        try:
            config = await trader_config_service.get_trader_config(trader)
            if config:
                print(f"   {trader}: {config.leverage}x leverage on {config.exchange.value}")
            else:
                print(f"   {trader}: No configuration found")
        except Exception as e:
            print(f"   {trader}: Error - {e}")


async def demo_signal_router():
    """Demonstrate the signal router with database-driven configuration."""

    print("\n\n🔄 Signal Router Demo")
    print("=" * 30)

    # Create mock trading engines
    class MockTradingEngine:
        def __init__(self, name):
            self.name = name

    binance_engine = MockTradingEngine("Binance")
    kucoin_engine = MockTradingEngine("KuCoin")

    # Create signal router
    signal_router = SignalRouter(binance_engine, kucoin_engine)

    # Demo routing signals
    test_signals = [
        {"trader": "@Johnny", "coin": "BTCUSDT", "action": "LONG"},
        {"trader": "@Tareeq", "coin": "ETHUSDT", "action": "SHORT"},
        {"trader": "@NewTrader", "coin": "SOLUSDT", "action": "LONG"},
    ]

    print("\nRouting test signals:")
    for signal in test_signals:
        try:
            is_supported = await signal_router.is_trader_supported(signal["trader"])
            if is_supported:
                exchange = await signal_router.get_exchange_for_trader(signal["trader"])
                print(f"   {signal['trader']} -> {signal['coin']} {signal['action']} -> {exchange.value} ✅")
            else:
                print(f"   {signal['trader']} -> {signal['coin']} {signal['action']} -> REJECTED ❌")
        except Exception as e:
            print(f"   {signal['trader']} -> Error: {e}")


async def demo_active_futures_sync():
    """Demonstrate the active futures sync service."""

    print("\n\n📊 Active Futures Sync Service Demo")
    print("=" * 40)

    # Create mock database manager
    class MockDatabaseManager:
        async def initialize(self):
            pass

    db_manager = MockDatabaseManager()
    sync_service = ActiveFuturesSyncService(db_manager)

    # Demo initialization
    print("\nInitializing sync service:")
    try:
        success = await sync_service.initialize()
        if success:
            print(f"   ✅ Service initialized successfully")
            print(f"   Target traders: {sync_service.target_traders}")
        else:
            print("   ❌ Service initialization failed")
    except Exception as e:
        print(f"   Error: {e}")

    # Demo sync status
    print("\nGetting sync status:")
    try:
        status = await sync_service.get_sync_status()
        print(f"   Status: {json.dumps(status, indent=2)}")
    except Exception as e:
        print(f"   Error: {e}")


async def demo_api_endpoints():
    """Demonstrate the API endpoints (if available)."""

    print("\n\n🌐 API Endpoints Demo")
    print("=" * 25)

    print("\nAvailable endpoints:")
    endpoints = [
        "GET /api/v1/trader-config/ - Get all trader configs",
        "GET /api/v1/trader-config/{trader_id} - Get specific trader config",
        "POST /api/v1/trader-config/ - Create/update trader config",
        "DELETE /api/v1/trader-config/{trader_id} - Delete trader config",
        "GET /api/v1/trader-config/exchange/{exchange} - Get traders for exchange",
        "GET /api/v1/trader-config/supported/traders - Get supported traders",
        "POST /api/v1/trader-config/validate/{trader_id} - Validate trader support",
        "POST /api/v1/trader-config/cache/clear - Clear cache"
    ]

    for endpoint in endpoints:
        print(f"   {endpoint}")

    print("\n💡 To test these endpoints, run:")
    print("   python scripts/tools/test_trader_config_api.py")


async def demo_migration_benefits():
    """Demonstrate the benefits of the modularized system."""

    print("\n\n✨ Migration Benefits")
    print("=" * 25)

    benefits = [
        "🔄 Dynamic Configuration: Traders can be added/removed without code changes",
        "💾 Database-Driven: All configuration stored in trader_exchange_config table",
        "🚀 Real-Time Updates: Changes take effect immediately without restarts",
        "🔧 Easy Management: Business users can manage traders via API endpoints",
        "📊 Centralized: Single source of truth for trader-to-exchange mapping",
        "🛡️ Fallback Support: Graceful degradation to .env config if database unavailable",
        "⚡ Caching: Performance optimized with configurable cache TTL",
        "🔍 Validation: Built-in validation for exchanges and leverage values",
        "📈 Scalable: Easy to add new exchanges or trader attributes"
    ]

    for benefit in benefits:
        print(f"   {benefit}")

    print("\n🎯 Key Improvements:")
    print("   • No more hardcoded trader lists in .env files")
    print("   • Business users can manage traders independently")
    print("   • System automatically adapts to configuration changes")
    print("   • Better separation of concerns between code and configuration")


async def main():
    """Main demo function."""

    print("🚀 Trader Configuration Modularization Demo")
    print("=" * 60)
    print("This demo shows the new database-driven trader configuration system")
    print("that replaces hardcoded TARGET_TRADERS with dynamic database management.")
    print("=" * 60)

    try:
        await demo_trader_config_service()
        await demo_signal_router()
        await demo_active_futures_sync()
        await demo_api_endpoints()
        await demo_migration_benefits()

        print("\n" + "=" * 60)
        print("🎉 Demo completed successfully!")
        print("\nNext steps:")
        print("1. Populate the trader_exchange_config table with your traders")
        print("2. Test the API endpoints")
        print("3. Remove TARGET_TRADERS from .env (optional, fallback still works)")
        print("4. Enjoy dynamic trader management! 🚀")

    except Exception as e:
        print(f"\n❌ Demo failed with error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
