#!/usr/bin/env python3
"""
Backfill PnL and exit prices for existing trades.
This script processes trades that are closed but missing PnL or exit_price data.
"""

import asyncio
import logging
import os
import sys
import json
from datetime import datetime, timedelta, timezone
from typing import Optional

# Add project root to the Python path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from dotenv import load_dotenv
from discord_bot.utils.trade_retry_utils import (
    initialize_clients,
    calculate_pnl,
    update_trade_status
)

# --- Setup ---
load_dotenv()
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def extract_order_info_from_binance_response(binance_response: str) -> tuple[Optional[str], Optional[str]]:
    """
    Extract orderId and symbol from binance_response text field.
    The binance_response is stored as text but contains JSON-like structure.

    Args:
        binance_response: Text field from binance_response column

    Returns:
        tuple of (orderId, symbol) or (None, None) if parsing fails
    """
    try:
        if not binance_response or binance_response.strip() == '':
            return None, None

        # Handle different formats of binance_response
        if isinstance(binance_response, str):
            # Try to parse as JSON first
            try:
                response_data = json.loads(binance_response)
            except json.JSONDecodeError:
                # If it's not valid JSON, try to extract using regex patterns
                import re

                # Extract orderId - look for "orderId": number pattern
                order_id_match = re.search(r'"orderId"\s*:\s*(\d+)', binance_response)
                order_id = order_id_match.group(1) if order_id_match else None

                # Extract symbol - look for "symbol": "SYMBOL" pattern
                symbol_match = re.search(r'"symbol"\s*:\s*"([^"]+)"', binance_response)
                symbol = symbol_match.group(1) if symbol_match else None

                if order_id and symbol:
                    return order_id, symbol
                else:
                    logging.warning(f"Could not extract orderId or symbol from text response: {binance_response}")
                    return None, None
        else:
            # If it's already a dict (shouldn't happen but just in case)
            response_data = binance_response

        # Extract orderId and symbol from parsed data
        order_id = str(response_data.get('orderId', ''))
        symbol = response_data.get('symbol', '')

        if order_id and symbol:
            return order_id, symbol
        else:
            logging.warning(f"Missing orderId or symbol in binance_response: {binance_response}")
            return None, None

    except Exception as e:
        logging.error(f"Error extracting order info: {e}")
        return None, None

async def backfill_pnl_and_exit_prices():
    """Backfill PnL and exit prices for existing trades."""
    logging.info("--- Starting PnL and Exit Price Backfill ---")

    bot, supabase = initialize_clients()
    if not bot or not supabase:
        logging.error("Failed to initialize clients.")
        return

    try:
        # Find trades that are closed but missing PnL or exit_price
        response = supabase.from_("trades").select("*").eq("status", "CLOSED").execute()
        closed_trades = response.data or []

        logging.info(f"Found {len(closed_trades)} closed trades to check.")

        for trade in closed_trades:
            trade_id = trade.get('id')
            pnl = trade.get('pnl')
            exit_price = trade.get('exit_price')
            symbol = trade.get('coin_symbol')
            binance_response = trade.get('binance_response', '')

            # Skip if already has both PnL and exit_price
            if pnl is not None and exit_price is not None:
                continue

            # Skip if missing required fields
            if not trade_id:
                logging.warning(f"Trade missing trade_id")
                continue

            # Try to get symbol from binance_response if not in coin_symbol
            if not symbol and binance_response:
                _, extracted_symbol = extract_order_info_from_binance_response(binance_response)
                if extracted_symbol:
                    symbol = extracted_symbol

            if not symbol:
                logging.warning(f"Trade {trade_id} missing symbol, skipping")
                continue

            logging.info(f"Processing trade {trade_id} ({symbol}) - PnL: {pnl}, Exit Price: {exit_price}")

            try:
                # Get current price for the symbol
                current_price = await bot.price_service.get_price(str(symbol))
                if not current_price:
                    logging.warning(f"Could not get current price for {symbol}, skipping trade {trade_id}")
                    continue

                # Extract trade data
                parsed_signal = trade.get('parsed_signal', {})
                entry_prices = parsed_signal.get('entry_prices', [])
                position_type = parsed_signal.get('position_type', 'LONG')
                position_size = trade.get('position_size', 0)

                if not entry_prices or not position_size:
                    logging.warning(f"Trade {trade_id} missing entry price or position size")
                    continue

                entry_price = float(entry_prices[0])

                # Calculate PnL if missing
                if pnl is None:
                    pnl_percentage = calculate_pnl(entry_price, current_price, position_size, position_type)
                else:
                    pnl_percentage = pnl

                # Update database
                now = datetime.now(timezone.utc).isoformat()
                updates = {}

                if exit_price is None:
                    updates["exit_price"] = current_price

                if pnl is None:
                    updates["pnl"] = pnl_percentage

                if updates:
                    updates["updated_at"] = now
                    await update_trade_status(supabase, int(trade_id), updates)
                    logging.info(f"Trade {trade_id} updated - Exit Price: {current_price}, PnL: {pnl_percentage:.2f}%")

            except Exception as e:
                logging.error(f"Error processing trade {trade_id}: {e}")

            await asyncio.sleep(0.5)  # Rate limiting

        logging.info("--- PnL and Exit Price Backfill Complete ---")

    except Exception as e:
        logging.error(f"Error during backfill: {e}", exc_info=True)
    finally:
        if bot and bot.binance_exchange:
            await bot.binance_exchange.close()
            logging.info("Binance client connection closed.")

async def main():
    """Main function."""
    await backfill_pnl_and_exit_prices()

if __name__ == "__main__":
    asyncio.run(main())