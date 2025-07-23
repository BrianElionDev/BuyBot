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
from datetime import datetime, timezone
from typing import Optional

# Add project root to the Python path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from dotenv import load_dotenv
from discord_bot.utils.trade_retry_utils import (
    initialize_clients,
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
    """Backfill PnL and exit prices for existing trades using actual Binance userTrades."""
    logging.info("--- Starting PnL and Exit Price Backfill (using Binance userTrades) ---")

    bot, supabase = initialize_clients()
    if not bot or not supabase:
        logging.error("Failed to initialize clients.")
        return

    binance_client = bot.binance_exchange.client
    if not binance_client:
        await bot.binance_exchange._init_client()
        binance_client = bot.binance_exchange.client
    if not binance_client:
        logging.error("Binance client is not initialized.")
        return

    try:
        page_size = 500
        offset = 0
        total_processed = 0
        while True:
            response = supabase.from_("trades").select("*").eq("status", "CLOSED").range(offset, offset + page_size - 1).execute()
            closed_trades = response.data or []
            if not closed_trades:
                break
            logging.info(f"Fetched {len(closed_trades)} closed trades (offset {offset})")
            for trade in closed_trades:
                trade_id = trade.get('id')
                if trade_id is None:
                    continue
                pnl = trade.get('pnl_usd') or trade.get('pnl')
                exit_price = trade.get('exit_price')
                binance_response = trade.get('binance_response', '')
                if (pnl not in [None, 0, 0.0]) and (exit_price not in [None, 0, 0.0]):
                    continue
                order_id, symbol = extract_order_info_from_binance_response(binance_response)
                if not order_id or not symbol:
                    logging.warning(f"Trade {trade_id} missing orderId or symbol, skipping")
                    continue
                logging.info(f"Processing trade {trade_id} ({symbol}) - orderId: {order_id}")
                try:
                    # Fetch all user trades for this symbol
                    user_trades = await binance_client.futures_account_trades(symbol=symbol, limit=1000)
                    # Filter for trades matching this orderId
                    matching_trades = [t for t in user_trades if str(t.get('orderId')) == str(order_id)]
                    if not matching_trades:
                        logging.warning(f"No userTrades found for trade {trade_id} orderId {order_id}")
                        continue
                    # Sum realizedPnl, get last price as exit_price
                    # realizedPnl from Binance is already the actual value (USD), not a percentage
                    total_realized_pnl = sum(float(t.get('realizedPnl', 0.0)) for t in matching_trades)
                    last_trade = matching_trades[-1]
                    exit_price_val = float(last_trade.get('price', 0.0))
                    # Update DB
                    updates = {}
                    if exit_price in [None, 0, 0.0] and exit_price_val > 0:
                        updates["exit_price"] = exit_price_val
                    # Always update pnl_usd with the actual value
                    if pnl in [None, 0, 0.0]:
                        updates["pnl_usd"] = total_realized_pnl
                    if updates:
                        updates["updated_at"] = datetime.now(timezone.utc).isoformat()
                        await update_trade_status(supabase, int(trade_id), updates)
                        logging.info(f"Trade {trade_id} updated - Exit Price: {exit_price_val}, PnL (USD): {total_realized_pnl}")
                except Exception as e:
                    logging.error(f"Error processing trade {trade_id}: {e}")
                await asyncio.sleep(0.5)
                total_processed += 1
            if len(closed_trades) < page_size:
                break
            offset += page_size
        logging.info(f"--- PnL and Exit Price Backfill Complete. Total processed: {total_processed} ---")
    except Exception as e:
        logging.error(f"Error during backfill: {e}", exc_info=True)
    finally:
        if bot and bot.binance_exchange:
            await bot.binance_exchange.close()
            logging.info("Binance client connection closed.")

async def main():
    await backfill_pnl_and_exit_prices()

if __name__ == "__main__":
    asyncio.run(main())