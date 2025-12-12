import uvicorn
from fastapi import FastAPI
import logging
import sys
import os
import asyncio
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone, timedelta

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from discord_bot.endpoints.discord_endpoint import router as discord_router
from discord_bot.endpoints.trader_config_endpoints import router as trader_config_router
from discord_bot.utils.trade_retry_utils import (
    initialize_clients,
    sync_trade_statuses_with_binance,
    sync_trade_statuses_with_kucoin,
)

from discord_bot.utils.activity_monitor import ActivityMonitor
from config import settings as _settings
from scripts.maintenance.cleanup_scripts.backfill_pnl_and_exit_prices import BinancePnLBackfiller
from scripts.maintenance.cleanup_scripts.backfill_coin_symbols import backfill_coin_symbols
from scripts.maintenance.cleanup_scripts.cleanup_orphaned_orders import OrphanedOrdersCleanup
from scripts.maintenance.migration_scripts.backfill_from_historical_trades import HistoricalTradeBackfillManager
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
            ActivityMonitor.mark_activity("entry")
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
                # Set attributes directly if they exist
                if hasattr(backfill_manager, 'binance_exchange'):
                    backfill_manager.binance_exchange = bot.binance_exchange
                if hasattr(backfill_manager, 'db_manager'):
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
        # Close shared Telegram session cleanly
        try:
            from src.services.notifications.telegram_service import TelegramService
            await TelegramService.close_shared()
            logger.info("✅ Telegram session closed successfully")
        except Exception as e:
            logger.warning(f"Failed to close Telegram session: {e}")
    except Exception as e:
        logger.error(f"❌ Error closing bot: {e}")

    logger.info("🛑 Discord Bot Service stopped")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application for the Discord service."""
    app = FastAPI(title="Rubicon Trading Bot - Discord Service", lifespan=lifespan)

    app.include_router(discord_router, prefix="/api/v1", tags=["discord"])
    app.include_router(trader_config_router, prefix="/api/v1", tags=["trader-config"])

    @app.get("/")
    async def root():
        return {"message": "Discord Bot Service is running"}

    @app.get("/health")
    async def health_check():
        """Health check endpoint for Docker and load balancers."""
        try:
            # Basic health check - can be extended with more checks
            return {
                "status": "healthy",
                "service": "Rubicon Trading Bot",
                "timestamp": datetime.now().isoformat(),
                "version": "1.0.0"
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }

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
        coin_symbol_interval = 6 * 60 * 60

        return {
            "scheduler": "Discord Bot Scheduler",
            "status": "Running",
            "intervals": {
                "daily_sync": f"{daily_interval/3600:.1f} hours",
                "transaction_history": f"{transaction_interval/3600:.1f} hours (Binance + KuCoin with 7min delay)",
                "pnl_backfill": f"{pnl_interval/3600:.1f} hours",
                "price_backfill": f"{price_interval/3600:.1f} hours",
                "weekly_backfill": f"{weekly_interval/3600:.1f} hours",
                "stop_loss_audit": "0.5 hours (30 minutes)",
                "take_profit_audit": "0.5 hours (30 minutes)",
                "orphaned_orders_cleanup": "2.0 hours",
                "balance_sync": "0.08 hours (5 minutes)",
                "coin_symbol_backfill": f"{coin_symbol_interval/3600:.1f} hours",
                "order_monitoring": "0.08 hours (5 minutes)"
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
                # success = await cleanup.close_orphaned_order(order)
                success = False
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
    last_kucoin_sync = 0
    last_transaction_sync = 0
    last_pnl_backfill = 0
    last_price_backfill = 0
    last_weekly_backfill = 0
    last_stop_loss_audit = 0
    last_take_profit_audit = 0
    last_orphaned_orders_cleanup = 0
    last_balance_sync = 0
    last_coin_symbol_backfill = 0
    last_active_futures_sync = 0
    last_order_monitor = 0
    last_reconciliation = 0
    last_missing_data_sync = 0

    # Task intervals (in seconds)
    DAILY_SYNC_INTERVAL = 24 * 60 * 60  # 24 hours
    KUCOIN_SYNC_INTERVAL = 10 * 60  # 10 minutes (enhanced frequency for KuCoin)
    TRANSACTION_SYNC_INTERVAL = 1 * 60 * 60  # 1 hour
    ORDER_MONITOR_INTERVAL = 35 * 60  # 5 minutes (comprehensive order status monitoring)
    PNL_BACKFILL_INTERVAL = 1 * 60 * 60  # 1 hour
    PRICE_BACKFILL_INTERVAL = 1 * 60 * 60  # 1 hour
    WEEKLY_BACKFILL_INTERVAL = 7 * 24 * 60 * 60  # 7 days
    STOP_LOSS_AUDIT_INTERVAL = 30 * 60  # 30 minutes
    TAKE_PROFIT_AUDIT_INTERVAL = 30 * 60  # 30 minutes
    ORPHANED_ORDERS_CLEANUP_INTERVAL = 2 * 60 * 60  # 2 hours
    BALANCE_SYNC_INTERVAL = 5 * 60  # 5 minutes
    COIN_SYMBOL_BACKFILL_INTERVAL = 6 * 60 * 60  # 6 hours
    ACTIVE_FUTURES_SYNC_INTERVAL = 5 * 60  # 5 minutes
    RECONCILIATION_INTERVAL = 6 * 60 * 60  # 6 hours
    MISSING_DATA_SYNC_INTERVAL = 2 * 60 * 60  # 2 hours

    logger.info("[Scheduler] ✅ Scheduler running - monitoring for tasks")

    last_inactivity_check = 0
    INACTIVITY_CHECK_INTERVAL = 5 * 60

    while True:
        try:
            current_time = time.time()
            tasks_run = 0

            # Daily sync tasks (every 24 hours) - comprehensive sync
            if current_time - last_daily_sync >= DAILY_SYNC_INTERVAL:
                logger.info("[Scheduler] Running daily sync tasks...")
                try:
                    # Sync Binance trades
                    await sync_trade_statuses_with_binance(bot, supabase)

                    # Sync KuCoin trades (comprehensive daily sync)
                    await sync_trade_statuses_with_kucoin(bot, supabase)

                    last_daily_sync = current_time
                    logger.info("[Scheduler] Daily sync completed successfully")
                    tasks_run += 1
                except Exception as e:
                    logger.error(f"[Scheduler] Error in daily sync: {e}")

            # Enhanced KuCoin sync (every 10 minutes) - for active trades
            if current_time - last_kucoin_sync >= KUCOIN_SYNC_INTERVAL:
                logger.info("[Scheduler] Running enhanced KuCoin sync (10min interval)...")
                try:
                    # Only sync active/pending KuCoin trades for faster processing
                    cutoff = datetime.now(timezone.utc) - timedelta(days=1)
                    cutoff_iso = cutoff.isoformat()
                    response = supabase.from_("trades").select("*").gte("created_at", cutoff_iso).eq("exchange", "kucoin").in_("status", ["PENDING", "ACTIVE", "OPEN"]).execute()
                    active_kucoin_trades = response.data or []

                    if active_kucoin_trades:
                        logger.info(f"[Scheduler] Found {len(active_kucoin_trades)} active KuCoin trades to sync")
                        await sync_trade_statuses_with_kucoin(bot, supabase)
                    else:
                        logger.debug("[Scheduler] No active KuCoin trades to sync")

                    last_kucoin_sync = current_time
                    tasks_run += 1
                except Exception as e:
                    logger.error(f"[Scheduler] Error in enhanced KuCoin sync: {e}")

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
                    # Set attributes directly if they exist
                    if hasattr(backfill_manager, 'binance_exchange'):
                        backfill_manager.binance_exchange = bot.binance_exchange
                    if hasattr(backfill_manager, 'db_manager'):
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
                    # Set attributes directly if they exist
                    if hasattr(backfill_manager, 'binance_exchange'):
                        backfill_manager.binance_exchange = bot.binance_exchange
                    if hasattr(backfill_manager, 'db_manager'):
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
            # Disabled: orphaned orders cleanup is not called from the scheduler
            # if current_time - last_orphaned_orders_cleanup >= ORPHANED_ORDERS_CLEANUP_INTERVAL:
            #     logger.info("[Scheduler] Running orphaned orders cleanup...")
            #     try:
            #         cleanup_results = await cleanup_orphaned_orders_automatic(bot)
            #         last_orphaned_orders_cleanup = current_time
            #         logger.info(f"[Scheduler] Orphaned orders cleanup completed: {cleanup_results}")
            #         tasks_run += 1
            #     except Exception as e:
            #         logger.error(f"[Scheduler] Error in orphaned orders cleanup: {e}")

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

            # Coin symbol backfill (every 6 hours) - backfill missing coin symbols
            if current_time - last_coin_symbol_backfill >= COIN_SYMBOL_BACKFILL_INTERVAL:
                logger.info("[Scheduler] Running coin symbol backfill...")
                try:
                    backfill_coin_symbols(batch_size=100)
                    last_coin_symbol_backfill = current_time
                    logger.info("[Scheduler] Coin symbol backfill completed successfully")
                    tasks_run += 1
                except Exception as e:
                    logger.error(f"[Scheduler] Error in coin symbol backfill: {e}")

            if current_time - last_active_futures_sync >= ACTIVE_FUTURES_SYNC_INTERVAL:
                logger.info("[Scheduler] Running active futures synchronization...")
                try:
                    await sync_active_futures_with_trades()
                    last_active_futures_sync = current_time
                    logger.info("[Scheduler] Active futures sync completed successfully")
                    tasks_run += 1
                except Exception as e:
                    logger.error(f"[Scheduler] Error in active futures sync: {e}")

            # Comprehensive order status monitoring (every 5 minutes)
            if current_time - last_order_monitor >= ORDER_MONITOR_INTERVAL:
                logger.info("[Scheduler] Running comprehensive order status monitoring...")
                try:
                    from src.bot.order_management.order_monitor import OrderMonitor

                    # Monitor Binance orders
                    if bot.binance_exchange:
                        binance_monitor = OrderMonitor(bot.db_manager, bot.binance_exchange)
                        binance_stats = await binance_monitor.monitor_pending_orders(max_age_minutes=30)
                        logger.info(f"[Scheduler] Binance order monitoring: {binance_stats}")

                    # Monitor KuCoin orders (if available)
                    if hasattr(bot, 'kucoin_exchange') and bot.kucoin_exchange:
                        kucoin_monitor = OrderMonitor(bot.db_manager, bot.kucoin_exchange)
                        kucoin_stats = await kucoin_monitor.monitor_pending_orders(max_age_minutes=30)
                        logger.info(f"[Scheduler] KuCoin order monitoring: {kucoin_stats}")

                    last_order_monitor = current_time
                    logger.info("[Scheduler] Order monitoring completed successfully")
                    tasks_run += 1
                except Exception as e:
                    logger.error(f"[Scheduler] Error in order monitoring: {e}")

            # Trade reconciliation (every 6 hours) - fix status inconsistencies and backfill missing data
            if current_time - last_reconciliation >= RECONCILIATION_INTERVAL:
                logger.info("[Scheduler] Running trade reconciliation...")
                try:
                    from src.services.reconciliation_service import ReconciliationService

                    recon_service = ReconciliationService(supabase, bot)
                    results = await recon_service.reconcile_closed_trades(
                        days_back=7,
                        fix_status_inconsistencies=True,
                        backfill_missing_data=True
                    )

                    # Also reconcile trades with PNL but no exit_price
                    pnl_results = await recon_service.reconcile_trades_with_pnl_but_no_exit_price(days_back=30)

                    logger.info(f"[Scheduler] Reconciliation completed: {results}")
                    logger.info(f"[Scheduler] PNL reconciliation completed: {pnl_results}")

                    last_reconciliation = current_time
                    tasks_run += 1
                except Exception as e:
                    logger.error(f"[Scheduler] Error in trade reconciliation: {e}")

            # Comprehensive missing data sync (every 2 hours) - populate entry_price, exit_price, position_size, pnl_usd
            if current_time - last_missing_data_sync >= MISSING_DATA_SYNC_INTERVAL:
                logger.info("[Scheduler] Running comprehensive missing trade data sync...")
                try:
                    from discord_bot.utils.trade_retry_utils import sync_missing_trade_data_comprehensive
                    result = await sync_missing_trade_data_comprehensive(bot, supabase, days_back=7)
                    last_missing_data_sync = current_time
                    logger.info(f"[Scheduler] Missing data sync completed: {result}")
                    tasks_run += 1
                except Exception as e:
                    logger.error(f"[Scheduler] Error in missing data sync: {e}")

            await asyncio.sleep(1)

        except Exception as e:
            logger.error(f"Error in trade retry scheduler: {e}")
            await asyncio.sleep(1)
            current_time = time.time()

        if _settings.INACTIVITY_ALERT_ENABLED and current_time - last_inactivity_check >= INACTIVITY_CHECK_INTERVAL:
            try:
                await ActivityMonitor.check_and_alert()
            except Exception as e:
                logger.error(f"[Scheduler] Error in inactivity check: {e}")
            finally:
                last_inactivity_check = current_time

async def sync_active_futures_with_trades():
    """Synchronize active futures table with local trades."""
    try:
        from src.services.active_futures_sync_service import ActiveFuturesSyncService
        from src.database.core.database_manager import DatabaseManager

        db_manager = DatabaseManager()
        sync_service = ActiveFuturesSyncService(db_manager)

        await sync_service.initialize()
        result = await sync_service.sync_active_futures()

        if getattr(result, 'success', False):
            logger.info(f"Active futures sync successful: {getattr(result, 'data', None)}")
        else:
            logger.error(f"Active futures sync failed: {getattr(result, 'error', 'unknown')}")

    except Exception as e:
        logger.error(f"Error in active futures sync: {e}")

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
    """Auto-fill transaction history from both Binance and KuCoin exchanges concurrently."""
    try:
        from discord_bot.database import DatabaseManager
        from src.exchange.kucoin.kucoin_transaction_fetcher import KucoinTransactionFetcher

        # Initialize database manager
        db_manager = DatabaseManager(supabase)

        logger.info("[Scheduler] Starting concurrent transaction history sync for Binance and KuCoin...")

        # Create tasks for concurrent execution
        binance_task = asyncio.create_task(
            _process_binance_transactions(bot, db_manager)
        )

        kucoin_task = asyncio.create_task(
            _process_kucoin_transactions(bot, db_manager)
        )

        # Wait for both tasks to complete
        binance_result, kucoin_result = await asyncio.gather(
            binance_task, kucoin_task, return_exceptions=True
        )

        # Log results
        if isinstance(binance_result, Exception):
            logger.error(f"[Scheduler] Binance transaction history error: {binance_result}")
        else:
            logger.info(f"[Scheduler] Binance transaction history: {binance_result}")

        if isinstance(kucoin_result, Exception):
            logger.error(f"[Scheduler] KuCoin transaction history error: {kucoin_result}")
        else:
            logger.info(f"[Scheduler] KuCoin transaction history: {kucoin_result}")

    except Exception as e:
        logger.error(f"[Scheduler] Transaction history error: {e}")


async def _process_binance_transactions(bot, db_manager):
    """Process Binance transaction history."""
    try:
        from scripts.maintenance.cleanup_scripts.autofill_transaction_history import AutoTransactionHistoryFiller

        logger.info("[Scheduler] Processing Binance transaction history...")

        autofiller = AutoTransactionHistoryFiller()
        # Set attributes directly if they exist
        if hasattr(autofiller, 'binance_exchange'):
            autofiller.binance_exchange = bot.binance_exchange
        if hasattr(autofiller, 'db_manager'):
            autofiller.db_manager = db_manager

        # Use the working autofill approach for Binance
        binance_result = await autofiller.auto_fill_transaction_history(
            symbols=None,  # All symbols
            days_back=7,   # Last 7 days
            income_type=""  # All income types
        )

        if binance_result.get('success'):
            inserted_count = binance_result.get('total_inserted', 0)
            if inserted_count > 0:
                return f"{inserted_count} records inserted"
            else:
                return f"{binance_result.get('total_inserted', 0)} inserted, {binance_result.get('total_skipped', 0)} skipped"
        else:
            # Don't treat "no income records found" as an error - this is normal
            if "No income records found" in binance_result.get('message', ''):
                return binance_result.get('message', 'No new income records')
            else:
                raise Exception(f"Binance autofill failed: {binance_result.get('message', 'Unknown error')}")

    except Exception as e:
        logger.error(f"[Scheduler] Binance transaction processing error: {e}")
        raise


async def _process_kucoin_transactions(bot, db_manager):
    """Process KuCoin transaction history."""
    try:
        from src.exchange.kucoin.kucoin_transaction_fetcher import KucoinTransactionFetcher

        logger.info("[Scheduler] Processing KuCoin transaction history...")

        # Initialize KuCoin transaction fetcher
        kucoin_fetcher = KucoinTransactionFetcher(bot.kucoin_exchange)

        # Calculate time range (last 7 days)
        end_time = int(datetime.now(timezone.utc).timestamp() * 1000)
        start_time = int((datetime.now(timezone.utc) - timedelta(days=7)).timestamp() * 1000)

        # Fetch KuCoin transactions using the enhanced fetcher
        kucoin_transactions = await kucoin_fetcher.fetch_transaction_history(
            symbol="",  # All symbols
            start_time=start_time,
            end_time=end_time,
            limit=1000
        )

        if not kucoin_transactions:
            return "No transactions found"

        transformed_transactions = []
        for transaction in kucoin_transactions:
            # Ensure exchange is set
            transaction['exchange'] = 'kucoin'
            transformed_transactions.append(transaction)

        # Insert in batches to avoid database locks
        batch_size = 100
        total_inserted = 0
        total_skipped = 0

        for i in range(0, len(transformed_transactions), batch_size):
            batch = transformed_transactions[i:i + batch_size]

            # Check for duplicates before inserting
            filtered_batch = []
            for transaction in batch:
                exists = await db_manager.check_transaction_exists(
                    time=transaction.get('time', ''),
                    type=transaction.get('type', ''),
                    amount=transaction.get('amount', 0),
                    asset=transaction.get('asset', ''),
                    symbol=transaction.get('symbol', '')
                )
                if not exists:
                    filtered_batch.append(transaction)
                else:
                    total_skipped += 1

            if filtered_batch:
                success = await db_manager.insert_transaction_history_batch(filtered_batch)
                if success:
                    total_inserted += len(filtered_batch)
                    logger.info(f"[Scheduler] KuCoin batch {i//batch_size + 1}: {len(filtered_batch)} transactions inserted")
                else:
                    logger.error(f"[Scheduler] KuCoin batch {i//batch_size + 1}: Failed to insert")

            await asyncio.sleep(0.5)

        return f"{total_inserted} inserted, {total_skipped} skipped"

    except Exception as e:
        logger.error(f"[Scheduler] KuCoin transaction processing error: {e}")
        raise


async def backfill_pnl_data(bot, supabase):
    """Backfill PnL and net PnL data for closed trades."""
    try:
        pnl_backfiller = BinancePnLBackfiller(bot, supabase)
        logger.info("[Scheduler] Starting PnL backfill for closed trades...")

        # Backfill PnL data for last 7 days
        await pnl_backfiller.backfill_trades_with_income_history(days=7, symbol="")

        # KuCoin: reconcile last 32 hours (1.33 days) using position history (after Binance)
        # Run more frequently to ensure accurate data for recent trades
        try:
            from scripts.maintenance.kucoin_pnl_reconcile_7d import main as kucoin_pnl_reconcile_main
            await kucoin_pnl_reconcile_main(days=2, missing_pnl_only=True)
            logger.info("[Scheduler] KuCoin PnL reconciliation completed (last 2 days, missing PnL only)")
        except Exception as e:
            logger.error(f"[Scheduler] Error in KuCoin PnL reconciliation: {e}")

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
        backfill_manager.kucoin_exchange = bot.kucoin_exchange  # Use existing KuCoin exchange instance
        backfill_manager.db_manager = bot.db_manager  # Use existing database manager

        # Backfill prices for last 7 days (recent trades that might have missed WebSocket updates)
        # Phase 1: Fill missing prices only
        await backfill_manager.backfill_from_historical_data(days=7, update_existing=False)

        # Phase 2: Update existing prices for better accuracy (every 2 hours for better accuracy)
        from datetime import datetime
        current_hour = datetime.now().hour
        if current_hour % 2 == 0:  # Run every 2 hours (0, 2, 4, 6, 8, 10, 12, 14, 16, 18, 20, 22)
            await backfill_manager.backfill_from_historical_data(days=7, update_existing=True)

        # KuCoin: fill missing/incorrect entry/exit prices using position history (strict matching)
        try:
            await backfill_manager.backfill_kucoin_prices(days=7, update_existing=False)
            # Optionally update existing for accuracy every 2 hours
            from datetime import datetime
            current_hour = datetime.now().hour
            if current_hour % 2 == 0:
                await backfill_manager.backfill_kucoin_prices(days=7, update_existing=True)
        except Exception as e:
            logger.error(f"[Scheduler] Error in KuCoin price backfill: {e}")

        logger.info("[Scheduler] Price backfill completed")

    except Exception as e:
        logger.error(f"[Scheduler] Error in price backfill: {e}")


app = create_app()

if __name__ == "__main__":
    logger.info("🚀 Starting Discord Bot Service...")
    uvicorn.run(app, host="127.0.0.1", port=8001)
