#!/usr/bin/env python3
"""
Simple Binance History Retrieval Script
Quick script to get order history, trade history, and transaction history from Binance.
"""

import os
import sys
import asyncio
import logging
import json
from datetime import datetime, timedelta, timezone
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

async def get_binance_history():
    """
    Get comprehensive Binance history including orders, trades, and transactions.
    """
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

        # Initialize exchange
        exchange = BinanceExchange(api_key=api_key, api_secret=api_secret, is_testnet=is_testnet)
        await exchange._init_client()

        logger.info("🚀 Starting Binance history retrieval...")

        # Define symbols to check (common ones)
        symbols = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'LINKUSDT']

        # Time range: last 30 days
        end_time = int(datetime.now(timezone.utc).timestamp() * 1000)
        start_time = int((datetime.now(timezone.utc) - timedelta(days=30)).timestamp() * 1000)

        logger.info(f"📅 Time range: {datetime.fromtimestamp(start_time/1000)} to {datetime.fromtimestamp(end_time/1000)}")
        logger.info(f"📊 Symbols: {', '.join(symbols)}")

        # Collect all data
        all_data = {
            'orders': {},
            'trades': {},
            'deposits': [],
            'withdrawals': [],
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

        # Get order history for each symbol
        logger.info("\n📋 Getting order history...")
        for symbol in symbols:
            try:
                orders = await exchange.get_order_history(symbol=symbol, limit=1000)
                all_data['orders'][symbol] = orders
                logger.info(f"  ✅ {symbol}: {len(orders)} orders")
            except Exception as e:
                logger.error(f"  ❌ {symbol}: Error getting orders - {e}")
                all_data['orders'][symbol] = []
            await asyncio.sleep(0.1)  # Rate limiting

        # Get trade history for each symbol
        logger.info("\n📈 Getting trade history...")
        for symbol in symbols:
            try:
                trades = await exchange.get_user_trades(symbol=symbol, limit=1000)
                all_data['trades'][symbol] = trades
                logger.info(f"  ✅ {symbol}: {len(trades)} trades")
            except Exception as e:
                logger.error(f"  ❌ {symbol}: Error getting trades - {e}")
                all_data['trades'][symbol] = []
            await asyncio.sleep(0.1)  # Rate limiting

        # Get deposit history
        logger.info("\n💰 Getting deposit history...")
        try:
            deposits = await exchange.get_deposit_history(start_time=start_time, end_time=end_time)
            all_data['deposits'] = deposits
            logger.info(f"  ✅ Deposits: {len(deposits)} records")
        except Exception as e:
            logger.error(f"  ❌ Error getting deposits - {e}")
            all_data['deposits'] = []

        # Get withdrawal history
        logger.info("\n💸 Getting withdrawal history...")
        try:
            withdrawals = await exchange.get_withdrawal_history(start_time=start_time, end_time=end_time)
            all_data['withdrawals'] = withdrawals
            logger.info(f"  ✅ Withdrawals: {len(withdrawals)} records")
        except Exception as e:
            logger.error(f"  ❌ Error getting withdrawals - {e}")
            all_data['withdrawals'] = []

        # Print summary
        logger.info("\n" + "="*60)
        logger.info("📊 BINANCE HISTORY SUMMARY")
        logger.info("="*60)

        total_orders = sum(len(orders) for orders in all_data['orders'].values())
        total_trades = sum(len(trades) for trades in all_data['trades'].values())

        logger.info(f"📋 Total Orders: {total_orders}")
        logger.info(f"📈 Total Trades: {total_trades}")
        logger.info(f"💰 Total Deposits: {len(all_data['deposits'])}")
        logger.info(f"💸 Total Withdrawals: {len(all_data['withdrawals'])}")

        # Show breakdown by symbol
        for symbol in symbols:
            orders_count = len(all_data['orders'].get(symbol, []))
            trades_count = len(all_data['trades'].get(symbol, []))
            if orders_count > 0 or trades_count > 0:
                logger.info(f"  {symbol}: {orders_count} orders, {trades_count} trades")

        logger.info("="*60)

        # Save to file
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"binance_history_{timestamp}.json"

        with open(filename, 'w') as f:
            json.dump(all_data, f, indent=2, default=str)

        logger.info(f"✅ Complete history saved to: {filename}")

        # Show sample data
        logger.info("\n📋 Sample Data:")

        # Sample order
        for symbol, orders in all_data['orders'].items():
            if orders:
                sample_order = orders[0]
                logger.info(f"  Order: {symbol} - ID {sample_order.get('orderId')} - {sample_order.get('type')} {sample_order.get('side')} {sample_order.get('origQty')} @ {sample_order.get('price', 'MARKET')}")
                break

        # Sample trade
        for symbol, trades in all_data['trades'].items():
            if trades:
                sample_trade = trades[0]
                logger.info(f"  Trade: {symbol} - ID {sample_trade.get('id')} - {sample_trade.get('side')} {sample_trade.get('qty')} @ {sample_trade.get('price')} (PnL: {sample_trade.get('realizedPnl', 'N/A')})")
                break

        # Sample deposit
        if all_data['deposits']:
            sample_deposit = all_data['deposits'][0]
            logger.info(f"  Deposit: {sample_deposit.get('coin')} - {sample_deposit.get('amount')} - Status: {sample_deposit.get('status')}")

        # Sample withdrawal
        if all_data['withdrawals']:
            sample_withdrawal = all_data['withdrawals'][0]
            logger.info(f"  Withdrawal: {sample_withdrawal.get('coin')} - {sample_withdrawal.get('amount')} - Status: {sample_withdrawal.get('status')}")

        return all_data

    except Exception as e:
        logger.error(f"❌ Fatal error: {e}")
        raise
    finally:
        if 'exchange' in locals():
            await exchange.close_client()

async def get_specific_symbol_history(symbol: str, days: int = 30):
    """
    Get history for a specific symbol.

    Args:
        symbol: Trading pair symbol (e.g., 'BTCUSDT')
        days: Number of days to look back
    """
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

        # Initialize exchange
        exchange = BinanceExchange(api_key=api_key, api_secret=api_secret, is_testnet=is_testnet)
        await exchange._init_client()

        logger.info(f"🚀 Getting history for {symbol} (last {days} days)...")

        # Time range
        end_time = int(datetime.now(timezone.utc).timestamp() * 1000)
        start_time = int((datetime.now(timezone.utc) - timedelta(days=days)).timestamp() * 1000)

        # Get orders
        orders = await exchange.get_order_history(symbol=symbol, limit=1000)
        logger.info(f"📋 Orders: {len(orders)}")

        # Get trades
        trades = await exchange.get_user_trades(symbol=symbol, limit=1000)
        logger.info(f"📈 Trades: {len(trades)}")

        # Save to file
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{symbol}_history_{timestamp}.json"

        data = {
            'symbol': symbol,
            'orders': orders,
            'trades': trades,
            'metadata': {
                'retrieved_at': datetime.now(timezone.utc).isoformat(),
                'time_range': {
                    'start': datetime.fromtimestamp(start_time/1000).isoformat(),
                    'end': datetime.fromtimestamp(end_time/1000).isoformat()
                },
                'days': days
            }
        }

        with open(filename, 'w') as f:
            json.dump(data, f, indent=2, default=str)

        logger.info(f"✅ {symbol} history saved to: {filename}")

        return data

    except Exception as e:
        logger.error(f"❌ Error getting {symbol} history: {e}")
        raise
    finally:
        if 'exchange' in locals():
            await exchange.close_client()

async def main():
    """Main function."""
    import argparse

    parser = argparse.ArgumentParser(description='Get Binance history')
    parser.add_argument('--symbol', type=str, help='Specific symbol to get history for (e.g., BTCUSDT)')
    parser.add_argument('--days', type=int, default=30, help='Number of days to look back (default: 30)')

    args = parser.parse_args()

    if args.symbol:
        await get_specific_symbol_history(args.symbol, args.days)
    else:
        await get_binance_history()

if __name__ == "__main__":
    asyncio.run(main())
