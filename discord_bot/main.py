import uvicorn
from fastapi import FastAPI
import logging
from discord_bot.discord_endpoint import router as discord_router
import asyncio
from discord_bot.utils.trade_retry_utils import (
    initialize_clients,
    process_pending_trades,
    process_cooldown_trades,
    process_empty_binance_response_trades,
    process_margin_insufficient_trades,
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


def create_app() -> FastAPI:
    """Create and configure the FastAPI application for the Discord service."""
    app = FastAPI(title="Rubicon Trading Bot - Discord Service")

    app.include_router(discord_router, prefix="/api/v1", tags=["discord"])

    @app.get("/")
    async def root():
        return {"message": "Discord Bot Service is running"}

    @app.on_event("startup")
    async def start_background_tasks():
        asyncio.create_task(trade_retry_scheduler())

    return app

async def trade_retry_scheduler():
    bot, supabase = initialize_clients()
    if not bot or not supabase:
        logger.error("Failed to initialize clients for trade retry scheduler.")
        return
    while True:
        logger.info("[Scheduler] Starting scheduled trade retry tasks...")
        await process_pending_trades(bot, supabase)
        await asyncio.sleep(24 * 60)  # 24 minutes
        await process_cooldown_trades(bot, supabase)
        await asyncio.sleep(24 * 60)  # 24 minutes
        await process_empty_binance_response_trades(bot, supabase)
        await asyncio.sleep(24 * 60)  # 24 minutes
        await process_margin_insufficient_trades(bot, supabase)
        await asyncio.sleep(24 * 60)  # 24 minutes
        await sync_trade_statuses_with_binance(bot, supabase)
        await asyncio.sleep(24 * 60)  # 24 minutes (total 2hr cycle)

app = create_app()

if __name__ == "__main__":
    logger.info("🚀 Starting Discord Bot Service...")
    # Run on a different port to avoid conflict with the Telegram service
    uvicorn.run(app, host="127.0.0.1", port=8001)