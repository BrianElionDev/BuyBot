import asyncio
import logging
import time
from typing import Dict, Any

from src.bot.trading_engine import TradingEngine
from .database import (
    find_trade_by_timestamp,
    find_trade_by_discord_id,
    update_existing_trade,
    save_alert_to_database
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
            return {
                "action_type": "stop_loss_hit",
                "action_description": f"Stop loss hit for {coin_symbol}",
                "binance_action": "MARKET_SELL",
                "position_status": "CLOSED",
                "reason": "Stop loss triggered"
            }

        elif "closed" in content_lower and ("profit" in content_lower or "be" in content_lower):
            return {
                "action_type": "position_closed",
                "action_description": f"Position closed for {coin_symbol}",
                "binance_action": "MARKET_SELL",
                "position_status": "CLOSED",
                "reason": "Manual close" if "profit" in content_lower else "Break even close"
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
                "position_status": "ACTIVE",
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

            # 3. Adapt the AI's response to fit the TradingEngine's requirements
            engine_params = {
                'coin_symbol': parsed_data.get('coin_symbol'),
                'signal_price': float(parsed_data.get('entry_prices', [0])[0]),
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
                # 5. Update database with execution status
                updates = { "status": "ACTIVE" }
                await update_existing_trade(trade_id=trade_row["id"], updates=updates)

                logger.info(f"Trade processed successfully for trade ID: {trade_row['id']}. Message: {result_message}")
                return {
                    "status": "success",
                    "message": f"Trade processed successfully: {result_message}"
                }
            else:
                # 5. Update database with failed status
                updates = {"status": "FAILED"}
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

    async def process_update_signal(self, signal_data: Dict[str, Any]) -> Dict[str, str]:
        """
        Process follow-up signal (stop loss hit, position closed, etc.)
        Updates the existing trade row with new information and stores the alert.
        """
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

            # Create the parsed_alert data structure
            parsed_alert_data = {
                "original_content": signal.content,
                "processed_at": time.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
                "action_determined": parsed_action,
                "original_trade_id": trade_row.get("id"),
                "coin_symbol": trade_row.get('parsed_signal', {}).get('coin_symbol', 'UNKNOWN') if trade_row.get('parsed_signal') else 'UNKNOWN',
                "trader": signal.trader
            }

            # Save the alert to the alerts table with parsed data
            alert_saved = await save_alert_to_database({
                "discord_id": signal.discord_id,
                "trade": signal.trade,
                "trader": signal.trader,
                "content": signal.content,
                "timestamp": signal.timestamp,
                "parsed_alert": parsed_alert_data
            })

            if not alert_saved:
                logger.warning("Failed to save alert to database, but continuing with processing")

            # Execute trading actions based on the parsed content
            trade_updates = {}

            content_lower = signal.content.lower()
            action_type = parsed_action["action_type"]

            # Determine what trading action to take based on the parsed action
            if action_type == "stop_loss_hit":
                logger.info(f"Processing stop loss for trade {trade_row['id']}")

                # Close position on exchange if still active
                if trade_row.get("status") == "ACTIVE":
                    parsed_signal = trade_row.get('parsed_signal', {})
                    coin_symbol = parsed_signal.get('coin_symbol')
                    if not coin_symbol:
                        return {"status": "error", "message": f"Could not determine coin_symbol for trade ID {trade_row['id']}"}

                    symbol = f"{coin_symbol}USDT"
                    close_result = await self.trading_engine.close_position_at_market(symbol)

                    exit_price = close_result.get("fill_price", 0)
                    pnl = self._calculate_pnl(
                        entry_price=trade_row.get("entry_price", 0),
                        exit_price=exit_price,
                        position_size=trade_row.get("position_size", 0)
                    )

                    trade_updates = {
                        "status": "CLOSED",
                        "exit_price": exit_price,
                        "pnl_usd": pnl
                    }
                else:
                    trade_updates = {"status": "CLOSED"}

            elif action_type == "position_closed":
                logger.info(f"Processing manual close for trade {trade_row['id']}")

                if trade_row.get("status") == "ACTIVE":
                    parsed_signal = trade_row.get('parsed_signal', {})
                    coin_symbol = parsed_signal.get('coin_symbol')
                    if not coin_symbol:
                        return {"status": "error", "message": f"Could not determine coin_symbol for trade ID {trade_row['id']}"}

                    symbol = f"{coin_symbol}USDT"
                    close_result = await self.trading_engine.close_position_at_market(symbol)

                    exit_price = close_result.get("fill_price", 0)
                    pnl = self._calculate_pnl(
                        entry_price=trade_row.get("entry_price", 0),
                        exit_price=exit_price,
                        position_size=trade_row.get("position_size", 0)
                    )

                    trade_updates = {
                        "status": "CLOSED",
                        "exit_price": exit_price,
                        "pnl_usd": pnl
                    }
                else:
                    trade_updates = {"status": "CLOSED"}

            elif action_type in ["take_profit_1", "take_profit_2"]:
                logger.info(f"Processing {action_type} for trade {trade_row['id']}")
                # For TP hits, we typically sell a portion and update stop loss
                # For now, just log the action - implement specific TP logic as needed
                trade_updates = {"status": "PARTIALLY_CLOSED"}

            elif action_type == "stop_loss_update":
                logger.info(f"Processing stop loss update for trade {trade_row['id']}")
                # Update stop loss order on exchange
                # For now, just log - implement stop loss update logic as needed
                pass

            elif action_type == "order_cancelled":
                logger.info(f"Processing order cancellation for trade {trade_row['id']}")
                trade_updates = {"status": "CANCELLED"}

            else:
                logger.info(f"Processing generic update for trade {trade_row['id']}: {action_type}")
                # No specific action needed for unknown updates

            # Update the trade in database if we have updates
            if trade_updates:
                success = await update_existing_trade(
                    trade_id=trade_row["id"],
                    updates=trade_updates
                )

                if success:
                    logger.info(f"Trade {trade_row['id']} updated successfully with: {trade_updates}")
                    return {"status": "success", "message": f"Update signal processed and trade updated: {parsed_action['action_description']}"}
                else:
                    return {"status": "error", "message": "Failed to update trade in database"}
            else:
                return {"status": "success", "message": f"Update signal processed: {parsed_action['action_description']}"}

        except Exception as e:
            error_msg = f"Error processing update signal: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return {"status": "error", "message": error_msg}

    def _calculate_pnl(self, entry_price: float, exit_price: float, position_size: float) -> float:
        """Calculate PnL in USD for a position"""
        if entry_price <= 0 or position_size <= 0:
            return 0.0

        # For long positions: (exit_price - entry_price) * position_size
        # This assumes position_size is in base currency units
        pnl = (exit_price - entry_price) * position_size
        return round(pnl, 2)

# Global bot instance
discord_bot = DiscordBot()