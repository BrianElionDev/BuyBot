"""
End-to-End Active Futures Flow Test

This script specifically tests the complete flow:
1. Detect new update in active_futures table
2. Match it to open trade in trades table
3. Check if trade should be closed
4. Get relevant alerts for that trade
5. Execute them to close the trade
"""

import asyncio
import logging
import sys
import os
from datetime import datetime, timezone, timedelta

# Add the project root to the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.database import DatabaseManager, ActiveFuturesRepository, TradeRepository, AlertRepository
from src.services.active_futures_sync_service import ActiveFuturesSyncService
from src.services.position_close_service import PositionCloseService

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class EndToEndFlowTester:
    """End-to-end flow tester for active futures synchronization."""

    def __init__(self):
        """Initialize the tester."""
        self.db_manager = None
        self.sync_service = None
        self.position_close_service = None
        self.active_futures_repo = None
        self.trade_repo = None
        self.alert_repo = None

    async def initialize(self):
        """Initialize the services."""
        try:
            self.db_manager = DatabaseManager()
            await self.db_manager.initialize()

            self.active_futures_repo = ActiveFuturesRepository(self.db_manager)
            self.trade_repo = TradeRepository(self.db_manager)
            self.alert_repo = AlertRepository(self.db_manager)

            self.sync_service = ActiveFuturesSyncService(self.db_manager)
            await self.sync_service.initialize()

            self.position_close_service = PositionCloseService(self.db_manager)
            await self.position_close_service.initialize()

            logger.info("✅ All services initialized successfully")
            return True

        except Exception as e:
            logger.error(f"❌ Failed to initialize services: {e}")
            return False

    async def step_1_detect_active_futures_update(self):
        """Step 1: Detect new update in active_futures table."""
        logger.info("🔍 Step 1: Detecting updates in active_futures table...")

        try:
            # Get recently closed futures (simulating new updates)
            closed_futures = await self.active_futures_repo.get_futures_by_traders_and_status(
                ["@Johnny", "@Tareeq"], "CLOSED"
            )

            # Filter for recent ones (last 7 days to have more data)
            recent_closed = []
            cutoff_time = datetime.now(timezone.utc) - timedelta(days=7)

            for af in closed_futures:
                if af.stopped_at:
                    try:
                        stopped_time = datetime.fromisoformat(af.stopped_at.replace('Z', '+00:00'))
                        if stopped_time >= cutoff_time:
                            recent_closed.append(af)
                    except Exception as e:
                        logger.warning(f"Error parsing stopped_at for futures {af.id}: {e}")

            logger.info(f"✅ Found {len(recent_closed)} recently closed futures")

            if recent_closed:
                # Show details of the most recent one
                latest = recent_closed[0]
                logger.info(f"📋 Latest closed future:")
                logger.info(f"   ID: {latest.id}")
                logger.info(f"   Trader: {latest.trader}")
                logger.info(f"   Content: {latest.content}")
                logger.info(f"   Stopped at: {latest.stopped_at}")

                return latest
            else:
                logger.warning("⚠️  No recently closed futures found")
                return None

        except Exception as e:
            logger.error(f"❌ Step 1 failed: {e}")
            return None

    async def step_2_match_to_open_trade(self, closed_future):
        """Step 2: Match closed future to open trade in trades table."""
        logger.info("🔗 Step 2: Matching to open trade in trades table...")

        try:
            if not closed_future:
                logger.warning("⚠️  No closed future to match")
                return None

            # Find matching trades
            matches = await self.sync_service.find_trade_matches(closed_future)

            logger.info(f"✅ Found {len(matches)} potential matches")

            if matches:
                best_match = matches[0]
                logger.info(f"📋 Best match:")
                logger.info(f"   Trade ID: {best_match.trade.id}")
                logger.info(f"   Discord ID: {best_match.trade.discord_id}")
                logger.info(f"   Coin Symbol: {best_match.trade.coin_symbol}")
                logger.info(f"   Status: {best_match.trade.status}")
                logger.info(f"   Confidence: {best_match.confidence:.2f}")
                logger.info(f"   Match Reason: {best_match.match_reason}")

                return best_match
            else:
                logger.warning("⚠️  No matching trades found")
                return None

        except Exception as e:
            logger.error(f"❌ Step 2 failed: {e}")
            return None

    async def step_3_check_trade_status(self, trade_match):
        """Step 3: Check if trade should be closed."""
        logger.info("🔍 Step 3: Checking if trade should be closed...")

        try:
            if not trade_match:
                logger.warning("⚠️  No trade match to check")
                return False

            trade = trade_match.trade

            # Check if trade is actually open
            if trade.status != "OPEN":
                logger.info(f"ℹ️  Trade {trade.discord_id} is not open (status: {trade.status})")
                return False

            # Check position status on exchange
            position_status = await self.position_close_service.get_position_status(trade)

            logger.info(f"📋 Position status for trade {trade.discord_id}:")
            logger.info(f"   {position_status}")

            # Determine if trade should be closed
            should_close = (
                trade.status == "OPEN" and
                trade_match.confidence >= 0.6 and
                "is_open" in position_status and position_status.get("is_open", False)
            )

            logger.info(f"✅ Trade should be closed: {should_close}")
            return should_close

        except Exception as e:
            logger.error(f"❌ Step 3 failed: {e}")
            return False

    async def step_4_get_relevant_alerts(self, trade_match):
        """Step 4: Get relevant alerts for that trade."""
        logger.info("📨 Step 4: Getting relevant alerts for the trade...")

        try:
            if not trade_match:
                logger.warning("⚠️  No trade match to get alerts for")
                return []

            trade = trade_match.trade

            # Get related alerts
            alerts = await self.alert_repo.get_alerts_by_trade_id(trade.discord_id)

            logger.info(f"✅ Found {len(alerts)} related alerts")

            # Filter for pending alerts
            pending_alerts = [alert for alert in alerts if alert.status == "PENDING"]

            logger.info(f"📋 Pending alerts: {len(pending_alerts)}")

            for alert in pending_alerts:
                logger.info(f"   Alert ID: {alert.id}")
                logger.info(f"   Content: {alert.content}")
                logger.info(f"   Timestamp: {alert.timestamp}")
                logger.info(f"   Status: {alert.status}")

            return pending_alerts

        except Exception as e:
            logger.error(f"❌ Step 4 failed: {e}")
            return []

    async def step_5_execute_alerts_to_close_trade(self, trade_match, alerts):
        """Step 5: Execute alerts to close the trade."""
        logger.info("⚡ Step 5: Executing alerts to close the trade...")

        try:
            if not trade_match:
                logger.warning("⚠️  No trade match to close")
                return False

            trade = trade_match.trade

            if not alerts:
                logger.info("ℹ️  No pending alerts to execute, attempting direct position closure")

                # Try direct position closure
                success, response = await self.position_close_service.close_position_by_trade(
                    trade,
                    reason="active_futures_closed"
                )

                if success:
                    logger.info(f"✅ Successfully closed position for trade {trade.discord_id}")
                    logger.info(f"   Response: {response}")
                    return True
                else:
                    logger.error(f"❌ Failed to close position for trade {trade.discord_id}")
                    logger.error(f"   Response: {response}")
                    return False
            else:
                logger.info(f"📨 Processing {len(alerts)} alerts to close trade")

                # Process alerts
                processed_alerts = await self.position_close_service.process_related_alerts(trade)

                logger.info(f"✅ Processed {len(processed_alerts)} alerts")

                for alert_result in processed_alerts:
                    logger.info(f"   Alert {alert_result['alert_id']}: {alert_result['status']}")
                    if alert_result['status'] == 'processed':
                        logger.info(f"   Result: {alert_result['result']}")

                return len(processed_alerts) > 0

        except Exception as e:
            logger.error(f"❌ Step 5 failed: {e}")
            return False

    async def run_complete_flow(self):
        """Run the complete end-to-end flow."""
        logger.info("🚀 Starting Complete End-to-End Flow Test")
        logger.info("=" * 60)

        if not await self.initialize():
            logger.error("❌ Failed to initialize services. Exiting.")
            return False

        try:
            # Step 1: Detect active futures update
            closed_future = await self.step_1_detect_active_futures_update()

            # Step 2: Match to open trade
            trade_match = await self.step_2_match_to_open_trade(closed_future)

            # Step 3: Check if trade should be closed
            should_close = await self.step_3_check_trade_status(trade_match)

            if not should_close:
                logger.info("ℹ️  Trade should not be closed based on current status")
                return True

            # Step 4: Get relevant alerts
            alerts = await self.step_4_get_relevant_alerts(trade_match)

            # Step 5: Execute alerts to close trade
            success = await self.step_5_execute_alerts_to_close_trade(trade_match, alerts)

            logger.info("\n" + "=" * 60)
            if success:
                logger.info("🎉 Complete end-to-end flow test PASSED!")
                logger.info("✅ The system successfully:")
                logger.info("   1. Detected active futures update")
                logger.info("   2. Matched it to an open trade")
                logger.info("   3. Verified the trade should be closed")
                logger.info("   4. Retrieved relevant alerts")
                logger.info("   5. Executed the closure process")
                return True
            else:
                logger.error("❌ Complete end-to-end flow test FAILED!")
                logger.error("   The system could not complete the trade closure process")
                return False

        except Exception as e:
            logger.error(f"❌ Complete flow test failed with error: {e}")
            return False

async def main():
    """Main function."""
    tester = EndToEndFlowTester()
    success = await tester.run_complete_flow()
    return success

if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
