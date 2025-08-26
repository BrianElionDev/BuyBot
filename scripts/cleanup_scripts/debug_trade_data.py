#!/usr/bin/env python3
"""
Script to debug trade data and identify what's missing from trades that are failing.
"""

import asyncio
import json
import logging
from supabase import create_client, Client
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class TradeDataDebugger:
    def __init__(self):
        self.supabase_url = os.getenv('SUPABASE_URL')
        self.supabase_key = os.getenv('SUPABASE_KEY')

        if not self.supabase_url or not self.supabase_key:
            raise ValueError("Missing SUPABASE_URL or SUPABASE_KEY environment variables")

        self.supabase: Client = create_client(self.supabase_url, self.supabase_key)

    async def debug_failing_trades(self):
        """Debug trades that are failing due to missing data."""
        logger.info("Debugging failing trades...")

        # Get the specific trade IDs from the logs
        failing_trade_ids = [31331, 31329, 31258, 31327, 31336, 31338]

        for trade_id in failing_trade_ids:
            await self.debug_single_trade(trade_id)

    async def debug_single_trade(self, trade_id: int):
        """Debug a single trade to see what data is missing."""
        try:
            response = self.supabase.from_("trades").select("*").eq("id", trade_id).execute()

            if not response.data:
                logger.warning(f"Trade {trade_id} not found")
                return

            trade = response.data[0]

            logger.info(f"\n=== Trade {trade_id} Debug ===")
            logger.info(f"discord_id: {trade.get('discord_id')}")
            logger.info(f"content: {trade.get('content', 'N/A')[:100]}...")
            logger.info(f"coin_symbol: {trade.get('coin_symbol')}")
            logger.info(f"position_size: {trade.get('position_size')}")
            logger.info(f"status: {trade.get('status')}")
            logger.info(f"order_status: {trade.get('order_status')}")
            logger.info(f"signal_type: {trade.get('signal_type')}")
            logger.info(f"entry_price: {trade.get('entry_price')}")
            logger.info(f"binance_entry_price: {trade.get('binance_entry_price')}")
            logger.info(f"exchange_order_id: {trade.get('exchange_order_id')}")
            logger.info(f"parsed_signal: {trade.get('parsed_signal')}")
            logger.info(f"binance_response: {trade.get('binance_response')}")
            logger.info(f"created_at: {trade.get('created_at')}")
            logger.info(f"updated_at: {trade.get('updated_at')}")

            # Check if parsed_signal exists and what it contains
            parsed_signal = trade.get('parsed_signal')
            if parsed_signal:
                try:
                    if isinstance(parsed_signal, str):
                        parsed_data = json.loads(parsed_signal)
                    else:
                        parsed_data = parsed_signal

                    logger.info(f"Parsed signal data:")
                    logger.info(f"  coin_symbol: {parsed_data.get('coin_symbol')}")
                    logger.info(f"  position_type: {parsed_data.get('position_type')}")
                    logger.info(f"  order_type: {parsed_data.get('order_type')}")
                    logger.info(f"  entry_prices: {parsed_data.get('entry_prices')}")
                    logger.info(f"  stop_loss: {parsed_data.get('stop_loss')}")
                    logger.info(f"  take_profits: {parsed_data.get('take_profits')}")
                except Exception as e:
                    logger.error(f"Error parsing parsed_signal: {e}")
            else:
                logger.warning("No parsed_signal found")

            # Check binance_response
            binance_response = trade.get('binance_response')
            if binance_response:
                try:
                    if isinstance(binance_response, str):
                        binance_data = json.loads(binance_response)
                    else:
                        binance_data = binance_response

                    logger.info(f"Binance response data:")
                    logger.info(f"  orderId: {binance_data.get('orderId')}")
                    logger.info(f"  status: {binance_data.get('status')}")
                    logger.info(f"  executedQty: {binance_data.get('executedQty')}")
                    logger.info(f"  avgPrice: {binance_data.get('avgPrice')}")
                except Exception as e:
                    logger.error(f"Error parsing binance_response: {e}")
            else:
                logger.warning("No binance_response found")

            logger.info("=" * 50)

        except Exception as e:
            logger.error(f"Error debugging trade {trade_id}: {e}")

    async def find_trades_with_missing_data(self):
        """Find trades that have missing critical data."""
        logger.info("Finding trades with missing critical data...")

        try:
            # Find trades with missing coin_symbol
            response = self.supabase.from_("trades").select("id,discord_id,coin_symbol,status,order_status").is_("coin_symbol", "null").execute()

            if response.data:
                logger.warning(f"Found {len(response.data)} trades with missing coin_symbol:")
                for trade in response.data[:10]:  # Show first 10
                    logger.warning(f"  Trade {trade['id']}: discord_id={trade['discord_id']}, status={trade['status']}, order_status={trade['order_status']}")
            else:
                logger.info("No trades found with missing coin_symbol")

            # Find trades with position_size = 0
            response = self.supabase.from_("trades").select("id,discord_id,position_size,status,order_status").eq("position_size", 0).execute()

            if response.data:
                logger.warning(f"Found {len(response.data)} trades with position_size = 0:")
                for trade in response.data[:10]:  # Show first 10
                    logger.warning(f"  Trade {trade['id']}: discord_id={trade['discord_id']}, position_size={trade['position_size']}, status={trade['status']}, order_status={trade['order_status']}")
            else:
                logger.info("No trades found with position_size = 0")

        except Exception as e:
            logger.error(f"Error finding trades with missing data: {e}")

async def main():
    """Main function."""
    try:
        debugger = TradeDataDebugger()

        # Debug specific failing trades
        await debugger.debug_failing_trades()

        # Find trades with missing data
        await debugger.find_trades_with_missing_data()

    except Exception as e:
        logger.error(f"Error in main: {e}")

if __name__ == "__main__":
    asyncio.run(main())
