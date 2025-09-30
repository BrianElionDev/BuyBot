import logging
from typing import Optional
from telegram import Bot
from telegram.error import TelegramError
from config import settings
from .notification_models import NotificationConfig

logger = logging.getLogger(__name__)


class TelegramService:
    """Core Telegram service for direct API interactions"""

    # Shared singleton bot to avoid leaking aiohttp sessions
    _shared_bot: Optional[Bot] = None

    def __init__(self, config: Optional[NotificationConfig] = None):
        """Initialize the Telegram service"""
        if config:
            self.config = config
        else:
            self.config = NotificationConfig(
                bot_token=settings.TELEGRAM_BOT_TOKEN,
                chat_id=settings.TELEGRAM_NOTIFICATION_CHAT_ID
            )

        self._validate_config()
        self.bot = self._initialize_bot()

    def _validate_config(self) -> None:
        """Validate the notification configuration"""
        if not self.config.bot_token or self.config.bot_token == "YOUR_TELEGRAM_BOT_TOKEN":
            logger.warning("Telegram bot token not configured - notifications will be disabled")
            self.config.enabled = False

        if not self.config.chat_id:
            logger.warning("Telegram chat ID not configured - notifications will be disabled")
            self.config.enabled = False

    def _initialize_bot(self) -> Optional[Bot]:
        """Initialize the Telegram bot"""
        if not self.config.enabled:
            return None

        try:
            if TelegramService._shared_bot is None:
                TelegramService._shared_bot = Bot(token=self.config.bot_token)
            return TelegramService._shared_bot
        except Exception as e:
            logger.error(f"Failed to initialize Telegram bot: {e}")
            self.config.enabled = False
            return None

    async def send_message(self, message: str, parse_mode: Optional[str] = None) -> bool:
        """
        Send a message to the configured Telegram chat

        Args:
            message: The message to send
            parse_mode: Message parse mode (HTML, Markdown, etc.)

        Returns:
            True if message sent successfully, False otherwise
        """
        if not self.config.enabled or not self.bot:
            logger.info(f"Telegram notification (disabled): {message[:100]}...")
            return False

        try:
            await self.bot.send_message(
                chat_id=self.config.chat_id,
                text=message,
                parse_mode=parse_mode or self.config.parse_mode
            )
            logger.info("✅ Telegram notification sent successfully")
            return True
        except TelegramError as e:
            logger.error(f"❌ Failed to send Telegram notification: {e}")
            return False
        except Exception as e:
            logger.error(f"❌ Unexpected error sending Telegram notification: {e}")
            return False

    def is_enabled(self) -> bool:
        """Check if the Telegram service is enabled"""
        return self.config.enabled

    def get_config(self) -> NotificationConfig:
        """Get the current notification configuration"""
        return self.config

    def update_config(self, config: NotificationConfig) -> None:
        """Update the notification configuration"""
        self.config = config
        self._validate_config()
        self.bot = self._initialize_bot()

    @classmethod
    async def close_shared(cls) -> None:
        """Close the shared bot session to avoid unclosed aiohttp sessions."""
        try:
            if cls._shared_bot and hasattr(cls._shared_bot, 'session') and cls._shared_bot.session:
                await cls._shared_bot.session.close()
        except Exception as e:
            logger.warning(f"Failed to close Telegram shared bot session: {e}")
        finally:
            cls._shared_bot = None
