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

from discord_bot.endpoints.discord_endpoint import router as discord_router
from discord_bot.utils.trade_retry_utils import (
    initialize_clients,
    sync_trade_statuses_with_binance,
    backfill_trades_from_binance_history,
)
from scripts.maintenance.cleanup_scripts.cleanup_orphaned_orders import OrphanedOrdersCleanup
from scripts.maintenance.migration_scripts.backfill_from_historical_trades import HistoricalTradeBackfillManager

# Configure logging for the Discord service using centralized config
from config.logging_config import setup_production_logging
logging_config = setup_production_logging()

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("🚀 Starting Discord Bot Service...")

    bot = None
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

            # Run initial price backfill on startup
            try:
                logger.info("🔄 Running initial price backfill on startup...")
                # Use the advanced backfill that can correct existing prices
                backfill_manager = HistoricalTradeBackfillManager()
                backfill_manager.binance_exchange = bot.binance_exchange
                backfill_manager.db_manager = bot.db_manager
                
                # Fill missing prices and correct existing ones for better accuracy
                await backfill_manager.backfill_from_historical_data(days=1, update_existing=True)
                logger.info("✅ Initial price backfill completed")
            except Exception as e:
                logger.error(f"❌ Failed to run initial price backfill: {e}")

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

    @app.post("/scheduler/test-orphaned-orders-cleanup")
    async def test_orphaned_orders_cleanup():
        """Manually trigger orphaned orders cleanup for testing."""
        try:
            bot, supabase = initialize_clients()
            if not bot or not supabase:
                return {"error": "Failed to initialize clients"}

            result = await cleanup_orphaned_orders_automatic(bot)
            return result
        except Exception as e:
            return {"error": f"Failed to run orphaned orders cleanup: {e}"}

    @app.post("/scheduler/test-balance-sync")
    async def test_balance_sync():
        """Manually trigger balance sync for testing."""
        try:
            bot, supabase = initialize_clients()
            if not bot or not supabase:
                return {"error": "Failed to initialize clients"}

            await sync_exchange_balances(supabase)
            return {"message": "Balance sync completed successfully"}
        except Exception as e:
            return {"error": f"Failed to run balance sync: {e}"}

    @app.get("/scheduler/status")
    async def scheduler_status():
        """Get scheduler status and next run times."""
        current_time = time.time()

        # Calculate next run times
        daily_interval = 24 * 60 * 60
        transaction_interval = 1 * 60 * 60
        pnl_interval = 1 * 60 * 60
        price_interval = 1 * 60 * 60
        weekly_interval = 7 * 24 * 60 * 60

        return {
            "scheduler": "Discord Bot Scheduler",
            "status": "Running",
            "intervals": {
                "daily_sync": f"{daily_interval/3600:.1f} hours",
                "transaction_history": f"{transaction_interval/3600:.1f} hours",
                "pnl_backfill": f"{pnl_interval/3600:.1f} hours",
                "price_backfill": f"{price_interval/3600:.1f} hours",
                "weekly_backfill": f"{weekly_interval/3600:.1f} hours",
                "stop_loss_audit": "0.5 hours (30 minutes)",
                "take_profit_audit": "0.5 hours (30 minutes)",
                "orphaned_orders_cleanup": "2.0 hours",
                "balance_sync": "0.08 hours (5 minutes)"
            },
            "current_time": datetime.fromtimestamp(current_time).isoformat(),
            "endpoints": {
                "test_transaction": "/scheduler/test-transaction-history",
                "test_daily_sync": "/scheduler/test-daily-sync",
                "test_orphaned_orders_cleanup": "/scheduler/test-orphaned-orders-cleanup",
                "test_balance_sync": "/scheduler/test-balance-sync"
            }
        }

    return app

