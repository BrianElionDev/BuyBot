import asyncio
import logging
import re
import time
from typing import Dict, Any, Optional
from datetime import datetime
import os
from dotenv import load_dotenv

from src.bot.trading_engine import TradingEngine
from .discord_signal_parser import DiscordSignalParser, client
from .models import InitialDiscordSignal, DiscordUpdateSignal
from .database import DatabaseManager
from config import settings as config
from supabase import create_client, Client
from src.services.price_service import PriceService
from src.exchange.binance_exchange import BinanceExchange

# Setup logging
logger = logging.getLogger(__name__)

class DiscordBot:
    def __init__(self):
        # Load environment variables
        load_dotenv()

        # --- Binance API Initialization ---
        api_key = os.getenv("BINANCE_API_KEY")
        api_secret = os.getenv("BINANCE_API_SECRET")
        is_testnet = os.getenv("BINANCE_TESTNET", "False").lower() == 'true'
        if not api_key or not api_secret:
            logger.critical("Binance API key/secret not set. Cannot start Trading Engine.")
            raise ValueError("Binance API key/secret not set.")

        # --- Supabase Initialization ---
        supabase_url = os.getenv("SUPABASE_URL")
        supabase_key = os.getenv("SUPABASE_KEY")
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

        logger.info(f"DiscordBot initialized with {'AI' if client else 'simple'} Signal Parser.")

    def _clean_text_for_llm(self, text: str) -> str:
        """
        Sanitizes text to remove invisible unicode characters that can confuse LLMs,
        especially zero-width characters from Discord.
        """
        if not text:
            return ""
        # This regex targets multiple ranges of invisible or problematic Unicode characters:
        # U+200B-U+200D: Zero-width spaces and joiners
        # U+FEFF: Byte Order Mark (can appear as a zero-width no-break space)
        # U+2060-U+206F: General-purpose invisible characters (e.g., word joiner)
        # U+00AD: Soft hyphen
        return re.sub(r'[\u200B-\u200D\uFEFF\u2060-\u206F\u00AD]', '', text).strip()

    def parse_alert_content(self, content, original_trade_data):
        """
        Parse alert content and determine what action should be taken.
        Returns structured data for logging.
        """
        content_lower = content.lower()

        # Safely extract coin symbol with fallback
        coin_symbol = 'UNKNOWN'
        if original_trade_data and isinstance(original_trade_data.get('parsed_signal'), dict):
            coin_symbol = original_trade_data.get('parsed_signal', {}).get('coin_symbol', 'UNKNOWN')

        # Determine action type and details
        if "stopped out" in content_lower or "stop loss" in content_lower or "stopped be" in content_lower:
            # Distinguish between a SL update (move to BE) and a SL being hit
            if "moved to be" in content_lower or "sl to be" in content_lower:
                return {
                    "action_type": "stop_loss_update",
                    "action_description": f"Stop loss moved to break even for {coin_symbol}",
                    "binance_action": "UPDATE_STOP_ORDER",
                    "position_status": "OPEN",
                    "reason": "Risk management - move to break even"
                }
            return {
                "action_type": "stop_loss_hit",
                "action_description": f"Stop loss hit for {coin_symbol}",
                "binance_action": "MARKET_SELL",
                "position_status": "CLOSED",
                "reason": "Stop loss triggered"
            }

        elif "closed" in content_lower:
            return {
                "action_type": "position_closed",
                "action_description": f"Position closed for {coin_symbol}",
                "binance_action": "MARKET_SELL",
                "position_status": "CLOSED",
                "reason": "Manual close signal received"
            }

        elif "tp1" in content_lower:
            return {
                "action_type": "take_profit_1",
                "action_description": f"Take Profit 1 hit for {coin_symbol}",
                "binance_action": "PARTIAL_SELL",
                "position_status": "PARTIALLY_CLOSED",
                "reason": "TP1 target reached"
            }

        elif "tp2" in content_lower:
            return {
                "action_type": "take_profit_2",
                "action_description": f"Take Profit 2 hit for {coin_symbol}",
                "binance_action": "PARTIAL_SELL",
                "position_status": "PARTIALLY_CLOSED",
                "reason": "TP2 target reached"
            }

        elif "stops moved to be" in content_lower or "sl to be" in content_lower:
            return {
                "action_type": "stop_loss_update",
                "action_description": f"Stop loss moved to break even for {coin_symbol}",
                "binance_action": "UPDATE_STOP_ORDER",
                "position_status": "OPEN",
                "reason": "Risk management - move to break even"
            }

        elif "limit order cancelled" in content_lower:
            return {
                "action_type": "order_cancelled",
                "action_description": f"Limit order cancelled for {coin_symbol}",
                "binance_action": "CANCEL_ORDER",
                "position_status": "CANCELLED",
                "reason": "Order cancellation"
            }

        else:
            return {
                "action_type": "unknown_update",
                "action_description": f"Update for {coin_symbol}: {content}",
                "binance_action": "NO_ACTION",
                "position_status": "UNKNOWN",
                "reason": "Unrecognized alert type"
            }

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
            updates = {"parsed_signal": parsed_data}
            position_type = parsed_data.get('position_type')

            if position_type:
                updates["signal_type"] = position_type
                logger.info(f"Extracted signal_type '{position_type}' from parsed signal for trade ID: {trade_row['id']}")
            else:
                logger.warning(f"Could not find 'position_type' in parsed_signal for trade ID: {trade_row['id']}")

            await self.db_manager.update_existing_trade(trade_id=trade_row["id"], updates=updates)
            logger.info(f"Successfully stored parsed signal and signal_type for trade ID: {trade_row['id']}")

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
                'client_order_id': trade_row.get('discord_id'), # Use discord_id for reconciliation
                'quantity_multiplier': parsed_data.get('quantity_multiplier') # For memecoin quantity prefixes
                # 'dca_range' could be added here if the AI provides it
            }

            # 4. Execute the trade using the clean parameters
            logger.info(f"Processing trade with TradingEngine using parameters: {engine_params}")
            success, result_message = await self.trading_engine.process_signal(**engine_params)

            # --- UNFILLED LOGIC ---
            def is_unfilled(order_result):
                if not isinstance(order_result, dict):
                    return False
                # Futures/Spot: executedQty == 0 and (avgPrice == 0 or not present)
                executed_qty = float(order_result.get('executedQty', 0.0))
                avg_price = float(order_result.get('avgPrice', 0.0)) if 'avgPrice' in order_result else None
                fills = order_result.get('fills', [])
                # If all are zero/empty, it's unfilled
                if executed_qty == 0 and (avg_price is None or avg_price == 0) and (not fills or sum(float(f.get('qty', 0.0)) for f in fills) == 0):
                    return True
                return False

            if success:
                # 5. Update database with execution status, order ID, and Binance response
                updates = {
                    "status": "OPEN",
                    "binance_response": result_message,
                    "entry_price": engine_params['signal_price']
                }

                # Ensure the result is a dictionary before accessing keys
                if isinstance(result_message, dict):
                    updates["exchange_order_id"] = str(result_message.get('orderId', ''))

                    # --- Robustly parse position size ---
                    # For market orders, 'executedQty' is the source of truth.
                    # For limit orders, 'origQty' is what we want, as 'executedQty' will be 0 until filled.
                    size = float(result_message.get('executedQty', 0.0))
                    if size == 0.0:
                        size = float(result_message.get('origQty', 0.0))

                    # For spot market orders, the size is in the 'fills' array
                    if size == 0.0 and 'fills' in result_message and result_message['fills']:
                        size = sum(float(fill.get('qty', 0.0)) for fill in result_message['fills'])

                    updates["position_size"] = size

                    # Also capture the true entry price from the fills if available (for market orders)
                    if 'fills' in result_message and result_message['fills']:
                        weighted_avg_price = sum(float(f['price']) * float(f['qty']) for f in result_message['fills']) / sum(float(f['qty']) for f in result_message['fills'])
                        if weighted_avg_price > 0:
                            updates["entry_price"] = weighted_avg_price
                            logger.info(f"Updated entry price to {weighted_avg_price} from fills.")

                    # Check if a stop loss order was also created
                    if 'stop_loss_order_details' in result_message and isinstance(result_message['stop_loss_order_details'], dict):
                        updates['stop_loss_order_id'] = str(result_message['stop_loss_order_details'].get('orderId', ''))

                    # --- UNFILLED status check ---
                    if 'orderId' in result_message and is_unfilled(result_message):
                        updates["status"] = "UNFILLED"
                        logger.info(f"Trade marked as UNFILLED for trade ID: {trade_row['id']}")

                await self.db_manager.update_existing_trade(trade_id=trade_row["id"], updates=updates)

                logger.info(f"Trade processed successfully for trade ID: {trade_row['id']}. Message: {result_message}")
                return {
                    "status": "success",
                    "message": f"Trade processed successfully: {result_message}"
                }
            else:
                # 5. Update database with failed status and Binance response
                updates = {
                    "status": "FAILED",
                    "binance_response": result_message
                }
                # --- UNFILLED status check for failed trades ---
                if isinstance(result_message, dict) and 'orderId' in result_message and is_unfilled(result_message):
                    updates["status"] = "UNFILLED"
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
                updates = {"status": "FAILED"}
                await self.db_manager.update_existing_trade(trade_id=trade_id, updates=updates)

            error_msg = f"Error executing initial trade: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return {"status": "error", "message": error_msg}

    async def process_update_signal(self, signal_data: Dict[str, Any], alert_id: Optional[int] = None) -> Dict[str, str]:
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

            # Parse the alert content to determine action
            parsed_action = self.parse_alert_content(signal.content, trade_row)

            # Execute trading actions based on the parsed content
            trade_updates = {}
            action_type = parsed_action["action_type"]
            action_successful = False # Flag to track if the engine action succeeded

            # Determine what trading action to take based on the parsed action
            if action_type == "stop_loss_hit" or action_type == "position_closed":
                logger.info(f"Processing '{action_type}' for trade {trade_row['id']}. Closing position.")
                action_successful, binance_response_log = await self.trading_engine.close_position_at_market(trade_row, reason=action_type)
                if action_successful:
                    trade_updates["status"] = "CLOSED"

            elif action_type == "take_profit_1":
                logger.info(f"Processing TP1 for trade {trade_row['id']}. Closing 50% of position.")
                action_successful, binance_response_log = await self.trading_engine.close_position_at_market(trade_row, reason="take_profit_1", close_percentage=50.0)
                if action_successful:
                    trade_updates["status"] = "PARTIALLY_CLOSED"

            elif action_type == "take_profit_2":
                logger.info(f"Processing TP2 for trade {trade_row['id']}. Closing remaining position.")
                # Assumption: TP2 closes the rest of the position. A more complex system could calculate remaining size.
                action_successful, binance_response_log = await self.trading_engine.close_position_at_market(trade_row, reason="take_profit_2", close_percentage=100.0)
                if action_successful:
                    trade_updates["status"] = "CLOSED"

            elif action_type == "stop_loss_update":
                logger.info(f"Processing stop loss update for trade {trade_row['id']}")
                new_sl_price = 0.0

                # Check for "BE" (Break Even) signal
                if parsed_action.get("value") == "BE" or "be" in signal.content.lower():
                    # Use the reliable entry_price from the database record
                    original_entry_price = trade_row.get('entry_price')
                    if original_entry_price:
                        new_sl_price = float(original_entry_price)
                        logger.info(f"Determined new stop loss price (Break Even) as {new_sl_price} from original entry.")
                    else:
                        logger.error(f"Could not determine entry price for BE stop loss on trade {trade_row['id']}")
                else:
                    # Get the new price from the parsed data if available
                    new_sl_price = float(parsed_action.get("value", 0.0))

                if new_sl_price > 0:
                    action_successful, binance_response_log = await self.trading_engine.update_stop_loss(trade_row, new_sl_price)
                    if action_successful and isinstance(binance_response_log, dict):
                        # The response from a successful SL update contains the new order details
                        trade_updates['stop_loss_order_id'] = str(binance_response_log.get('orderId', ''))
                else:
                    logger.warning(f"Could not determine a valid new stop loss price for trade {trade_row['id']}")

            elif action_type == "order_cancelled":
                logger.info(f"Processing cancellation for trade {trade_row['id']}")
                action_successful, binance_response_log = await self.trading_engine.cancel_order(trade_row)
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
                        entry_price = float((trade_row.get('parsed_signal') or {}).get('entry_prices', [0.0])[0])
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
                    "coin_symbol": parsed_action.get('coin_symbol', (trade_row.get('parsed_signal') or {}).get('coin_symbol')),
                    "trader": signal.trader
                },
                "binance_response": binance_response_log # This will be None if no action was taken, or the dict from Binance
            }

            if alert_id is not None:
                logger.info(f"Updating existing alert record (ID: {alert_id}) with processed data.")
                await self.db_manager.update_existing_alert(alert_id, alert_updates)
            else:
                logger.info("Saving new alert record with processed data.")
                await self.db_manager.save_alert_to_database(alert_updates)

            return {
                "status": "success",
                "message": f"Update signal processed: {parsed_action['action_description']}"
            }

        except Exception as e:
            error_msg = f"Error processing update signal: {str(e)}"
            logger.error(error_msg, exc_info=True)
            # Log error to the alert if possible
            if alert_id is not None:
                await self.db_manager.update_existing_alert(alert_id, {"binance_response": {"error": error_msg}})
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

    async def close(self):
        """Gracefully shutdown the trading engine."""
        await self.trading_engine.close()

# Global bot instance
discord_bot = DiscordBot()