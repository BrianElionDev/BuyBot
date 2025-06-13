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

    async def _send_notification(
        self,
        sell_coin: str,
        buy_coin: str,
        amount: float,
        signal_price: Optional[float] = None,
        is_valid: bool = True,
        rejection_reason: Optional[str] = None,
        success: Optional[bool] = None,
        final_balances: Optional[dict] = None
    ):
        """
        Send notification with enhanced format for both valid and invalid transactions

        Args:
            sell_coin: The coin being sold
            buy_coin: The coin being bought
            amount: Transaction amount
            signal_price: Price from the signal
            is_valid: Whether the transaction is valid and will go through
            rejection_reason: Reason for rejection if transaction is invalid
            success: Whether the transaction was successful
            final_balances: Final wallet balances after the transaction
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

        # Determine which coin's price to check for slippage
        price_check_coin = buy_coin
        base_currencies = ['USDC', 'ETH', 'WETH']
        if buy_coin.upper() in base_currencies:
            # If we are buying a base currency, the price is for the other asset
            price_check_coin = sell_coin
            logger.info(f"[SLIPPAGE] Target is a base currency ({buy_coin}), checking price of {sell_coin} instead.")

        # Fetch price from CoinGecko for the correct coin
        coingecko_price_value = None
        coingecko_price = "Price unavailable"
        try:
            logger.info(f"[PRICE] Fetching CoinGecko price for {price_check_coin}...")
            coingecko_price_value = await self.price_service.get_coin_price(price_check_coin)
            if coingecko_price_value:
                coingecko_price = f"${coingecko_price_value:.6f}"
                logger.info(f"[SUCCESS] CoinGecko price for {price_check_coin}: {coingecko_price}")
            else:
                logger.warning(f"[WARNING] Could not fetch CoinGecko price for {price_check_coin}")
        except Exception as e:
            logger.error(f"[ERROR] Error fetching CoinGecko price for {price_check_coin}: {e}")

        # Slippage information
        slippage_info = "Slippage: Not calculated"
        slippage_threshold = self.config.SLIPPAGE_PERCENTAGE
        price_difference_percent = None
        price_difference_info = "Price Difference: Not calculated"

        # Slippage protection check
        if signal_price and coingecko_price_value:
            price_difference_percent = abs(coingecko_price_value - signal_price) / signal_price * 100

            logger.info(f"[PRICE_CHECK] Signal price: ${signal_price:.6f}")
            logger.info(f"[PRICE_CHECK] Current market price: ${coingecko_price_value:.6f}")
            logger.info(f"[PRICE_CHECK] Price difference: {price_difference_percent:.2f}%")
            logger.info(f"[PRICE_CHECK] Price difference threshold: {self.trading_engine.get_price_threshold():.1f}%")

            price_difference_info = f"Price Difference: {price_difference_percent:.2f}% (Threshold: {self.trading_engine.get_price_threshold():.1f}%)"
            slippage_info = f"Slippage Tolerance: {self.config.DEX_SLIPPAGE_PERCENTAGE}%"

            # This check is now handled inside the trading engine, but we can log it here
            if price_difference_percent > self.trading_engine.get_price_threshold():
                logger.warning(f"❌ PRICE DIFFERENCE HIGH: {price_difference_info}")
                # The engine will reject this, this is just for notification purposes.
            else:
                logger.info(f"✅ PRICE DIFFERENCE OK: {price_difference_percent:.2f}% <= {self.trading_engine.get_price_threshold():.1f}%")

        elif signal_price:
            price_difference_info = "Price Difference: Could not calculate - CoinGecko price unavailable"
            logger.warning(f"[WARNING] Cannot perform price difference check - CoinGecko price unavailable")
        else:
            price_difference_info = "Price Difference: Could not calculate - Signal price not provided"
            logger.warning(f"[WARNING] Cannot perform price difference check - signal price not provided")

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
                f"🚨 TRADE SIGNAL PROCESSED!\n\n"
                f"Transaction Type: {transaction_type} {buy_coin}\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"🔄 Pair: {sell_coin}/{buy_coin}\n"
                f"💲 Signal Price: ${signal_price:.6f}\n"
                f"📊 CoinGecko Price: {coingecko_price}\n"
                f"📈 {price_difference_info}\n"
                f"💰 Amount: ${amount:.2f}\n"
                f"⏱️ Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            )
        else:
            message = (
                f"🚨 TRADE SIGNAL REJECTED!\n\n"
                f"Transaction Type: {transaction_type} {buy_coin}\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"🔄 Pair: {sell_coin}/{buy_coin}\n"
                f"💲 Signal Price: ${signal_price:.6f}\n"
                f"📊 CoinGecko Price: {coingecko_price}\n"
                f"📈 {price_difference_info}\n"
                f"💰 Amount: ${amount:.2f}\n"
                f"⏱️ Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                f"❌ Reason: {rejection_reason if rejection_reason else 'Unknown error'}"
            )

        # Add trade summary
        message += f"\n\nProposed trade: To buy {buy_coin} in exchange for ${amount:.2f} of {sell_coin}."

        # Add final status and wallet balances
        if success is True:
            message += "\n\n✅ Transaction Successful"
        elif success is False:
            message += f"\n\n❌ Transaction Failed: {rejection_reason}"

        if final_balances:
            balance_lines = []
            for token, balance in final_balances.items():
                if balance > 0:
                    # Format based on token value
                    if balance > 0.0001:
                        balance_lines.append(f"- {token.upper()}: {balance:,.4f}")
                    else:
                        balance_lines.append(f"- {token.upper()}: {balance:.8f}")

            if balance_lines:
                message += "\n\n💰 Wallet Balance:\n" + "\n".join(balance_lines)

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

                # Process "Trade detected" and "Swap detected" messages (with or without emoji) - case insensitive
                message_lower = message.lower() if message else ""
                is_trade_signal = (
                    # Trade detected patterns
                    'trade detected' in message_lower or
                    '[trade] trade detected' in message_lower or
                    # Swap detected patterns
                    'swap detected' in message_lower or
                    '[swap] swap detected' in message_lower or
                    # Handle variations with emoji, spaces, and punctuation
                    ('👋' in message and 'trade detected' in message_lower) or
                    ('👋' in message and 'swap detected' in message_lower) or
                    ('👋' in message and 'trade signal' in message_lower) or
                    # Handle text format variations
                    '[trade]' in message_lower or
                    '[swap]' in message_lower or
                    # Direct pattern matches for common formats
                    message_lower.strip().startswith('trade detected') or
                    message_lower.strip().startswith('swap detected') or
                    '👋  trade detected' in message_lower or
                    '👋 trade detected' in message_lower or
                    '👋  swap detected' in message_lower or
                    '👋 swap detected' in message_lower
                )

                if message and is_trade_signal:
                    # Determine signal type
                    signal_type = "SWAP" if 'swap detected' in message_lower else "TRADE"
                    logger.info(f"[SIGNAL] {signal_type} SIGNAL DETECTED!")
                    logger.info(f"[SUCCESS] {signal_type} signal from {sender_display}")
                    logger.info(f"[CONTENT] Full message content:")
                    logger.info(f"{message}")
                    logger.info("-" * 60)

                    # The new parser returns a reason for failure
                    sell_coin, buy_coin, price, is_valid, rejection_reason = self._parse_enhanced_signal(message)

                    # Handle case where parsing fails to find essential info
                    if not (sell_coin and buy_coin and price):
                        failure_reason = rejection_reason or "Could not parse trade signal."
                        logger.warning(f"[WARNING] {failure_reason} from {sender_display}")
                        await self._send_parsing_failure_notification(
                            message_text=message,
                            failure_reason=failure_reason
                        )
                        return

                    # Handle case where the pair is invalid (e.g., not ETH/USDC based)
                    if not is_valid:
                        logger.warning(f"[IGNORED] {rejection_reason}")
                        await self._send_notification(
                            sell_coin=sell_coin,
                            buy_coin=buy_coin,
                            amount=self.config.TRADE_AMOUNT,
                            signal_price=price,
                            is_valid=False,
                            rejection_reason=rejection_reason,
                            success=False,
                            final_balances=await self.trading_engine.get_all_wallet_balances()
                        )
                        return

                    # If we reach here, the signal is valid and parsed. Proceed with trade.
                    logger.info(f"[SUCCESS] VALID TRADE: {sell_coin}/{buy_coin} @ ${price}")
                    exchange_type = getattr(self.config, "PREFERRED_EXCHANGE_TYPE", "dex").lower()
                    logger.info(f"[TRADE] Using {exchange_type.upper()} for trading")

                    try:
                        success, reason = await self.trading_engine.process_signal(
                            coin_symbol=buy_coin,
                            signal_price=price,
                            exchange_type=exchange_type,
                            sell_coin=sell_coin
                        )

                        final_balances = await self.trading_engine.get_all_wallet_balances()

                        await self._send_notification(
                            sell_coin=sell_coin,
                            buy_coin=buy_coin,
                            amount=self.config.TRADE_AMOUNT,
                            signal_price=price,
                            is_valid=True,
                            rejection_reason=reason, # reason for failure from engine
                            success=success,
                            final_balances=final_balances
                        )

                    except Exception as e:
                        logger.error(f"[ERROR] An unexpected error occurred in the trading engine: {e}", exc_info=True)
                        rejection_reason = f"Trading engine failed: {e}"
                        await self._send_notification(
                            sell_coin=sell_coin,
                            buy_coin=buy_coin,
                            amount=self.config.TRADE_AMOUNT,
                            is_valid=True, # It was valid, but failed during processing
                            rejection_reason=rejection_reason,
                            success=False,
                            final_balances=await self.trading_engine.get_all_wallet_balances()
                        )
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

    def _parse_enhanced_signal(self, text: str) -> Tuple[Optional[str], Optional[str], Optional[float], bool, Optional[str]]:
        """
        Enhanced parsing to extract sell_coin, buy_coin, price, and validate the pair.
        Handles both "trade detected" and "swap detected" formats.
        Returns: (sell_coin, buy_coin, price, is_valid, rejection_reason)
        """
        logger.info(f"Enhanced parsing: {text[:200]}...")

        sell_coin = None
        buy_coin = None
        price = None
        is_valid_transaction = False
        rejection_reason = "Signal could not be parsed."

        # Helper function to find a coin symbol in a line of text
        def find_coin_symbol(line: str) -> Optional[str]:
            # Priority 1: Check for symbol in parentheses, e.g., "Name (SYMBOL)"
            # This is the most reliable format.
            match = re.search(r'\(([A-Z0-9]{2,10})\)', line, re.IGNORECASE)
            if match:
                logger.info(f"Parser found symbol in parentheses: {match.group(1)}")
                return match.group(1).upper().strip()

            # Priority 2: Check for symbol before parentheses, e.g., "1,000 SYMBOL (Name)"
            match = re.search(r'[\d,.]+\s+([A-Z0-9]{2,10})\s+\(', line, re.IGNORECASE)
            if match:
                logger.info(f"Parser found symbol before parentheses: {match.group(1)}")
                return match.group(1).upper().strip()

            # Priority 3: Check for symbol at the end of the line
            match = re.search(r'[\d,.]+\s+([A-Z0-9]{2,10})\s*$', line, re.IGNORECASE)
            if match:
                logger.info(f"Parser found symbol at end of line: {match.group(1)}")
                return match.group(1).upper().strip()

            logger.warning(f"Could not find a coin symbol in line: '{line}'")
            return None

        # Determine if this is a swap or trade message
        text_lower = text.lower()
        is_swap_message = 'swap detected' in text_lower
        signal_type = "SWAP" if is_swap_message else "TRADE"
        logger.info(f"[PARSING] Signal type: {signal_type}")

        # Extract coins based on the actual signal logic:
        # 🟢 + COIN = BUYING COIN (green with plus)
        # 🔴 - COIN = SPENDING COIN to buy (red with minus)
        # 🟢 - COIN = SELLING COIN (green with minus)
        # 🔴 + COIN = GETTING COIN from selling (red with plus)

        # First, determine if this is a BUY or SELL transaction
        transaction_type = None

        # Check for BUY pattern: 🟢 + [coin] and 🔴 - [coin]
        green_plus_match = re.search(r'🟢\s*\+', text)
        red_minus_match = re.search(r'🔴\s*-', text)

        # Check for SELL pattern: 🟢 - [coin] and 🔴 + [coin]
        green_minus_match = re.search(r'🟢\s*-', text)
        red_plus_match = re.search(r'🔴\s*\+', text)

        if green_plus_match and red_minus_match:
            transaction_type = "BUY"
            logger.info(f"[TRANSACTION] Detected BUY transaction (🟢+ and 🔴-)")
        elif green_minus_match and red_plus_match:
            transaction_type = "SELL"
            logger.info(f"[TRANSACTION] Detected SELL transaction (🟢- and 🔴+)")
        else:
            logger.warning(f"[WARNING] Could not determine transaction type")

        # Extract the actual green and red lines for debugging
        green_line_match = re.search(r'(🟢[^\n\r]*)', text)
        red_line_match = re.search(r'(🔴[^\n\r]*)', text)

        green_line = green_line_match.group(1).strip() if green_line_match else ""
        red_line = red_line_match.group(1).strip() if red_line_match else ""

        logger.info(f"Green line: {green_line}")
        logger.info(f"Red line: {red_line}")

        # Find coin symbols using the new helper function
        green_coin = find_coin_symbol(green_line)
        red_coin = find_coin_symbol(red_line)

        if not green_coin: logger.warning(f"⚠️ Failed to parse green coin symbol.")
        if not red_coin: logger.warning(f"⚠️ Failed to parse red coin symbol.")

        # Determine buy_coin and sell_coin based on transaction type
        if transaction_type == "BUY":
            # BUY: 🟢 + [buy_coin], 🔴 - [sell_coin]
            buy_coin = green_coin  # What we're getting (green +)
            sell_coin = red_coin   # What we're spending (red -)
            logger.info(f"[BUY] Buying {buy_coin} with {sell_coin}")
        elif transaction_type == "SELL":
            # SELL: 🟢 - [sell_coin], 🔴 + [buy_coin]
            sell_coin = green_coin  # What we're selling (green -)
            buy_coin = red_coin     # What we're getting (red +)
            logger.info(f"[SELL] Selling {sell_coin} for {buy_coin}")
        else:
            # Fallback - try to determine from the coins themselves
            logger.warning(f"[FALLBACK] Could not determine transaction type, using fallback logic")
            # If one is ETH/USDC and the other isn't, assume we're trading the base currency
            if green_coin in ['ETH', 'USDC'] and red_coin not in ['ETH', 'USDC']:
                sell_coin = green_coin
                buy_coin = red_coin
            elif red_coin in ['ETH', 'USDC'] and green_coin not in ['ETH', 'USDC']:
                sell_coin = red_coin
                buy_coin = green_coin
            else:
                sell_coin = green_coin
                buy_coin = red_coin

        # Validate that one of the coins in the pair is a base currency
        base_currencies = ['ETH', 'USDC', 'WETH']
        if sell_coin and buy_coin:
            is_buy_base = buy_coin.upper() in base_currencies
            is_sell_base = sell_coin.upper() in base_currencies

            if is_buy_base or is_sell_base:
                is_valid_transaction = True
                rejection_reason = None
                logger.info(f"✅ Valid transaction pair: {sell_coin}/{buy_coin}")
            else:
                is_valid_transaction = False
                rejection_reason = f"Invalid pair: neither {sell_coin} nor {buy_coin} is a base currency (e.g., ETH, USDC)."
                logger.warning(f"❌ {rejection_reason}")
        elif not sell_coin or not buy_coin:
            is_valid_transaction = False
            rejection_reason = "Could not parse a valid trading pair from the signal."
            logger.warning(f"❌ {rejection_reason}")

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

        if not price and is_valid_transaction:
            rejection_reason = "Could not identify price in signal."
            is_valid_transaction = False

        logger.info(f"Parsed result: sell={sell_coin}, buy={buy_coin}, price=${price}, valid={is_valid_transaction}, reason={rejection_reason}")
        return sell_coin, buy_coin, price, is_valid_transaction, rejection_reason

    async def start(self):
        """Start the Telegram monitor - async method"""
        logger.info("[STARTUP] Starting Enhanced Telegram Monitor...")
        if self.config.TELEGRAM_PHONE is None:
            logger.error("TELEGRAM_PHONE must be set in the configuration and cannot be None")
            return

        try:
            # Start the client asynchronously
            await self.client.start(phone=self.config.TELEGRAM_PHONE)

            logger.info("[LOGIN] Successfully connected to Telegram")

            # Log the monitoring setup
            logger.info("=" * 80)
            logger.info(f"[TARGET] Monitoring group ID: {self.config.TARGET_GROUP_ID}")
            logger.info("=" * 80)
            logger.info("[MONITOR] Now monitoring ALL messages in the target group...")
            logger.info("[LOG] All message activity will be logged. Press Ctrl+C to stop.")
            logger.info("=" * 80)

            # Check wallet connection on startup
            if self.trading_engine and hasattr(self.trading_engine, 'check_wallet_connection'):
                await self.trading_engine.check_wallet_connection()

            # Run until disconnected
            await self.client.run_until_disconnected()

        except Exception as e:
            logger.error(f"[ERROR] Failed to start Telegram client: {e}")
            raise

    def stop(self):
        """Stop the Telegram monitor - synchronous method"""
        if self.client.is_connected():
            self.client.disconnect()
            logger.info("Telegram client disconnected")