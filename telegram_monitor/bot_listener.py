# crypto-signal-bot/telegram_monitor/bot_listener.py

from telethon import TelegramClient, events
from telethon.tl.types import User, Channel
from telethon.errors.rpcerrorlist import FloodWaitError, AuthKeyUnregisteredError, SessionPasswordNeededError
import re
import logging
import asyncio
from typing import TYPE_CHECKING, Optional, Tuple

from config.settings import settings

# Type checking for dependency injection to avoid circular imports
if TYPE_CHECKING:
    from trading.trading_engine import TradingEngine

logger = logging.getLogger(__name__)

class TelegramSignalMonitor:
    """
    Monitors a specific Telegram group for messages from a designated bot,
    parses trading signals, and passes them to the trading engine.
    """

    def __init__(self, trading_engine: 'TradingEngine'):
        """
        Initializes the TelegramSignalMonitor.

        Args:
            trading_engine (TradingEngine): An instance of the TradingEngine to process signals.
        """
        self.trading_engine = trading_engine
        # Telethon client session name. Using a fixed name for simplicity.
        # Ensure this session file is not accessed by other Telethon instances.
        self.client = TelegramClient(
            'telegram_bot_monitor_session',
            settings.TELEGRAM_API_ID,
            settings.TELEGRAM_API_HASH
        )
        self._setup_handlers()
        self.target_group_entity = None # To store resolved group entity
        self.target_bot_entity = None # To store resolved bot entity

    def _setup_handlers(self):
        """
        Sets up the Telethon event handler for new messages.
        The handler will filter messages by chat and sender.
        """
        @self.client.on(events.NewMessage()) # Listen to all new messages initially
        async def handler(event):
            # Ensure chat and sender entities are resolved before filtering
            chat = await event.get_chat()
            sender = await event.get_sender()

            # Check if the message is from the target bot and in the target group
            is_from_target_bot = False
            if isinstance(sender, User) and sender.bot and sender.username:
                if sender.username.lower() == settings.TARGET_BOT.lower():
                    is_from_target_bot = True
                else:
                    logger.debug(f"Message from non-target bot: {sender.username}")
            elif isinstance(sender, User): # Not a bot, or bot without username
                logger.debug(f"Message from user: {sender.username or sender.id}")
            else: # Channel, etc.
                logger.debug(f"Message from non-user sender type: {type(sender)}")


            is_in_target_group = False
            if chat:
                # Handle both username and ID for target group
                if isinstance(chat, Channel) and chat.username and chat.username.lower() == settings.TARGET_GROUP.replace('@', '').lower():
                    is_in_target_group = True
                elif str(chat.id) == settings.TARGET_GROUP: # If TARGET_GROUP is an ID string
                    is_in_target_group = True
                elif isinstance(chat, Channel) and chat.id == self.target_group_entity.id if self.target_group_entity else False:
                     is_in_target_group = True
                else:
                    logger.debug(f"Message in non-target chat: {chat.title or chat.id}")
            else:
                logger.debug("Message has no associated chat entity.")


            if is_from_target_bot and is_in_target_group:
                logger.info(f"Detected message from target bot '{settings.TARGET_BOT}' in target group '{settings.TARGET_GROUP}'.")
                await self._process_signal(event.raw_text)
            elif is_from_target_bot:
                logger.debug(f"Message from target bot '{settings.TARGET_BOT}' but not in target group.")
            elif is_in_target_group:
                logger.debug(f"Message in target group '{settings.TARGET_GROUP}' but not from target bot.")


    async def _resolve_target_entities(self):
        """
        Resolves the Telegram entities (group and bot) to ensure accurate filtering.
        This is important because Telethon's event objects might not always contain full entity info.
        """
        logger.info(f"Resolving target group '{settings.TARGET_GROUP}' and bot '{settings.TARGET_BOT}'...")
        try:
            # Resolve target group
            self.target_group_entity = await self.client.get_entity(settings.TARGET_GROUP)
            logger.info(f"Resolved target group: {self.target_group_entity.title} (ID: {self.target_group_entity.id})")

            # Resolve target bot
            self.target_bot_entity = await self.client.get_entity(settings.TARGET_BOT)
            logger.info(f"Resolved target bot: {self.target_bot_entity.username} (ID: {self.target_bot_entity.id})")

        except ValueError as e:
            logger.critical(f"Could not resolve Telegram entity. Please check TARGET_GROUP or TARGET_BOT in settings. Error: {e}")
            # Exit or raise a more specific error if entities cannot be resolved
            raise

        except Exception as e:
            logger.critical(f"An unexpected error occurred while resolving Telegram entities: {e}")
            raise


    async def _process_signal(self, message_text: str):
        """
        Extracts coin symbol and price from the signal message using regex patterns.
        Then passes the extracted data to the TradingEngine.

        Args:
            message_text (str): The raw text content of the Telegram message.
        """
        coin_symbol, signal_price = self._parse_signal(message_text)

        if coin_symbol and signal_price is not None:
            logger.info(f"Parsed signal: BUY {coin_symbol} @ {signal_price}")
            # Pass to trading engine for processing
            await self.trading_engine.process_signal(coin_symbol, signal_price)
        else:
            logger.warning(f"Could not parse valid signal from message: '{message_text}'")

    def _parse_signal(self, text: str) -> Tuple[Optional[str], Optional[float]]:
        """
        Parses the signal message using a list of predefined regex patterns.
        Returns the extracted coin symbol and price, or (None, None) if no match.

        Args:
            text (str): The message text to parse.

        Returns:
            tuple[Optional[str], Optional[float]]: (coin_symbol, price) or (None, None).
        """
        # Patterns to match various signal formats.
        # Group 1: Coin Symbol (e.g., BTC, ETH)
        # Group 2: Price (numeric, possibly with decimal)
        patterns = [
            r'BUY\s+([A-Z]+)\s+@\s+\$?\s*(\d+\.?\d*)', # e.g., "BUY BTC @ $25000"
            r'ALERT:\s+([A-Z]+)\s+breakout\s+at\s+\$?\s*(\d+\.?\d*)', # e.g., "ALERT: ETH breakout at $1800"
            r'Purchase\s+signal:\s+([A-Z]+)\s+current\s+price\s+\$?\s*(\d+\.?\d*)', # e.g., "Purchase signal: ADA current price $0.30"
            r'New\s+signal:\s+([A-Z]+)\s+-\s+(\d+\.?\d*)', # e.g., "New signal: XRP - 0.55"
            r'#([A-Z]+)\s+target\s+\$?\s*(\d+\.?\d*)', # e.g., "#LTC target $75" (might indicate a buy)
            r'Coin:\s*([A-Z]+),\s*Price:\s*(\d+\.?\d*)' # e.g., "Coin: SOL, Price: 150.23"
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                coin_symbol = match.group(1).upper()
                try:
                    price = float(match.group(2))
                    logger.debug(f"Matched pattern '{pattern}' for '{text}'. Extracted: {coin_symbol}, {price}")
                    return coin_symbol, price
                except ValueError:
                    logger.warning(f"Could not convert extracted price '{match.group(2)}' to float for pattern '{pattern}'.")
                    continue # Try next pattern
        return None, None

    async def start(self):
        """
        Connects to Telegram and starts monitoring for messages.
        Handles authentication and keeps the client running until disconnected.
        """
        logger.info("Starting Telegram monitor...")
        try:
            # Connect to Telegram. If session file doesn't exist, it will prompt for phone/code.
            await self.client.start(phone=settings.TELEGRAM_PHONE)
            logger.info("Successfully connected to Telegram!")

            # Resolve entities after successful connection
            await self._resolve_target_entities()

            logger.info(f"Monitoring messages from bot '{settings.TARGET_BOT}' in group '{settings.TARGET_GROUP}'...")
            await self.client.run_until_disconnected()
        except FloodWaitError as e:
            logger.error(f"Telegram FloodWaitError: Too many requests. Waiting for {e.seconds} seconds.")
            await asyncio.sleep(e.seconds)
            # Optionally, try to restart or re-connect after waiting
            await self.start()
        except AuthKeyUnregisteredError:
            logger.critical("Telegram AuthKeyUnregisteredError: Your API ID/Hash might be invalid or session expired. Please re-authenticate.")
        except SessionPasswordNeededError:
            logger.critical("Telegram SessionPasswordNeededError: Two-factor authentication is enabled. Please run the script interactively once to enter the password.")
        except Exception as e:
            logger.critical(f"An unexpected error occurred during Telegram monitoring: {e}", exc_info=True)
        finally:
            if self.client.is_connected():
                logger.info("Disconnecting Telegram client.")
                await self.client.disconnect()