import logging
import asyncio
from typing import Dict, Optional
from fastapi import FastAPI
from .telegram_bot import TelegramBot
from src.api.notification_endpoint import create_notification_router
from config.settings import (
    TARGET_GROUP_ID, NOTIFICATION_GROUP_ID
)

logger = logging.getLogger(__name__)

class BotManager:
    def __init__(self, loop: Optional[asyncio.AbstractEventLoop] = None):
        """Initialize the bot manager."""
        self.loop = loop or asyncio.get_event_loop()
        self.telegram_bot = TelegramBot(loop=self.loop)
        self.app = self._setup_fastapi()

    def _setup_fastapi(self) -> FastAPI:
        """Set up the FastAPI application with notification endpoints."""
        app = FastAPI(title="Rubicon Trading Bot - Telegram Service")

        notification_router = create_notification_router(self.telegram_bot)
        app.include_router(notification_router, prefix="/api/v1", tags=["notifications"])

        @app.get("/")
        async def root():
            return {"message": "Telegram Bot Service is running"}

        return app

    async def _check_wallet_connection(self) -> bool:
        """Check if the wallet is properly connected."""
        try:
            wallet_connected = await self.telegram_bot.trading_engine.check_wallet_connection()
            if wallet_connected:
                logger.info("✅ Wallet connection successful")
                return True
            else:
                logger.warning("⚠️ Wallet connection failed - DEX functionality will be disabled")
                return False
        except Exception as e:
            logger.error(f"❌ Error checking wallet connection: {str(e)}")
            return False

    async def start(self):
        """Start the Telegram bot and the API server."""
        try:
            logger.info("🚀 Starting Rubicon Telegram Service")
            logger.info("=" * 50)

            # Log configuration
            logger.info("📋 Configuration:")
            logger.info(f"  • Target Group/Bot: {TARGET_GROUP_ID if TARGET_GROUP_ID else 'Not set'}")
            logger.info(f"  • Notification Group: {NOTIFICATION_GROUP_ID if NOTIFICATION_GROUP_ID else 'Not set'}")

            # Check wallet connection
            logger.info("\n🔗 Checking wallet connection...")
            await self._check_wallet_connection()

            # Start Telegram bot and API server
            logger.info("\n🔄 Service Status:")
            logger.info("  • Telegram Bot: Starting...")
            logger.info("  • Notification API: Starting...")

            telegram_task = asyncio.create_task(self.telegram_bot.start())

            import uvicorn
            config = uvicorn.Config(
                self.app,
                host="0.0.0.0",
                port=8000,
                log_level="info"
            )
            server = uvicorn.Server(config)

            logger.info("  • Telegram Bot: Running")
            logger.info("  • Notification API: Running on http://0.0.0.0:8000")
            logger.info("\n✨ Service started successfully")
            logger.info("=" * 50)

            await asyncio.gather(
                telegram_task,
                server.serve()
            )

        except Exception as e:
            logger.error(f"❌ Error starting bot manager: {str(e)}")
            raise

    async def stop(self):
        """Stop the Telegram bot and the API server."""
        try:
            logger.info("\n🛑 Shutting down services...")
            await self.telegram_bot.stop()
            logger.info("✅ All services stopped successfully")
        except Exception as e:
            logger.error(f"❌ Error stopping bot manager: {str(e)}")
            raise