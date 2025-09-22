#!/usr/bin/env python3
"""
Position Management Integration Script

This script integrates the new position management system into the existing
trading engine to prevent database inconsistencies and orphaned orders.
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
    from src.bot.position_management import EnhancedTradeCreator, PositionManager, SymbolCooldownManager
    from src.bot.trading_engine import TradingEngine
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


class PositionManagementIntegrator:
    """
    Integrates position management into the existing trading system.
    """

    def __init__(self):
        self.db_manager = None
        self.binance_exchange = None
        self.trading_engine = None
        self.enhanced_trade_creator = None
        self.position_manager = None
        self.cooldown_manager = None

    async def initialize(self):
        """Initialize all required components."""
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

            # Initialize trading engine
            self.trading_engine = TradingEngine(
                api_key=api_key,
                api_secret=api_secret,
                is_testnet=is_testnet
            )
            await self.trading_engine.initialize()

            # Initialize position management components
            self.position_manager = PositionManager(self.db_manager, self.binance_exchange)
            self.cooldown_manager = SymbolCooldownManager()
            self.enhanced_trade_creator = EnhancedTradeCreator(
                self.db_manager,
                self.binance_exchange,
                self.trading_engine
            )

            logger.info("Successfully initialized position management integration")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize: {e}")
            return False

    async def analyze_existing_positions(self):
        """Analyze existing positions to identify potential conflicts."""
        try:
            logger.info("Analyzing existing positions...")

            # Get position summary
            position_summary = await self.position_manager.get_position_summary()

            print("\n" + "=" * 60)
            print("EXISTING POSITIONS ANALYSIS")
            print("=" * 60)

            if position_summary.get('error'):
                print(f"❌ Error analyzing positions: {position_summary['error']}")
                return

            total_positions = position_summary.get('total_positions', 0)
            total_unrealized_pnl = position_summary.get('total_unrealized_pnl', 0)

            print(f"Total Active Positions: {total_positions}")
            print(f"Total Unrealized PnL: ${total_unrealized_pnl:.2f}")

            if total_positions > 0:
                print(f"\nPosition Details:")
                print("-" * 60)
                print(f"{'Symbol':<12} {'Side':<6} {'Size':<12} {'Entry':<12} {'Mark':<12} {'PnL':<12} {'Trades':<8}")
                print("-" * 60)

                for position in position_summary.get('positions', []):
                    pnl_color = "🟢" if position['unrealized_pnl'] >= 0 else "🔴"
                    print(f"{position['symbol']:<12} {position['side']:<6} "
                          f"{position['size']:<12.4f} {position['entry_price']:<12.4f} "
                          f"{position['mark_price']:<12.4f} {pnl_color} {position['unrealized_pnl']:<10.2f} "
                          f"{position['trade_count']:<8}")

                # Check for potential conflicts
                await self._check_for_conflicts(position_summary.get('positions', []))
            else:
                print("✅ No active positions found")

        except Exception as e:
            logger.error(f"Error analyzing existing positions: {e}")

    async def _check_for_conflicts(self, positions):
        """Check for potential position conflicts."""
        try:
            # Group positions by symbol
            positions_by_symbol = {}
            for position in positions:
                symbol = position['symbol']
                if symbol not in positions_by_symbol:
                    positions_by_symbol[symbol] = []
                positions_by_symbol[symbol].append(position)

            conflicts_found = 0
            for symbol, symbol_positions in positions_by_symbol.items():
                if len(symbol_positions) > 1:
                    conflicts_found += 1
                    print(f"\n⚠️  CONFLICT DETECTED: {symbol}")
                    print(f"   Multiple positions found:")
                    for pos in symbol_positions:
                        print(f"   - {pos['side']} {pos['size']} @ {pos['entry_price']} "
                              f"({pos['trade_count']} trades)")

            if conflicts_found > 0:
                print(f"\n⚠️  Found {conflicts_found} symbols with multiple positions")
                print("   These will be handled by the position management system")
            else:
                print("\n✅ No position conflicts detected")

        except Exception as e:
            logger.error(f"Error checking for conflicts: {e}")

    async def test_enhanced_trade_creation(self, symbol: str = "BTC", side: str = "LONG"):
        """Test the enhanced trade creation system."""
        try:
            logger.info(f"Testing enhanced trade creation for {symbol} {side}")

            # Test conflict detection
            conflict = await self.position_manager.check_position_conflict(
                symbol, side, 999999  # Use a fake trade ID for testing
            )

            if conflict:
                print(f"\n🔍 Conflict detected for {symbol} {side}:")
                print(f"   Type: {conflict.conflict_type}")
                print(f"   Reason: {conflict.reason}")
                print(f"   Suggested Action: {conflict.suggested_action.value}")
            else:
                print(f"\n✅ No conflict detected for {symbol} {side}")

            # Test cooldown status
            cooldown_status = self.cooldown_manager.get_cooldown_status(symbol)
            if cooldown_status['is_on_cooldown']:
                print(f"\n⏰ Cooldown active for {symbol}:")
                for cooldown in cooldown_status['cooldowns']:
                    print(f"   {cooldown['type']}: {cooldown['remaining_seconds']}s remaining")
            else:
                print(f"\n✅ No cooldown active for {symbol}")

        except Exception as e:
            logger.error(f"Error testing enhanced trade creation: {e}")

    async def run_enhanced_cleanup(self):
        """Run the enhanced orphaned orders cleanup."""
        try:
            logger.info("Running enhanced orphaned orders cleanup...")

            # Import and run the enhanced cleanup
            from scripts.maintenance.cleanup_scripts.enhanced_orphaned_orders_cleanup import EnhancedOrphanedOrdersCleanup

            cleanup = EnhancedOrphanedOrdersCleanup()
            cleanup.binance_exchange = self.binance_exchange
            cleanup.db_manager = self.db_manager
            cleanup.position_manager = self.position_manager
            cleanup.position_db_ops = PositionDatabaseOperations(self.db_manager)

            # Run cleanup in dry-run mode first
            await cleanup.run_cleanup(dry_run=True, save_report=False)

        except Exception as e:
            logger.error(f"Error running enhanced cleanup: {e}")

    async def create_integration_guide(self):
        """Create a guide for integrating the position management system."""
        try:
            guide_content = """
