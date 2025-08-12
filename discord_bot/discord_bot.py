import asyncio
import logging
import re
import time
from typing import Dict, Any, Optional, Union, List, Tuple
from datetime import datetime
import os
from dotenv import load_dotenv
import uuid
import json

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.bot.trading_engine import TradingEngine
from discord_bot.discord_signal_parser import DiscordSignalParser, client
from discord_bot.models import InitialDiscordSignal, DiscordUpdateSignal
from discord_bot.database import DatabaseManager
from config import settings as config
from supabase import create_client, Client
from src.services.price_service import PriceService
from src.exchange.binance_exchange import BinanceExchange
from discord_bot.websocket_manager import DiscordBotWebSocketManager
from config import settings

# Setup logging
logger = logging.getLogger(__name__)

class DiscordBot:
    def __init__(self):
        # Load environment variables
        load_dotenv()

        # --- Binance API Initialization ---
        api_key = settings.BINANCE_API_KEY
        api_secret = settings.BINANCE_API_SECRET
        is_testnet = settings.BINANCE_TESTNET
        if not api_key or not api_secret:
            logger.critical("Binance API key/secret not set. Cannot start Trading Engine.")
            raise ValueError("Binance API key/secret not set.")

        # --- Supabase Initialization ---
        supabase_url = settings.SUPABASE_URL
        supabase_key = settings.SUPABASE_KEY
        if not supabase_url or not supabase_key:
            logger.critical("Supabase URL or Key not set. Cannot connect to the database.")
            raise ValueError("Supabase URL or Key not set.")

        self.supabase: Client = create_client(supabase_url, supabase_key)
        self.db_manager = DatabaseManager(self.supabase)

        # --- Component Initialization ---
        self.price_service = PriceService()
        self.binance_exchange = BinanceExchange(api_key, api_secret, is_testnet)
        self.trading_engine = TradingEngine(
            price_service=self.price_service,
            binance_exchange=self.binance_exchange,
            db_manager=self.db_manager
        )
        self.signal_parser = DiscordSignalParser()

        # Initialize WebSocket manager for real-time database sync
        self.websocket_manager = DiscordBotWebSocketManager(self, self.db_manager)

        logger.info(f"DiscordBot initialized with {'AI' if client else 'simple'} Signal Parser.")

    def _clean_text_for_llm(self, text: str) -> str:
        """
        Clean text for LLM processing by removing problematic characters and formatting.
        """
        if not text:
            return ""

        # Remove or replace problematic characters
        cleaned = text.replace('"', '"').replace('"', '"')  # Smart quotes to regular quotes
        cleaned = cleaned.replace(''', "'").replace(''', "'")  # Smart apostrophes to regular apostrophes
        cleaned = cleaned.replace('–', '-').replace('—', '-')  # Em dashes to regular dashes
        cleaned = cleaned.replace('…', '...')  # Ellipsis to three dots

        # Remove any other non-ASCII characters that might cause issues
        cleaned = ''.join(char for char in cleaned if ord(char) < 128)

        return cleaned.strip()

    def _parse_parsed_signal(self, parsed_signal_data) -> Dict[str, Any]:
        """
        Safely parse parsed_signal data which can be either a dict or JSON string.
        """
        if isinstance(parsed_signal_data, dict):
            return parsed_signal_data
        elif isinstance(parsed_signal_data, str):
            try:
                return json.loads(parsed_signal_data)
            except json.JSONDecodeError:
                logger.warning(f"Failed to parse parsed_signal JSON: {parsed_signal_data}")
                return {}
        else:
            logger.warning(f"Unexpected parsed_signal type: {type(parsed_signal_data)}")
            return {}

    def parse_alert_content(self, content, signal_data):
        """
        Parse alert content and determine what action(s) should be taken.
        Returns structured data for logging. Can handle single or multiple actions.
        """
        content_lower = content.lower()

        # Extract coin symbol from content
        coin_symbol = self._extract_coin_symbol_from_content(content)

        # Determine action type and details
        stop_loss_regex = r"stoploss moved to ([-+]?\d*\.?\d+)"
        stops_to_be_regex= r"\b(stop|sl)\b.*\bbe\b"
        stops_to_x_regex = r"\b(stop\w*|sl)\b.*\bto\b\s*(-?\d+(\.\d+)?)"
        dca_to_entry_regex = r"\bdca\b.*\bentry\b.*?(\d+\.\d+)(?:\s|$)"


        # 1. Take Profit 1 with Stop Loss move to Break Even (MUST BE FIRST!)
        if "tp1 & stops moved to be" in content_lower:
            return {
                "action_type": "tp1_and_sl_to_be",
                "action_description": f"TP1 hit and stop loss moved to break even for {coin_symbol}",
                "binance_action": "PARTIAL_SELL_AND_UPDATE_STOP_ORDER",
                "position_status": "PARTIALLY_CLOSED",
                "reason": "TP1 hit and risk management - move to break even",
                "coin_symbol": coin_symbol
            }

        if "stopped out" in content_lower or "stop loss" in content_lower or "closed be" in content_lower or  "stopped be" in content_lower or "closed in profits" in content_lower or  "closed in loss" in content_lower or "closed be/in slight loss" in content_lower:
            # Distinguish between a SL update (move to BE) and a SL being hit
            return {
                "action_type": "stop_loss_hit",
                "action_description": f"Stop loss hit for {coin_symbol}",
                "binance_action": "MARKET_SELL",
                "stop_loss": None,
                "take_profit":None,
                "position_status": "CLOSED",
                "reason": "Stop loss triggered",
                "coin_symbol": coin_symbol
            }
        elif "limit order cancelled" in content_lower:
            return {
                "action_type": "limit_order_cancelled",
                "action_description": f"Limit order cancelld for {coin_symbol}",
                "binance_action": "CANCEL_ORDER",
                "position_status": "CLOSED",
                "stop_loss": None,
                "take_profit":None,
                "reason": "Cancel limit order",
                "coin_symbol": coin_symbol
            }
        elif "move stops to 1H" in content_lower or "updated stoploss" in content_lower or "move stops to " in content_lower or "updated stop loss " in content_lower:
            return {
                "action_type": "cancelled_stoploss_order_and_create_new",
                "action_description": f"Limit order cancelld for {coin_symbol}",
                "binance_action": "UPDATE_ORDER",
                "position_status": "OPEN",
                "stop_loss": 2,
                "take_profit":None,
                "reason": "Cancel SL order and create new one +-2%",
                "coin_symbol": coin_symbol
            }
        elif "tp1 taken" in content_lower:
            return {
                "action_type": "take_profit_taken_hit",
                "action_description": f"Take Profit 2 hit for {coin_symbol}",
                "binance_action": "PARTIAL_SELL",
                "position_status": "PARTIALLY_CLOSED",
                "reason": "TP2 target reached",
                "coin_symbol": coin_symbol
            }
        elif "tp1" in content_lower:
            return {
                "action_type": "take_profit_1",
                "action_description": f"Take Profit 1 hit for {coin_symbol}",
                "binance_action": "PARTIAL_SELL",
                "position_status": "PARTIALLY_CLOSED",
                "reason": "TP1 target reached",
                "coin_symbol": coin_symbol
            }
        elif "tp2" in content_lower:
            return {
                "action_type": "take_profit_2",
                "action_description": f"Take Profit 2 hit for {coin_symbol}",
                "binance_action": "PARTIAL_SELL",
                "position_status": "PARTIALLY_CLOSED",
                "reason": "TP2 target reached",
                "coin_symbol": coin_symbol
            }
        elif "tp1 taken" in content_lower:
            return {
                "action_type": "take_profit_taken_hit",
                "action_description": f"Take Profit 2 hit for {coin_symbol}",
                "binance_action": "PARTIAL_SELL",
                "position_status": "PARTIALLY_CLOSED",
                "reason": "TP2 target reached",
                "coin_symbol": coin_symbol
            }
        if re.search(stops_to_be_regex, content_lower):
            return {
                "action_type": "stop_loss_update",
                "action_description": f"Stop loss moved to break even for {coin_symbol}",
                "binance_action": "UPDATE_STOP_ORDER",
                "position_status": "OPEN",
                "stop_loss": "BE",
                "take_profit": None,
                "reason": "Risk management - move to break even",
                "coin_symbol": coin_symbol
            }
        elif re.search(stops_to_x_regex, content_lower):
            match = re.search(stops_to_x_regex, content_lower)
            if match:
                entry_value = match.group(2) # Convert the extracted string to a float
                return {
                "action_type": "stop_loss_update",
                "action_description": f"Stop loss moved to {entry_value} for {coin_symbol}",
                "binance_action": "UPDATE_STOP_ORDER",
                "position_status": "OPEN",
                "stop_loss": entry_value,
                "take_profit": None,
                "reason": "Stop loss adjusted to specific value",
                "coin_symbol": coin_symbol
                }
        elif re.search(dca_to_entry_regex, content_lower):
            match = re.search(dca_to_entry_regex, content_lower)
            if match:
                entry_value = match.group(1) # Convert the extracted string to a float
                return {
                "action_type": "dca_to_entry",
                "action_description": f"Create a new order if their is no open positions {entry_value} for {coin_symbol}",
                "binance_action": "CREATE_NEW_ORDER_IF_NONE_STOP_ORDER",
                "position_status": "OPEN",
                "entry": entry_value,
                "take_profit": None,
                "reason": "Stop loss adjusted to specific value",
                "coin_symbol": coin_symbol
                }
        else:
            return {
                "action_type": "unknown_update",
                "action_description": f"Update for {coin_symbol}: {content}",
                "binance_action": "NO_ACTION",
                "position_status": "UNKNOWN",
                "reason": "Unrecognized alert type",
                "coin_symbol": coin_symbol
            }

    def _extract_coin_symbol_from_content(self, content: str) -> str:
        """
        Extract coin symbol from alert content using regex patterns.
        """
        import re

        # Common coin symbols pattern - look for uppercase letters at start of content
        # Pattern: " COIN 🚀｜trades" or "COIN 🚀｜trades" or "COIN:"
        coin_patterns = [
            r'^\s*([A-Z0-9]{2,10})\s*[🚀📈📉]',  # COIN 🚀 at start
            r'^\s*([A-Z0-9]{2,10}):',  # COIN: at start
            r'^\s*([A-Z0-9]{2,10})\s+',  # COIN followed by space
            r'\s+([A-Z0-9]{2,10})\s*[🚀📈📉]',  # COIN 🚀 anywhere
            r'\s+([A-Z0-9]{2,10}):',  # COIN: anywhere
        ]

        for pattern in coin_patterns:
            match = re.search(pattern, content)
            if match:
                coin_symbol = match.group(1).strip()
                # Validate it's a reasonable coin symbol (2-10 chars, alphanumeric)
                if 2 <= len(coin_symbol) <= 10 and coin_symbol.isalnum():
                    logger.info(f"Extracted coin symbol '{coin_symbol}' from content: '{content[:50]}...'")
                    return coin_symbol

        # Fallback: try to extract from the original trade's parsed_signal
        logger.warning(f"Could not extract coin symbol from content: '{content[:50]}...'")
        return "UNKNOWN"

    async def process_initial_signal(self, signal_data: Dict[str, Any]) -> Dict[str, str]:
        """
        Process initial trading signal by finding the trade, parsing the content with AI,
        and then executing the trade.
        """
        try:
            signal = InitialDiscordSignal(**signal_data)
            logger.info(f"Processing initial signal: {signal.structured}")

            trade_row = await self.db_manager.find_trade_by_timestamp(signal.timestamp)
            if not trade_row:
                clean_timestamp = signal.timestamp.replace('T', ' ').rstrip('Z')
                error_msg = f"No existing trade found for timestamp: '{signal.timestamp}'. Query was performed using cleaned timestamp: '{clean_timestamp}'"
                logger.error(error_msg)
                return {"status": "error", "message": f"No existing trade found for timestamp: {signal.timestamp}"}

            # 1. Sanitize the structured signal and then parse it with the AI
            logger.info(f"Original structured signal: '{signal.structured}'")
            sanitized_signal = self._clean_text_for_llm(signal.structured)
            logger.info(f"Sanitized signal for AI parser: '{sanitized_signal}'")
            parsed_data = await self.signal_parser.parse_new_trade_signal(sanitized_signal)

            if not parsed_data:
                raise ValueError("AI parsing failed to return valid data.")

            # 2. Store the AI's parsed response in the database and set signal_type
            updates: Dict[str, Any] = {"parsed_signal": json.dumps(parsed_data) if isinstance(parsed_data, dict) else str(parsed_data)}
            position_type = parsed_data.get('position_type')

            # Store coin_symbol in database
            coin_symbol = parsed_data.get('coin_symbol')
            if coin_symbol:
                updates["coin_symbol"] = str(coin_symbol)
                logger.info(f"Stored coin_symbol '{coin_symbol}' for trade ID: {trade_row['id']}")
            else:
                logger.warning(f"Could not find 'coin_symbol' in parsed_signal for trade ID: {trade_row['id']}")

            # Check if open position exists
            if await self.binance_exchange.has_open_futures_postion(f"{parsed_data.get('coin_symbol')}USDT"):
                logger.info("There exist aready an open trade for this coin symbol, setting position_type to 'FUTURES'.")
                updates["binance_response"] = f"We have already open postions for: {parsed_data.get('coin_symbol')}USDT. Skipping this trade!"
                await self.db_manager.update_existing_trade(trade_id=trade_row["id"], updates=updates)
                return {"status": "error", "message": "We have already open postions for this coin symbol. Skipping this trade!"}
            if position_type:
                updates["signal_type"] = position_type
                logger.info(f"Extracted signal_type '{position_type}' from parsed signal for trade ID: {trade_row['id']}")
            else:
                logger.warning(f"Could not find 'position_type' in parsed_signal for trade ID: {trade_row['id']}")

            # --- Parse entry_price from structured field (text) ---
            entry_price_structured = None
            entry_match = re.search(r"Entry:?\|([\d\.\-]+)", signal.structured)
            if entry_match:
                try:
                    entry_price_structured = float(entry_match.group(1).split('-')[0])
                    if entry_price_structured is not None:
                        updates["entry_price"] = float(entry_price_structured)
                except Exception:
                    pass

            # --- Fetch binance_entry_price from Binance ---
            binance_entry_price = None
            try:
                coin_symbol_for_binance = parsed_data.get('coin_symbol')
                if coin_symbol_for_binance:
                    binance_entry_price = await self.price_service.get_coin_price(coin_symbol_for_binance)
                    if binance_entry_price is not None:
                        updates["binance_entry_price"] = float(binance_entry_price)
                        logger.info(f"Fetched binance_entry_price for {coin_symbol_for_binance}: {binance_entry_price}")
                    else:
                        # CRITICAL: Set a fallback value to prevent empty field
                        logger.warning(f"Could not fetch binance_entry_price for {coin_symbol_for_binance}, using entry_price as fallback")
                        if entry_price_structured:
                            updates["binance_entry_price"] = float(entry_price_structured)
            except Exception as e:
                logger.warning(f"Could not fetch binance_entry_price: {e}")
                # CRITICAL: Set a fallback value to prevent empty field
                if entry_price_structured:
                    updates["binance_entry_price"] = float(entry_price_structured)

            # CRITICAL: Validate all required fields before updating database
            self._validate_required_fields(updates, trade_row['id'])

            await self.db_manager.update_existing_trade(trade_id=trade_row["id"], updates=updates)
            logger.info(f"Successfully stored parsed signal, signal_type, entry_price, and binance_entry_price for trade ID: {trade_row['id']}")

            # --- Start of new validation ---
            # Validate that the parser returned a coin symbol
            coin_symbol = parsed_data.get('coin_symbol')
            if not coin_symbol:
                error_msg = "AI parser did not return a 'coin_symbol'. Cannot proceed with trade."
                logger.error(f"{error_msg} for trade ID: {trade_row['id']}")
                await self.db_manager.update_existing_trade(trade_id=trade_row["id"], updates={"status": "FAILED", "binance_response": {"error": error_msg}})
                return {"status": "error", "message": error_msg}

            # Validate that the parser returned entry prices
            entry_prices = parsed_data.get('entry_prices')
            if not entry_prices or not isinstance(entry_prices, list) or not entry_prices[0]:
                error_msg = "AI parser did not return valid 'entry_prices'. Cannot proceed with trade."
                logger.error(f"{error_msg} for trade ID: {trade_row['id']}")
                await self.db_manager.update_existing_trade(trade_id=trade_row["id"], updates={"status": "FAILED", "binance_response": {"error": error_msg}})
                return {"status": "error", "message": error_msg}
            # --- End of new validation ---

            # 3. Adapt the AI's response to fit the TradingEngine's requirements
            engine_params = {
                'coin_symbol': coin_symbol,
                'signal_price': float(entry_prices[0]),
                'position_type': parsed_data.get('position_type', 'SPOT'),
                'order_type': parsed_data.get('order_type', 'LIMIT'),
                'stop_loss': parsed_data.get('stop_loss'),
                'take_profits': parsed_data.get('take_profits'),
                'client_order_id': trade_row.get('discord_id'),
                'quantity_multiplier': parsed_data.get('quantity_multiplier') # For memecoin quantity prefixes
                # 'dca_range' could be added here if the AI provides it
            }

            # Ensure clientOrderId is always unique
            if not engine_params.get('client_order_id'):
                engine_params['client_order_id'] = f"rubicon-{uuid.uuid4().hex[:16]}"

            # 4. Execute the trade using the clean parameters
            logger.info(f"Processing trade with TradingEngine using parameters: {engine_params}")
            success, result_message = await self.trading_engine.process_signal(**engine_params)

            # --- UNFILLED LOGIC ---
            def is_unfilled(order_result):
                if not isinstance(order_result, dict):
                    return False
                # Check for API errors first
                if 'error' in order_result:
                    return True
                # Futures/Spot: executedQty == 0 and (avgPrice == 0 or not present)
                executed_qty = float(order_result.get('executedQty', 0.0))
                avg_price = float(order_result.get('avgPrice', 0.0)) if 'avgPrice' in order_result else None
                fills = order_result.get('fills', [])
                # If all are zero/empty, it's unfilled
                if executed_qty == 0 and (avg_price is None or avg_price == 0) and (not fills or sum(float(f.get('qty', 0.0)) for f in fills) == 0):
                    return True
                return False

            if success:
                # Check if order was actually placed successfully
                if isinstance(result_message, dict) and 'error' in result_message:
                    # Order failed due to validation or API error
                    error_msg = result_message.get('error', 'Unknown error')
                    logger.error(f"Order failed for trade {trade_row['id']}: {error_msg}")
                    await self.db_manager.update_existing_trade(
                        trade_id=trade_row["id"],
                        updates={
                            "order_status": "REJECTED",
                            "status": "NONE",  # No position created
                            "binance_response": result_message
                        }
                    )
                    return {"status": "error", "message": f"Order failed: {error_msg}"}

                # Order was created successfully - use new method to preserve original response
                logger.info(f"Order created successfully for trade {trade_row['id']}: {result_message}")

                # Try to get order status, but don't fail if it doesn't work
                status_response = None
                sync_error = None

                if isinstance(result_message, dict) and 'orderId' in result_message:
                    order_id = result_message['orderId']
                    symbol = result_message.get('symbol', '')
                    if symbol:
                        try:
                            # Try to get order status
                            status_response = await self.trading_engine.binance_exchange.get_order_status(symbol, order_id)
                        except Exception as e:
                            sync_error = f"Could not get order status: {str(e)}"
                            logger.warning(f"Status check failed for order {order_id}: {sync_error}")

                # Ensure result_message is a dict for the update method
                original_response = result_message if isinstance(result_message, dict) else {"error": str(result_message)}

                # Update trade with preserved original response
                await self.db_manager.update_trade_with_original_response(
                    trade_id=trade_row["id"],
                    original_response=original_response,
                    status_response=status_response,
                    sync_error=sync_error
                )

                return {"status": "success", "message": "Order created successfully"}
            else:
                # 5. Update database with failed status and Binance response
                updates = {
                    "order_status": "REJECTED",
                    "status": "NONE",  # No position created
                    "binance_response": result_message
                }
                # --- UNFILLED status check for failed trades ---
                if isinstance(result_message, dict) and 'orderId' in result_message and is_unfilled(result_message):
                    updates["order_status"] = "PENDING"
                    updates["status"] = "NONE"
                    logger.info(f"Trade marked as UNFILLED (failure branch) for trade ID: {trade_row['id']}")
                await self.db_manager.update_existing_trade(trade_id=trade_row["id"], updates=updates)

                logger.error(f"Trade processing failed for trade ID: {trade_row['id']}. Reason: {result_message}")
                return {
                    "status": "error",
                    "message": f"Trade processing failed: {result_message}"
                }

        except Exception as e:
            # This part is tricky because we might not have trade_row['id'] if the timestamp search fails
            trade_id = locals().get('trade_row', {}).get('id')
            if trade_id is not None:
                # Update database with failed status
                updates = {
                    "order_status": "REJECTED",
                    "status": "NONE"  # No position created
                }
                await self.db_manager.update_existing_trade(trade_id=trade_id, updates=updates)

            error_msg = f"Error executing initial trade: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return {"status": "error", "message": error_msg}

    def _validate_required_fields(self, updates: Dict[str, Any], trade_id: int) -> None:
        """
        CRITICAL: Validate that all required fields are populated to prevent fraud.
        """
        try:
            required_fields = {
                'entry_price': 'Entry price from signal',
                'binance_entry_price': 'Binance entry price for accurate PnL',
                'coin_symbol': 'Coin symbol for trade identification',
                'signal_type': 'Position type (LONG/SHORT) for PnL calculation'
            }

            missing_fields = []

            for field, description in required_fields.items():
                if field not in updates or not updates[field]:
                    missing_fields.append(f"{field}: {description}")

            if missing_fields:
                logger.error(f"CRITICAL: Trade {trade_id} missing required fields: {missing_fields}")
                logger.critical(f"FRAUD RISK: Trade {trade_id} has missing critical fields")

                # Add validation issues to updates
                if 'sync_issues' not in updates:
                    updates['sync_issues'] = []
                updates['sync_issues'].extend(missing_fields)
                updates['manual_verification_needed'] = True
            else:
                logger.info(f"✅ Trade {trade_id} has all required fields populated")

        except Exception as e:
            logger.error(f"Error validating required fields for trade {trade_id}: {e}")

    async def process_update_signal(self, signal_data: Dict[str, Any]) -> Dict[str, str]:
        """
        Process follow-up signal (stop loss hit, position closed, etc.)
        Updates the existing trade row with new information.
        """
        binance_response_log = None # To store any response from a trading action
        try:
            signal = DiscordUpdateSignal(**signal_data)
            logger.info(f"Processing update signal: {signal.content}")

            # The 'trade' field in the update signal refers to the discord_id of the original trade
            trade_row = await self.db_manager.find_trade_by_discord_id(signal.trade)
            if not trade_row:
                error_msg = f"No original trade found for discord_id: {signal.trade}"
                logger.error(error_msg)
                return {"status": "error", "message": error_msg}

            # --- SKIP follow-up if original trade is FAILED or UNFILLED ---
            if trade_row.get('order_status') in ('REJECTED', 'CANCELED', 'EXPIRED') or trade_row.get('status') == 'NONE':
                logger.warning(f"Skipping follow-up: original trade {trade_row['id']} has order_status={trade_row.get('order_status')} and position_status={trade_row.get('status')}")
                # Update alert to reflect no open position
                alert_updates = {
                    "parsed_alert": {
                        "original_content": signal.content,
                        "processed_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
                        "original_trade_id": trade_row['id'],
                        "coin_symbol": self._parse_parsed_signal(trade_row.get('parsed_signal')).get('coin_symbol'),
                        "trader": signal.trader,
                        "note": "Skipped: original trade is FAILED or UNFILLED. No open position to update."
                    },
                    "binance_response": None
                }
                trade_val = getattr(signal, 'trade', None)
                if not isinstance(trade_val, str):
                    trade_val = None
                await self.db_manager.update_alert_by_discord_id_or_trade(
                    discord_id=signal.discord_id,
                    trade=trade_val,
                    updates=alert_updates
                )
                return {"status": "skipped", "message": "No open position to update (original trade is FAILED or UNFILLED)"}

            # Parse the alert content to determine action(s)
            parsed_action = self.parse_alert_content(signal.content, trade_row)

            # Ensure parsed_action is not None
            if parsed_action is None:
                error_msg = f"Failed to parse alert content: {signal.content}"
                logger.error(error_msg)
                return {"status": "error", "message": error_msg}

            # Handle multiple actions
            if parsed_action.get("multiple_actions"):
                logger.info(f"Processing multiple actions: {len(parsed_action['actions'])} actions")

                trade_updates = {}
                all_actions_successful = True

                for i, action in enumerate(parsed_action['actions']):
                    logger.info(f"Executing action {i+1}/{len(parsed_action['actions'])}: {action['action_type']}")

                    # Execute each action using the existing logic
                    action_successful, binance_response_log = await self._execute_single_action(action, trade_row, signal)

                    if not action_successful:
                        logger.error(f"Action {i+1} failed: {action['action_type']}")
                        all_actions_successful = False
                        break
                    else:
                        # Merge trade updates from each action
                        if binance_response_log and isinstance(binance_response_log, dict):
                            if 'trade_updates' in binance_response_log:
                                trade_updates.update(binance_response_log['trade_updates'])

                action_successful = all_actions_successful
                action_type = "multiple_actions"

                if action_successful:
                    return {"status": "success", "message": f"Processed {len(parsed_action['actions'])} actions successfully"}
                else:
                    return {"status": "error", "message": f"Failed to process all {len(parsed_action['actions'])} actions"}
            else:
                # Execute single action (existing logic)
                trade_updates = {}
                action_type = parsed_action["action_type"]
                action_successful = False # Flag to track if the engine action succeeded

            # Determine what trading action to take based on the parsed action
            if action_type == "stop_loss_hit" or action_type == "position_closed":
                logger.info(f"Processing '{action_type}' for trade {trade_row['id']}. Closing position.")
                action_successful, binance_response_log = await self.trading_engine.close_position_at_market(trade_row, reason=action_type)
                if action_successful:
                    trade_updates["status"] = "CLOSED"

                    # Ensure coin_symbol is stored in database
                    if not trade_row.get('coin_symbol') and parsed_action.get('coin_symbol'):
                        trade_updates["coin_symbol"] = parsed_action.get('coin_symbol')
                        logger.info(f"Updated coin_symbol to {parsed_action.get('coin_symbol')} for trade {trade_row['id']}")

                    # --- Fetch binance_exit_price from Binance ---
                    coin_symbol_exit = self._parse_parsed_signal(trade_row.get('parsed_signal')).get('coin_symbol')
                    if coin_symbol_exit and isinstance(coin_symbol_exit, str):
                        try:
                            from src.services.price_service import PriceService
                            price_service = PriceService()
                            binance_exit_price = await price_service.get_coin_price(coin_symbol_exit)
                            if binance_exit_price is not None:
                                trade_updates["binance_exit_price"] = float(binance_exit_price)
                                logger.info(f"Fetched binance_exit_price for {coin_symbol_exit}: {binance_exit_price}")
                        except Exception as e:
                            logger.warning(f"Could not fetch binance_exit_price: {e}")

            elif action_type == "take_profit_1":
                logger.info(f"Processing TP1 for trade {trade_row['id']}. Closing 50% of position.")
                action_successful, binance_response_log = await self.trading_engine.close_position_at_market(trade_row, reason="take_profit_1", close_percentage=50.0)
                if action_successful:
                    trade_updates["status"] = "PARTIALLY_CLOSED"

                    # Update position_size in database - remaining 50%
                    current_position_size = float(trade_row.get('position_size', 0.0))
                    new_position_size = current_position_size * 0.5  # 50% remaining
                    trade_updates["position_size"] = new_position_size
                    logger.info(f"Updated position_size from {current_position_size} to {new_position_size} after TP1")

            elif action_type == "tp1_and_sl_to_be":
                logger.info(f"Processing TP1 + SL to BE for trade {trade_row['id']}. Closing 50% and moving SL to break-even.")

                # Step 1: Close 50% of position (TP1)
                action_successful, binance_response_log = await self.trading_engine.close_position_at_market(trade_row, reason="take_profit_1", close_percentage=50.0)
                if action_successful:
                    trade_updates["status"] = "PARTIALLY_CLOSED"

                    # Update position_size in database - remaining 50%
                    current_position_size = float(trade_row.get('position_size', 0.0))
                    new_position_size = current_position_size * 0.5  # 50% remaining
                    trade_updates["position_size"] = new_position_size
                    logger.info(f"Updated position_size from {current_position_size} to {new_position_size} after TP1")

                    # Step 2: Move stop loss to break-even for remaining position
                    try:
                        coin_symbol = self._parse_parsed_signal(trade_row.get('parsed_signal')).get('coin_symbol')
                        if coin_symbol:
                            trading_pair = f"{coin_symbol}USDT"
                            positions = await self.binance_exchange.get_futures_position_information()

                            # Find the specific position
                            position = None
                            for pos in positions:
                                if pos['symbol'] == trading_pair and float(pos['positionAmt']) != 0:
                                    position = pos
                                    break

                            if position:
                                # Use the entry price from Binance position data as break-even
                                entry_price = float(position['entryPrice'])
                                new_sl_price = round(entry_price, 2)

                                logger.info(f"Moving SL to break-even at {new_sl_price} for remaining position ({new_position_size})")

                                # Update stop loss to break-even with the new position size
                                # First, update the trade row with new position size for the SL update
                                trade_row['position_size'] = new_position_size

                                sl_update_successful, sl_response = await self.trading_engine.update_stop_loss(trade_row, new_sl_price)
                                if sl_update_successful:
                                    logger.info(f"Successfully moved SL to break-even for trade {trade_row['id']}")
                                    # Store the new SL order ID in trade updates
                                    if isinstance(sl_response, dict) and 'orderId' in sl_response:
                                        trade_updates['stop_loss_order_id'] = str(sl_response['orderId'])
                                else:
                                    logger.warning(f"Failed to move SL to break-even: {sl_response}")
                            else:
                                logger.warning(f"Could not find position for {trading_pair} to move SL to break-even")
                        else:
                            logger.warning(f"Could not determine coin symbol for SL update on trade {trade_row['id']}")
                    except Exception as e:
                        logger.error(f"Error moving SL to break-even: {str(e)}")
                else:
                    logger.error(f"Failed to execute TP1 for trade {trade_row['id']}")

            elif action_type == "take_profit_2":
                logger.info(f"Processing TP2 for trade {trade_row['id']}. Closing remaining position.")
                # Assumption: TP2 closes the rest of the position. A more complex system could calculate remaining size.
                action_successful, binance_response_log = await self.trading_engine.close_position_at_market(trade_row, reason="take_profit_2", close_percentage=100.0)
                if action_successful:
                    trade_updates["status"] = "CLOSED"

                    # Ensure coin_symbol is stored in database
                    if not trade_row.get('coin_symbol') and parsed_action.get('coin_symbol'):
                        trade_updates["coin_symbol"] = parsed_action.get('coin_symbol')
                        logger.info(f"Updated coin_symbol to {parsed_action.get('coin_symbol')} for trade {trade_row['id']}")

            elif action_type == "stop_loss_update":
                logger.info(f"Processing stop loss update for trade {trade_row['id']}")
                new_sl_price = 0.0

                # Check for "BE" (Break Even) signal
                if parsed_action.get("stop_loss") == "BE" or "be" in signal.content.lower():
                    # Get the actual position data from Binance for accurate break-even calculation
                    try:
                        coin_symbol = self._parse_parsed_signal(trade_row.get('parsed_signal')).get('coin_symbol')
                        if coin_symbol:
                            trading_pair = f"{coin_symbol}USDT"
                            positions = await self.binance_exchange.get_futures_position_information()

                            # Find the specific position
                            position = None
                            for pos in positions:
                                if pos['symbol'] == trading_pair and float(pos['positionAmt']) != 0:
                                    position = pos
                                    break

                            if position:
                                # Use the entry price from Binance position data as break-even
                                entry_price = float(position['entryPrice'])
                                new_sl_price = entry_price

                                # Round to 2 decimal places for precision
                                new_sl_price = round(new_sl_price, 2)

                                logger.info(f"Determined break-even price as {new_sl_price} (using entry price directly)")
                            else:
                                # Fallback to database entry price
                                original_entry_price = trade_row.get('entry_price')
                                if original_entry_price:
                                    # Use entry price directly as break-even
                                    new_sl_price = float(original_entry_price)

                                    # Round to 2 decimal places for precision
                                    new_sl_price = round(new_sl_price, 2)

                                    logger.info(f"Determined break-even price as {new_sl_price} from database entry price.")
                                else:
                                    logger.error(f"Could not determine entry price for BE stop loss on trade {trade_row['id']}")
                        else:
                            logger.error(f"Could not determine coin symbol for BE stop loss on trade {trade_row['id']}")
                    except Exception as e:
                        logger.warning(f"Could not fetch position data from Binance: {e}. Using database entry price.")
                        # Fallback to database entry price
                        original_entry_price = trade_row.get('entry_price')
                        if original_entry_price:
                            # Use entry price directly as break-even
                            new_sl_price = float(original_entry_price)

                            # Round to 2 decimal places for precision
                            new_sl_price = round(new_sl_price, 2)

                            logger.info(f"Determined break-even price as {new_sl_price} from database entry price.")
                        else:
                            logger.error(f"Could not determine entry price for BE stop loss on trade {trade_row['id']}")
                else:
                    # Get the new price from the parsed data if available
                    new_sl_price = float(parsed_action.get("stop_loss", 0.0))
                print(f"New SL price determined from parsed action: {new_sl_price}")
                if new_sl_price > 0:
                    action_successful, binance_response_log = await self.trading_engine.update_stop_loss(trade_row, new_sl_price)
                    if action_successful and isinstance(binance_response_log, dict):
                        # The response from a successful SL update contains the new order details
                        trade_updates['stop_loss_order_id'] = str(binance_response_log.get('orderId', ''))
                else:
                    logger.warning(f"Could not determine a valid new stop loss price for trade {trade_row['id']}")
            elif action_type == "cancelled_stoploss_order_and_create_new":
                logger.info(f"Processing stop loss update for trade {trade_row['id']}")

                try:
                    coin_symbol = self._parse_parsed_signal(trade_row.get('parsed_signal')).get('coin_symbol')
                    position_type = trade_row.get('signal_type', 'UNKNOWN')
                    if not coin_symbol:
                        logger.error(f"Could not determine coin symbol for trade {trade_row['id']}")
                        return {"status": "error", "message": "Could not determine coin symbol for stop loss update."}

                    stop_loss_percentage = parsed_action.get('stop_loss_percentage', 2.0)
                    if stop_loss_percentage <= 0 or stop_loss_percentage > 50:
                        logger.error(f"Invalid stop loss percentage: {stop_loss_percentage}%. Must be between 0.1 and 50.")
                        return {"status": "error", "message": f"Invalid stop loss percentage: {stop_loss_percentage}%. Must be between 0.1 and 50."}

                    new_sl_price = await self.trading_engine.calculate_percentage_stop_loss(coin_symbol, position_type, stop_loss_percentage)
                    print(f"New SL price determined from percentage: {new_sl_price}")
                    if not new_sl_price:
                        logger.error(f"Could not calculate {stop_loss_percentage}% stop loss for {coin_symbol}")
                        return {"status": "error", "message": f"Could not calculate {stop_loss_percentage}% stop loss for {coin_symbol}"}
                    if new_sl_price > 0:
                        action_successful, binance_response_log = await self.trading_engine.update_stop_loss(trade_row, new_sl_price)
                        if action_successful and isinstance(binance_response_log, dict):
                            trade_updates['stop_loss_order_id'] = str(binance_response_log.get('orderId', ''))
                        else:
                            logger.warning(f"Stop loss update failed for trade {trade_row['id']}. Binance response: {binance_response_log}")
                    else:
                        logger.warning(f"Could not determine a valid new stop loss price for trade {trade_row['id']}. new_sl_price was {new_sl_price}")
                except Exception as e:
                    logger.error(f"An error occurred while updating stop loss for trade {trade_row['id']}: {e}")
            elif action_type == "take_profit_taken_hit":
                logger.info(f"Processing take profit taken hit for trade {trade_row['id']} - creating new TP and moving SL to entry")

                try:
                    coin_symbol = self._parse_parsed_signal(trade_row.get('parsed_signal')).get('coin_symbol')
                    position_type = trade_row.get('signal_type', 'UNKNOWN')
                    if not coin_symbol:
                        logger.error(f"Could not determine coin symbol for trade {trade_row['id']}")
                        return {"status": "error", "message": "Could not determine coin symbol for take profit taken hit."}

                    trading_pair = f"{coin_symbol}USDT"
                    positions = await self.binance_exchange.get_position_risk(symbol=trading_pair)
                    current_position_size = 0.0
                    for position in positions:
                        if position.get('symbol') == trading_pair and float(position.get('positionAmt', 0)) != 0:
                            current_position_size = abs(float(position.get('positionAmt', 0)))
                            break

                    if current_position_size <= 0:
                        logger.warning(f"No open position found for {trading_pair} - position may have been fully closed")
                        return {"status": "warning", "message": f"No open position found for {trading_pair}"}

                    logger.info(f"Current position size for {trading_pair}: {current_position_size}")

                    # Step 2: Get current market price
                    current_price = await self.binance_exchange.get_futures_mark_price(trading_pair)
                    if not current_price or current_price <= 0:
                        logger.error(f"Could not get current price for {trading_pair}")
                        return {"status": "error", "message": f"Could not get current price for {trading_pair}"}

                    logger.info(f"Current price for {trading_pair}: {current_price}")

                    # Step 3: Calculate new TP price (3% away from current price)
                    if position_type.upper() == 'LONG':
                        new_tp_price = current_price * 1.03  # 3% above current price
                    else:  # SHORT
                        new_tp_price = current_price * 0.97  # 3% below current price

                    logger.info(f"New TP price calculated: {new_tp_price} (3% {'above' if position_type.upper() == 'LONG' else 'below'} current price)")

                                         # Step 4: Get entry price for break-even stop loss
                    entry_price = float(self._parse_parsed_signal(trade_row.get('parsed_signal')).get('entry_prices', [0.0])[0])
                    if entry_price <= 0:
                         logger.error(f"Could not determine entry price for trade {trade_row['id']}")
                         return {"status": "error", "message": f"Could not determine entry price for trade {trade_row['id']}"}

                    logger.info(f"Entry price for break-even SL: {entry_price}")

                    # Step 5: Cancel existing TP/SL orders
                    logger.info(f"Canceling existing TP/SL orders for {trading_pair}")
                    await self.trading_engine.cancel_tp_sl_orders(trading_pair, trade_row)

                    # Step 6: Create new TP order for remaining position
                    tp_side = 'SELL' if position_type.upper() == 'LONG' else 'BUY'
                    new_tp_order = await self.binance_exchange.create_futures_order(
                        pair=trading_pair,
                        side=tp_side,
                        order_type_market='TAKE_PROFIT_MARKET',
                        amount=current_position_size,
                        stop_price=new_tp_price,
                        reduce_only=True
                    )

                    if not new_tp_order or 'orderId' not in new_tp_order:
                        logger.error(f"Failed to create new TP order: {new_tp_order}")
                        return {"status": "error", "message": f"Failed to create new TP order for {trading_pair}"}

                    logger.info(f"Successfully created new TP order: {new_tp_order['orderId']} at {new_tp_price}")

                    # Step 7: Update stop loss to entry (break-even)
                    action_successful, binance_response_log = await self.trading_engine.update_stop_loss(trade_row, entry_price)
                    if action_successful and isinstance(binance_response_log, dict):
                        trade_updates['stop_loss_order_id'] = str(binance_response_log.get('orderId', ''))
                        logger.info(f"Successfully moved stop loss to entry price: {entry_price}")
                    else:
                        logger.warning(f"Stop loss update to entry failed for trade {trade_row['id']}. Binance response: {binance_response_log}")

                    # Step 8: Update trade status and position size
                    trade_updates["status"] = "PARTIALLY_CLOSED"
                    trade_updates["position_size"] = current_position_size

                    # Store the new TP order information
                    if 'tp_sl_orders' not in trade_updates:
                        trade_updates['tp_sl_orders'] = []
                    trade_updates['tp_sl_orders'].append({
                        'orderId': new_tp_order['orderId'],
                        'order_type': 'TAKE_PROFIT',
                        'tp_level': 2,  # This is the second TP
                        'stopPrice': str(new_tp_price),
                        'symbol': trading_pair,
                        'amount': str(current_position_size)
                    })

                    action_successful = True
                    binance_response_log = {
                        'message': f'TP taken hit processed - new TP at {new_tp_price}, SL moved to entry {entry_price}',
                        'new_tp_order': new_tp_order,
                        'position_size': current_position_size
                    }

                except Exception as e:
                    logger.error(f"An error occurred while processing take profit taken hit for trade {trade_row['id']}: {e}")
                    return {"status": "error", "message": f"Error processing take profit taken hit: {str(e)}"}
            elif action_type == "limit_order_cancelled":
                logger.info(f"Processing cancellation for trade {trade_row['id']}")
                action_successful, binance_response_log = await self.trading_engine.cancel_order(trade_row)
                await self.trading_engine.cancel_tp_sl_orders(f"{trade_row.get('coin_symbol', 'UNKNOWN')}USDT", trade_row)
                if action_successful:
                    trade_updates["status"] = "CANCELLED"

            elif action_type == "order_filled":
                 # Usually, the initial signal opens the position. This is just an informational update.
                 # We can update the status to ensure it reflects 'OPEN'.
                 logger.info(f"Received 'order filled' notification for trade {trade_row['id']}. Status confirmed as OPEN.")
                 trade_updates["status"] = "OPEN"
                 action_successful = True # No engine action, but we mark as successful to log correctly.
                 binance_response_log = {"message": "Order fill notification processed."}

            # After executing action, update the database
            if action_successful:
                logger.info(f"Successfully executed '{action_type}' for trade {trade_row['id']}. Binance Response: {binance_response_log}")

                # --- PNL and Exit Price Calculation ---
                if binance_response_log and 'fill_price' in binance_response_log and 'executed_qty' in binance_response_log:
                    exit_price = float(binance_response_log['fill_price'])
                    qty_closed = float(binance_response_log['executed_qty'])

                    if exit_price > 0 and qty_closed > 0:
                        # Safely get entry price and position type from the trade row
                        entry_price = float(self._parse_parsed_signal(trade_row.get('parsed_signal')).get('entry_prices', [0.0])[0])
                        position_type = trade_row.get('signal_type', 'UNKNOWN')

                        # Calculate PnL for this specific action
                        newly_realized_pnl = self._calculate_pnl(position_type, entry_price, exit_price, qty_closed)

                        # Get existing PnL and add the new PnL
                        current_pnl = float(trade_row.get('pnl_usd', 0.0) or 0.0)
                        total_pnl = current_pnl + newly_realized_pnl

                        trade_updates["pnl_usd"] = total_pnl
                        trade_updates["exit_price"] = exit_price # This will store the latest exit price

                        logger.info(f"PnL for this action: {newly_realized_pnl:.2f}. Total realized PnL for trade: {total_pnl:.2f}")

                # Update the trade with new status or SL order ID
                if trade_updates:
                    await self.db_manager.update_existing_trade(trade_id=trade_row["id"], updates=trade_updates)
                    logger.info(f"Updated trade {trade_row['id']} with: {trade_updates}")
            elif binance_response_log: # Action was attempted but failed
                logger.error(f"Failed to execute '{action_type}' for trade {trade_row['id']}. Reason: {binance_response_log}")


            # Always update the alert record with the outcome
            alert_updates = {
                "parsed_alert": {
                    "original_content": signal.content,
                    "processed_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
                    "action_determined": parsed_action,
                    "original_trade_id": trade_row['id'],
                    "coin_symbol": parsed_action.get('coin_symbol', self._parse_parsed_signal(trade_row.get('parsed_signal')).get('coin_symbol')),
                    "trader": signal.trader
                },
                "binance_response": binance_response_log # This will be None if no action was taken, or the dict from Binance
            }

            # Always fetch the alert row by discord_id before updating
            alert_row = None
            try:
                alert_response = self.db_manager.supabase.from_("alerts").select("*").eq("discord_id", signal.discord_id).limit(1).execute()
                if alert_response.data and len(alert_response.data) > 0:
                    alert_row = alert_response.data[0]
            except Exception as e:
                logger.error(f"Error fetching alert row for update: {e}")

            if alert_row and alert_row.get('id'):
                logger.info(f"Updating alert by found alert id {alert_row['id']} with processed data.")
                await self.db_manager.update_existing_alert(alert_row['id'], alert_updates)
            else:
                # Create a new alert if none exists
                logger.info(f"Creating new alert for discord_id {signal.discord_id}")
                new_alert_data = {
                    "timestamp": signal.timestamp,
                    "discord_id": signal.discord_id,
                    "trade": signal.trade,
                    "content": signal.content,
                    "trader": signal.trader,
                    **alert_updates
                }
                await self.db_manager.save_alert_to_database(new_alert_data)

            return {
                "status": "success",
                "message": f"Update signal processed: {parsed_action['action_description']}"
            }

        except Exception as e:
            error_msg = f"Error processing update signal: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return {"status": "error", "message": error_msg}

    def _calculate_pnl(self, position_type: str, entry_price: float, exit_price: float, position_size: float) -> float:
        """Calculate PnL in USD for a position, considering LONG or SHORT."""
        if entry_price <= 0 or exit_price <= 0 or position_size <= 0:
            return 0.0

        if position_type.upper() == 'LONG':
            pnl = (exit_price - entry_price) * position_size
        elif position_type.upper() == 'SHORT':
            pnl = (entry_price - exit_price) * position_size
        else:
            pnl = 0.0

        return round(pnl, 2)

    async def update_trade_position_size(self, trade_id: int, new_position_size: float) -> bool:
        """Update the position_size field in a trade record."""
        try:
            updates = {"position_size": float(new_position_size)}
            success = await self.db_manager.update_existing_trade(trade_id=trade_id, updates=updates)
            if success:
                logger.info(f"Updated position_size to {new_position_size} for trade {trade_id}")
            return success
        except Exception as e:
            logger.error(f"Error updating position_size for trade {trade_id}: {e}")
            return False

    async def update_trade_coin_symbol(self, trade_id: int, new_coin_symbol: str) -> bool:
        """Update the coin_symbol field in a trade record."""
        try:
            updates = {"coin_symbol": str(new_coin_symbol)}
            success = await self.db_manager.update_existing_trade(trade_id=trade_id, updates=updates)
            if success:
                logger.info(f"Updated coin_symbol to {new_coin_symbol} for trade {trade_id}")
            return success
        except Exception as e:
            logger.error(f"Error updating coin_symbol for trade {trade_id}: {e}")
            return False

    async def close(self):
        """Gracefully shutdown the trading engine and WebSocket manager."""
        try:
            # Stop WebSocket manager
            if hasattr(self, 'websocket_manager') and self.websocket_manager:
                await self.websocket_manager.stop()

            # Close trading engine
            await self.trading_engine.close()

            logger.info("DiscordBot closed successfully.")
        except Exception as e:
            logger.error(f"Error closing DiscordBot: {e}")

    async def start_websocket_sync(self):
        """Start WebSocket real-time database synchronization."""
        try:
            if hasattr(self, 'websocket_manager') and self.websocket_manager:
                success = await self.websocket_manager.start()
                if success:
                    logger.info("WebSocket real-time sync started successfully")
                    return True
                else:
                    logger.error("Failed to start WebSocket sync")
                    return False
            else:
                logger.error("WebSocket manager not initialized")
                return False
        except Exception as e:
            logger.error(f"Error starting WebSocket sync: {e}")
            return False

    def get_websocket_status(self) -> dict:
        """Get WebSocket manager status."""
        if hasattr(self, 'websocket_manager') and self.websocket_manager:
            return self.websocket_manager.get_status()
        else:
            return {
                'running': False,
                'initialized': False,
                'error': 'WebSocket manager not available'
            }

    async def _execute_single_action(self, action: Dict[str, Any], trade_row: Dict[str, Any], signal) -> Tuple[bool, Any]:
        """
        Execute a single action from the parsed alert content.
        """
        try:
            action_type = action.get('action_type')
            if not action_type:
                logger.error(f"No action_type found in action: {action}")
                return False, {"error": "No action_type found"}

            # Execute the action based on type
            if action_type == "stop_loss_hit" or action_type == "position_closed":
                return await self.trading_engine.close_position_at_market(trade_row, reason=action_type)
            elif action_type == "take_profit_1":
                return await self.trading_engine.close_position_at_market(trade_row, reason="take_profit_1", close_percentage=50.0)
            elif action_type == "take_profit_2":
                return await self.trading_engine.close_position_at_market(trade_row, reason="take_profit_2", close_percentage=100.0)
            elif action_type == "limit_order_cancelled":
                return await self.trading_engine.cancel_order(trade_row)
            elif action_type == "stop_loss_update":
                stop_loss = action.get('stop_loss')
                if stop_loss and stop_loss != "BE":
                    return await self.trading_engine.update_stop_loss(trade_row, float(stop_loss))
                else:
                    # Handle break-even stop loss
                    return await self.trading_engine.update_stop_loss(trade_row, "BE")
            else:
                logger.warning(f"Unknown action_type: {action_type}")
                return False, {"error": f"Unknown action_type: {action_type}"}

        except Exception as e:
            logger.error(f"Error executing action {action.get('action_type', 'unknown')}: {e}")
            return False, {"error": str(e)}

# Global bot instance
discord_bot = DiscordBot()