async def cleanup_orphaned_orders_automatic(bot):
    """
    Automatic orphaned orders cleanup function for the scheduler.
    Runs without user confirmation and logs results.
    """
    try:
        cleanup = OrphanedOrdersCleanup()

        # Initialize with the bot's existing exchange connection
        cleanup.binance_exchange = bot.binance_exchange

        # Get current state
        orders = await cleanup.get_open_orders()
        positions = await cleanup.get_positions()

        # Identify orphaned orders
        orphaned = cleanup.identify_orphaned_orders(orders, positions)

        if not orphaned:
            return {
                'success': True,
                'orphaned_orders_found': 0,
                'orders_closed': 0,
                'message': 'No orphaned orders found'
            }

        # Close orphaned orders automatically (no confirmation needed)
        closed_count = 0
        failed_count = 0

        for order in orphaned:
            try:
                success = await cleanup.close_orphaned_order(order)
                if success:
                    closed_count += 1
                else:
                    failed_count += 1

                # Small delay to avoid rate limiting
                await asyncio.sleep(0.1)

            except Exception as e:
                logger.error(f"Error closing orphaned order {order.get('symbol')} {order.get('orderId')}: {e}")
                failed_count += 1

        # Save report
        cleanup.save_report()

        return {
            'success': True,
            'orphaned_orders_found': len(orphaned),
            'orders_closed': closed_count,
            'orders_failed': failed_count,
            'message': f'Cleanup completed: {closed_count} closed, {failed_count} failed'
        }

    except Exception as e:
        logger.error(f"Error in automatic orphaned orders cleanup: {e}")
        return {
            'success': False,
            'error': str(e),
            'message': f'Cleanup failed: {e}'
        }

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
    last_pnl_backfill = 0
    last_price_backfill = 0
    last_weekly_backfill = 0
    last_stop_loss_audit = 0
    last_take_profit_audit = 0
    last_orphaned_orders_cleanup = 0
    last_balance_sync = 0

    # Task intervals (in seconds)
    DAILY_SYNC_INTERVAL = 24 * 60 * 60  # 24 hours
    TRANSACTION_SYNC_INTERVAL = 1 * 60 * 60  # 1 hour
    PNL_BACKFILL_INTERVAL = 1 * 60 * 60  # 1 hour
    PRICE_BACKFILL_INTERVAL = 1 * 60 * 60  # 1 hour
    WEEKLY_BACKFILL_INTERVAL = 7 * 24 * 60 * 60  # 7 days
    STOP_LOSS_AUDIT_INTERVAL = 30 * 60  # 30 minutes
    TAKE_PROFIT_AUDIT_INTERVAL = 30 * 60  # 30 minutes
    ORPHANED_ORDERS_CLEANUP_INTERVAL = 2 * 60 * 60  # 2 hours
    BALANCE_SYNC_INTERVAL = 5 * 60  # 5 minutes

    logger.info("[Scheduler] ✅ Scheduler running - monitoring for tasks")

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

            # Transaction history autofill (every 1 hour)
            if current_time - last_transaction_sync >= TRANSACTION_SYNC_INTERVAL:
                logger.info("[Scheduler] Running transaction history autofill...")
                try:
                    await auto_fill_transaction_history(bot, supabase)
                    last_transaction_sync = current_time
                    logger.info("[Scheduler] Transaction history autofill completed successfully")
                    tasks_run += 1
                except Exception as e:
                    logger.error(f"[Scheduler] Error in transaction history autofill: {e}")

            # PnL backfill (every 1 hour)
            if current_time - last_pnl_backfill >= PNL_BACKFILL_INTERVAL:
                logger.info("[Scheduler] Running PnL backfill...")
                try:
                    await backfill_pnl_data(bot, supabase)
                    last_pnl_backfill = current_time
                    logger.info("[Scheduler] PnL backfill completed successfully")
                    tasks_run += 1
                except Exception as e:
                    logger.error(f"[Scheduler] Error in PnL backfill: {e}")

            # Price backfill (every 1 hour) - includes correcting existing prices
            if current_time - last_price_backfill >= PRICE_BACKFILL_INTERVAL:
                logger.info("[Scheduler] Running price backfill...")
                try:
                    # Use the advanced backfill that can correct existing prices
                    backfill_manager = HistoricalTradeBackfillManager()
                    backfill_manager.binance_exchange = bot.binance_exchange
                    backfill_manager.db_manager = bot.db_manager
                    
                    # First fill missing prices, then correct existing ones
                    await backfill_manager.backfill_from_historical_data(days=1, update_existing=True)
                    
                    last_price_backfill = current_time
                    logger.info("[Scheduler] Price backfill completed successfully")
                    tasks_run += 1
                except Exception as e:
                    logger.error(f"[Scheduler] Error in price backfill: {e}")

            # Weekly historical backfill (every 7 days) - includes correcting existing prices
            if current_time - last_weekly_backfill >= WEEKLY_BACKFILL_INTERVAL:
                logger.info("[Scheduler] Running weekly historical backfill...")
                try:
                    # Use the advanced backfill that can correct existing prices
                    backfill_manager = HistoricalTradeBackfillManager()
                    backfill_manager.binance_exchange = bot.binance_exchange
                    backfill_manager.db_manager = bot.db_manager
                    
                    # Fill missing prices first, then correct existing ones for better accuracy
                    await backfill_manager.backfill_from_historical_data(days=7, update_existing=True)
                    
                    last_weekly_backfill = current_time
                    logger.info("[Scheduler] Weekly historical backfill completed successfully")
                    tasks_run += 1
                except Exception as e:
                    logger.error(f"[Scheduler] Error in weekly historical backfill: {e}")

            # Stop loss audit (every 30 minutes) - supervisor requirement
            if current_time - last_stop_loss_audit >= STOP_LOSS_AUDIT_INTERVAL:
                logger.info("[Scheduler] Running stop loss audit for all open positions...")
                try:
                    audit_results = await bot.trading_engine.audit_open_positions_for_stop_loss()
                    last_stop_loss_audit = current_time
                    logger.info(f"[Scheduler] Stop loss audit completed: {audit_results}")
                    tasks_run += 1
                except Exception as e:
                    logger.error(f"[Scheduler] Error in stop loss audit: {e}")

            # Take profit audit (every 30 minutes, 5 minutes after SL audit) - supervisor requirement
            if current_time - last_take_profit_audit >= TAKE_PROFIT_AUDIT_INTERVAL:
                # Check if it's been at least 5 minutes since the last SL audit
                time_since_sl_audit = current_time - last_stop_loss_audit
                if time_since_sl_audit >= 5 * 60:  # 5 minutes
                    logger.info("[Scheduler] Running take profit audit for all open positions...")
                    try:
                        audit_results = await bot.trading_engine.audit_open_positions_for_take_profit()
                        last_take_profit_audit = current_time
                        logger.info(f"[Scheduler] Take profit audit completed: {audit_results}")
                        tasks_run += 1
                    except Exception as e:
                        logger.error(f"[Scheduler] Error in take profit audit: {e}")

            # Orphaned orders cleanup (every 2 hours) - supervisor requirement
            if current_time - last_orphaned_orders_cleanup >= ORPHANED_ORDERS_CLEANUP_INTERVAL:
                logger.info("[Scheduler] Running orphaned orders cleanup...")
                try:
                    cleanup_results = await cleanup_orphaned_orders_automatic(bot)
                    last_orphaned_orders_cleanup = current_time
                    logger.info(f"[Scheduler] Orphaned orders cleanup completed: {cleanup_results}")
                    tasks_run += 1
                except Exception as e:
                    logger.error(f"[Scheduler] Error in orphaned orders cleanup: {e}")

            # Balance sync (every 5 minutes) - fetch and store exchange balances
            if current_time - last_balance_sync >= BALANCE_SYNC_INTERVAL:
                logger.info("[Scheduler] Running balance sync...")
                try:
                    await sync_exchange_balances(supabase)
                    last_balance_sync = current_time
                    logger.info("[Scheduler] Balance sync completed successfully")
                    tasks_run += 1
                except Exception as e:
                    logger.error(f"[Scheduler] Error in balance sync: {e}")

            # Sleep for 1 second to prevent CPU overload while maintaining responsiveness
            await asyncio.sleep(1)  # 1 second sleep to prevent CPU overload

        except Exception as e:
            logger.error(f"Error in trade retry scheduler: {e}")
            await asyncio.sleep(1)  # Wait 1 second before retrying

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
    """Auto-fill transaction history from Binance income endpoint - incremental approach using latest timestamp."""
    try:
        from scripts.maintenance.cleanup_scripts.manual_transaction_history_fill import TransactionHistoryFiller
        
        filler = TransactionHistoryFiller()
        filler.bot = bot  # Use existing bot instance
        filler.db_manager = DatabaseManager(supabase)  # Use existing supabase instance
        
        logger.info("[Scheduler] Auto-filling transaction history incrementally...")
        
        # Calculate time range - last 7 days
        end_time = int(datetime.now(timezone.utc).timestamp() * 1000)
        start_time = int((datetime.now(timezone.utc) - timedelta(days=7)).timestamp() * 1000)
        
        # Use the working incremental approach
        result = await filler.fill_all_symbols_manual(
            days=7,  # Look back 7 days as fallback if no existing data
            income_type=""  # All income types
        )
        
        if result.get('success'):
            inserted_count = result.get('total_inserted', 0)
            if inserted_count > 0:
                logger.info(f"[Scheduler] Transaction history: {inserted_count} records inserted")
            else:
                logger.debug("[Scheduler] No new transactions inserted (duplicates filtered)")
        else:
            logger.debug(f"[Scheduler] Transaction history error: {result.get('message', 'Unknown error')}")

    except Exception as e:
        logger.debug(f"[Scheduler] Transaction history error: {e}")


