#!/usr/bin/env python3
"""
Test script for alert status tracking functionality.
This script tests the new status column in the alerts table.
"""

import asyncio
import logging
import sys
import os
from datetime import datetime, timedelta, timezone

# Add the project root to Python path
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(script_dir))
sys.path.insert(0, project_root)

from discord_bot.discord_bot import DiscordBot

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def test_alert_status_tracking():
    """
    Test alert status tracking functionality.
    """
    logger.info("🧪 Testing Alert Status Tracking")
    logger.info("=" * 50)

    try:
        # Initialize bot
        bot = DiscordBot()
        supabase = bot.db_manager.supabase

        logger.info("Fetching all alerts...")

        # Get all alerts
        response = supabase.from_("alerts").select("*").execute()
        alerts = response.data or []

        logger.info(f"Found {len(alerts)} recent alerts")

        # Analyze alert statuses
        status_counts = {}
        alerts_with_status = []
        alerts_without_status = []

        for alert in alerts:
            alert_id = alert.get('id')
            status = alert.get('status')

            if status:
                alerts_with_status.append(alert)
                status_counts[status] = status_counts.get(status, 0) + 1
            else:
                alerts_without_status.append(alert)

        logger.info(f"📊 Alert Status Analysis:")
        logger.info(f"  - Alerts with status: {len(alerts_with_status)}")
        logger.info(f"  - Alerts without status: {len(alerts_without_status)}")

        if status_counts:
            logger.info(f"  - Status breakdown:")
            for status, count in status_counts.items():
                logger.info(f"    - {status}: {count}")

        # Show examples of each status
        if alerts_with_status:
            logger.info("\n📋 Examples by status:")
            for status in ['PENDING', 'SUCCESS', 'ERROR', 'SKIPPED']:
                status_alerts = [a for a in alerts_with_status if a.get('status') == status]
                if status_alerts:
                    example = status_alerts[0]
                    logger.info(f"  {status}:")
                    logger.info(f"    - Alert ID: {example.get('id')}")
                    logger.info(f"    - Content: {example.get('content', 'N/A')[:100]}...")
                    logger.info(f"    - Discord ID: {example.get('discord_id')}")
                    logger.info(f"    - Trade: {example.get('trade')}")

        # Test creating a new alert with status
        logger.info("\n🧪 Testing new alert creation with status...")

        test_alert_data = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "discord_id": f"test_{datetime.now().timestamp()}",
            "trade": "test_trade_123",
            "content": "Test alert for status tracking",
            "trader": "TestTrader",
            "status": "PENDING"  # This should be set automatically
        }

        success = await bot.db_manager.save_alert_to_database(test_alert_data)
        if success:
            logger.info("✅ Successfully created test alert with status")
        else:
            logger.error("❌ Failed to create test alert")

        # Test updating alert status
        logger.info("\n🧪 Testing alert status update...")

        # Find the test alert we just created
        test_response = supabase.from_("alerts").select("*").eq("discord_id", test_alert_data["discord_id"]).execute()
        if test_response.data:
            test_alert = test_response.data[0]
            test_alert_id = test_alert['id']

            # Update status to SUCCESS
            update_success = await bot.db_manager.update_existing_alert(test_alert_id, {
                "status": "SUCCESS",
                "binance_response": {"message": "Test successful execution"}
            })

            if update_success:
                logger.info("✅ Successfully updated alert status to SUCCESS")
            else:
                logger.error("❌ Failed to update alert status")
        else:
            logger.error("❌ Could not find test alert for status update")

        # Clean up test data
        logger.info("\n🧹 Cleaning up test data...")
        try:
            supabase.from_("alerts").delete().eq("discord_id", test_alert_data["discord_id"]).execute()
            logger.info("✅ Test data cleaned up")
        except Exception as e:
            logger.error(f"❌ Could not clean up test data: {e}")

        return True

    except Exception as e:
        logger.error(f"❌ Error testing alert status tracking: {e}")
        return False

async def main():
    """Main function."""
    logger.info("🧪 Alert Status Tracking Test Script")
    logger.info("=" * 50)

    success = await test_alert_status_tracking()

    if success:
        logger.info("✅ Test completed successfully")
    else:
        logger.error("❌ Test failed")

if __name__ == "__main__":
    asyncio.run(main())
