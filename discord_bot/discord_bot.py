import asyncio
import logging
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field
from fastapi import HTTPException

from src.bot.trading_engine import TradingEngine
from .database import (
    find_trade_by_timestamp,
    find_trade_by_signal_id,
    update_existing_trade
)
from .discord_signal_parser import DiscordSignalParser

# Setup logging
logger = logging.getLogger(__name__)

class DiscordSignal(BaseModel):
    """Model for incoming Discord signals"""
    timestamp: str
    content: str  # This is a string, not a dict
    structured: str
    trader: Optional[str] = None
    trade: Optional[str] = None  # Reference to original trade signal_id
    discord_id: Optional[str] = None

class DiscordBot:
    def __init__(self):
        self.trading_engine = TradingEngine()
        self.signal_parser = DiscordSignalParser()
        logger.info("DiscordBot initialized with AI Signal Parser.")

    async def process_signal(self, signal_data: Dict[str, Any]) -> Dict[str, str]:
        """
        Process Discord trading signal and update existing database rows.

        Logic:
        - If signal has 'trade' field: This is a follow-up signal, find original by signal_id
        - If signal has no 'trade' field: This is initial signal, find by timestamp
        """
        try:
            # Validate and parse the signal
            signal = DiscordSignal(**signal_data)
            logger.info(f"Processing signal: {signal.structured}")

            # Determine signal type and find the corresponding trade
            if signal.trade:
                # Follow-up signal - find original trade by signal_id
                trade_row = await find_trade_by_signal_id(signal.trade)
                if not trade_row:
                    error_msg = f"No original trade found for signal_id: {signal.trade}"
                    logger.error(error_msg)
                    return {"status": "error", "message": error_msg}

                # Process as update signal
                return await self._process_update_signal(signal, trade_row)

            else:
                # Initial signal - find trade by timestamp
                trade_row = await find_trade_by_timestamp(signal.timestamp)
                if not trade_row:
                    clean_timestamp = signal.timestamp.replace('T', ' ').rstrip('Z')
                    error_msg = f"No existing trade found for timestamp: '{signal.timestamp}'. Query was performed using cleaned timestamp: '{clean_timestamp}'"
                    logger.error(error_msg)
                    return {"status": "error", "message": f"No existing trade found for timestamp: {signal.timestamp}"}

                # Process as initial execution signal
                return await self._process_initial_signal(signal, trade_row)

        except Exception as e:
            error_msg = f"Error processing signal: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return {"status": "error", "message": error_msg}

    async def _process_initial_signal(self, signal: DiscordSignal, trade_row: Dict[str, Any]) -> Dict[str, str]:
        """
        Process initial trading signal by parsing the content with AI
        and then executing the trade.
        """
        try:
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
            # Update database with failed status
            updates = {"status": "FAILED"}
            await update_existing_trade(trade_id=trade_row["id"], updates=updates)

            error_msg = f"Error executing initial trade: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return {"status": "error", "message": error_msg}

    async def _process_update_signal(self, signal: DiscordSignal, trade_row: Dict[str, Any]) -> Dict[str, str]:
        """
        Process follow-up signal (stop loss hit, position closed, etc.)
        Updates the existing trade row with new information.
        """
        try:
            content_lower = signal.content.lower()

            # Determine update type based on content
            if "stopped out" in content_lower or "stop loss" in content_lower:
                # Position was stopped out
                logger.info(f"Processing stop loss for trade {trade_row['id']}")

                # Close position on exchange if still active
                if trade_row.get("status") == "ACTIVE":
                    symbol = f"{trade_row['coin_symbol']}USDT"
                    close_result = await self.trading_engine.close_position_at_market(symbol)

                    exit_price = close_result.get("fill_price", 0)
                    pnl = self._calculate_pnl(
                        entry_price=trade_row.get("entry_price", 0),
                        exit_price=exit_price,
                        position_size=trade_row.get("position_size", 0)
                    )

                    updates = {
                        "status": "CLOSED",
                        "exit_price": exit_price,
                        "pnl_usd": pnl
                    }
                else:
                    # Trade already closed, just update status
                    updates = {"status": "CLOSED"}

            elif "closed" in content_lower or "exit" in content_lower:
                # Position was manually closed
                logger.info(f"Processing manual close for trade {trade_row['id']}")

                # Similar logic to stop loss
                if trade_row.get("status") == "ACTIVE":
                    symbol = f"{trade_row['coin_symbol']}USDT"
                    close_result = await self.trading_engine.close_position_at_market(symbol)

                    exit_price = close_result.get("fill_price", 0)
                    pnl = self._calculate_pnl(
                        entry_price=trade_row.get("entry_price", 0),
                        exit_price=exit_price,
                        position_size=trade_row.get("position_size", 0)
                    )

                    updates = {
                        "status": "CLOSED",
                        "exit_price": exit_price,
                        "pnl_usd": pnl
                    }
                else:
                    updates = {"status": "CLOSED"}

            else:
                # Generic update (might be status update, comment, etc.)
                logger.info(f"Processing generic update for trade {trade_row['id']}")
                updates = {}  # Could add timestamp or other metadata if needed

            # Update the database
            if updates:
                success = await update_existing_trade(
                    trade_id=trade_row["id"],
                    updates=updates
                )

                if success:
                    return {"status": "success", "message": f"Trade updated successfully"}
                else:
                    return {"status": "error", "message": "Failed to update trade in database"}
            else:
                return {"status": "success", "message": "Signal processed (no updates needed)"}

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