async def backfill_pnl_data(bot, supabase):
    """Backfill PnL and net PnL data for closed trades."""
    try:
        from discord_bot.utils.trade_retry_utils import backfill_trades_from_binance_history

        logger.info("[Scheduler] Starting PnL backfill for closed trades...")

        # Backfill PnL data for last 7 days (more recent, faster processing)
        await backfill_trades_from_binance_history(bot, supabase, days=7)

        logger.info("[Scheduler] PnL backfill completed")

    except Exception as e:
        logger.error(f"[Scheduler] Error in PnL backfill: {e}")


async def sync_exchange_balances(supabase):
    """Sync exchange balances from Binance and KuCoin."""
    try:
        from scripts.account_management.balance_scripts.combined_balance_fetcher import CombinedBalanceFetcher
        
        fetcher = CombinedBalanceFetcher()
        
        if not await fetcher.initialize():
            logger.error("[Scheduler] Failed to initialize balance fetcher")
            return
        
        # Fetch and store all balances
        results = await fetcher.fetch_and_store_all_balances()
        logger.info(f"[Scheduler] Balance sync: Binance={results['binance_futures']}, KuCoin={results['kucoin_futures']}, Total={results['total']}")
        
        await fetcher.cleanup()
        
    except Exception as e:
        logger.error(f"[Scheduler] Error in balance sync: {e}")


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


