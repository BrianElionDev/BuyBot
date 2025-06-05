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
        self.price_service = PriceService()

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

    async def _send_notification(self, sell_coin: str, buy_coin: str, amount: float, signal_price: Optional[float] = None,
                              is_valid: bool = True, rejection_reason: Optional[str] = None):
        """
        Send notification with enhanced format for both valid and invalid transactions

        Args:
            sell_coin: The coin being sold
            buy_coin: The coin being bought
            amount: Transaction amount
            signal_price: Price from the signal
            is_valid: Whether the transaction is valid and will go through
            rejection_reason: Reason for rejection if transaction is invalid
        """
        if not self.notification_group:
            try:
                entity = await self.client.get_entity(self.config.NOTIFICATION_GROUP_ID)
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

        # Fetch price from CoinGecko for the buy coin
        coingecko_price_value = None
        coingecko_price = "Price unavailable"
        try:
            logger.info(f"[PRICE] Fetching CoinGecko price for {buy_coin}...")
            coingecko_price_value = await self.price_service.get_coin_price(buy_coin)
            if coingecko_price_value:
                coingecko_price = f"${coingecko_price_value:.6f}"
                logger.info(f"[SUCCESS] CoinGecko price for {buy_coin}: {coingecko_price}")
            else:
                logger.warning(f"[WARNING] Could not fetch CoinGecko price for {buy_coin}")
        except Exception as e:
            logger.error(f"[ERROR] Error fetching CoinGecko price for {buy_coin}: {e}")

        # Slippage information
        slippage_info = "Slippage: Not calculated"
        slippage_threshold = self.config.SLIPPAGE_PERCENTAGE
        price_difference_percent = None

        # Slippage protection check
        if signal_price and coingecko_price_value:
            price_difference_percent = abs(coingecko_price_value - signal_price) / signal_price * 100

            logger.info(f"[SLIPPAGE] Signal price: ${signal_price:.6f}")
            logger.info(f"[SLIPPAGE] Current market price: ${coingecko_price_value:.6f}")
            logger.info(f"[SLIPPAGE] Price difference: {price_difference_percent:.2f}%")
            logger.info(f"[SLIPPAGE] Slippage threshold: {slippage_threshold:.1f}%")

            slippage_info = f"Slippage: {price_difference_percent:.2f}% (Threshold: {slippage_threshold:.1f}%)"

            # Update rejection reason if slippage is too high
            if price_difference_percent > slippage_threshold:
                is_valid = False
                rejection_reason = f"Price slippage too high ({price_difference_percent:.2f}% > {slippage_threshold:.1f}%)"
                logger.warning(f"❌ SLIPPAGE PROTECTION: {rejection_reason}")
                logger.warning(f"❌ TRANSACTION BLOCKED: Signal ${signal_price:.6f} vs Market ${coingecko_price_value:.6f}")
            else:
                logger.info(f"✅ SLIPPAGE CHECK PASSED: {price_difference_percent:.2f}% <= {slippage_threshold:.1f}%")
        elif signal_price:
            slippage_info = "Slippage: Could not calculate - CoinGecko price unavailable"
            logger.warning(f"[WARNING] Cannot perform slippage check - CoinGecko price unavailable")
        else:
            slippage_info = "Slippage: Could not calculate - Signal price not provided"
            logger.warning(f"[WARNING] Cannot perform slippage check - signal price not provided")

        # Determine transaction type and validation status
        # We're buying the buy_coin and selling the sell_coin
        transaction_type = "Buy"

        # Status indicators for validity
        if is_valid:
            status_emoji = "✅"
            status_indicator = "VALID"
        else:
            status_emoji = "❌"
            status_indicator = "INVALID"

        # Build notification message with improved formatting
        if is_valid:
            message = (
                f"🚨 TRADE SIGNAL DETECTED!\n\n"
                f"Transaction Type: {transaction_type} {buy_coin}\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"🔄 Pair: {sell_coin}/{buy_coin}\n"
                f"💲 Signal Price: ${signal_price if signal_price else 'N/A'}\n"
                f"📊 CoinGecko Price: {coingecko_price}\n"
                f"📈 {slippage_info}\n"
                f"💰 Amount: ${amount:.2f}\n"
                f"⏱️ Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            )
        else:
            message = (
                f"🚨 TRADE SIGNAL DETECTED!\n\n"
                f"Transaction Type: {transaction_type} {buy_coin}\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"🔄 Pair: {sell_coin}/{buy_coin}\n"
                f"💲 Signal Price: ${signal_price if signal_price else 'N/A'}\n"
                f"📊 CoinGecko Price: {coingecko_price}\n"
                f"📈 {slippage_info}\n"
                f"💰 Amount: ${amount:.2f}\n"
                f"⏱️ Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                f"❌ Reason: {rejection_reason if rejection_reason else 'Unknown error'}"
            )

        # Send notification regardless of transaction validity
        try:
            await self.client.send_message(self.notification_group, message)
            logger.info(f"✅ Notification sent successfully to group ID {self.config.NOTIFICATION_GROUP_ID}")
        except Exception as e:
            logger.error(f"❌ Failed to send notification: {e}")

    async def _send_parsing_failure_notification(self, message_text: str, failure_reason: str):
        """
        Send notification when signal parsing fails

        Args:
            message_text: The original message text
            failure_reason: The reason why parsing failed
        """
        if not self.notification_group:
            try:
                entity = await self.client.get_entity(self.config.NOTIFICATION_GROUP_ID)
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

        # Build error notification message
        notification = (
            f"🚨 TRADE SIGNAL DETECTED!\n\n"
            f"Transaction Type: Unknown\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"⚠️ SIGNAL PARSING FAILED\n"
            f"Error: {failure_reason}\n"
            f"Original Message:\n"
            f"`{message_text[:200]}...`\n\n"
            f"⏱️ Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )

        # Send notification
        try:
            await self.client.send_message(self.notification_group, notification)
            logger.info(f"✅ Parsing failure notification sent to group ID {self.config.NOTIFICATION_GROUP_ID}")
        except Exception as e:
            logger.error(f"❌ Failed to send parsing failure notification: {e}")

    def _setup_handlers(self):
        @self.client.on(events.NewMessage())
        async def handler(event):
            try:
                chat = await event.get_chat()

                # Debug logging for ALL incoming messages
                chat_title = getattr(chat, 'title', 'Unknown Group')
                chat_id = getattr(chat, 'id', 'Unknown')
                logger.info(f"[DEBUG] Message received in '{chat_title}' [ID: {chat_id}] - Target: {self.config.TARGET_GROUP_ID}")

                # Enhanced group ID matching - handle multiple formats
                target_id = self.config.TARGET_GROUP_ID
                current_id = getattr(chat, 'id', None)

                # TEMPORARY: Extra debug logging
                logger.info(f"[DEBUG] Raw comparison: current_id={current_id}, target_id={target_id}")
                if str(target_id).startswith('-100'):
                    target_without_prefix = int(str(target_id)[4:])
                    logger.info(f"[DEBUG] Target without -100 prefix: {target_without_prefix}")
                    logger.info(f"[DEBUG] Testing: {current_id} == {target_without_prefix}")


                # Check if this is our target group (handle different ID formats)
                is_target_group = False
                if current_id is not None:
                    # Direct match
                    if current_id == target_id:
                        is_target_group = True
                        logger.debug(f"[MATCH] Direct ID match: {current_id} == {target_id}")
                    # Handle supergroup format: target is -100XXXXXXXXX, current is XXXXXXXXX
                    elif str(target_id).startswith('-100'):
                        # Extract the group ID without -100 prefix
                        target_without_prefix = int(str(target_id)[4:])  # Remove -100 prefix
                        if current_id == target_without_prefix:
                            is_target_group = True
                            logger.debug(f"[MATCH] Supergroup match: {current_id} matches {target_id} (without -100 prefix)")
                    # Handle reverse case: current is -100XXXXXXXXX, target is XXXXXXXXX
                    elif str(current_id).startswith('-100'):
                        current_without_prefix = int(str(current_id)[4:])  # Remove -100 prefix
                        if current_without_prefix == abs(target_id):
                            is_target_group = True
                            logger.debug(f"[MATCH] Reverse supergroup match: {current_id} matches {target_id}")
                    # Absolute value match as fallback
                    elif abs(current_id) == abs(target_id):
                        is_target_group = True
                        logger.debug(f"[MATCH] Absolute value match: |{current_id}| == |{target_id}|")
                    else:
                        logger.debug(f"[NO MATCH] {current_id} != {target_id} (Group: {chat_title})")
                        # Show what we tried to match
                        if str(target_id).startswith('-100'):
                            target_without_prefix = int(str(target_id)[4:])
                            logger.debug(f"[DEBUG] Tried supergroup match: {current_id} vs {target_without_prefix} (from {target_id})")
                else:
                    logger.debug(f"[NO MATCH] current_id is None (Group: {chat_title})")

                if not is_target_group:
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
                    '👋  trade detected' in message_lower or
                    '👋 trade detected' in message_lower
                )

                if message and is_trade_signal:
                    logger.info(f"[SIGNAL] TRADE SIGNAL DETECTED!")
                    logger.info(f"[SUCCESS] Trade signal from {sender_display}")
                    logger.info(f"[CONTENT] Full message content:")
                    logger.info(f"{message}")
                    logger.info("-" * 60)

                    sell_coin, buy_coin, price, is_valid = self._parse_enhanced_signal(message)

                    # Always process the signal regardless of validity
                    rejection_reason = None

                    # Handle case when we have all required elements
                    if sell_coin and buy_coin and price:
                        if is_valid:
                            logger.info(f"[SUCCESS] VALID TRADE: {sell_coin}/{buy_coin} @ ${price}")

                            # Determine exchange type based on configuration
                            exchange_type = getattr(self.config, "PREFERRED_EXCHANGE_TYPE", "cex").lower()
                            logger.info(f"[TRADE] Using {exchange_type.upper()} for trading")

                            try:
                                if exchange_type == "dex":
                                    # For DEX, we need to pass the sell_coin as well
                                    success = await self.trading_engine.process_signal(
                                        coin_symbol=buy_coin,
                                        signal_price=price,
                                        exchange_type="dex",
                                        sell_coin=sell_coin
                                    )
                                else:
                                    # For CEX, we use the original YoBit logic
                                    success = await self.trading_engine.process_signal(
                                        coin_symbol=buy_coin,
                                        signal_price=price,
                                        exchange_type="cex"
                                    )

                                if success:
                                    logger.info(f"[SUCCESS] Trade execution successful for {buy_coin}")
                                else:
                                    logger.warning(f"[WARNING] Trade execution failed for {buy_coin}")
                                    is_valid = False
                                    rejection_reason = "Trading engine failed to execute the transaction"
                            except Exception as e:
                                logger.error(f"[ERROR] Failed to process signal: {e}")
                                is_valid = False
                                rejection_reason = f"Error processing signal: {str(e)}"
                        else:
                            # Transaction is invalid - specify reason
                            rejection_reason = f"Invalid base currency (selling {sell_coin}). Only ETH/USDC allowed."
                            logger.warning(f"[IGNORED] {rejection_reason}")

                        # Send notification for both valid and invalid transactions
                        try:
                            await self._send_notification(
                                sell_coin=sell_coin,
                                buy_coin=buy_coin,
                                amount=10.0,
                                signal_price=price,
                                is_valid=is_valid,
                                rejection_reason=rejection_reason
                            )
                        except Exception as e:
                            logger.error(f"[ERROR] Failed to send notification: {e}")
                    else:
                        # Failed to parse the signal
                        failure_reason = "Could not parse trade signal"
                        if not sell_coin:
                            failure_reason = "Could not identify sell coin"
                        elif not buy_coin:
                            failure_reason = "Could not identify buy coin"
                        elif not price:
                            failure_reason = "Could not identify price"

                        logger.warning(f"[WARNING] {failure_reason} from {sender_display}")

                        # Send notification about parsing failure
                        try:
                            await self._send_parsing_failure_notification(
                                message_text=message,
                                failure_reason=failure_reason
                            )
                        except Exception as e:
                            logger.error(f"[ERROR] Failed to send parsing failure notification: {e}")

                        # Send parsing failure notification
                        try:
                            await self._send_parsing_failure_notification(
                                message_text=message,
                                failure_reason=failure_reason
                            )
                        except Exception as e:
                            logger.error(f"[ERROR] Failed to send parsing failure notification: {e}")
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

    def _parse_enhanced_signal(self, text: str) -> Tuple[Optional[str], Optional[str], Optional[float], bool]:
        """
        Enhanced parsing to extract sell_coin, buy_coin, price, and validate ETH/USDC requirement
        Returns: (sell_coin, buy_coin, price, is_valid_transaction)
        """
        logger.info(f"Enhanced parsing: {text[:200]}...")

        sell_coin = None
        buy_coin = None
        price = None
        is_valid_transaction = False

        # Extract coins from green (buy) and red (sell) lines
        # Pattern 1: 🟢 +2,336.576 USD Coin (USDC) / 🔴 - 104,347.826 DAR Open Network (D)
        green_patterns = [
            # Standard format with token name and symbol
            r'🟢.*?\+.*?([A-Za-z0-9\s]+)\s*\(([A-Z0-9]{1,10})\)',
            # With etherscan link
            r'🟢.*?\+.*?([A-Za-z0-9\s]+)\s*\(([A-Z0-9]{1,10})\s*\(https://.*?\)\)',
            # Format with just the symbol and no name
            r'🟢.*?\+.*?\(([A-Z0-9]{1,10})\)',
            # Direct extract for SHIB with or without INU
            r'🟢.*?\+.*?(SHIBA INU|SHIBA)\s*\(([A-Z0-9]{1,10})\)',
            # More flexible pattern that works better with special token names
            r'🟢.*?\+\s*[\d,.]+\s*([A-Za-z0-9\s]+)\s*\(([A-Z0-9]{1,10})\)',
        ]

        red_patterns = [
            # Standard format with token name and symbol
            r'🔴.*?-.*?([A-Za-z0-9\s]+)\s*\(([A-Z0-9]{1,10})\)',
            # With etherscan link
            r'🔴.*?-.*?([A-Za-z0-9\s]+)\s*\(([A-Z0-9]{1,10})\s*\(https://.*?\)\)',
            # Format with just the symbol and no name
            r'🔴.*?-.*?\(([A-Z0-9]{1,10})\)',
            # Direct extract for SHIB with or without INU
            r'🔴.*?-.*?(SHIBA INU|SHIBA)\s*\(([A-Z0-9]{1,10})\)',
            # More flexible pattern that works better with special token names
            r'🔴.*?-\s*[\d,.]+\s*([A-Za-z0-9\s]+)\s*\(([A-Z0-9]{1,10})\)',
        ]

        # Find buy coin (green line)
        for i, pattern in enumerate(green_patterns):
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                # Different patterns may have the group in different positions
                if len(match.groups()) == 1:
                    buy_coin = match.group(1).upper()
                else:
                    buy_coin = match.group(2).upper()
                logger.info(f"Found buy coin (green): {buy_coin} using pattern {i+1}")
                break

        if not buy_coin:
            logger.warning(f"⚠️ Failed to parse buy coin. Check regex patterns against this green line")
            # Extract green line for debugging
            green_line_match = re.search(r'(🟢.*)', text)
            if green_line_match:
                green_line = green_line_match.group(1)
                logger.warning(f"Green line content: {green_line}")
                # Try direct SHIB check
                if "SHIB" in green_line.upper():
                    logger.info("SHIB token detected in green line, using special handling")
                    buy_coin = "SHIB"

        # Find sell coin (red line)
        for i, pattern in enumerate(red_patterns):
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                # Different patterns may have the group in different positions
                if len(match.groups()) == 1:
                    sell_coin = match.group(1).upper()
                else:
                    sell_coin = match.group(2).upper()
                logger.info(f"Found sell coin (red): {sell_coin} using pattern {i+1}")
                break

        if not sell_coin:
            logger.warning(f"⚠️ Failed to parse sell coin. Check regex patterns against this red line")
            # Extract red line for debugging
            red_line_match = re.search(r'(🔴.*)', text)
            if red_line_match:
                logger.warning(f"Red line content: {red_line_match.group(1)}")

        # Validate that sell coin is ETH or USDC
        if sell_coin and sell_coin in ['ETH', 'USDC']:
            is_valid_transaction = True
            logger.info(f"✅ Valid transaction: Selling {sell_coin}")
        elif sell_coin:
            logger.warning(f"❌ Invalid transaction: Selling {sell_coin} (only ETH/USDC allowed)")
            is_valid_transaction = False
        else:
            logger.warning(f"❌ Could not determine sell coin")
            is_valid_transaction = False

        # Extract price
        price_patterns = [
            r'💰.*?Price per token\s*\$?([\d,]+\.?\d*)\s*USD',  # 💰 Price per token $0.136 USD
            r'💵.*?Price per token\s*\$?([\d,]+\.?\d*)\s*USD',  # 💵 Price per token $0.008 USD
            r'Price per token\s*\$?([\d,]+\.?\d*)\s*USD',      # Generic pattern
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

        logger.info(f"Parsed result: sell={sell_coin}, buy={buy_coin}, price=${price}, valid={is_valid_transaction}")
        return sell_coin, buy_coin, price, is_valid_transaction

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