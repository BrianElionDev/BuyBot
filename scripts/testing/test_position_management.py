#!/usr/bin/env python3
"""
Position Management Test Script

This script demonstrates the position management system functionality
and tests the conflict detection and resolution mechanisms.
"""

import asyncio
import logging
import sys
import os
from datetime import datetime, timezone

# Add project root to path
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(script_dir))
sys.path.insert(0, project_root)

try:
    from config.settings import *
    from src.bot.position_management import (
        PositionManager,
        SymbolCooldownManager,
        EnhancedTradeCreator,
        PositionDatabaseOperations
    )
    from discord_bot.database.database_manager import DatabaseManager
    from src.exchange import BinanceExchange
except ImportError as e:
    print(f"❌ Import error: {e}")
    print("Please ensure you're running this script from the project root directory")
    sys.exit(1)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class PositionManagementTester:
    """
    Test the position management system functionality.
    """

    def __init__(self):
        self.db_manager = None
        self.binance_exchange = None
        self.position_manager = None
        self.cooldown_manager = None
        self.enhanced_trade_creator = None

    async def initialize(self):
        """Initialize all components for testing."""
        try:
            # Initialize database manager
            self.db_manager = DatabaseManager()
            await self.db_manager.initialize()

            # Initialize Binance exchange
            api_key = BINANCE_API_KEY
            api_secret = BINANCE_API_SECRET
            is_testnet = BINANCE_TESTNET

            if not api_key or not api_secret:
                logger.error("Binance API credentials not found!")
                return False

            self.binance_exchange = BinanceExchange(api_key, api_secret, is_testnet)
            await self.binance_exchange._init_client()

            # Initialize position management components
            self.position_manager = PositionManager(self.db_manager, self.binance_exchange)
            self.cooldown_manager = SymbolCooldownManager()

            logger.info("Successfully initialized position management tester")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize: {e}")
            return False

    async def test_position_detection(self):
        """Test position detection and conflict analysis."""
        try:
            print("\n" + "=" * 60)
            print("TESTING POSITION DETECTION")
            print("=" * 60)

            # Get current positions
            positions = await self.position_manager.get_active_positions()

            print(f"Found {len(positions)} active positions")

            if positions:
                print("\nPosition Details:")
                print("-" * 60)
                print(f"{'Symbol':<12} {'Side':<6} {'Size':<12} {'Entry':<12} {'Mark':<12} {'Trades':<8}")
                print("-" * 60)

                for position in positions.values():
                    print(f"{position.symbol:<12} {position.side:<6} "
                          f"{position.size:<12.4f} {position.entry_price:<12.4f} "
                          f"{position.mark_price:<12.4f} {len(position.trade_ids):<8}")

                # Test conflict detection for each position
                print(f"\nTesting Conflict Detection:")
                print("-" * 60)

                for position in positions.values():
                    # Test same-side conflict
                    conflict = await self.position_manager.check_position_conflict(
                        position.symbol, position.side, 999999
                    )

                    if conflict:
                        print(f"✅ {position.symbol} {position.side}: Conflict detected")
                        print(f"   Type: {conflict.conflict_type}")
                        print(f"   Action: {conflict.suggested_action.value}")
                    else:
                        print(f"❌ {position.symbol} {position.side}: No conflict detected")
            else:
                print("No active positions found")

        except Exception as e:
            logger.error(f"Error testing position detection: {e}")

    async def test_cooldown_system(self):
        """Test the cooldown system."""
        try:
            print("\n" + "=" * 60)
            print("TESTING COOLDOWN SYSTEM")
            print("=" * 60)

            test_symbol = "BTC"
            test_trader = "test_trader"

            # Test initial state
            is_on_cooldown, reason = self.cooldown_manager.is_on_cooldown(test_symbol, test_trader)
            print(f"Initial state for {test_symbol}: {'On cooldown' if is_on_cooldown else 'Not on cooldown'}")

            # Set a cooldown
            self.cooldown_manager.set_cooldown(test_symbol, test_trader, 10)  # 10 seconds
            print(f"Set 10-second cooldown for {test_symbol} {test_trader}")

            # Check cooldown status
            is_on_cooldown, reason = self.cooldown_manager.is_on_cooldown(test_symbol, test_trader)
            print(f"After setting cooldown: {'On cooldown' if is_on_cooldown else 'Not on cooldown'}")
            if is_on_cooldown:
                print(f"Reason: {reason}")

            # Get detailed status
            status = self.cooldown_manager.get_cooldown_status(test_symbol, test_trader)
            print(f"Detailed status: {status}")

            # Test position cooldown
            self.cooldown_manager.set_position_cooldown(test_symbol, 15)  # 15 seconds
            print(f"Set 15-second position cooldown for {test_symbol}")

            # Check position cooldown
            is_on_cooldown, reason = self.cooldown_manager.is_on_cooldown(test_symbol)
            print(f"Position cooldown: {'Active' if is_on_cooldown else 'Not active'}")
            if is_on_cooldown:
                print(f"Reason: {reason}")

            # Clean up
            self.cooldown_manager.clear_cooldown(test_symbol, test_trader)
            print(f"Cleared cooldowns for {test_symbol} {test_trader}")

        except Exception as e:
            logger.error(f"Error testing cooldown system: {e}")

    async def test_database_operations(self):
        """Test database operations for position management."""
        try:
            print("\n" + "=" * 60)
            print("TESTING DATABASE OPERATIONS")
            print("=" * 60)

            position_db_ops = PositionDatabaseOperations(self.db_manager)

            # Test getting active trades
            active_trades = await position_db_ops.get_active_trades()
            print(f"Found {len(active_trades)} active trades in database")

            if active_trades:
                # Group by symbol
                symbols = set(trade.get('coin_symbol') for trade in active_trades if trade.get('coin_symbol'))
                print(f"Active symbols: {', '.join(symbols)}")

                # Test position summary
                summary = await position_db_ops.get_position_summary()
                print(f"Position summary: {summary.get('total_positions', 0)} positions")

                for position in summary.get('positions', []):
                    print(f"  {position['symbol']} {position['side']}: "
                          f"{position['total_size']} size, {position['trade_count']} trades")

        except Exception as e:
            logger.error(f"Error testing database operations: {e}")

    async def test_conflict_scenarios(self):
        """Test various conflict scenarios."""
        try:
            print("\n" + "=" * 60)
            print("TESTING CONFLICT SCENARIOS")
            print("=" * 60)

            # Test scenarios
            test_scenarios = [
                ("BTC", "LONG", "Same-side conflict"),
                ("BTC", "SHORT", "Opposite-side conflict"),
                ("ETH", "LONG", "No existing position"),
                ("SOL", "SHORT", "No existing position")
            ]

            for symbol, side, description in test_scenarios:
                print(f"\nTesting: {description}")
                print(f"Symbol: {symbol}, Side: {side}")

                conflict = await self.position_manager.check_position_conflict(
                    symbol, side, 999999
                )

                if conflict:
                    print(f"  ✅ Conflict detected")
                    print(f"  Type: {conflict.conflict_type}")
                    print(f"  Suggested action: {conflict.suggested_action.value}")
                    print(f"  Reason: {conflict.reason}")
                else:
                    print(f"  ❌ No conflict detected")

        except Exception as e:
            logger.error(f"Error testing conflict scenarios: {e}")

    async def run_all_tests(self):
        """Run all tests."""
        try:
            print("🧪 Position Management System Tests")
            print("=" * 60)

            # Initialize
            if not await self.initialize():
                print("❌ Failed to initialize. Exiting.")
                return

            # Run tests
            await self.test_position_detection()
            await self.test_cooldown_system()
            await self.test_database_operations()
            await self.test_conflict_scenarios()

            print("\n✅ All tests completed successfully!")

        except Exception as e:
            logger.error(f"Error running tests: {e}")
        finally:
            if self.binance_exchange:
                await self.binance_exchange.close_client()


async def main():
    """Main function"""
    tester = PositionManagementTester()
    await tester.run_all_tests()


if __name__ == "__main__":
    asyncio.run(main())
