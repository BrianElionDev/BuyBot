import logging
import asyncio
from typing import Dict
from .discord_signal_parser import DiscordSignalParser
from .trading_engine import TradingEngine
from .telegram_client import send_telegram_notification

logger = logging.getLogger(__name__)

class DiscordBot:
    def __init__(self, loop: asyncio.AbstractEventLoop = None):
        """Initialize the Discord bot with signal parsing and trading capabilities."""
        self.loop = loop or asyncio.get_event_loop()
        self.signal_parser = DiscordSignalParser()
        # Note: The trading engine here would be configured for CEX
        self.trading_engine = TradingEngine(loop=self.loop)

    async def process_signal(self, signal_data: Dict) -> tuple[bool, str]:
        """
        Process a Discord signal for CEX trading.
        """
        try:
            # Parse the signal
            signal = self.signal_parser.parse_signal(signal_data)
            if not signal:
                return False, "Failed to parse signal"

            # Validate the signal
            is_valid, error_message = self.signal_parser.validate_signal(signal)
            if not is_valid:
                logger.warning(f"Invalid signal: {error_message}")
                await send_telegram_notification(f"⚠️ Invalid Discord signal: {error_message}")
                return False, f"Invalid signal: {error_message}"

            # Process the CEX signal
            logger.info(f"Processing CEX signal: {signal}")
            success, reason = await self.trading_engine.process_signal(
                coin_symbol=signal['coin_symbol'],
                signal_price=signal['signal_price'],
                exchange_type='cex', # Hardcode to CEX for Discord
                order_type=signal.get('order_type', 'MARKET'),
                stop_loss=signal.get('stop_loss'),
                take_profits=signal.get('take_profits')
            )

            # Create a user-friendly message
            if success:
                message = (
                    f"✅ CEX Trade successful for {signal['coin_symbol']}!\n"
                    f"Details: {reason or 'No additional details.'}"
                )
            else:
                message = (
                    f"❌ CEX Trade failed for {signal['coin_symbol']}: {reason}"
                )

            # Send the result to Telegram
            await send_telegram_notification(message)

            return success, message

        except Exception as e:
            error_message = f"Error processing Discord signal: {str(e)}"
            logger.error(error_message, exc_info=True)
            await send_telegram_notification(f"🚨 CRITICAL ERROR in Discord Bot: {error_message}")
            return False, error_message

    async def stop(self):
        """Stop the Discord bot."""
        logger.info("Discord bot stopped")
        if self.trading_engine:
            await self.trading_engine.close()