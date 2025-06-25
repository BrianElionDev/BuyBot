import logging
import asyncio
from telethon import TelegramClient, events
from telethon.tl.types import PeerChannel
from config.settings import (
    TELEGRAM_API_ID, TELEGRAM_API_HASH, TELEGRAM_PHONE,
    TARGET_GROUP_ID, NOTIFICATION_GROUP_ID
)
from .signal_parser import SignalParser
from .trading_engine import TradingEngine

logger = logging.getLogger(__name__)

class TelegramBot:
    def __init__(self, loop: asyncio.AbstractEventLoop = None):
        """Initialize the Telegram bot."""
        self.loop = loop or asyncio.get_event_loop()
        self.client = TelegramClient('trading_bot_session', TELEGRAM_API_ID, TELEGRAM_API_HASH, loop=self.loop)
        self.signal_parser = SignalParser()
        self.trading_engine = TradingEngine(loop=self.loop)
        self.target_group_id = TARGET_GROUP_ID
        self.notification_group_id = NOTIFICATION_GROUP_ID if NOTIFICATION_GROUP_ID else None

        # Register the event handler
        self.client.on(events.NewMessage(chats=self.target_group_id))(self.handle_new_message)

    async def start(self):
        """Start the Telegram bot and begin monitoring for signals."""
        await self.client.start(phone=TELEGRAM_PHONE)
        logger.info("Telegram bot started successfully")
        logger.info(f"Monitoring group {self.target_group_id} for signals")
        await self.client.run_until_disconnected()

    async def handle_new_message(self, event):
        """Handle new messages in the target group."""
        message_text = event.message.text
        logger.info(f"Received message: {message_text}")

        try:
            signal = self.signal_parser.parse_signal(message_text)
            if not signal:
                return

            logger.info(f"Processing signal: {signal}")
            success, reason = await self.trading_engine.process_signal(
                coin_symbol=signal['buy_coin'],
                signal_price=signal['price'],
                sell_coin=signal['sell_coin']
            )

            await self._send_notification(reason)

        except Exception as e:
            logger.error(f"Error processing message: {str(e)}")
            await self._send_notification(f"⚠️ Error processing signal: {str(e)}")

    async def _send_notification(self, message: str):
        """Send a notification to the notification group."""
        if self.notification_group_id:
            try:
                await self.client.send_message(self.notification_group_id, message)
            except Exception as e:
                logger.error(f"Failed to send notification: {str(e)}")
        else:
            logger.info(f"Notification (no group set): {message}")

    async def stop(self):
        """Stop the Telegram bot."""
        await self.client.disconnect()
        logger.info("Telegram bot stopped")