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
        """Initialize the Telegram bot with signal parsing and trading capabilities."""
        self.loop = loop or asyncio.get_event_loop()
        self.client = TelegramClient('trading_bot_session', TELEGRAM_API_ID, TELEGRAM_API_HASH, loop=self.loop)
        self.signal_parser = SignalParser()
        self.trading_engine = TradingEngine(loop=self.loop)
        self.target_group = PeerChannel(TARGET_GROUP_ID)
        self.notification_group = PeerChannel(NOTIFICATION_GROUP_ID) if NOTIFICATION_GROUP_ID else None

    async def start(self):
        """Start the Telegram bot and begin monitoring for signals."""
        await self.client.start(phone=TELEGRAM_PHONE)
        logger.info("Telegram bot started successfully")

        @self.client.on(events.NewMessage(chats=self.target_group))
        async def handle_new_message(event):
            """Handle new messages in the target group."""
            try:
                # Parse the signal
                signal = self.signal_parser.parse_signal(event.message.text)
                if not signal:
                    return  # Not a valid signal

                # Validate the signal
                is_valid, error_message = self.signal_parser.validate_signal(signal)
                if not is_valid:
                    logger.warning(f"Invalid signal: {error_message}")
                    await self._send_notification(f"⚠️ Invalid signal received: {error_message}")
                    return

                # Process the signal
                logger.info(f"Processing signal: {signal}")
                success, reason = await self.trading_engine.process_signal(
                    coin_symbol=signal['sell_coin'],
                    signal_price=signal['price'],
                    exchange_type=signal['exchange_type'],
                    sell_coin=signal['buy_coin'] if signal['exchange_type'] == 'dex' else None
                )

                # Send notification
                if success:
                    await self._send_notification(
                        f"✅ Trade executed successfully!\n"
                        f"Pair: {signal['trading_pair']}\n"
                        f"Amount: {signal['sell_amount']} {signal['sell_coin']}\n"
                        f"Price: ${signal['price']:.8f}\n"
                        f"Value: ${signal['value']:.2f}\n"
                        f"Exchange: {signal['exchange_type'].upper()}"
                    )
                else:
                    await self._send_notification(
                        f"❌ Trade failed: {reason}\n"
                        f"Pair: {signal['trading_pair']}\n"
                        f"Amount: {signal['sell_amount']} {signal['sell_coin']}\n"
                        f"Price: ${signal['price']:.8f}\n"
                        f"Value: ${signal['value']:.2f}\n"
                        f"Exchange: {signal['exchange_type'].upper()}"
                    )

            except Exception as e:
                logger.error(f"Error processing message: {str(e)}")
                await self._send_notification(f"⚠️ Error processing signal: {str(e)}")

        # Start monitoring
        logger.info(f"Monitoring group {TARGET_GROUP_ID} for signals")
        await self.client.run_until_disconnected()

    async def _send_notification(self, message: str):
        """Send a notification to the notification group."""
        if self.notification_group:
            try:
                await self.client.send_message(self.notification_group, message)
            except Exception as e:
                logger.error(f"Failed to send notification: {str(e)}")
        else:
            logger.info(f"Notification (no group set): {message}")

    async def stop(self):
        """Stop the Telegram bot."""
        await self.client.disconnect()
        logger.info("Telegram bot stopped")