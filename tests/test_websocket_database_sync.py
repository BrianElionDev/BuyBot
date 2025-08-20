#!/usr/bin/env python3
"""
Test script for WebSocket database synchronization.
Tests real-time database updates when orders are filled on Binance.
"""

import asyncio
import json
import logging
from datetime import datetime, timezone
from config import settings
import sys

from src.websocket.binance_websocket_manager import BinanceWebSocketManager
from discord_bot.database import DatabaseManager
from supabase import create_client

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class WebSocketDatabaseSyncTester:
    """Test class for WebSocket database synchronization."""

    def __init__(self):
        # Get credentials
        self.api_key = settings.BINANCE_API_KEY
        self.api_secret = settings.BINANCE_API_SECRET
        self.is_testnet = settings.BINANCE_TESTNET

        if not self.api_key or not self.api_secret:
            raise ValueError("BINANCE_API_KEY and BINANCE_API_SECRET must be set")

        # Initialize database manager
        supabase_url = settings.SUPABASE_URL
        supabase_key = settings.SUPABASE_KEY
        if not supabase_url or not supabase_key:
            raise ValueError("SUPABASE_URL and SUPABASE_KEY must be set")

        self.supabase = create_client(supabase_url, supabase_key)
        self.db_manager = DatabaseManager(self.supabase)

        # Initialize WebSocket manager with database sync
        self.ws_manager = BinanceWebSocketManager(
            api_key=self.api_key,
            api_secret=self.api_secret,
            is_testnet=self.is_testnet,
            db_manager=self.db_manager
        )

        # Test counters
        self.event_counts = {
            'executionReport': 0,
            'outboundAccountPosition': 0,
            'balanceUpdate': 0,
            'ticker': 0,
            'connection': 0,
            'disconnection': 0,
            'error': 0
        }

        # Database sync stats
        self.db_updates = {
            'trades_updated': 0,
            'order_id_mappings': 0,
            'pnl_updates': 0
        }

        # Register event handlers
        self._register_handlers()

    def _register_handlers(self):
        """Register event handlers for testing."""

        async def handle_execution_report(data):
            """Handle execution report events."""
            self.event_counts['executionReport'] += 1
            order_id = data.get('i', 'Unknown')
            symbol = data.get('s', 'Unknown')
            status = data.get('X', 'Unknown')

            logger.info(f"Execution Report #{self.event_counts['executionReport']}: {symbol} {order_id} - {status}")

            # Log important fields for database sync
            if status == 'FILLED':
                executed_qty = float(data.get('z', 0))
                avg_price = float(data.get('ap', 0))
                realized_pnl = float(data.get('Y', 0))
                logger.info(f"ORDER FILLED: {symbol} {order_id} at {avg_price} - Qty: {executed_qty} - PnL: {realized_pnl}")

                # Check if this order was linked to a database trade
                await self._check_trade_linking(order_id, symbol, avg_price, realized_pnl)

        async def handle_account_position(data):
            """Handle account position updates."""
            self.event_counts['outboundAccountPosition'] += 1
            logger.info(f"Account Position Update #{self.event_counts['outboundAccountPosition']}")

            # Log balance changes
            for balance in data.get('B', []):
                asset = balance.get('a')
                free = balance.get('f')
                locked = balance.get('l')
                if float(free) > 0 or float(locked) > 0:
                    logger.info(f"Balance: {asset} - Free: {free}, Locked: {locked}")

        async def handle_ticker(data):
            """Handle ticker updates."""
            self.event_counts['ticker'] += 1
            if self.event_counts['ticker'] % 10 == 0:  # Log every 10th ticker
                symbol = data.get('s', 'Unknown')
                price = data.get('c', 'Unknown')
                logger.info(f"Ticker #{self.event_counts['ticker']}: {symbol} - {price}")

        async def handle_connection(data):
            """Handle connection events."""
            self.event_counts['connection'] += 1
            stream_type = data.get('type', 'unknown')
            logger.info(f"Connected to {stream_type} stream")

        async def handle_disconnection(data):
            """Handle disconnection events."""
            self.event_counts['disconnection'] += 1
            stream_type = data.get('type', 'unknown')
            logger.warning(f"Disconnected from {stream_type} stream")

        async def handle_error(data):
            """Handle error events."""
            self.event_counts['error'] += 1
            error_msg = data.get('error', 'Unknown error')
            logger.error(f"WebSocket Error #{self.event_counts['error']}: {error_msg}")

        # Register handlers
        self.ws_manager.add_event_handler('executionReport', handle_execution_report)
        self.ws_manager.add_event_handler('outboundAccountPosition', handle_account_position)
        self.ws_manager.add_event_handler('ticker', handle_ticker)
        self.ws_manager.add_event_handler('connection', handle_connection)
        self.ws_manager.add_event_handler('disconnection', handle_disconnection)
        self.ws_manager.add_event_handler('error', handle_error)

    async def _check_trade_linking(self, order_id: str, symbol: str, fill_price: float, realized_pnl: float):
        """
        Check if an order was successfully linked to a database trade.
        """
        try:
            # Wait a moment for database sync to complete
            await asyncio.sleep(1)

            # Check if trade was updated in database
            response = self.supabase.from_("trades").select("*").eq("exchange_order_id", order_id).execute()

            if response.data:
                trade = response.data[0]
                logger.info(f"✅ SUCCESS: Order {order_id} linked to trade {trade['id']}")
                logger.info(f"   Trade status: {trade.get('status')}")
                logger.info(f"   Exit price: {trade.get('exit_price')}")
                logger.info(f"   PnL: {trade.get('pnl_usd')}")

                self.db_updates['trades_updated'] += 1
                self.db_updates['order_id_mappings'] += 1

                # Verify the data matches
                if trade.get('exit_price') == fill_price:
                    logger.info(f"   ✅ Exit price matches: {fill_price}")
                else:
                    logger.warning(f"   ❌ Exit price mismatch: DB={trade.get('exit_price')}, WS={fill_price}")

                if trade.get('pnl_usd') == realized_pnl:
                    logger.info(f"   ✅ PnL matches: {realized_pnl}")
                else:
                    logger.warning(f"   ❌ PnL mismatch: DB={trade.get('pnl_usd')}, WS={realized_pnl}")

            else:
                logger.warning(f"❌ FAILED: Order {order_id} not found in database")

        except Exception as e:
            logger.error(f"Error checking trade linking: {e}")

    async def create_test_trade(self):
        """
        Create a test trade in the database to demonstrate linking.
        """
        try:
            # Create a test trade entry
            test_trade = {
                'coin_symbol': 'BTC',
                'signal_type': 'LONG',
                'position_size': 0.001,
                'entry_price': 45000.0,
                'status': 'PENDING',
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'created_at': datetime.now(timezone.utc).isoformat(),
                'updated_at': datetime.now(timezone.utc).isoformat()
            }

            response = self.supabase.from_("trades").insert(test_trade).execute()

            if response.data:
                trade_id = response.data[0]['id']
                logger.info(f"Created test trade {trade_id}")
                return trade_id
            else:
                logger.error("Failed to create test trade")
                return None

        except Exception as e:
            logger.error(f"Error creating test trade: {e}")
            return None

    async def run_database_sync_test(self, duration: int = 300):
        """
        Run database synchronization test.
        """
        logger.info(f"Starting WebSocket database sync test for {duration} seconds...")
        logger.info(f"Using {'testnet' if self.is_testnet else 'mainnet'}")

        try:
            # Create a test trade
            test_trade_id = await self.create_test_trade()

            # Start WebSocket manager
            await self.ws_manager.start()

            # Monitor for specified duration
            start_time = datetime.now()
            while (datetime.now() - start_time).seconds < duration:
                await asyncio.sleep(10)

                # Print status every 60 seconds
                if (datetime.now() - start_time).seconds % 60 == 0:
                    status = self.ws_manager.get_connection_status()
                    logger.info(f"Status: {json.dumps(status, indent=2)}")
                    logger.info(f"Event counts: {self.event_counts}")
                    logger.info(f"Database updates: {self.db_updates}")

            # Print final statistics
            logger.info("Test completed. Final statistics:")
            logger.info(f"Event counts: {self.event_counts}")
            logger.info(f"Database updates: {self.db_updates}")
            logger.info(f"Total events: {sum(self.event_counts.values())}")

            # Check for errors
            if self.event_counts['error'] > 0:
                logger.warning(f"Encountered {self.event_counts['error']} errors during test")
            else:
                logger.info("No errors encountered during test")

            # Check database sync success
            if self.db_updates['trades_updated'] > 0:
                logger.info(f"✅ SUCCESS: {self.db_updates['trades_updated']} trades updated via WebSocket")
            else:
                logger.warning("⚠️ No trades were updated during the test period")

            # Check connection status
            final_status = self.ws_manager.get_connection_status()
            if final_status.get('db_sync_stats'):
                logger.info(f"Database sync stats: {final_status['db_sync_stats']}")

        except Exception as e:
            logger.error(f"Test failed: {e}")
            raise

        finally:
            # Stop WebSocket manager
            await self.ws_manager.stop()

async def main():
    """Main test function."""
    try:
        tester = WebSocketDatabaseSyncTester()
        await tester.run_database_sync_test(duration=300)  # 5 minutes

    except Exception as e:
        logger.error(f"Test failed: {e}")
        return 1

    return 0

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)     