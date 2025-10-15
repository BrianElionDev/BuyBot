"""
KuCoin Follow-up Signal Processor

This script processes follow-up signals specifically for KuCoin exchange.
It allows you to select which alerts to process using customizable SQL queries.

Usage:
1. Edit the SELECT_QUERY variable below to specify which alerts to process
2. Run the script: python scripts/kucoin_followup_processor.py
"""

import asyncio
import logging
import sys
import os
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from discord_bot.discord_bot import DiscordBot
from discord_bot.utils.trade_retry_utils import initialize_clients

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ============================================================================
# CUSTOMIZABLE SELECT QUERY - EDIT THIS TO SELECT ALERTS TO PROCESS
# ============================================================================

# Example queries - uncomment and modify the one you want to use:

# 1. Process by specific alert ID
SELECT_QUERY = """
SELECT * FROM alerts
WHERE id = 4011
"""

# 2. Process by Discord ID
# SELECT_QUERY = """
# SELECT * FROM alerts
# WHERE discord_id = '1422900509475606689'
# """

# 3. Process by trader
# SELECT_QUERY = """
# SELECT * FROM alerts
# WHERE trader = '@-Tareeq'
# """

# 4. Process by date range
# SELECT_QUERY = """
# SELECT * FROM alerts
# WHERE created_at >= '2025-10-01 00:00:00'
# AND created_at <= '2025-10-01 23:59:59'
# """

# 5. Process by exchange
# SELECT_QUERY = """
# SELECT * FROM alerts
# WHERE exchange = 'kucoin'
# """

# 6. Process by status
# SELECT_QUERY = """
# SELECT * FROM alerts
# WHERE status = 'PENDING'
# """

# 7. Process by trade reference
# SELECT_QUERY = """
# SELECT * FROM alerts
# WHERE trade = '1422897504382615595'
# """

# 8. Process multiple conditions
# SELECT_QUERY = """
# SELECT * FROM alerts
# WHERE trader = '@-Tareeq'
# AND exchange = 'kucoin'
# AND status = 'PENDING'
# ORDER BY created_at DESC
# LIMIT 10
# """

# ============================================================================
# PROCESSING CONFIGURATION
# ============================================================================

# Set to True to actually process the alerts, False to just preview
PROCESS_ALERTS = True

# Set to True to update alert status after processing
UPDATE_ALERT_STATUS = True

# Delay between processing each alert (seconds)
PROCESSING_DELAY = 2.0

# ============================================================================
# MAIN PROCESSING CLASS
# ============================================================================

