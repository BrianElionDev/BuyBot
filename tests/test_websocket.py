#!/usr/bin/env python3
"""
Test script for Binance WebSocket implementation.
Tests connection, event handling, and error scenarios.
"""

import asyncio
import json
import logging
import os
import sys
from datetime import datetime
from config import settings

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src', 'websocket'))

from src.websocket import WebSocketManager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class WebSocketTester:
    """Test class for WebSocket functionality."""

    def __init__(self):
        # Get credentials
        self.api_key = settings.BINANCE_API_KEY
        self.api_secret = settings.BINANCE_API_SECRET
        self.is_testnet = settings.BINANCE_TESTNET

        if not self.api_key or not self.api_secret:
            raise ValueError("BINANCE_API_KEY and BINANCE_API_SECRET must be set")

        # Initialize WebSocket manager
        self.ws_manager = WebSocketManager(
            api_key=self.api_key,
            api_secret=self.api_secret,
            is_testnet=self.is_testnet
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

        # Connection status
        self.connection_successful = False

        # Register event handlers
        self._register_handlers()

    def _register_handlers(self):
        """Register event handlers for testing."""

        async def handle_execution_report(data):
            """Handle execution report events."""
            self.event_counts['executionReport'] += 1
            logger.info(f"Execution Report #{self.event_counts['executionReport']}: {data.get('s', 'Unknown')} - {data.get('X', 'Unknown Status')}")

            # Log important fields
            if data.get('X') == 'FILLED':
                logger.info(f"ORDER FILLED: {data.get('s')} at {data.get('L')} - PnL: {data.get('Y')}")

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

        async def handle_balance_update(data):
            """Handle balance updates."""
            self.event_counts['balanceUpdate'] += 1
            logger.info(f"Balance Update #{self.event_counts['balanceUpdate']}: {data.get('a')} - {data.get('d')}")

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

            # Check if both streams are connected
            if self.event_counts['connection'] >= 2:
                logger.info("✅ Both WebSocket streams connected successfully!")
                # Set a flag to indicate successful connection
                self.connection_successful = True

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
        self.ws_manager.register_handler('executionReport', handle_execution_report)
        self.ws_manager.register_handler('outboundAccountPosition', handle_account_position)
        self.ws_manager.register_handler('balanceUpdate', handle_balance_update)
        self.ws_manager.register_handler('ticker', handle_ticker)
        self.ws_manager.register_handler('connection', handle_connection)
        self.ws_manager.register_handler('disconnection', handle_disconnection)
        self.ws_manager.register_handler('error', handle_error)

    async def run_test(self, duration: int = 60):
        """Run WebSocket test for specified duration."""
        logger.info(f"Starting WebSocket test for {duration} seconds...")
        logger.info(f"Using {'testnet' if self.is_testnet else 'mainnet'}")

        try:
            # Start WebSocket manager
            await self.ws_manager.start()

            # Monitor for specified duration
            start_time = datetime.now()
            while (datetime.now() - start_time).seconds < duration:
                await asyncio.sleep(5)

                # Print status every 30 seconds
                if (datetime.now() - start_time).seconds % 30 == 0:
                    status = self.ws_manager.get_connection_status()
                    logger.info(f"Status: {json.dumps(status, indent=2)}")

                    # Print event counts
                    logger.info(f"Event counts: {self.event_counts}")

            # Print final statistics
            logger.info("Test completed. Final statistics:")
            logger.info(f"Event counts: {self.event_counts}")
            logger.info(f"Total events: {sum(self.event_counts.values())}")

            # Check for errors
            if self.event_counts['error'] > 0:
                logger.warning(f"Encountered {self.event_counts['error']} errors during test")
            else:
                logger.info("No errors encountered during test")

            # Check connection status
            final_status = self.ws_manager.get_connection_status()
            if final_status['user_data_connected'] and final_status['market_data_connected']:
                logger.info("✅ Both streams connected successfully")
            else:
                logger.warning("⚠️ Some streams not connected")
                logger.info(f"User data: {final_status['user_data_connected']}")
                logger.info(f"Market data: {final_status['market_data_connected']}")

        except Exception as e:
            logger.error(f"Test failed: {e}")
            raise

        finally:
            # Stop WebSocket manager
            await self.ws_manager.stop()

    async def test_connection_only(self):
        """Test just the connection without running the full test."""
        logger.info("Testing WebSocket connection...")

        try:
            await self.ws_manager.start()

                        # Wait for connections to be established
            max_wait = 30  # seconds
            wait_time = 0
            while wait_time < max_wait:
                await asyncio.sleep(1)
                wait_time += 1

                # Check if both streams connected via event handlers
                if self.connection_successful:
                    logger.info(f"✅ WebSocket connection successful after {wait_time} seconds")
                    status = self.ws_manager.get_connection_status()
                    logger.info(f"Connection status: {json.dumps(status, indent=2)}")
                    return True

                # Fallback: check connection status directly
                status = self.ws_manager.get_connection_status()
                if status['user_data_connected'] or status['market_data_connected']:
                    logger.info(f"✅ WebSocket connection successful after {wait_time} seconds")
                    logger.info(f"Connection status: {json.dumps(status, indent=2)}")
                    return True

            # If we get here, connections didn't establish
            status = self.ws_manager.get_connection_status()
            logger.error(f"❌ WebSocket connection failed after {max_wait} seconds")
            logger.info(f"Connection status: {json.dumps(status, indent=2)}")
            return False

        except Exception as e:
            logger.error(f"Connection test failed: {e}")
            return False

        finally:
            await self.ws_manager.stop()

async def main():
    """Main test function."""
    try:
        tester = WebSocketTester()

        # Test connection first
        logger.info("=== Testing Connection ===")
        connection_success = await tester.test_connection_only()

        if connection_success:
            logger.info("=== Running Full Test ===")
            await tester.run_test(duration=120)  # 2 minutes
        else:
            logger.error("Connection test failed, skipping full test")

    except Exception as e:
        logger.error(f"Test failed: {e}")
        return 1

    return 0

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)