# Position Management Integration Guide

## Overview
This guide explains how to integrate the new position management system into your existing trading bot to prevent database inconsistencies and orphaned orders.

## Key Components

### 1. PositionManager
- Handles position conflict detection and resolution
- Manages trade aggregation for same-symbol positions
- Provides position information with trade counts

### 2. SymbolCooldownManager
- Manages cooldowns for trading symbols
- Prevents rapid multiple trades for the same symbol
- Supports trader-specific and position-based cooldowns

### 3. EnhancedTradeCreator
- Integrates conflict detection into trade creation
- Automatically handles position conflicts
- Prevents orphaned orders

### 4. Enhanced Orphaned Orders Cleanup
- Cleans up orphaned orders with position aggregation awareness
- Prevents removal of legitimate orders from aggregated positions

## Integration Steps

### Step 1: Update Trade Creation
Replace your existing trade creation logic with the EnhancedTradeCreator:

```python
from src.bot.position_management import EnhancedTradeCreator

# Initialize the enhanced trade creator
enhanced_creator = EnhancedTradeCreator(db_manager, exchange, trading_engine)

# Create trades with conflict detection
result = await enhanced_creator.create_trade_with_conflict_detection(
    coin_symbol="BTC",
    signal_price=50000.0,
    position_type="LONG",
    trader="trader_name",
    discord_id="unique_id"
)
```

### Step 2: Update Discord Bot
Modify your Discord bot to use the enhanced trade creator:

```python
# In your Discord bot's process_initial_signal method
enhanced_creator = EnhancedTradeCreator(self.db_manager, self.exchange, self.trading_engine)

result = await enhanced_creator.create_trade_with_conflict_detection(
    coin_symbol=parsed_signal['coin_symbol'],
    signal_price=parsed_signal['entry_prices'][0],
    position_type=parsed_signal['position_type'],
    trader=signal.trader,
    discord_id=signal.discord_id
)
```

### Step 3: Update Cleanup Scripts
Use the enhanced orphaned orders cleanup:

```bash
python3 scripts/maintenance/cleanup_scripts/enhanced_orphaned_orders_cleanup.py --dry-run
```

### Step 4: Monitor Position Status
Use the position manager to monitor positions:

```python
from src.bot.position_management import PositionManager

position_manager = PositionManager(db_manager, exchange)
positions = await position_manager.get_active_positions()
summary = await position_manager.get_position_summary()
```

## Configuration

### Cooldown Settings
```python
cooldown_manager = SymbolCooldownManager(
    default_cooldown=300,  # 5 minutes
    position_cooldown=600  # 10 minutes
)
```

### Auto-merge Settings
```python
enhanced_creator.auto_merge_enabled = True
enhanced_creator.auto_reject_conflicts = True
enhanced_creator.max_position_trades = 5
```

## Benefits

1. **Database Consistency**: Prevents multiple trade records for the same position
2. **No Orphaned Orders**: Orders are properly associated with positions
3. **Conflict Resolution**: Automatic handling of position conflicts
4. **Cooldown Management**: Prevents rapid multiple trades
5. **Position Aggregation**: Proper handling of multiple trades for same symbol

## Monitoring

Use the provided scripts to monitor the system:

```bash
# Analyze existing positions
python3 scripts/setup/integrate_position_management.py

# Run enhanced cleanup
python3 scripts/maintenance/cleanup_scripts/enhanced_orphaned_orders_cleanup.py

# Test trade creation
python3 scripts/testing/test_position_management.py
```

## Troubleshooting

### Common Issues

1. **Import Errors**: Ensure all dependencies are installed
2. **Database Errors**: Check database connection and permissions
3. **Exchange Errors**: Verify API credentials and permissions

### Debug Mode

Enable debug logging to see detailed information:

```python
import logging
logging.getLogger('src.bot.position_management').setLevel(logging.DEBUG)
```

## Support

For issues or questions, check the logs and use the provided debugging tools.
"""

            with open('POSITION_MANAGEMENT_INTEGRATION_GUIDE.md', 'w') as f:
                f.write(guide_content)

            logger.info("Integration guide created: POSITION_MANAGEMENT_INTEGRATION_GUIDE.md")

        except Exception as e:
            logger.error(f"Error creating integration guide: {e}")

    async def run_integration(self):
        """Run the complete integration process."""
        try:
            print("🚀 Position Management Integration")
            print("=" * 50)

            # Initialize
            if not await self.initialize():
                print("❌ Failed to initialize. Exiting.")
                return

            # Analyze existing positions
            await self.analyze_existing_positions()

            # Test enhanced trade creation
            await self.test_enhanced_trade_creation()

            # Run enhanced cleanup (dry run)
            await self.run_enhanced_cleanup()

            # Create integration guide
            await self.create_integration_guide()

            print("\n✅ Integration process completed successfully!")
            print("📖 Check POSITION_MANAGEMENT_INTEGRATION_GUIDE.md for next steps")

        except Exception as e:
            logger.error(f"Error during integration: {e}")
        finally:
            if self.binance_exchange:
                await self.binance_exchange.close_client()


async def main():
    """Main function"""
    integrator = PositionManagementIntegrator()
    await integrator.run_integration()


if __name__ == "__main__":
    asyncio.run(main())
