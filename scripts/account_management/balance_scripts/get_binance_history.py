#!/usr/bin/env python3
"""
Binance History Retrieval Script
Retrieves order history, trade history, and transaction history from Binance API.
"""

import os
import sys
import asyncio
import logging
import json
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional
from dotenv import load_dotenv

# Add the project root to Python path
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(script_dir))
sys.path.insert(0, project_root)

from config import settings
from src.exchange.binance_exchange import BinanceExchange

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class BinanceHistoryRetriever:
    """
    Comprehensive Binance history retriever for orders, trades, and transactions.
    """

    def __init__(self, api_key: str, api_secret: str, is_testnet: bool = False):
        self.exchange = BinanceExchange(api_key=api_key, api_secret=api_secret, is_testnet=is_testnet)
        self.history_data = {
            'orders': {},
            'trades': {},
            'deposits': [],
            'withdrawals': []
        }

    async def initialize(self):
        """Initialize the exchange client."""
        await self.exchange._init_client()
        logger.info("✅ Binance client initialized")

    async def get_order_history(self, symbol: str, limit: int = 1000,
                               start_time: Optional[int] = None,
                               end_time: Optional[int] = None) -> List[Dict]:
        """
        Get order history for a specific symbol.

        Args:
            symbol: Trading pair symbol (e.g., 'BTCUSDT')
            limit: Maximum number of orders to retrieve (max 1000)
            start_time: Start time in milliseconds since epoch
            end_time: End time in milliseconds since epoch

        Returns:
            List of order dictionaries
        """
        try:
            logger.info(f"📋 Getting order history for {symbol}...")

            # Get all orders for the symbol
            orders = await self.exchange.get_order_history(
                symbol=symbol,
                limit=limit,
                start_time=start_time,
                end_time=end_time
            )

            logger.info(f"✅ Retrieved {len(orders)} orders for {symbol}")
            return orders

        except Exception as e:
            logger.error(f"❌ Error getting order history for {symbol}: {e}")
            return []

    async def get_trade_history(self, symbol: str, limit: int = 1000,
                               start_time: Optional[int] = None,
                               end_time: Optional[int] = None) -> List[Dict]:
        """
        Get trade history for a specific symbol.

        Args:
            symbol: Trading pair symbol (e.g., 'BTCUSDT')
            limit: Maximum number of trades to retrieve (max 1000)
            start_time: Start time in milliseconds since epoch
            end_time: End time in milliseconds since epoch

        Returns:
            List of trade dictionaries
        """
        try:
            logger.info(f"📋 Getting trade history for {symbol}...")

            # Get user trades for the symbol
            trades = await self.exchange.get_user_trades(
                symbol=symbol,
                limit=limit,
                start_time=start_time,
                end_time=end_time
            )

            logger.info(f"✅ Retrieved {len(trades)} trades for {symbol}")
            return trades

        except Exception as e:
            logger.error(f"❌ Error getting trade history for {symbol}: {e}")
            return []

    async def get_deposit_history(self, coin: Optional[str] = None,
                                 start_time: Optional[int] = None,
                                 end_time: Optional[int] = None,
                                 limit: int = 1000) -> List[Dict]:
        """
        Get deposit history.

        Args:
            coin: Specific coin to filter by (optional)
            start_time: Start time in milliseconds since epoch
            end_time: End time in milliseconds since epoch
            limit: Maximum number of deposits to retrieve

        Returns:
            List of deposit dictionaries
        """
        try:
            logger.info("📋 Getting deposit history...")

            # Get deposit history
            deposits = await self.exchange.get_deposit_history(
                coin=coin,
                start_time=start_time,
                end_time=end_time,
                limit=limit
            )

            logger.info(f"✅ Retrieved {len(deposits)} deposits")
            return deposits

        except Exception as e:
            logger.error(f"❌ Error getting deposit history: {e}")
            return []

    async def get_withdrawal_history(self, coin: Optional[str] = None,
                                   start_time: Optional[int] = None,
                                   end_time: Optional[int] = None,
                                   limit: int = 1000) -> List[Dict]:
        """
        Get withdrawal history.

        Args:
            coin: Specific coin to filter by (optional)
            start_time: Start time in milliseconds since epoch
            end_time: End time in milliseconds since epoch
            limit: Maximum number of withdrawals to retrieve

        Returns:
            List of withdrawal dictionaries
        """
        try:
            logger.info("📋 Getting withdrawal history...")

            # Get withdrawal history
            withdrawals = await self.exchange.get_withdrawal_history(
                coin=coin,
                start_time=start_time,
                end_time=end_time,
                limit=limit
            )

            logger.info(f"✅ Retrieved {len(withdrawals)} withdrawals")
            return withdrawals

        except Exception as e:
            logger.error(f"❌ Error getting withdrawal history: {e}")
            return []

    async def get_all_symbols_history(self, symbols: List[str],
                                    start_time: Optional[int] = None,
                                    end_time: Optional[int] = None) -> Dict:
        """
        Get order and trade history for multiple symbols.

        Args:
            symbols: List of trading pair symbols
            start_time: Start time in milliseconds since epoch
            end_time: End time in milliseconds since epoch

        Returns:
            Dictionary containing orders and trades for all symbols
        """
        all_data = {
            'orders': {},
            'trades': {},
            'summary': {
                'total_orders': 0,
                'total_trades': 0,
                'symbols_processed': 0
            }
        }

        for symbol in symbols:
            logger.info(f"\n🔄 Processing {symbol}...")

            # Get orders for this symbol
            orders = await self.get_order_history(symbol, start_time=start_time, end_time=end_time)
            all_data['orders'][symbol] = orders
            all_data['summary']['total_orders'] += len(orders)

            # Get trades for this symbol
            trades = await self.get_trade_history(symbol, start_time=start_time, end_time=end_time)
            all_data['trades'][symbol] = trades
            all_data['summary']['total_trades'] += len(trades)

            all_data['summary']['symbols_processed'] += 1

            # Rate limiting
            await asyncio.sleep(0.1)

        return all_data

    def save_history_to_file(self, data: Dict, filename: str):
        """
        Save history data to a JSON file.

        Args:
            data: History data to save
            filename: Output filename
        """
        try:
            with open(filename, 'w') as f:
                json.dump(data, f, indent=2, default=str)
            logger.info(f"✅ History data saved to {filename}")
        except Exception as e:
            logger.error(f"❌ Error saving history data: {e}")

    def print_summary(self, data: Dict):
        """
        Print a summary of the retrieved history data.

        Args:
            data: History data to summarize
        """
        logger.info("\n" + "="*60)
        logger.info("📊 BINANCE HISTORY SUMMARY")
        logger.info("="*60)

        if 'orders' in data:
            total_orders = sum(len(orders) for orders in data['orders'].values())
            logger.info(f"📋 Total Orders: {total_orders}")
            for symbol, orders in data['orders'].items():
                if orders:
                    logger.info(f"  - {symbol}: {len(orders)} orders")

        if 'trades' in data:
            total_trades = sum(len(trades) for trades in data['trades'].values())
            logger.info(f"📈 Total Trades: {total_trades}")
            for symbol, trades in data['trades'].items():
                if trades:
                    logger.info(f"  - {symbol}: {len(trades)} trades")

        if 'deposits' in data:
            logger.info(f"💰 Total Deposits: {len(data['deposits'])}")

        if 'withdrawals' in data:
            logger.info(f"💸 Total Withdrawals: {len(data['withdrawals'])}")

        if 'summary' in data:
            summary = data['summary']
            logger.info(f"🔄 Symbols Processed: {summary.get('symbols_processed', 0)}")

        logger.info("="*60)

    async def close(self):
        """Close the exchange client."""
        await self.exchange.close_client()
        logger.info("🔒 Binance client closed")

