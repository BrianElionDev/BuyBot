import uvicorn
from fastapi import FastAPI
import logging
import sys
import os
import asyncio
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
    """Reduced frequency scheduler for maintenance tasks (WebSocket handles real-time updates)."""
    bot, supabase = initialize_clients()
    if not bot or not supabase:
        logger.error("Failed to initialize clients for trade retry scheduler.")
        return

    while True:
        try:
            logger.info("[Scheduler] Starting maintenance tasks (WebSocket handles real-time updates)...")

            # Reduced frequency: Run every 24 hours instead of 2 hours
            # WebSocket handles real-time order/position/PnL updates

            # Daily validation and cleanup (once per day)
            await sync_trade_statuses_with_binance(bot, supabase)
            await asyncio.sleep(24 * 60 * 60)  # 24 hours

            # Weekly historical backfill (once per week)
            # This is now handled by the sync script with reduced frequency

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

app = create_app()

if __name__ == "__main__":
    logger.info("🚀 Starting Discord Bot Service...")
    # Run on a different port to avoid conflict with the Telegram service
    uvicorn.run(app, host="127.0.0.1", port=8001)