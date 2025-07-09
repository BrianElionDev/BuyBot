import asyncio
import logging
import re
import time
from typing import Dict, Any
from datetime import datetime

from src.bot.trading_engine import TradingEngine
from .database import (
    find_trade_by_timestamp,
    find_trade_by_discord_id,
    update_existing_trade,
    save_alert_to_database,
    update_existing_alert
)
from .discord_signal_parser import DiscordSignalParser
from .models import InitialDiscordSignal, DiscordUpdateSignal
from config import settings as config

# Setup logging
logger = logging.getLogger(__name__)

class DiscordBot:
    def __init__(self):
        self.trading_engine = TradingEngine(
            api_key=config.BINANCE_API_KEY,
            api_secret=config.BINANCE_API_SECRET,
            is_testnet=config.BINANCE_TESTNET
        )
        self.signal_parser = DiscordSignalParser()
        logger.info("DiscordBot initialized with AI Signal Parser.")

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

            trade_row = await find_trade_by_timestamp(signal.timestamp)
            if not trade_row:
                clean_timestamp = signal.timestamp.replace('T', ' ').rstrip('Z')
                error_msg = f"No existing trade found for timestamp: '{signal.timestamp}'. Query was performed using cleaned timestamp: '{clean_timestamp}'"
                logger.error(error_msg)
                return {"status": "error", "message": f"No existing trade found for timestamp: {signal.timestamp}"}

            # 1. Parse the signal content using the AI parser
            logger.info(f"Parsing signal content with AI: '{signal.content}'")
            parsed_data = await self.signal_parser.parse_new_trade_signal(signal.content)

            if not parsed_data:
                raise ValueError("AI parsing failed to return valid data.")

            # 2. Store the AI's parsed response in the database
            await update_existing_trade(trade_id=trade_row["id"], updates={"parsed_signal": parsed_data})
            logger.info(f"Successfully stored parsed signal for trade ID: {trade_row['id']}")

            # --- Start of new validation ---
            # Validate that the parser returned a coin symbol
            coin_symbol = parsed_data.get('coin_symbol')
            if not coin_symbol:
                error_msg = "AI parser did not return a 'coin_symbol'. Cannot proceed with trade."
                logger.error(f"{error_msg} for trade ID: {trade_row['id']}")
                await update_existing_trade(trade_id=trade_row["id"], updates={"status": "FAILED", "binance_response": {"error": error_msg}})
                return {"status": "error", "message": error_msg}

            # Validate that the parser returned entry prices
            entry_prices = parsed_data.get('entry_prices')
            if not entry_prices or not isinstance(entry_prices, list) or not entry_prices[0]:
                error_msg = "AI parser did not return valid 'entry_prices'. Cannot proceed with trade."
                logger.error(f"{error_msg} for trade ID: {trade_row['id']}")
                await update_existing_trade(trade_id=trade_row["id"], updates={"status": "FAILED", "binance_response": {"error": error_msg}})
                return {"status": "error", "message": error_msg}
            # --- End of new validation ---

            # 3. Adapt the AI's response to fit the TradingEngine's requirements
            engine_params = {
                'coin_symbol': coin_symbol,
                'signal_price': float(entry_prices[0]),
                'position_type': parsed_data.get('position_type', 'SPOT'),
                'sell_coin': 'USDT',
                'order_type': parsed_data.get('order_type', 'LIMIT'),
                'stop_loss': parsed_data.get('stop_loss'),
                'take_profits': parsed_data.get('take_profits'),
                'exchange_type': 'cex'
                # 'dca_range' could be added here if the AI provides it
            }

            # 4. Execute the trade using the clean parameters
            logger.info(f"Processing trade with TradingEngine using parameters: {engine_params}")
            success, result_message = await self.trading_engine.process_signal(**engine_params)

            if success:
                # 5. Update database with execution status, order ID, and Binance response
                updates = {
                    "status": "OPEN",
                    "exchange_order_id": str(result_message.get('orderId', '')),
                    "position_size": float(result_message.get('origQty', 0.0)),
                    "binance_response": result_message
                }
                # Check if a stop loss order was also created
                if 'stop_loss_order_details' in result_message and result_message['stop_loss_order_details']:
                    updates['stop_loss_order_id'] = str(result_message['stop_loss_order_details'].get('orderId', ''))

                await update_existing_trade(trade_id=trade_row["id"], updates=updates)

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
                await update_existing_trade(trade_id=trade_row["id"], updates=updates)

                logger.error(f"Trade processing failed for trade ID: {trade_row['id']}. Reason: {result_message}")
                return {
                    "status": "error",
                    "message": f"Trade processing failed: {result_message}"
                }

        except Exception as e:
            # This part is tricky because we might not have trade_row['id'] if the timestamp search fails
            trade_id = locals().get('trade_row', {}).get('id')
            if trade_id:
                # Update database with failed status
                updates = {"status": "FAILED"}
                await update_existing_trade(trade_id=trade_id, updates=updates)

            error_msg = f"Error executing initial trade: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return {"status": "error", "message": error_msg}

    async def process_update_signal(self, signal_data: Dict[str, Any], alert_id: int = None) -> Dict[str, str]:
        """
        Process follow-up signal (stop loss hit, position closed, etc.)
        Updates the existing trade row with new information.
        """
        binance_response_log = None # To store any response from a trading action
        try:
            signal = DiscordUpdateSignal(**signal_data)
            logger.info(f"Processing update signal: {signal.content}")

            # The 'trade' field in the update signal refers to the discord_id of the original trade
            trade_row = await find_trade_by_discord_id(signal.trade)
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
                if "be" in signal.content.lower():
                    # Get original entry price from parsed_signal, guarding against None
                    parsed_signal = trade_row.get('parsed_signal') or {}
                    original_entry_price = parsed_signal.get('entry_prices', [0.0])[0]
                    if original_entry_price:
                        new_sl_price = float(original_entry_price)
                        logger.info(f"Determined new stop loss price (Break Even) as {new_sl_price} from original entry.")
                    else:
                        logger.error(f"Could not determine entry price for BE stop loss on trade {trade_row['id']}")
                else:
                    # Fallback to regex for a numerical price
                    price_match = re.search(r'(\d+\.?\d*)', signal.content)
                    if price_match:
                        new_sl_price = float(price_match.group(1))

                if new_sl_price > 0:
                    action_successful, binance_response_log = await self.trading_engine.update_stop_loss(trade_row, new_sl_price)
                    if action_successful:
                        # The response from a successful SL update contains the new order details
                        trade_updates['stop_loss_order_id'] = str(binance_response_log.get('orderId', ''))
                else:
                    logger.warning(f"Could not determine a valid new stop loss price for trade {trade_row['id']}")


            # After executing action, update the database
            if action_successful:
                logger.info(f"Successfully executed '{action_type}' for trade {trade_row['id']}. Binance Response: {binance_response_log}")
                # Update the trade with new status or SL order ID
                if trade_updates:
                    await update_existing_trade(trade_id=trade_row["id"], updates=trade_updates)
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

            if alert_id:
                logger.info(f"Updating existing alert record (ID: {alert_id}) with processed data.")
                await update_existing_alert(alert_id, alert_updates)
            else:
                logger.info("Saving new alert record with processed data.")
                await save_alert_to_database(alert_updates)

            return {
                "status": "success",
                "message": f"Update signal processed: {parsed_action['action_description']}"
            }

        except Exception as e:
            error_msg = f"Error processing update signal: {str(e)}"
            logger.error(error_msg, exc_info=True)
            # Log error to the alert if possible
            if alert_id:
                await update_existing_alert(alert_id, {"binance_response": {"error": error_msg}})
            return {"status": "error", "message": error_msg}

    def _calculate_pnl(self, entry_price: float, exit_price: float, position_size: float) -> float:
        """Calculate PnL in USD for a position"""
        if entry_price <= 0 or position_size <= 0:
            return 0.0

        # For long positions: (exit_price - entry_price) * position_size
        # This assumes position_size is in base currency units
        pnl = (exit_price - entry_price) * position_size
        return round(pnl, 2)

    async def close(self):
        """Gracefully shutdown the trading engine."""
        await self.trading_engine.close()

# Global bot instance
discord_bot = DiscordBot()