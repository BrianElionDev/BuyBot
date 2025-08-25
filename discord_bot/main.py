import uvicorn
from fastapi import FastAPI
import logging
import sys
import os
import asyncio
import time
from contextlib import asynccontextmanager
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from discord_bot.discord_endpoint import router as discord_router
from discord_bot.utils.trade_retry_utils import (
    initialize_clients,
    sync_trade_statuses_with_binance,
)

# Configure logging for the Discord service
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - [DiscordSvc] - %(message)s',
    handlers=[
        logging.StreamHandler()
        # You could also add a FileHandler here for persistence
    ]
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("🚀 Starting Discord Bot Service...")
    
    try:
        bot, supabase = initialize_clients()
        if bot and supabase:
            logger.info("✅ Clients initialized successfully")
            
            # Start WebSocket real-time sync
            try:
                await bot.start_websocket_sync()
                logger.info("✅ WebSocket sync started")
            except Exception as e:
                logger.error(f"❌ Failed to start WebSocket sync: {e}")

            # Start traditional sync scheduler (reduced frequency)
            try:
                scheduler_task = asyncio.create_task(trade_retry_scheduler())
                logger.info("✅ Scheduler task created")
            except Exception as e:
                logger.error(f"❌ Failed to create scheduler task: {e}")

            logger.info("✅ Discord Bot Service started with WebSocket real-time sync and scheduler")
        else:
            logger.error("❌ Failed to initialize Discord Bot Service - clients not available")
    except Exception as e:
        logger.error(f"❌ Failed to initialize Discord Bot Service: {e}")

    yield

    # Shutdown
    logger.info("🛑 Shutting down Discord Bot Service...")
    try:
        if bot:
            await bot.close()
            logger.info("✅ Bot closed successfully")
    except Exception as e:
        logger.error(f"❌ Error closing bot: {e}")
    
    logger.info("🛑 Discord Bot Service stopped")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application for the Discord service."""
    app = FastAPI(title="Rubicon Trading Bot - Discord Service", lifespan=lifespan)

    app.include_router(discord_router, prefix="/api/v1", tags=["discord"])

    @app.get("/")
    async def root():
        return {"message": "Discord Bot Service is running"}

    @app.get("/websocket/status")
    async def websocket_status():
        """Get WebSocket real-time sync status."""
        bot, supabase = initialize_clients()
        if bot:
            status = bot.get_websocket_status()
            return {
                "service": "Discord Bot",
                "websocket_status": status,
                "message": "WebSocket real-time sync status"
            }
        else:
            return {
                "service": "Discord Bot",
                "error": "Bot not initialized",
                "message": "Unable to get WebSocket status"
            }

    @app.post("/scheduler/test-transaction-history")
    async def test_transaction_history():
        """Manually trigger transaction history autofill for testing."""
        try:
            bot, supabase = initialize_clients()
            if not bot or not supabase:
                return {"error": "Failed to initialize clients"}
            
            await auto_fill_transaction_history(bot, supabase)
            return {"message": "Transaction history autofill completed"}
        except Exception as e:
            return {"error": f"Failed to run transaction history autofill: {e}"}

    @app.post("/scheduler/test-daily-sync")
    async def test_daily_sync():
        """Manually trigger daily sync for testing."""
        try:
            bot, supabase = initialize_clients()
            if not bot or not supabase:
                return {"error": "Failed to initialize clients"}
            
            await sync_trade_statuses_with_binance(bot, supabase)
            return {"message": "Daily sync completed"}
        except Exception as e:
            return {"error": f"Failed to run daily sync: {e}"}

    @app.get("/scheduler/status")
    async def scheduler_status():
        """Get scheduler status and next run times."""
        current_time = time.time()
        
        # Calculate next run times
        daily_interval = 24 * 60 * 60
        transaction_interval = 6 * 60 * 60
        weekly_interval = 7 * 24 * 60 * 60
        
        return {
            "scheduler": "Discord Bot Scheduler",
            "status": "Running",
            "intervals": {
                "daily_sync": f"{daily_interval/3600:.1f} hours",
                "transaction_history": f"{transaction_interval/3600:.1f} hours", 
                "weekly_backfill": f"{weekly_interval/3600:.1f} hours"
            },
            "current_time": datetime.fromtimestamp(current_time).isoformat(),
            "endpoints": {
                "test_transaction": "/scheduler/test-transaction-history",
                "test_daily_sync": "/scheduler/test-daily-sync"
            }
        }

    return app

async def trade_retry_scheduler():
    """Centralized scheduler for all maintenance tasks and auto-scripts."""
    logger.info("[Scheduler] Initializing trade retry scheduler...")
    
    try:
        bot, supabase = initialize_clients()
        if not bot or not supabase:
            logger.error("Failed to initialize clients for trade retry scheduler.")
            return
    except Exception as e:
        logger.error(f"Failed to initialize clients for scheduler: {e}")
        return

    # Initialize task timers
    last_daily_sync = 0
    last_transaction_sync = 0
    last_weekly_backfill = 0

    # Task intervals (in seconds)
    DAILY_SYNC_INTERVAL = 24 * 60 * 60  # 24 hours
    TRANSACTION_SYNC_INTERVAL = 6 * 60 * 60  # 6 hours
    WEEKLY_BACKFILL_INTERVAL = 7 * 24 * 60 * 60  # 7 days

    logger.info("[Scheduler] Starting centralized maintenance scheduler...")
    logger.info(f"[Scheduler] Intervals - Daily: {DAILY_SYNC_INTERVAL/3600}h, Transaction: {TRANSACTION_SYNC_INTERVAL/3600}h, Weekly: {WEEKLY_BACKFILL_INTERVAL/3600}h")

    while True:
        try:
            current_time = time.time()
            tasks_run = 0

            # Daily sync tasks (every 24 hours)
            if current_time - last_daily_sync >= DAILY_SYNC_INTERVAL:
                logger.info("[Scheduler] Running daily sync tasks...")
                try:
                    await sync_trade_statuses_with_binance(bot, supabase)
                    last_daily_sync = current_time
                    logger.info("[Scheduler] Daily sync completed successfully")
                    tasks_run += 1
                except Exception as e:
                    logger.error(f"[Scheduler] Error in daily sync: {e}")

            # Transaction history autofill (every 6 hours)
            if current_time - last_transaction_sync >= TRANSACTION_SYNC_INTERVAL:
                logger.info("[Scheduler] Running transaction history autofill...")
                try:
                    await auto_fill_transaction_history(bot, supabase)
                    last_transaction_sync = current_time
                    logger.info("[Scheduler] Transaction history autofill completed successfully")
                    tasks_run += 1
                except Exception as e:
                    logger.error(f"[Scheduler] Error in transaction history autofill: {e}")

            # Weekly historical backfill (every 7 days)
            if current_time - last_weekly_backfill >= WEEKLY_BACKFILL_INTERVAL:
                logger.info("[Scheduler] Running weekly historical backfill...")
                try:
                    await weekly_historical_backfill(bot, supabase)
                    last_weekly_backfill = current_time
                    logger.info("[Scheduler] Weekly historical backfill completed successfully")
                    tasks_run += 1
                except Exception as e:
                    logger.error(f"[Scheduler] Error in weekly historical backfill: {e}")

            # Log status
            if tasks_run > 0:
                logger.info(f"[Scheduler] Completed {tasks_run} task(s) this cycle")
            else:
                logger.info("[Scheduler] No tasks due this cycle")

            # Sleep for 6 hours before next check (since most frequent task is every 6 hours)
            logger.info("[Scheduler] Sleeping for 6 hours before next check...")
            await asyncio.sleep(6 * 60 * 60)  # 6 hours

        except Exception as e:
            logger.error(f"Error in trade retry scheduler: {e}")
            logger.info("[Scheduler] Waiting 6 hours before retrying...")
            await asyncio.sleep(6 * 60 * 60)  # Wait 6 hours before retrying

async def check_api_permissions(bot):
    """Check if API key has proper permissions for futures trading"""
    try:
        # Try to get account info to test API permissions
        account_info = await bot.binance_exchange.client.futures_account()
        if account_info:
            logger.info("API permissions check passed")
            return True
        else:
            logger.error("API permissions check failed - no account info returned")
            return False
    except Exception as e:
        logger.error(f"API permissions check failed: {e}")
        return False


async def auto_fill_transaction_history(bot, supabase):
    """Auto-fill transaction history from Binance income endpoint."""
    try:
        from scripts.manual_transaction_history_fill import TransactionHistoryFiller
        from discord_bot.database import DatabaseManager

        filler = TransactionHistoryFiller()
        filler.bot = bot  # Use the existing bot instance
        filler.db_manager = DatabaseManager(supabase)  # Use the existing supabase instance

        # No need to filter symbols - we'll fetch ALL income data from Binance
        logger.info("[Scheduler] Auto-filling transaction history for all symbols")

        # Use the last sync time approach to avoid duplicates - fetch ALL income data
        result = await filler.fill_transaction_history_manual(
            symbol="",  # Empty symbol fetches ALL income data
            days=1,  # Last 24 hours (will be overridden by last sync time if data exists)
            income_type="",
            batch_size=100
        )

        if result.get('success'):
            total_inserted = result.get('inserted', 0)
            total_skipped = result.get('skipped', 0)
            logger.info(f"[Scheduler] Transaction history autofill completed: {total_inserted} inserted, {total_skipped} skipped")
        else:
            logger.error(f"[Scheduler] Transaction history autofill failed: {result.get('message', 'Unknown error')}")

    except Exception as e:
        logger.error(f"[Scheduler] Error in transaction history autofill: {e}")


async def weekly_historical_backfill(bot, supabase):
    """Weekly historical data backfill for comprehensive data sync."""
    try:
        logger.info("[Scheduler] Starting weekly historical backfill...")

        # This can include various historical data backfill tasks
        # For now, we'll just log that it's running
        # You can add specific backfill logic here as needed

        logger.info("[Scheduler] Weekly historical backfill completed")

    except Exception as e:
        logger.error(f"[Scheduler] Error in weekly_historical_backfill: {e}")


app = create_app()

if __name__ == "__main__":
    logger.info("🚀 Starting Discord Bot Service...")
    # Run on a different port to avoid conflict with the Telegram service
    uvicorn.run(app, host="127.0.0.1", port=8001)