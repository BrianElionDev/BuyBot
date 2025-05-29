import re
import logging
from telethon import TelegramClient, events
from typing import Optional, Tuple
from datetime import datetime
from src.services.price_service import PriceService

logger = logging.getLogger(__name__)

class TelegramMonitor:
    def __init__(self, trading_engine, config):
        self.trading_engine = trading_engine
        self.config = config
        self.price_service = PriceService()  # Initialize price service

        if config.TELEGRAM_API_HASH is None:
            raise ValueError("TELEGRAM_API_HASH must be set in the configuration and cannot be None")

        self.client = TelegramClient(
            'rubicon_session',
            config.TELEGRAM_API_ID,
            config.TELEGRAM_API_HASH
        )
        self.notification_group = None
        self._setup_handlers()

    async def _log_message(self, message: str, sender: str = "Unknown"):
        """Log a message with timestamp and sender information"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_message = f"[{timestamp}] {sender}: {message}"
        logger.info(log_message)

    async def _send_notification(self, transaction_type: str, sell_coin: str, buy_coin: str, amount: float, buy_coin_symbol: Optional[str] = None):
        """Send notification with dynamic pricing from CoinGecko"""
        if not self.notification_group:
            try:
                entity = await self.client.get_entity(self.config.NOTIFICATION_GROUP_ID)
                # Ensure entity is not a list
                if isinstance(entity, list):
                    if len(entity) > 0:
                        self.notification_group = entity[0]
                    else:
                        logger.error(f"No entity found for group ID {self.config.NOTIFICATION_GROUP_ID}")
                        return
                else:
                    self.notification_group = entity
            except Exception as e:
                logger.error(f"Failed to find notification group with ID {self.config.NOTIFICATION_GROUP_ID}: {e}")
                return

        # Fetch dynamic price from CoinGecko
        cost_message = "N/A"
        coin_to_price = buy_coin_symbol or buy_coin

        try:
            logger.info(f"🔍 Fetching price for {coin_to_price} from CoinGecko...")
            dynamic_price = await self.price_service.get_coin_price(coin_to_price)

            if dynamic_price:
                cost_value = dynamic_price * amount
                cost_message = f"${cost_value:.6f} (${dynamic_price:.6f} per {coin_to_price})"
                logger.info(f"✅ Got dynamic price: {coin_to_price} = ${dynamic_price:.6f}")
            else:
                cost_message = f"Price unavailable for {coin_to_price}"
                logger.warning(f"❌ Could not fetch price for {coin_to_price}")

        except Exception as e:
            logger.error(f"❌ Error fetching price for {coin_to_price}: {e}")
            cost_message = f"Error fetching price for {coin_to_price}"

        message = (
            f"Transaction Type: {transaction_type}\n"
            f"Sell: {sell_coin}\n"
            f"Buy: {buy_coin}\n"
            f"Amount: {amount}\n"
            f"Cost: {cost_message}"
        )

        try:
            await self.client.send_message(self.notification_group, message)
            logger.info(f"Notification sent to group ID {self.config.NOTIFICATION_GROUP_ID}")
        except Exception as e:
            logger.error(f"Failed to send notification: {e}")

    def _setup_handlers(self):
        @self.client.on(events.NewMessage())
        async def handler(event):
            try:
                chat = await event.get_chat()

                # Debug logging for ALL incoming messages
                chat_title = getattr(chat, 'title', 'Unknown Group')
                chat_id = getattr(chat, 'id', 'Unknown')
                logger.debug(f"🔍 DEBUG: Message received in '{chat_title}' [ID: {chat_id}] - Target: {self.config.TARGET_GROUP_ID}")

                # Filter for target group only using ID (handle both positive and negative IDs)
                if not (hasattr(chat, 'id') and abs(chat.id) == abs(self.config.TARGET_GROUP_ID)):
                    return

                # Get detailed chat information
                chat_username = getattr(chat, 'username', None)

                # Get detailed sender information
                sender = await event.get_sender()
                sender_username = getattr(sender, 'username', None)
                sender_first_name = getattr(sender, 'first_name', '')
                sender_last_name = getattr(sender, 'last_name', '')
                sender_full_name = f"{sender_first_name} {sender_last_name}".strip() or 'Unknown'
                sender_id = getattr(sender, 'id', 'Unknown')

                # Format sender display name
                if sender_username:
                    sender_display = f"@{sender_username} ({sender_full_name})"
                else:
                    sender_display = f"{sender_full_name}"

                message = event.raw_text

                # Enhanced logging for all messages
                logger.info("=" * 80)
                logger.info(f"📨 NEW MESSAGE IN TARGET GROUP")
                logger.info(f"🏠 Group: '{chat_title}' (@{chat_username if chat_username else 'no_username'}) [ID: {chat_id}]")
                logger.info(f"👤 From: {sender_display} [ID: {sender_id}]")
                logger.info(f"💬 Message: {message if message else '[Media/Non-text content]'}")
                logger.info("=" * 80)

                # Also use the old format for compatibility
                await self._log_message(message, sender_display)

                # Process "Trade detected" messages (with or without emoji)
                if message and (message.startswith('Trade detected') or message.startswith('👋 Trade detected')):
                    logger.info(f"🚨 TRADE SIGNAL DETECTED! 🚨")
                    logger.info(f"✅ Trade signal from {sender_display}")
                    logger.info(f"📄 Full message content:")
                    logger.info(f"{message}")
                    logger.info("-" * 60)

                    coin_symbol, price = self._parse_signal(message)

                    if coin_symbol and price:
                        logger.info(f"🎯 SUCCESSFUL PARSE: {coin_symbol} @ ${price}")
                        # Send notification with dynamic pricing before processing the signal
                        await self._send_notification(
                            transaction_type="Buy",
                            sell_coin="ETH",
                            buy_coin="USDC",
                            amount=10,  # You can adjust these values based on your needs
                            buy_coin_symbol=coin_symbol  # Pass the actual coin symbol for pricing
                        )
                        await self.trading_engine.process_signal(coin_symbol, price)
                    else:
                        logger.warning(f"❌ FAILED TO PARSE trade signal from {sender_display}")
                else:
                    if message:
                        logger.info(f"ℹ️ Regular message (not a trade signal) - ignoring")
                    else:
                        logger.info(f"📷 Non-text message (media/sticker/etc) - ignoring")

            except Exception as e:
                logger.error(f"❌ Error in message handler: {e}", exc_info=True)

    def _parse_signal(self, text: str) -> Tuple[Optional[str], Optional[float]]:
        """Extract coin symbol and price from trade detected message"""
        logger.info(f"Parsing message: {text[:200]}...")

        coin_symbol = None
        price = None

        # Extract coin symbol from format: "🟢 +531,835.742 Destra Network (DSync)"
        # Look for text in parentheses which should be the symbol
        symbol_patterns = [
            r'\(([A-Z0-9]{2,10})\)',  # Symbol in parentheses like (DSync)
            r'([A-Z]{3,6})\s*\)',     # Symbol before closing parenthesis
        ]

        for pattern in symbol_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                coin_symbol = match.group(1).upper()
                logger.info(f"Found symbol: {coin_symbol}")
                break

        # Extract price from format: "💰 Price per token $0.136 USD"
        price_patterns = [
            r'Price per token\s*\$?([\d,]+\.?\d*)\s*USD',
            r'💰.*\$?([\d,]+\.?\d*)\s*USD',
            r'\$?([\d,]+\.?\d*)\s*USD',
        ]

        for pattern in price_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                try:
                    price_str = match.group(1).replace(',', '')
                    price = float(price_str)
                    logger.info(f"Found price: ${price}")
                    break
                except (ValueError, IndexError):
                    continue

        if coin_symbol and price:
            logger.info(f"✅ Successfully parsed: {coin_symbol} @ ${price}")
            return coin_symbol, price
        else:
            logger.warning(f"❌ Failed to parse - Symbol: {coin_symbol}, Price: {price}")
            return None, None

    async def start(self):
        logger.info("🚀 Starting Enhanced Telegram Monitor...")
        if self.config.TELEGRAM_PHONE is None:
            logger.error("TELEGRAM_PHONE must be set in the configuration and cannot be None")
            return

        await self.client.start(phone=self.config.TELEGRAM_PHONE)

        # Get information about the current user
        me = await self.client.get_me()
        me_first_name = getattr(me, 'first_name', 'Unknown')
        me_last_name = getattr(me, 'last_name', '') or ''
        me_username = getattr(me, 'username', 'no_username')
        logger.info(f"👋 Logged in as: {me_first_name} {me_last_name} (@{me_username})")

        # Resolve target group and get detailed information
        try:
            group = await self.client.get_entity(self.config.TARGET_GROUP_ID)
            group_title = getattr(group, 'title', 'Unknown Group')
            group_username = getattr(group, 'username', None)
            group_id = getattr(group, 'id', 'Unknown')

            logger.info("=" * 80)
            logger.info(f"🎯 TARGET GROUP FOUND!")
            logger.info(f"📋 Group Name: '{group_title}'")
            logger.info(f"🔗 Username: @{group_username if group_username else 'no_username'}")
            logger.info(f"🆔 Group ID: {group_id}")
            logger.info("=" * 80)
            logger.info("👀 Now monitoring ALL messages in this group...")
            logger.info("🔍 Filtering for messages starting with 'Trade detected' or '👋 Trade detected'")
            logger.info("📝 All message activity will be logged. Press Ctrl+C to stop.")
            logger.info("=" * 80)
        except Exception as e:
            logger.error(f"❌ Failed to find group with ID {self.config.TARGET_GROUP_ID}: {e}")
            return

        await self.client.run_until_disconnected()

    async def stop(self):
        if self.client.is_connected():
            await self.client.disconnect()
            logger.info("Telegram client disconnected")