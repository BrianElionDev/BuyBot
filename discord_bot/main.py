import uvicorn
from fastapi import FastAPI
import logging
import sys
import os
import asyncio
import time
from contextlib import asynccontextmanager

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
    bot, supabase = initialize_clients()
    if bot and supabase:
        # Start WebSocket real-time sync
        await bot.start_websocket_sync()

        # Start traditional sync scheduler (reduced frequency)
        asyncio.create_task(trade_retry_scheduler())

        logger.info("✅ Discord Bot Service started with WebSocket real-time sync")
    else:
        logger.error("❌ Failed to initialize Discord Bot Service")

    yield

    # Shutdown
    if bot:
        await bot.close()
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

    return app

async def trade_retry_scheduler():
    """Centralized scheduler for all maintenance tasks and auto-scripts."""
    bot, supabase = initialize_clients()
    if not bot or not supabase:
        logger.error("Failed to initialize clients for trade retry scheduler.")
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

    while True:
        try:
            current_time = time.time()

            # Daily sync tasks (every 24 hours)
            if current_time - last_daily_sync >= DAILY_SYNC_INTERVAL:
                logger.info("[Scheduler] Running daily sync tasks...")
                try:
                    await sync_trade_statuses_with_binance(bot, supabase)
                    last_daily_sync = current_time
                    logger.info("[Scheduler] Daily sync completed successfully")
                except Exception as e:
                    logger.error(f"[Scheduler] Error in daily sync: {e}")

            # Transaction history autofill (every 6 hours)
            if current_time - last_transaction_sync >= TRANSACTION_SYNC_INTERVAL:
                logger.info("[Scheduler] Running transaction history autofill...")
                try:
                    await auto_fill_transaction_history(bot, supabase)
                    last_transaction_sync = current_time
                    logger.info("[Scheduler] Transaction history autofill completed successfully")
                except Exception as e:
                    logger.error(f"[Scheduler] Error in transaction history autofill: {e}")

            # Weekly historical backfill (every 7 days)
            if current_time - last_weekly_backfill >= WEEKLY_BACKFILL_INTERVAL:
                logger.info("[Scheduler] Running weekly historical backfill...")
                try:
                    await weekly_historical_backfill(bot, supabase)
                    last_weekly_backfill = current_time
                    logger.info("[Scheduler] Weekly historical backfill completed successfully")
                except Exception as e:
                    logger.error(f"[Scheduler] Error in weekly historical backfill: {e}")

            # Sleep for 1 hour before next check
            await asyncio.sleep(60 * 60)  # 1 hour

        except Exception as e:
            logger.error(f"Error in trade retry scheduler: {e}")
            await asyncio.sleep(60 * 60)  # Wait 1 hour before retrying

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

        # Get all active symbols from recent trades
        response = supabase.from_("trades").select("coin_symbol").not_.is_("coin_symbol", "null").limit(100).execute()
        all_symbols = list(set([trade['coin_symbol'] for trade in response.data if trade.get('coin_symbol')]))

        # Filter out invalid symbols
        invalid_symbols = {
            'APE', 'BT', 'ARC', 'AUCTION', 'AEVO', 'AERO', 'BANANAS31', 'APT', 'AAVE',
            'ARKM', 'ARB', 'ALT', 'BNX', 'BILLY', 'AI16Z', 'BLAST', 'BSW', 'B2', 'API3',
            'BON', 'AIXBT', 'AI', '1000BONK', 'ANIME', 'ARK', 'BOND', 'ANYONE', 'ADA',
            'ALCH', 'BERA', 'ALU', 'ALGO', 'BONK', 'AGT', 'AVAX', 'AIN', 'ATOM',
            '1000RATS', 'BMT', 'BB', 'AR', 'BENDOG', 'AVA', '0X0', 'BRETT', 'BANANA',
            '1000TURBO', 'M', 'PUMPFUN', 'SPX', 'MYX', 'MOG', 'PENGU', 'SPK', 'CRV',
            'HYPE', 'MAGIC', 'ZRC', 'FARTCOIN', 'IP', 'SYN', 'SKATE', 'SOON', 'PUMP'
        }

        # Filter symbols
        valid_symbols = []
        for symbol in all_symbols:
            if (symbol and len(symbol) >= 2 and len(symbol) <= 10 and
                symbol.isalnum() and symbol.upper() not in invalid_symbols):
                valid_symbols.append(symbol)
            else:
                logger.warning(f"Skipping invalid symbol '{symbol}' in transaction history autofill")

        if not valid_symbols:
            logger.info("[Scheduler] No valid symbols found for transaction history autofill")
            return

        logger.info(f"[Scheduler] Auto-filling transaction history for {len(valid_symbols)} valid symbols")

        total_inserted = 0
        total_skipped = 0

        for symbol in valid_symbols:
            try:
                # Use the existing fill method for last 24 hours
                result = await filler.fill_transaction_history_manual(
                    symbol=symbol,
                    days=1,  # Last 24 hours
                    income_type="",
                    batch_size=100
                )

                if result.get('success'):
                    total_inserted += result.get('inserted', 0)
                    total_skipped += result.get('skipped', 0)

                # Rate limiting between symbols
                await asyncio.sleep(0.5)

            except Exception as e:
                logger.error(f"[Scheduler] Error processing symbol {symbol}: {e}")
                continue

        logger.info(f"[Scheduler] Transaction history autofill completed: {total_inserted} inserted, {total_skipped} skipped")

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