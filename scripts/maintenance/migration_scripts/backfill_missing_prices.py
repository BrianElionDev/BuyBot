#!/usr/bin/env python3
"""
Script to backfill missing binance_entry_price and exit_price for trades
that were executed but not properly updated by the WebSocket due to the truncation issue.
"""

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

import asyncio
import logging
import json
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional

from discord_bot.database import DatabaseManager
from src.exchange.binance_exchange import BinanceExchange

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class PriceBackfillManager:
    """Manages backfilling of missing prices for executed trades (unified)."""

    def __init__(self):
        """Initialize the price backfill manager."""
        self.db_manager = DatabaseManager()
        self.binance_exchange = BinanceExchange()

    async def find_trades_with_missing_prices(self, days_back: int = 7) -> list:
        """
        Find trades that have been executed but are missing entry_price or exit_price.

        Args:
            days_back: Number of days to look back

        Returns:
            List of trades with missing prices
        """
        try:
            cutoff_date = datetime.now(timezone.utc) - timedelta(days=days_back)
            cutoff_iso = cutoff_date.isoformat()

            # Find trades with exchange_order_id but missing prices
            response = self.db_manager.supabase.from_("trades").select(
                "id, discord_id, exchange_order_id, stop_loss_order_id, status, "
                "entry_price, exit_price, exchange_response, binance_response, created_at"
            ).not_.is_("exchange_order_id", "null").gte("created_at", cutoff_iso).execute()

            missing_prices_trades = []

            for trade in response.data:
                entry_price = trade.get('entry_price')
                exit_price = trade.get('exit_price')

                # Check if prices are missing (0, None, or empty string)
                missing_entry = not entry_price or float(entry_price or 0) == 0
                missing_exit = not exit_price or float(exit_price or 0) == 0

                if missing_entry or missing_exit:
                    missing_prices_trades.append({
                        **trade,
                        'missing_entry': missing_entry,
                        'missing_exit': missing_exit
                    })

            logger.info(f"Found {len(missing_prices_trades)} trades with missing prices")
            return missing_prices_trades

        except Exception as e:
            logger.error(f"Error finding trades with missing prices: {e}")
            return []

    async def get_order_details_from_binance(self, order_id: str, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Get order details from Binance API.

        Args:
            order_id: Binance order ID
            symbol: Trading symbol (e.g., 'BTCUSDT')

        Returns:
            Order details from Binance or None if not found
        """
        try:
            # Get order details from Binance
            order_details = await self.binance_exchange.get_order(symbol, order_id)

            if order_details and order_details.get('status') == 'FILLED':
                return order_details
            else:
                logger.warning(f"Order {order_id} not found or not filled on Binance")
                return None

        except Exception as e:
            logger.error(f"Error getting order details for {order_id}: {e}")
            return None

    async def extract_prices_from_order_details(self, order_details: Dict[str, Any]) -> Dict[str, float]:
        """
        Extract entry and exit prices from Binance order details.

        Args:
            order_details: Order details from Binance API

        Returns:
            Dictionary with entry_price and exit_price
        """
        try:
            avg_price = float(order_details.get('avgPrice', 0))
            side = order_details.get('side', '').upper()

            # Determine if this is an entry or exit order
            reduce_only = order_details.get('reduceOnly', False)
            close_position = order_details.get('closePosition', False)

            is_exit_order = reduce_only or close_position

            if is_exit_order:
                return {
                    'entry_price': 0.0,
                    'exit_price': avg_price if avg_price > 0 else 0.0
                }
            else:
                return {
                    'entry_price': avg_price if avg_price > 0 else 0.0,
                    'exit_price': 0.0
                }

        except Exception as e:
            logger.error(f"Error extracting prices from order details: {e}")
            return {'entry_price': 0.0, 'exit_price': 0.0}

    async def update_trade_prices(self, trade_id: int, entry_price: float, exit_price: float) -> bool:
        """
        Update trade with the correct prices.

        Args:
            trade_id: Database trade ID
            entry_price: Entry price from Binance
            exit_price: Exit price from Binance

        Returns:
            True if update was successful
        """
        try:
            updates = {}

            if entry_price > 0:
                updates['entry_price'] = float(entry_price)
                logger.info(f"Updated trade {trade_id} with entry price: {entry_price}")

            if exit_price > 0:
                updates['exit_price'] = float(exit_price)
                logger.info(f"Updated trade {trade_id} with exit price: {exit_price}")

            if updates:
                updates['updated_at'] = datetime.now(timezone.utc).isoformat()
                success = await self.db_manager.update_existing_trade(trade_id, updates)
                return success

            return True

        except Exception as e:
            logger.error(f"Error updating trade {trade_id}: {e}")
            return False

    async def backfill_missing_prices(self, days_back: int = 7) -> Dict[str, int]:
        """
        Backfill missing prices for executed trades.

        Args:
            days_back: Number of days to look back

        Returns:
            Dictionary with statistics about the backfill operation
        """
        stats = {
            'total_trades_checked': 0,
            'trades_updated': 0,
            'trades_failed': 0,
            'entry_prices_filled': 0,
            'exit_prices_filled': 0
        }

        try:
            # Find trades with missing prices
            trades = await self.find_trades_with_missing_prices(days_back)
            stats['total_trades_checked'] = len(trades)

            for trade in trades:
                trade_id = trade['id']
                order_id = trade['exchange_order_id']
                discord_id = trade['discord_id']

                logger.info(f"Processing trade {trade_id} (Order: {order_id}, Discord: {discord_id})")

                try:
                    # Determine symbol from discord_id or other fields
                    # This might need adjustment based on your data structure
                    symbol = self._extract_symbol_from_trade(trade)

                    if not symbol:
                        logger.warning(f"Could not determine symbol for trade {trade_id}")
                        stats['trades_failed'] += 1
                        continue

                    # Get order details from Binance
                    order_details = await self.get_order_details_from_binance(order_id, symbol)

                    if not order_details:
                        logger.warning(f"Could not get order details for trade {trade_id}")
                        stats['trades_failed'] += 1
                        continue

                    # Extract prices from order details
                    prices = await self.extract_prices_from_order_details(order_details)

                    # Update trade with correct prices
                    success = await self.update_trade_prices(
                        trade_id,
                        prices['entry_price'],
                        prices['exit_price']
                    )

                    if success:
                        stats['trades_updated'] += 1
                        if prices['entry_price'] > 0:
                            stats['entry_prices_filled'] += 1
                        if prices['exit_price'] > 0:
                            stats['exit_prices_filled'] += 1
                    else:
                        stats['trades_failed'] += 1

                    # Add small delay to avoid rate limiting
                    await asyncio.sleep(0.1)

                except Exception as e:
                    logger.error(f"Error processing trade {trade_id}: {e}")
                    stats['trades_failed'] += 1

            return stats

        except Exception as e:
            logger.error(f"Error in backfill operation: {e}")
            return stats

    def _extract_symbol_from_trade(self, trade: Dict[str, Any]) -> Optional[str]:
        """
        Extract trading symbol from trade data.

        Args:
            trade: Trade data from database

        Returns:
            Trading symbol (e.g., 'BTCUSDT') or None
        """
        try:
            # Try to extract symbol from exchange_response (fallback to legacy binance_response)
            raw = trade.get('exchange_response') or trade.get('binance_response', '')
            if raw:
                try:
                    response_data = json.loads(raw) if isinstance(raw, str) else raw
                    symbol = response_data.get('symbol')
                    if symbol:
                        return symbol
                except json.JSONDecodeError:
                    pass

            # Try to extract from discord_id or other fields
            # This is a fallback - you might need to adjust based on your data structure
            discord_id = trade.get('discord_id', '')

            # Common patterns in your data
            if 'BTC' in str(discord_id):
                return 'BTCUSDT'
            elif 'ETH' in str(discord_id):
                return 'ETHUSDT'
            elif 'LINK' in str(discord_id):
                return 'LINKUSDT'

            return None

        except Exception as e:
            logger.error(f"Error extracting symbol from trade: {e}")
            return None

async def main():
    """Main function to run the price backfill."""
    logger.info("Starting price backfill for missing entry_price and exit_price")

    backfill_manager = PriceBackfillManager()

    # Run backfill for last 7 days
    stats = await backfill_manager.backfill_missing_prices(days_back=7)

    logger.info("=== Backfill Statistics ===")
    logger.info(f"Total trades checked: {stats['total_trades_checked']}")
    logger.info(f"Trades updated: {stats['trades_updated']}")
    logger.info(f"Trades failed: {stats['trades_failed']}")
    logger.info(f"Entry prices filled: {stats['entry_prices_filled']}")
    logger.info(f"Exit prices filled: {stats['exit_prices_filled']}")

    logger.info("Price backfill completed!")

if __name__ == "__main__":
    asyncio.run(main())
