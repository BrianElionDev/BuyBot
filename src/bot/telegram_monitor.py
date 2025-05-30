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
            logger.info(f"[PRICE] Fetching price for {coin_to_price} from CoinGecko...")
            dynamic_price = await self.price_service.get_coin_price(coin_to_price)

            if dynamic_price:
                cost_value = dynamic_price * amount
                cost_message = f"${cost_value:.6f} (${dynamic_price:.6f} per {coin_to_price})"
                logger.info(f"[SUCCESS] Got dynamic price: {coin_to_price} = ${dynamic_price:.6f}")
            else:
                cost_message = f"Price unavailable for {coin_to_price}"
                logger.warning(f"[WARNING] Could not fetch price for {coin_to_price}")

        except Exception as e:
            logger.error(f"[ERROR] Error fetching price for {coin_to_price}: {e}")
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
                logger.debug(f"[DEBUG] Message received in '{chat_title}' [ID: {chat_id}] - Target: {self.config.TARGET_GROUP_ID}")

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
                logger.info(f"[MESSAGE] NEW MESSAGE IN TARGET GROUP")
                logger.info(f"[GROUP] Group: '{chat_title}' (@{chat_username if chat_username else 'no_username'}) [ID: {chat_id}]")
                logger.info(f"[SENDER] From: {sender_display} [ID: {sender_id}]")
                logger.info(f"[CONTENT] Message: {message if message else '[Media/Non-text content]'}")
                
                # Debug: Show message analysis
                if message:
                    logger.info(f"[DEBUG] Message starts with: '{message[:30]}...'")
                    logger.info(f"[DEBUG] Message lower starts with: '{message.lower()[:30]}...'")
                    logger.info(f"[DEBUG] Checking for trade signal patterns...")
                
                logger.info("=" * 80)

                # Also use the old format for compatibility
                await self._log_message(message, sender_display)

                # Process "Trade detected" messages (with or without emoji) - case insensitive
                message_lower = message.lower() if message else ""
                is_trade_signal = (
                    'trade detected' in message_lower or 
                    '[trade] trade detected' in message_lower or
                    # Handle variations with emoji, spaces, and punctuation
                    ('👋' in message and 'trade detected' in message_lower) or
                    ('👋' in message and 'trade signal' in message_lower) or
                    # Handle text format variations
                    '[trade]' in message_lower or
                    # Direct pattern matches for common formats
                    message_lower.strip().startswith('trade detected') or
                    '👋  trade detected' in message_lower or  # Double space
                    '👋 trade detected' in message_lower       # Single space
                )
                
                if message and is_trade_signal:
                    logger.info(f"[SIGNAL] TRADE SIGNAL DETECTED!")
                    logger.info(f"[SUCCESS] Trade signal from {sender_display}")
                    logger.info(f"[CONTENT] Full message content:")
                    logger.info(f"{message}")
                    logger.info("-" * 60)

                    coin_symbol, price = self._parse_signal(message)

                    if coin_symbol and price:
                        logger.info(f"[SUCCESS] SUCCESSFUL PARSE: {coin_symbol} @ ${price}")
                        # Send notification with dynamic pricing before processing the signal
                        try:
                            await self._send_notification(
                                transaction_type="Buy",
                                sell_coin="ETH",
                                buy_coin="USDC",
                                amount=10,  # You can adjust these values based on your needs
                                buy_coin_symbol=coin_symbol  # Pass the actual coin symbol for pricing
                            )
                            await self.trading_engine.process_signal(coin_symbol, price)
                        except Exception as e:
                            logger.error(f"[ERROR] Failed to process signal: {e}")
                    else:
                        logger.warning(f"[WARNING] FAILED TO PARSE trade signal from {sender_display}")
                else:
                    if message:
                        logger.info(f"[INFO] Regular message (not a trade signal) - ignoring")
                        logger.info(f"[DEBUG] Message content: '{message[:100]}...'")
                        
                        # Show which patterns were tested
                        message_lower = message.lower() if message else ""
                        patterns_tested = [
                            f"starts with 'trade detected': {message_lower.startswith('trade detected')}",
                            f"starts with '[trade] trade detected': {message_lower.startswith('[trade] trade detected')}",
                            f"starts with '👋 trade detected': {message_lower.startswith('👋 trade detected')}",
                            f"starts with '👋  trade detected': {message_lower.startswith('👋  trade detected')}"
                        ]
                        for pattern in patterns_tested:
                            logger.debug(f"[DEBUG] {pattern}")
                    else:
                        logger.info(f"[MEDIA] Non-text message (media/sticker/etc) - ignoring")

            except Exception as e:
                logger.error(f"[ERROR] Error in message handler: {e}", exc_info=True)

    def _parse_signal(self, text: str) -> Tuple[Optional[str], Optional[float]]:
        """Extract coin symbol and price from trade detected message"""
        logger.info(f"Parsing message: {text[:200]}...")

        coin_symbol = None
        price = None

        # Extract coin symbol from format: "[GREEN] +531,835.742 Destra Network (DSync)"
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

        # Extract price from format: "💰 Price per token $0.136 USD" or "[PRICE] Price per token $0.136 USD"
        price_patterns = [
            r'Price per token\s*\$?([\d,]+\.?\d*)\s*USD',  # Generic price pattern
            r'💰.*\$?([\d,]+\.?\d*)\s*USD',                # Original emoji pattern
            r'\[PRICE\].*\$?([\d,]+\.?\d*)\s*USD',         # Windows-compatible pattern
            r'\$?([\d,]+\.?\d*)\s*USD',                    # Fallback pattern
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
            logger.info(f"[SUCCESS] Successfully parsed: {coin_symbol} @ ${price}")
            return coin_symbol, price
        else:
            logger.warning(f"[WARNING] Failed to parse - Symbol: {coin_symbol}, Price: {price}")
            return None, None

    def start(self):
        """Start the Telegram monitor - synchronous method"""
        logger.info("[STARTUP] Starting Enhanced Telegram Monitor...")
        if self.config.TELEGRAM_PHONE is None:
            logger.error("TELEGRAM_PHONE must be set in the configuration and cannot be None")
            return

        try:
            # Start the client synchronously
            self.client.start(phone=self.config.TELEGRAM_PHONE)
            
            logger.info("[LOGIN] Successfully connected to Telegram")

            # Log the monitoring setup
            logger.info("=" * 80)
            logger.info(f"[TARGET] Monitoring group ID: {self.config.TARGET_GROUP_ID}")
            logger.info("=" * 80)
            logger.info("[MONITOR] Now monitoring ALL messages in the target group...")
            logger.info("[DEBUG] Filtering for messages containing:")
            logger.info("[DEBUG]   - 'trade detected' (case insensitive)")
            logger.info("[DEBUG]   - '👋 trade detected' (with emoji)")
            logger.info("[DEBUG]   - '[trade]' patterns")
            logger.info("[LOG] All message activity will be logged. Press Ctrl+C to stop.")
            logger.info("=" * 80)

            # Run until disconnected
            self.client.run_until_disconnected()
            
        except Exception as e:
            logger.error(f"[ERROR] Failed to start Telegram client: {e}")
            raise

    def stop(self):
        """Stop the Telegram monitor - synchronous method"""
        if self.client.is_connected():
            self.client.disconnect()
            logger.info("Telegram client disconnected")