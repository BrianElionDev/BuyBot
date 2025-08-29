#!/usr/bin/env python3
"""
Update existing alerts with status based on their current state.
This script analyzes existing alerts and assigns appropriate status values.
"""

import asyncio
import logging
import sys
import os
import json
from datetime import datetime, timezone

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

async def update_existing_alert_statuses():
    """
    Update existing alerts with appropriate status values.
    """
    logger.info("🔄 Updating Existing Alert Statuses")
    logger.info("=" * 50)

    try:
        # Initialize bot
        bot = DiscordBot()
        supabase = bot.db_manager.supabase

        logger.info("Fetching all alerts...")

        # Get all alerts
        response = supabase.from_("alerts").select("*").gte("timestamp", "2025-08-05T00:00:00Z").execute()
        alerts = response.data or []

        logger.info(f"Found {len(alerts)} alerts to process")

        # Process alerts in batches to avoid overwhelming the database
        batch_size = 50
        updated_count = 0
        error_count = 0

        for i in range(0, len(alerts), batch_size):
            batch = alerts[i:i + batch_size]
            logger.info(f"Processing batch {i//batch_size + 1}/{(len(alerts) + batch_size - 1)//batch_size} ({len(batch)} alerts)")

            for alert in batch:
                alert_id = alert.get('id')
                current_status = alert.get('status')

                # Skip if already has status
                if current_status:
                    continue

                # Determine status based on alert data
                new_status = determine_alert_status(alert)

                try:
                    # Update the alert with the determined status
                    update_success = await bot.db_manager.update_existing_alert(alert_id, {
                        "status": new_status
                    })

                    if update_success:
                        updated_count += 1
                        if updated_count % 100 == 0:
                            logger.info(f"✅ Updated {updated_count} alerts so far...")
                    else:
                        error_count += 1
                        logger.error(f"❌ Failed to update alert {alert_id}")

                except Exception as e:
                    error_count += 1
                    logger.error(f"❌ Error updating alert {alert_id}: {e}")

        logger.info(f"🎉 Status update completed!")
        logger.info(f"  - Total alerts processed: {len(alerts)}")
        logger.info(f"  - Successfully updated: {updated_count}")
        logger.info(f"  - Errors: {error_count}")

        # Show final status breakdown
        logger.info("\n📊 Final Status Breakdown:")
        final_response = supabase.from_("alerts").select("status").execute()
        final_alerts = final_response.data or []

        status_counts = {}
        for alert in final_alerts:
            status = alert.get('status', 'NO_STATUS')
            status_counts[status] = status_counts.get(status, 0) + 1

        for status, count in status_counts.items():
            logger.info(f"  - {status}: {count}")

        return True

    except Exception as e:
        logger.error(f"❌ Error updating alert statuses: {e}")
        return False

def determine_alert_status(alert):
    """
    Determine the appropriate status for an alert based on its data.
    """
    # Check if there's a binance_response
    binance_response = alert.get('binance_response')
    parsed_alert = alert.get('parsed_alert')

    # If there's a binance_response, check if it indicates success or error
    if binance_response:
        try:
            if isinstance(binance_response, str):
                response_data = json.loads(binance_response)
            else:
                response_data = binance_response

            # Check for error indicators
            if isinstance(response_data, dict):
                if 'error' in response_data:
                    return 'ERROR'
                elif 'success' in response_data and not response_data['success']:
                    return 'ERROR'
                elif 'message' in response_data and 'success' in response_data.get('message', '').lower():
                    return 'SUCCESS'
                elif 'orderId' in response_data:
                    return 'SUCCESS'
                else:
                    return 'SUCCESS'  # Default to success if we have a response
        except:
            pass

    # Check parsed_alert for status indicators
    if parsed_alert:
        try:
            if isinstance(parsed_alert, str):
                parsed_data = json.loads(parsed_alert)
            else:
                parsed_data = parsed_alert

            if isinstance(parsed_data, dict):
                if 'success' in parsed_data and not parsed_data['success']:
                    return 'ERROR'
                elif 'error' in parsed_data:
                    return 'ERROR'
                elif 'note' in parsed_data and 'skipped' in parsed_data['note'].lower():
                    return 'SKIPPED'
        except:
            pass

    # Default to PENDING if we can't determine status
    return 'PENDING'

async def main():
    """Main function."""
    logger.info("🔄 Alert Status Update Script")
    logger.info("=" * 50)

    success = await update_existing_alert_statuses()

    if success:
        logger.info("✅ Status update completed successfully")
    else:
        logger.error("❌ Status update failed")

if __name__ == "__main__":
    asyncio.run(main())

