"""
Manual Test Script for Active Futures Synchronization

This script provides manual testing capabilities for the active futures sync feature.
"""

import asyncio
import logging
import sys
import os
from datetime import datetime, timezone, timedelta

# Add the project root to the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.database import DatabaseManager, ActiveFuturesRepository, TradeRepository
from src.services.active_futures_sync_service import ActiveFuturesSyncService
from src.services.position_close_service import PositionCloseService

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class ActiveFuturesSyncTester:
    """Manual tester for active futures synchronization."""

    def __init__(self):
        """Initialize the tester."""
        self.db_manager = None
        self.sync_service = None
        self.position_close_service = None

    async def initialize(self):
        """Initialize the services."""
        try:
            self.db_manager = DatabaseManager()
            await self.db_manager.initialize()

            self.sync_service = ActiveFuturesSyncService(self.db_manager)
            await self.sync_service.initialize()

            self.position_close_service = PositionCloseService(self.db_manager)
            await self.position_close_service.initialize()

            logger.info("✅ All services initialized successfully")
            return True

        except Exception as e:
            logger.error(f"❌ Failed to initialize services: {e}")
            return False

    async def test_coin_symbol_extraction(self):
        """Test coin symbol extraction from content."""
        logger.info("🧪 Testing coin symbol extraction...")

        test_cases = [
            "BTC Entry: 110547-110328 SL: 108310",
            "ETH Entry: 4437-4421 SL: 4348",
            "SOL Entry: 177-172.9 SL: 169",
            "PUMP Entry: 0.0041-0.0039 SL: 0.00384",
            "1000SATS Entry: 0.0000356-0.0000372 SL: 30m",
            "NAORIS Entry: 0.10773 SL: 0.101 PnL: +1.44%",
            "VELVET Entry: 0.12121 SL: 0.1126 PnL: +4.10%",
            "Invalid content without coin",
            ""
        ]

        for content in test_cases:
            symbol = self.sync_service.extract_coin_symbol_from_content(content)
            logger.info(f"Content: '{content}' -> Symbol: {symbol}")

        logger.info("✅ Coin symbol extraction test completed")

    async def test_content_similarity(self):
        """Test content similarity calculation."""
        logger.info("🧪 Testing content similarity...")

        test_cases = [
            ("BTC Entry: 110547-110328 SL: 108310", "BTC Entry: 110547-110328 SL: 108310"),
            ("BTC Entry: 110547-110328 SL: 108310", "BTC Entry: 110500-110300 SL: 108000"),
            ("ETH Entry: 4437-4421 SL: 4348", "BTC Entry: 110547-110328 SL: 108310"),
            ("", "BTC Entry: 110547-110328 SL: 108310"),
        ]

        for content1, content2 in test_cases:
            similarity = self.sync_service.calculate_content_similarity(content1, content2)
            logger.info(f"Similarity between '{content1}' and '{content2}': {similarity:.2f}")

        logger.info("✅ Content similarity test completed")

    async def test_timestamp_proximity(self):
        """Test timestamp proximity check."""
        logger.info("🧪 Testing timestamp proximity...")

        base_time = "2025-01-15T10:00:00Z"
        test_times = [
            "2025-01-15T10:00:00Z",
            "2025-01-15T11:00:00Z",
            "2025-01-15T12:00:00Z",
            "2025-01-15T15:00:00Z",
            "2025-01-15T20:00:00Z",
            "2025-01-16T10:00:00Z",
            "invalid_timestamp"
        ]

        for test_time in test_times:
            is_proximate = self.sync_service.is_timestamp_proximate(base_time, test_time, max_hours=24)
            logger.info(f"Time '{test_time}' is proximate to '{base_time}': {is_proximate}")

        logger.info("✅ Timestamp proximity test completed")

    async def test_get_active_futures(self):
        """Test getting active futures from database."""
        logger.info("🧪 Testing active futures retrieval...")

        try:
            active_futures_repo = ActiveFuturesRepository(self.db_manager)

            # Get active futures for target traders
            active_futures = await active_futures_repo.get_futures_by_traders_and_status(
                ["@Johnny", "@Tareeq"], "ACTIVE"
            )

            logger.info(f"Found {len(active_futures)} active futures for target traders")

            for af in active_futures[:5]:  # Show first 5
                logger.info(f"Active Future: ID={af.id}, Trader={af.trader}, Content='{af.content[:50]}...'")

            # Get closed futures
            closed_futures = await active_futures_repo.get_futures_by_traders_and_status(
                ["@Johnny", "@Tareeq"], "CLOSED"
            )

            logger.info(f"Found {len(closed_futures)} closed futures for target traders")

            for cf in closed_futures[:5]:  # Show first 5
                logger.info(f"Closed Future: ID={cf.id}, Trader={cf.trader}, Stopped={cf.stopped_at}")

            logger.info("✅ Active futures retrieval test completed")

        except Exception as e:
            logger.error(f"❌ Error testing active futures retrieval: {e}")

    async def test_get_matching_trades(self):
        """Test finding matching trades."""
        logger.info("🧪 Testing trade matching...")

        try:
            trade_repo = TradeRepository(self.db_manager)

            # Get open trades for target traders
            open_trades = await trade_repo.get_trades_by_filter({
                "trader": "@Johnny",
                "status": "OPEN"
            })

            logger.info(f"Found {len(open_trades)} open trades for @Johnny")

            for trade in open_trades[:3]:  # Show first 3
                logger.info(f"Open Trade: ID={trade.id}, DiscordID={trade.discord_id}, Coin={trade.coin_symbol}, Content='{trade.content[:50]}...'")

            # Test matching logic
            if open_trades:
                test_trade = open_trades[0]
                logger.info(f"Testing matching for trade: {test_trade.discord_id}")

                # Create a mock active futures entry
                from src.database.models.trade_models import ActiveFutures
                mock_active_futures = ActiveFutures(
                    id=999,
                    trader=test_trade.trader,
                    content=test_trade.content,
                    status="CLOSED",
                    created_at=test_trade.timestamp
                )

                matches = await self.sync_service.find_trade_matches(mock_active_futures)
                logger.info(f"Found {len(matches)} matches for mock active futures")

                for match in matches:
                    logger.info(f"Match: Trade={match.trade.discord_id}, Confidence={match.confidence:.2f}, Reason={match.match_reason}")

            logger.info("✅ Trade matching test completed")

        except Exception as e:
            logger.error(f"❌ Error testing trade matching: {e}")

    async def test_sync_status(self):
        """Test getting sync status."""
        logger.info("🧪 Testing sync status...")

        try:
            status = await self.sync_service.get_sync_status()
            logger.info(f"Sync Status: {status}")
            logger.info("✅ Sync status test completed")

        except Exception as e:
            logger.error(f"❌ Error testing sync status: {e}")

    async def test_dry_run_sync(self):
        """Test a dry run of the sync process."""
        logger.info("🧪 Testing dry run sync...")

        try:
            # Get closed futures to process
            closed_futures = await self.sync_service.get_closed_futures_to_process()
            logger.info(f"Found {len(closed_futures)} closed futures to process")

            if closed_futures:
                logger.info("Processing closed futures (DRY RUN - no actual position closures):")

                for af in closed_futures[:3]:  # Process first 3
                    logger.info(f"Processing Active Future ID={af.id}, Trader={af.trader}")

                    # Find matches
                    matches = await self.sync_service.find_trade_matches(af)
                    logger.info(f"  Found {len(matches)} matching trades")

                    for match in matches:
                        logger.info(f"    Match: Trade={match.trade.discord_id}, Confidence={match.confidence:.2f}")
                        logger.info(f"    Would close position for trade {match.trade.discord_id}")
            else:
                logger.info("No closed futures to process")

            logger.info("✅ Dry run sync test completed")

        except Exception as e:
            logger.error(f"❌ Error in dry run sync: {e}")

    async def run_all_tests(self):
        """Run all tests."""
        logger.info("🚀 Starting Active Futures Sync Tests")

        if not await self.initialize():
            logger.error("❌ Failed to initialize services. Exiting.")
            return

        try:
            await self.test_coin_symbol_extraction()
            await self.test_content_similarity()
            await self.test_timestamp_proximity()
            await self.test_get_active_futures()
            await self.test_get_matching_trades()
            await self.test_sync_status()
            await self.test_dry_run_sync()

            logger.info("🎉 All tests completed successfully!")

        except Exception as e:
            logger.error(f"❌ Error running tests: {e}")

async def main():
    """Main function."""
    tester = ActiveFuturesSyncTester()
    await tester.run_all_tests()

if __name__ == "__main__":
    asyncio.run(main())