class KuCoinFollowupProcessor:
    """Process follow-up signals specifically for KuCoin exchange."""

    def __init__(self):
        self.bot = None
        self.supabase = None

    async def initialize(self):
        """Initialize the bot and database connections."""
        try:
            logger.info("Initializing KuCoin Follow-up Processor...")

            # Initialize clients
            self.bot, self.supabase = initialize_clients()
            if not self.supabase:
                raise Exception("Failed to initialize Supabase client")
            if not self.bot:
                raise Exception("Failed to initialize Discord bot")

            logger.info("✅ Initialization complete")

        except Exception as e:
            logger.error(f"❌ Initialization failed: {e}")
            raise

    async def fetch_alerts(self) -> List[Dict[str, Any]]:
        """Fetch alerts based on the configured SELECT query."""
        try:
            logger.info(f"Fetching alerts with query: {SELECT_QUERY.strip()}")

            # Parse the query to extract conditions
            query_lower = SELECT_QUERY.lower()

            # Start with base query
            query = self.supabase.table("alerts").select("*")

            # Parse WHERE conditions
            if "where id = " in query_lower:
                # Extract ID from query
                id_match = SELECT_QUERY.split("id = ")[1].split()[0]
                alert_id = int(id_match) if id_match.isdigit() else None
                if alert_id:
                    query = query.eq("id", alert_id)

            elif "where discord_id = " in query_lower:
                # Extract discord_id from query
                discord_id = SELECT_QUERY.split("'")[1]
                query = query.eq("discord_id", discord_id)

            elif "where trader = " in query_lower:
                # Extract trader from query
                trader = SELECT_QUERY.split("'")[1]
                query = query.eq("trader", trader)

            elif "where exchange = " in query_lower:
                # Extract exchange from query
                exchange = SELECT_QUERY.split("'")[1]
                query = query.eq("exchange", exchange)

            elif "where status = " in query_lower:
                # Extract status from query
                status = SELECT_QUERY.split("'")[1]
                query = query.eq("status", status)

            elif "where trade = " in query_lower:
                # Extract trade from query
                trade = SELECT_QUERY.split("'")[1]
                query = query.eq("trade", trade)

            # Parse date range conditions
            if "created_at >=" in query_lower and "created_at <=" in query_lower:
                start_date = SELECT_QUERY.split("created_at >= '")[1].split("'")[0]
                end_date = SELECT_QUERY.split("created_at <= '")[1].split("'")[0]
                query = query.gte("created_at", start_date).lte("created_at", end_date)
            elif "created_at >=" in query_lower:
                start_date = SELECT_QUERY.split("created_at >= '")[1].split("'")[0]
                query = query.gte("created_at", start_date)
            elif "created_at <=" in query_lower:
                end_date = SELECT_QUERY.split("created_at <= '")[1].split("'")[0]
                query = query.lte("created_at", end_date)

            # Parse ORDER BY
            if "order by" in query_lower:
                if "created_at desc" in query_lower:
                    query = query.order("created_at", desc=True)
                elif "created_at asc" in query_lower:
                    query = query.order("created_at", desc=False)
                elif "id desc" in query_lower:
                    query = query.order("id", desc=True)
                elif "id asc" in query_lower:
                    query = query.order("id", desc=False)

            # Parse LIMIT
            if "limit" in query_lower:
                limit_match = SELECT_QUERY.split("limit")[1].strip()
                limit = int(limit_match) if limit_match.isdigit() else None
                if limit:
                    query = query.limit(limit)

            # Execute the query
            response = query.execute()
            alerts = response.data or []

            logger.info(f"Found {len(alerts)} alert(s) to process")
            return alerts

        except Exception as e:
            logger.error(f"Error fetching alerts: {e}")
            logger.info("Falling back to simple query...")

            # Fallback to simple query
            try:
                response = self.supabase.table("alerts").select("*").limit(10).execute()
                alerts = response.data or []
                logger.info(f"Found {len(alerts)} alert(s) with fallback query")
                return alerts
            except Exception as fallback_error:
                logger.error(f"Fallback query also failed: {fallback_error}")
                return []

    async def process_alert(self, alert: Dict[str, Any]) -> Dict[str, Any]:
        """Process a single alert."""
        try:
            alert_id = alert.get('id')
            discord_id = alert.get('discord_id')
            trader = alert.get('trader')
            content = alert.get('content')
            trade_ref = alert.get('trade')

            logger.info(f"Processing alert {alert_id}: {trader} - {content[:50]}...")

            # Construct signal data for processing
            signal_data = {
                "timestamp": alert.get("timestamp"),
                "content": content,
                "discord_id": discord_id,
                "trader": trader,
                "trade": trade_ref,
            }

            # Process the alert using the Discord bot
            result = await self.bot.process_update_signal(signal_data)

            # Log the result
            status = result.get("status", "unknown")
            message = result.get("message", "No message")

            if status == "success":
                logger.info(f"✅ Alert {alert_id} processed successfully: {message}")
            else:
                logger.error(f"❌ Alert {alert_id} processing failed: {message}")

            return {
                "alert_id": alert_id,
                "status": status,
                "message": message,
                "processed_at": datetime.now(timezone.utc).isoformat()
            }

        except Exception as e:
            logger.error(f"Error processing alert {alert.get('id', 'unknown')}: {e}")
            return {
                "alert_id": alert.get('id'),
                "status": "error",
                "message": str(e),
                "processed_at": datetime.now(timezone.utc).isoformat()
            }

    async def update_alert_status(self, alert_id: int, status: str, message: str):
        """Update the alert status in the database."""
        try:
            if not UPDATE_ALERT_STATUS:
                return

            updates = {
                "status": status.upper(),
                "updated_at": datetime.now(timezone.utc).isoformat()
            }

            # Add response data based on status
            if status == "success":
                updates["exchange_response"] = message
            else:
                updates["sync_issues"] = [message]

            response = self.supabase.table("alerts").update(updates).eq("id", alert_id).execute()

            if response.data:
                logger.info(f"Updated alert {alert_id} status to {status.upper()}")
            else:
                logger.warning(f"Failed to update alert {alert_id} status")

        except Exception as e:
            logger.error(f"Error updating alert {alert_id} status: {e}")

    async def process_all_alerts(self):
        """Process all alerts matching the query."""
        try:
            # Fetch alerts
            alerts = await self.fetch_alerts()

            if not alerts:
                logger.info("No alerts to process")
                return

            # Display alert summary
            logger.info("\n" + "="*60)
            logger.info("ALERT PROCESSING SUMMARY")
            logger.info("="*60)
            for i, alert in enumerate(alerts, 1):
                logger.info(f"{i}. ID: {alert.get('id')} | {alert.get('trader')} | {alert.get('content', '')[:50]}...")
            logger.info("="*60)

            if not PROCESS_ALERTS:
                logger.info("PREVIEW MODE - No alerts will be processed")
                return

            # Process each alert
            results = []
            for i, alert in enumerate(alerts, 1):
                logger.info(f"\n--- Processing Alert {i}/{len(alerts)} ---")

                # Process the alert
                result = await self.process_alert(alert)
                results.append(result)

                # Update alert status
                await self.update_alert_status(
                    alert.get('id'),
                    result['status'],
                    result['message']
                )

                # Delay between processing
                if i < len(alerts):
                    logger.info(f"Waiting {PROCESSING_DELAY}s before next alert...")
                    await asyncio.sleep(PROCESSING_DELAY)

            # Display final results
            logger.info("\n" + "="*60)
            logger.info("PROCESSING RESULTS")
            logger.info("="*60)

            success_count = sum(1 for r in results if r['status'] == 'success')
            error_count = len(results) - success_count

            logger.info(f"Total processed: {len(results)}")
            logger.info(f"Successful: {success_count}")
            logger.info(f"Failed: {error_count}")

            if error_count > 0:
                logger.info("\nFailed alerts:")
                for result in results:
                    if result['status'] != 'success':
                        logger.info(f"  - Alert {result['alert_id']}: {result['message']}")

            logger.info("="*60)

        except Exception as e:
            logger.error(f"Error in main processing: {e}")
            raise

# ============================================================================
# MAIN EXECUTION
# ============================================================================

async def main():
    """Main execution function."""
    processor = KuCoinFollowupProcessor()

    try:
        # Initialize
        await processor.initialize()

        # Process alerts
        await processor.process_all_alerts()

        logger.info("✅ KuCoin follow-up processing completed")

    except Exception as e:
        logger.error(f"❌ Processing failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    print("KuCoin Follow-up Signal Processor")
    print("=" * 40)
    print(f"Query: {SELECT_QUERY.strip()}")
    print(f"Process Alerts: {PROCESS_ALERTS}")
    print(f"Update Status: {UPDATE_ALERT_STATUS}")
    print("=" * 40)

    asyncio.run(main())