async def main():
    """Main function to demonstrate usage."""
    try:
        # Load environment variables
        load_dotenv()

        # Get credentials
        api_key = settings.BINANCE_API_KEY
        api_secret = settings.BINANCE_API_SECRET
        is_testnet = settings.BINANCE_TESTNET

        if not all([api_key, api_secret]):
            logger.error("❌ Missing Binance API credentials")
            return

        # Initialize retriever
        retriever = BinanceHistoryRetriever(api_key, api_secret, is_testnet)
        await retriever.initialize()

        # Define symbols to retrieve history for
        symbols = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'LINKUSDT']

        # Define time range (last 30 days)
        end_time = int(datetime.now(timezone.utc).timestamp() * 1000)
        start_time = int((datetime.now(timezone.utc) - timedelta(days=30)).timestamp() * 1000)

        logger.info("🚀 Starting Binance history retrieval...")
        logger.info(f"📅 Time range: {datetime.fromtimestamp(start_time/1000)} to {datetime.fromtimestamp(end_time/1000)}")
        logger.info(f"📊 Symbols: {', '.join(symbols)}")

        # Get order and trade history for all symbols
        history_data = await retriever.get_all_symbols_history(
            symbols=symbols,
            start_time=start_time,
            end_time=end_time
        )

        # Get transaction history
        logger.info("\n💰 Getting transaction history...")
        deposits = await retriever.get_deposit_history(start_time=start_time, end_time=end_time)
        withdrawals = await retriever.get_withdrawal_history(start_time=start_time, end_time=end_time)

        # Combine all data
        complete_history = {
            **history_data,
            'deposits': deposits,
            'withdrawals': withdrawals,
            'metadata': {
                'retrieved_at': datetime.now(timezone.utc).isoformat(),
                'time_range': {
                    'start': datetime.fromtimestamp(start_time/1000).isoformat(),
                    'end': datetime.fromtimestamp(end_time/1000).isoformat()
                },
                'symbols': symbols,
                'is_testnet': is_testnet
            }
        }

        # Print summary
        retriever.print_summary(complete_history)

        # Save to file
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"binance_history_{timestamp}.json"
        retriever.save_history_to_file(complete_history, filename)

        # Print sample data
        logger.info("\n📋 Sample Order Data:")
        for symbol, orders in complete_history['orders'].items():
            if orders:
                sample_order = orders[0]
                logger.info(f"  {symbol}: Order ID {sample_order.get('orderId')} - {sample_order.get('type')} {sample_order.get('side')} {sample_order.get('origQty')} @ {sample_order.get('price', 'MARKET')}")
                break

        logger.info("\n📈 Sample Trade Data:")
        for symbol, trades in complete_history['trades'].items():
            if trades:
                sample_trade = trades[0]
                logger.info(f"  {symbol}: Trade ID {sample_trade.get('id')} - {sample_trade.get('side')} {sample_trade.get('qty')} @ {sample_trade.get('price')} (PnL: {sample_trade.get('realizedPnl', 'N/A')})")
                break

        logger.info(f"\n✅ Complete history saved to: {filename}")

    except Exception as e:
        logger.error(f"❌ Fatal error: {e}")
        raise
    finally:
        if 'retriever' in locals():
            await retriever.close()

if __name__ == "__main__":
    asyncio.run(main())