async def backfill_missing_prices(bot, supabase):
    """Backfill missing Binance entry and exit prices for recent trades."""
    try:
        logger.info("[Scheduler] Starting price backfill for recent trades...")

        # Create backfill manager with existing clients
        backfill_manager = HistoricalTradeBackfillManager()
        backfill_manager.binance_exchange = bot.binance_exchange  # Use existing exchange instance
        backfill_manager.db_manager = bot.db_manager  # Use existing database manager

        # Backfill prices for last 7 days (recent trades that might have missed WebSocket updates)
        # Phase 1: Fill missing prices only
        await backfill_manager.backfill_from_historical_data(days=7, update_existing=False)

        # Phase 2: Update existing prices for better accuracy (every 2 hours for better accuracy)
        from datetime import datetime
        current_hour = datetime.now().hour
        if current_hour % 2 == 0:  # Run every 2 hours (0, 2, 4, 6, 8, 10, 12, 14, 16, 18, 20, 22)
            await backfill_manager.backfill_from_historical_data(days=7, update_existing=True)

        logger.info("[Scheduler] Price backfill completed")

    except Exception as e:
        logger.error(f"[Scheduler] Error in price backfill: {e}")


app = create_app()

if __name__ == "__main__":
    logger.info("🚀 Starting Discord Bot Service...")
    uvicorn.run(app, host="127.0.0.1", port=8001)
