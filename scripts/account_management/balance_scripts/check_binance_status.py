#!/usr/bin/env python3
"""
Binance Status Checker
Checks open orders and positions on Binance Futures
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Dict, List, Optional

import sys
import os

script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(os.path.dirname(script_dir)))
sys.path.insert(0, project_root)

from config.settings import *
from src.exchange import BinanceExchange

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class BinanceStatusChecker:
    def __init__(self):
        self.binance_exchange = None

    async def initialize(self):
        """Initialize the Binance exchange connection"""
        try:
            # Get credentials from environment variables
            api_key = BINANCE_API_KEY
            api_secret = BINANCE_API_SECRET
            is_testnet = BINANCE_TESTNET

            if not api_key or not api_secret:
                logger.error("Binance API credentials not found in environment variables!")
                logger.error("Please set BINANCE_API_KEY and BINANCE_API_SECRET")
                return False

            self.binance_exchange = BinanceExchange(api_key, api_secret, is_testnet)
            await self.binance_exchange._init_client()

            logger.info(f"Connected to Binance {'Testnet' if is_testnet else 'Mainnet'}")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize Binance connection: {e}")
            return False

    async def get_open_orders(self) -> List[Dict]:
        """Get all open orders"""
        try:
            if not self.binance_exchange:
                logger.error("Binance exchange not initialized")
                return []

            orders = await self.binance_exchange.get_all_open_futures_orders()
            logger.info(f"Found {len(orders)} open orders")
            # Sort by time (latest first) - time comes as integer timestamp from Binance API
            sorted_orders = sorted(orders, key=lambda x: int(x.get('time', 0)), reverse=True)
            return sorted_orders

        except Exception as e:
            logger.error(f"Error fetching open orders: {e}")
            return []

    async def get_order_details(self, symbol: str, order_id: str) -> Optional[Dict]:
        """Get detailed information about a specific order"""
        try:
            if not self.binance_exchange:
                return None

            order_details = await self.binance_exchange.get_order_status(symbol, order_id)
            return order_details

        except Exception as e:
            logger.error(f"Error fetching order details for {symbol} {order_id}: {e}")
            return None

    async def get_recent_trades(self, symbol: str, limit: int = 10) -> List[Dict]:
        """Get recent trades for a symbol"""
        try:
            if not self.binance_exchange:
                return []

            trades = await self.binance_exchange.get_user_trades(symbol=symbol, limit=limit)
            return trades

        except Exception as e:
            logger.error(f"Error fetching recent trades for {symbol}: {e}")
            return []

    async def get_positions(self) -> List[Dict]:
        """Get all positions"""
        try:
            if not self.binance_exchange:
                logger.error("Binance exchange not initialized")
                return []

            positions = await self.binance_exchange.get_futures_position_information()

            # Filter out positions with zero size
            active_positions = [
                pos for pos in positions
                if float(pos.get('positionAmt', 0)) != 0
            ]

            logger.info(f"Found {len(active_positions)} active positions out of {len(positions)} total")
            return active_positions

        except Exception as e:
            logger.error(f"Error fetching positions: {e}")
            return []

    async def get_account_balance(self) -> Dict:
        """Get account balance"""
        try:
            if not self.binance_exchange:
                logger.error("Binance exchange not initialized")
                return {}

            balance = await self.binance_exchange.get_account_balances()
            return balance

        except Exception as e:
            logger.error(f"Error fetching account balance: {e}")
            return {}

    async def get_comprehensive_account_info(self) -> Dict:
        """Get comprehensive account information including leverage settings"""
        try:
            if not self.binance_exchange:
                logger.error("Binance exchange not initialized")
                return {}

            account_info = await self.binance_exchange.get_futures_account_info()
            return account_info

        except Exception as e:
            logger.error(f"Error fetching comprehensive account info: {e}")
            return {}

    def format_order(self, order: Dict) -> Dict:
        """Format order data for display"""
        return {
            'symbol': order.get('symbol'),
            'orderId': order.get('orderId'),
            'clientOrderId': order.get('clientOrderId', 'N/A'),
            'side': order.get('side'),
            'type': order.get('type'),
            'quantity': float(order.get('origQty', 0)),
            'price': float(order.get('price', 0)),
            'stopPrice': float(order.get('stopPrice', 0)) if order.get('stopPrice') else None,
            'status': order.get('status'),
            'time': datetime.fromtimestamp(int(order.get('time', 0)) / 1000).strftime('%Y-%m-%d %H:%M:%S'),
            'reduceOnly': order.get('reduceOnly', False),
            'workingType': order.get('workingType', 'N/A'),
            'priceProtect': order.get('priceProtect', False),
            'goodTillDate': order.get('goodTillDate', 'N/A'),
            'timeInForce': order.get('timeInForce', 'N/A')
        }

    def format_position(self, position: Dict) -> Dict:
        """Format position data for display"""
        position_amt = float(position.get('positionAmt', 0))
        entry_price = float(position.get('entryPrice', 0))
        mark_price = float(position.get('markPrice', 0))
        unrealized_pnl = float(position.get('unRealizedProfit', 0))
        notional = float(position.get('notional', 0))
        isolated_margin = float(position.get('isolatedMargin', 0))

        # Calculate PnL percentage
        pnl_percentage = 0
        if entry_price > 0 and position_amt != 0:
            if position_amt > 0:  # Long position
                pnl_percentage = ((mark_price - entry_price) / entry_price) * 100
            else:  # Short position
                pnl_percentage = ((entry_price - mark_price) / entry_price) * 100

        return {
            'symbol': position.get('symbol'),
            'side': 'LONG' if position_amt > 0 else 'SHORT',
            'size': abs(position_amt),
            'entryPrice': entry_price,
            'markPrice': mark_price,
            'unrealizedPnl': unrealized_pnl,
            'pnlPercentage': round(pnl_percentage, 2),
            'liquidationPrice': float(position.get('liquidationPrice', 0)),
            'leverage': int(position.get('leverage', 1)),
            'marginType': position.get('marginType', 'isolated'),
            'notional': notional,
            'isolatedMargin': isolated_margin,
            'positionSide': position.get('positionSide', 'BOTH'),
            'isAutoAddMargin': position.get('isAutoAddMargin', False)
        }

    def display_orders(self, orders: List[Dict]):
        """Display open orders in a formatted table"""
        if not orders:
            print("\n📋 No open orders found")
            return

        print(f"\n📋 Open Orders ({len(orders)}):")
        print("=" * 160)
        print(f"{'Symbol':<12} {'Side':<6} {'Type':<12} {'Quantity':<12} {'Price':<12} {'Stop Price':<12} {'Status':<10} {'Client ID':<15} {'Time':<20}")
        print("-" * 160)

        for order in orders:
            formatted = self.format_order(order)
            client_id = formatted['clientOrderId'][:14] if formatted['clientOrderId'] != 'N/A' else 'N/A'
            print(f"{formatted['symbol']:<12} {formatted['side']:<6} {formatted['type']:<12} "
                  f"{formatted['quantity']:<12.4f} {formatted['price']:<12.4f} "
                  f"{formatted['stopPrice'] or 'N/A':<12} {formatted['status']:<10} {client_id:<15} {formatted['time']:<20}")

    def display_order_details(self, order: Dict, details: Optional[Dict] = None):
        """Display detailed order information"""
        formatted = self.format_order(order)

        print(f"\n🔍 Order Details for {formatted['symbol']}:")
        print("=" * 60)
        print(f"Order ID: {formatted['orderId']}")
        print(f"Client Order ID: {formatted['clientOrderId']}")
        print(f"Symbol: {formatted['symbol']}")
        print(f"Side: {formatted['side']}")
        print(f"Type: {formatted['type']}")
        print(f"Status: {formatted['status']}")
        print(f"Quantity: {formatted['quantity']:.4f}")
        print(f"Price: {formatted['price']:.4f}")
        if formatted['stopPrice']:
            print(f"Stop Price: {formatted['stopPrice']:.4f}")
        print(f"Time: {formatted['time']}")
        print(f"Reduce Only: {formatted['reduceOnly']}")
        print(f"Working Type: {formatted['workingType']}")
        print(f"Time In Force: {formatted['timeInForce']}")

        if details:
            print(f"\n📊 Additional Details:")
            print(f"Executed Qty: {float(details.get('executedQty', 0)):.4f}")
            print(f"Cumulative Quote Qty: {float(details.get('cumQuote', 0)):.4f}")
            print(f"Average Price: {float(details.get('avgPrice', 0)):.4f}")
            print(f"Update Time: {datetime.fromtimestamp(int(details.get('updateTime', 0)) / 1000).strftime('%Y-%m-%d %H:%M:%S')}")

    def display_positions(self, positions: List[Dict]):
        """Display positions in a formatted table"""
        if not positions:
            print("\n💰 No active positions found")
            return

        print(f"\n💰 Active Positions ({len(positions)}):")
        print("=" * 180)
        print(f"{'Symbol':<12} {'Side':<6} {'Size':<12} {'Entry Price':<12} {'Mark Price':<12} "
              f"{'PnL':<12} {'PnL %':<8} {'Liquidation':<12} {'Leverage':<8} {'Notional':<12} {'Margin':<12}")
        print("-" * 180)

        total_pnl = 0
        total_notional = 0
        for position in positions:
            formatted = self.format_position(position)
            total_pnl += formatted['unrealizedPnl']
            total_notional += formatted['notional']

            pnl_color = "🟢" if formatted['unrealizedPnl'] >= 0 else "🔴"
            print(f"{formatted['symbol']:<12} {formatted['side']:<6} {formatted['size']:<12.4f} "
                  f"{formatted['entryPrice']:<12.4f} {formatted['markPrice']:<12.4f} "
                  f"{pnl_color} {formatted['unrealizedPnl']:<10.2f} {formatted['pnlPercentage']:<8.2f}% "
                  f"{formatted['liquidationPrice']:<12.4f} {formatted['leverage']:<8}x "
                  f"{formatted['notional']:<12.2f} {formatted['isolatedMargin']:<12.2f}")

        print("-" * 180)
        pnl_color = "🟢" if total_pnl >= 0 else "🔴"
        print(f"{'TOTAL PnL:':<60} {pnl_color} {total_pnl:<10.2f} USDT")
        print(f"{'TOTAL NOTIONAL:':<60} {total_notional:<10.2f} USDT")

    def display_balance(self, balance: Dict):
        """Display account balance"""
        if not balance:
            print("\n💳 Unable to fetch account balance")
            return

        print(f"\n💳 Account Balance:")
        print("=" * 50)

        # Show only assets with non-zero balance
        non_zero_assets = {k: v for k, v in balance.items() if float(v) > 0}

        if not non_zero_assets:
            print("No assets with non-zero balance")
            return

        for asset, amount in sorted(non_zero_assets.items()):
            print(f"{asset:<10}: {float(amount):<15.4f}")

    def display_account_info(self, account_info: Dict):
        """Display comprehensive account information"""
        if not account_info:
            print("\n📊 Unable to fetch comprehensive account information")
            return

        print(f"\n📊 Account Information:")
        print("=" * 60)

        # Total wallet balance
        total_wallet_balance = float(account_info.get('totalWalletBalance', 0))
        print(f"Total Wallet Balance: {total_wallet_balance:.4f} USDT")

        # Total unrealized PnL
        total_unrealized_pnl = float(account_info.get('totalUnrealizedProfit', 0))
        pnl_color = "🟢" if total_unrealized_pnl >= 0 else "🔴"
        print(f"Total Unrealized PnL: {pnl_color} {total_unrealized_pnl:.4f} USDT")

        # Total margin balance
        total_margin_balance = float(account_info.get('totalMarginBalance', 0))
        print(f"Total Margin Balance: {total_margin_balance:.4f} USDT")

        # Available balance
        available_balance = float(account_info.get('availableBalance', 0))
        print(f"Available Balance: {available_balance:.4f} USDT")

        # Max withdraw amount
        max_withdraw_amount = float(account_info.get('maxWithdrawAmount', 0))
        print(f"Max Withdraw Amount: {max_withdraw_amount:.4f} USDT")

        # Can trade
        can_trade = account_info.get('canTrade', False)
        print(f"Can Trade: {'✅' if can_trade else '❌'}")

        # Can withdraw
        can_withdraw = account_info.get('canWithdraw', False)
        print(f"Can Withdraw: {'✅' if can_withdraw else '❌'}")

        # Can deposit
        can_deposit = account_info.get('canDeposit', False)
        print(f"Can Deposit: {'✅' if can_deposit else '❌'}")

    async def run_full_check(self):
        """Run a complete status check"""
        print("🔍 Binance Status Checker")
        print("=" * 50)

        # Initialize connection
        if not await self.initialize():
            return

        try:
            # Get all data
            orders = await self.get_open_orders()
            positions = await self.get_positions()
            balance = await self.get_account_balance()
            account_info = await self.get_comprehensive_account_info()

            # Display results
            self.display_account_info(account_info)
            self.display_balance(balance)
            self.display_orders(orders)
            self.display_positions(positions)

            # Summary
            print(f"\n📊 Summary:")
            print(f"Open Orders: {len(orders)}")
            print(f"Active Positions: {len(positions)}")

            if positions:
                total_pnl = sum(float(pos.get('unRealizedProfit', 0)) for pos in positions)
                pnl_color = "🟢" if total_pnl >= 0 else "🔴"
                print(f"Total Unrealized PnL: {pnl_color} {total_pnl:.2f} USDT")

        except Exception as e:
            logger.error(f"Error during status check: {e}")
        finally:
            if self.binance_exchange:
                await self.binance_exchange.close_client()

    async def get_detailed_order_info(self, symbol: str, order_id: str):
        """Get and display detailed information about a specific order"""
        print(f"\n🔍 Getting detailed info for order {order_id} on {symbol}")
        print("=" * 60)

        if not await self.initialize():
            return

        try:
            # Get order details
            order_details = await self.get_order_details(symbol, order_id)
            if order_details:
                print(f"Order Details:")
                print(json.dumps(order_details, indent=2, default=str))
            else:
                print(f"Could not fetch details for order {order_id}")

            # Get recent trades for this symbol
            recent_trades = await self.get_recent_trades(symbol, limit=5)
            if recent_trades:
                print(f"\nRecent Trades for {symbol}:")
                for trade in recent_trades:
                    print(f"  {trade.get('time')}: {trade.get('side')} {trade.get('qty')} @ {trade.get('price')}")

        except Exception as e:
            logger.error(f"Error getting detailed order info: {e}")
        finally:
            if self.binance_exchange:
                await self.binance_exchange.close_client()

async def main():
    """Main function"""
    import argparse

    parser = argparse.ArgumentParser(description='Binance Status Checker')
    parser.add_argument('--order-details', nargs=2, metavar=('SYMBOL', 'ORDER_ID'),
                       help='Get detailed information about a specific order')

    args = parser.parse_args()

    checker = BinanceStatusChecker()

    if args.order_details:
        symbol, order_id = args.order_details
        await checker.get_detailed_order_info(symbol, order_id)
    else:
        await checker.run_full_check()

if __name__ == "__main__":
    asyncio.run(main())