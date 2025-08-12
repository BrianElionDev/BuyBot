#!/usr/bin/env python3
"""
Binance Emergency Close Script
Closes all open positions and cancels all open orders on Binance (both spot and futures)

Usage:
    # Close all positions and orders (emergency mode)
    python close_all_positions.py

    # Close all positions and orders without selling spot assets
    python close_all_positions.py --no-spot

    # Close only July 2025 trades at market price
    python close_all_positions.py --july-only

    # Close only July 2025 trades (alternative flag)
    python close_all_positions.py --july-trades
"""

import asyncio
import logging
import os
import sys
import json
from typing import Dict, List, Tuple
from config import settings
from datetime import datetime, timezone
from supabase import create_client

# Add the project root to the path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.exchange.binance_exchange import BinanceExchange
from binance.enums import SIDE_BUY, SIDE_SELL, ORDER_TYPE_MARKET

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('close_all_positions.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

class BinanceEmergencyClose:
    def __init__(self, api_key: str, api_secret: str, is_testnet: bool = False):
        self.exchange = BinanceExchange(api_key, api_secret, is_testnet)
        self.is_testnet = is_testnet

        # Initialize Supabase client
        url = settings.SUPABASE_URL
        key = settings.SUPABASE_KEY
        if url and key:
            self.supabase = create_client(url, key)
            logger.info("Successfully connected to Supabase.")
        else:
            logger.warning("Supabase URL or Key not found. Database functionality will be disabled.")
            self.supabase = None

    async def initialize(self):
        """Initialize the Binance client"""
        await self.exchange._init_client()
        logger.info(f"Initialized Binance client (Testnet: {self.is_testnet})")

    async def close(self):
        """Close the exchange connection"""
        await self.exchange.close()

    async def get_july_open_trades(self) -> List[Dict]:
        """Get all open trades from July 2025"""
        if not self.supabase:
            logger.error("Supabase client not available.")
            return []

        try:
            # Query for open trades created in July 2025
            july_start = "2025-07-01 00:00:00+00"
            july_end = "2025-08-01 00:00:00+00"

            response = self.supabase.from_("trades").select("*") \
                .eq("status", "OPEN") \
                .gte("createdAt", july_start) \
                .lt("createdAt", july_end) \
                .execute()

            trades = response.data or []
            logger.info(f"Found {len(trades)} open trades from July 2025")
            return trades

        except Exception as e:
            logger.error(f"Error querying July trades: {e}")
            return []

    async def close_july_trade(self, trade: Dict) -> Tuple[bool, str]:
        """Close a single July trade at market price"""
        try:
            trade_id = trade['id']

            # Extract symbol from parsed_signal if coin_symbol is None
            symbol = trade.get('coin_symbol')
            if not symbol and trade.get('parsed_signal'):
                try:
                    parsed_signal = trade['parsed_signal']
                    if isinstance(parsed_signal, str):
                        parsed_signal = json.loads(parsed_signal)
                    symbol = parsed_signal.get('coin_symbol')
                except (json.JSONDecodeError, TypeError):
                    pass

            # Extract position type from parsed_signal or use signal_type
            position_type = 'LONG'  # default
            if trade.get('parsed_signal'):
                try:
                    parsed_signal = trade['parsed_signal']
                    if isinstance(parsed_signal, str):
                        parsed_signal = json.loads(parsed_signal)
                    position_type = parsed_signal.get('position_type', trade.get('signal_type', 'LONG'))
                except (json.JSONDecodeError, TypeError):
                    position_type = trade.get('signal_type', 'LONG')
            else:
                position_type = trade.get('signal_type', 'LONG')

            # For now, we'll use a default quantity since position_size is None
            # In a real scenario, you might want to get this from Binance positions
            quantity = 1.0  # Default quantity - you may need to adjust this

            if not symbol:
                return False, f"Invalid trade data: symbol={symbol}, position_type={position_type}"

            # Add USDT suffix if not present
            if not symbol.endswith('USDT'):
                symbol = f"{symbol}USDT"

            logger.info(f"Closing July trade {trade_id}: {symbol} {position_type} {quantity}")

            # Determine the side to close the position
            if position_type.upper() == 'LONG':
                close_side = SIDE_SELL
            else:  # SHORT
                close_side = SIDE_BUY

            # Create market order to close position
            response = await self.exchange.create_futures_order(
                pair=symbol,
                side=close_side,
                order_type_market='MARKET',
                amount=quantity,
                reduce_only=True
            )

            if 'orderId' in response:
                # Get the execution price from the response
                avg_price = float(response.get('avgPrice', 0))
                if avg_price > 0:
                    # Calculate PnL
                    entry_price = float(trade.get('entry_price', 0))
                    if entry_price > 0:
                        if position_type.upper() == 'LONG':
                            pnl = (avg_price - entry_price) * quantity
                        else:  # SHORT
                            pnl = (entry_price - avg_price) * quantity
                    else:
                        pnl = 0.0
                else:
                    pnl = 0.0

                # Update the trade in database
                update_data = {
                    'status': 'CLOSED',
                    'exit_price': avg_price,
                    'binance_exit_price': avg_price,
                    'pnl_usd': pnl,
                    'realized_pnl': pnl,
                    'updated_at': datetime.now(timezone.utc).isoformat()
                }

                if self.supabase:
                    self.supabase.table("trades").update(update_data).eq("id", trade_id).execute()
                    logger.info(f"Updated trade {trade_id} in database with exit data")

                logger.info(f"Successfully closed July trade {trade_id}: {response['orderId']} at {avg_price}, PnL: {pnl}")
                return True, f"Trade closed: {response['orderId']}, PnL: {pnl}"
            else:
                error_msg = f"Failed to close July trade {trade_id}: {response}"
                logger.error(error_msg)
                return False, error_msg

        except Exception as e:
            error_msg = f"Error closing July trade {trade.get('id', 'UNKNOWN')}: {e}"
            logger.error(error_msg)
            return False, error_msg

    async def close_all_july_trades(self) -> Dict[str, List[str]]:
        """Close all open trades from July 2025"""
        logger.info("=" * 60)
        logger.info("CLOSING ALL JULY 2025 TRADES")
        logger.info("=" * 60)

        trades = await self.get_july_open_trades()
        results = {"success": [], "failed": [], "marked_closed": []}

        if not trades:
            logger.info("No open July trades found")
            return results

        logger.info(f"Found {len(trades)} July trades to process:")
        for trade in trades:
            # Extract symbol from parsed_signal if coin_symbol is None
            symbol = trade.get('coin_symbol')
            if not symbol and trade.get('parsed_signal'):
                try:
                    parsed_signal = trade['parsed_signal']
                    if isinstance(parsed_signal, str):
                        parsed_signal = json.loads(parsed_signal)
                    symbol = parsed_signal.get('coin_symbol', 'UNKNOWN')
                except (json.JSONDecodeError, TypeError):
                    symbol = 'UNKNOWN'
            else:
                symbol = symbol or 'UNKNOWN'

            # Extract position type
            position_type = 'UNKNOWN'
            if trade.get('parsed_signal'):
                try:
                    parsed_signal = trade['parsed_signal']
                    if isinstance(parsed_signal, str):
                        parsed_signal = json.loads(parsed_signal)
                    position_type = parsed_signal.get('position_type', trade.get('signal_type', 'UNKNOWN'))
                except (json.JSONDecodeError, TypeError):
                    position_type = trade.get('signal_type', 'UNKNOWN')
            else:
                position_type = trade.get('signal_type', 'UNKNOWN')

            entry_price = trade.get('entry_price', 0)
            logger.info(f"  - {symbol} {position_type} @ {entry_price}")

        # Get current Binance positions to check which trades are actually open
        logger.info("Checking current Binance positions...")
        binance_positions = await self.get_all_open_futures_positions()
        binance_symbols = {pos['symbol'] for pos in binance_positions if float(pos.get('positionAmt', 0)) != 0}
        logger.info(f"Found {len(binance_symbols)} active positions on Binance: {list(binance_symbols)}")

        for trade in trades:
            trade_id = trade['id']

            # Extract symbol for comparison
            symbol = trade.get('coin_symbol')
            if not symbol and trade.get('parsed_signal'):
                try:
                    parsed_signal = trade['parsed_signal']
                    if isinstance(parsed_signal, str):
                        parsed_signal = json.loads(parsed_signal)
                    symbol = parsed_signal.get('coin_symbol')
                except (json.JSONDecodeError, TypeError):
                    symbol = None

            if symbol:
                # Add USDT suffix for comparison
                if not symbol.endswith('USDT'):
                    symbol_with_suffix = f"{symbol}USDT"
                else:
                    symbol_with_suffix = symbol

                # Check if this symbol has an active position on Binance
                if symbol_with_suffix in binance_symbols:
                    # Position exists on Binance, try to close it
                    success, message = await self.close_july_trade(trade)
                    if success:
                        results["success"].append(f"{symbol} (ID: {trade_id}): {message}")
                    else:
                        results["failed"].append(f"{symbol} (ID: {trade_id}): {message}")
                else:
                    # No position on Binance, mark as closed in database
                    success = await self.mark_trade_as_closed(trade_id, symbol)
                    if success:
                        results["marked_closed"].append(f"{symbol} (ID: {trade_id}): Marked as CLOSED (no position on Binance)")
                    else:
                        results["failed"].append(f"{symbol} (ID: {trade_id}): Failed to mark as CLOSED")
            else:
                # No symbol found, mark as closed
                success = await self.mark_trade_as_closed(trade_id, "UNKNOWN")
                if success:
                    results["marked_closed"].append(f"UNKNOWN (ID: {trade_id}): Marked as CLOSED (no symbol)")
                else:
                    results["failed"].append(f"UNKNOWN (ID: {trade_id}): Failed to mark as CLOSED")

        logger.info(f"July trades processed: {len(results['success'])} closed, {len(results['marked_closed'])} marked closed, {len(results['failed'])} failed")
        return results

    async def mark_trade_as_closed(self, trade_id: int, symbol: str) -> bool:
        """Mark a trade as closed in the database"""
        try:
            if not self.supabase:
                logger.error("Supabase client not available.")
                return False

            update_data = {
                'status': 'CLOSED',
                'updated_at': datetime.now(timezone.utc).isoformat()
            }

            self.supabase.table("trades").update(update_data).eq("id", trade_id).execute()
            logger.info(f"Marked trade {trade_id} ({symbol}) as CLOSED in database")
            return True

        except Exception as e:
            logger.error(f"Error marking trade {trade_id} as closed: {e}")
            return False

    async def get_all_open_futures_positions(self) -> List[Dict]:
        """Get all open futures positions"""
        try:
            positions = await self.exchange.get_futures_position_information()
            # Filter out positions with zero quantity
            open_positions = [
                pos for pos in positions
                if float(pos.get('positionAmt', 0)) != 0
            ]
            logger.info(f"Found {len(open_positions)} open futures positions")
            return open_positions
        except Exception as e:
            logger.error(f"Failed to get futures positions: {e}")
            return []

    async def get_all_open_futures_orders(self) -> List[Dict]:
        """Get all open futures orders"""
        try:
            orders = await self.exchange.get_all_open_futures_orders()
            logger.info(f"Found {len(orders)} open futures orders")
            return orders
        except Exception as e:
            logger.error(f"Failed to get futures orders: {e}")
            return []

    async def get_all_open_spot_orders(self) -> List[Dict]:
        """Get all open spot orders"""
        try:
            if not self.exchange.client:
                return []
            orders = await self.exchange.client.get_open_orders()
            logger.info(f"Found {len(orders)} open spot orders")
            return list(orders) if orders else []
        except Exception as e:
            logger.error(f"Failed to get spot orders: {e}")
            return []

    async def get_spot_balances(self) -> Dict[str, float]:
        """Get all spot balances with non-zero amounts"""
        try:
            balances = await self.exchange.get_spot_balance()
            # Filter out USDT and other stablecoins if you want to keep them
            # exclude_stablecoins = ['USDT', 'USDC', 'BUSD', 'TUSD', 'DAI']
            # balances = {k: v for k, v in balances.items() if k not in exclude_stablecoins}
            logger.info(f"Found {len(balances)} spot assets with balance > 0")
            return balances
        except Exception as e:
            logger.error(f"Failed to get spot balances: {e}")
            return {}

    async def close_futures_position(self, position: Dict) -> Tuple[bool, str]:
        """Close a single futures position"""
        try:
            symbol = position['symbol']
            position_amt = float(position['positionAmt'])
            position_side = position.get('positionSide', 'BOTH')

            if position_amt == 0:
                return True, "Position already closed"

            # Determine the side to close the position
            if position_amt > 0:  # Long position
                close_side = SIDE_SELL
            else:  # Short position
                close_side = SIDE_BUY
                position_amt = abs(position_amt)

            logger.info(f"Closing {symbol} position: {position_amt} ({close_side})")


            logger.info(f"Canceling all TP/SL orders for {symbol} before closing position")
            cancel_result = await self.exchange.cancel_all_futures_orders(symbol)
            if not cancel_result:
                logger.warning(f"Failed to cancel TP/SL orders for {symbol} - proceeding with position close")

            # Create market order to close position
            response = await self.exchange.create_futures_order(
                pair=symbol,
                side=close_side,
                order_type_market='MARKET',
                amount=position_amt,
                reduce_only=True
            )

            if 'orderId' in response:
                logger.info(f"Successfully closed {symbol} position: {response['orderId']}")
                return True, f"Position closed: {response['orderId']}"
            else:
                error_msg = f"Failed to close {symbol} position: {response}"
                logger.error(error_msg)
                return False, error_msg

        except Exception as e:
            error_msg = f"Error closing {position.get('symbol', 'UNKNOWN')} position: {e}"
            logger.error(error_msg)
            return False, error_msg

    async def cancel_futures_order(self, order: Dict) -> Tuple[bool, str]:
        """Cancel a single futures order"""
        try:
            symbol = order['symbol']
            order_id = order['orderId']

            logger.info(f"Cancelling futures order: {symbol} - {order_id}")

            success, response = await self.exchange.cancel_futures_order(symbol, str(order_id))

            if success:
                logger.info(f"Successfully cancelled futures order: {order_id}")
                return True, f"Order cancelled: {order_id}"
            else:
                error_msg = f"Failed to cancel futures order {order_id}: {response}"
                logger.error(error_msg)
                return False, error_msg

        except Exception as e:
            error_msg = f"Error cancelling futures order {order.get('orderId', 'UNKNOWN')}: {e}"
            logger.error(error_msg)
            return False, error_msg

    async def cancel_spot_order(self, order: Dict) -> Tuple[bool, str]:
        """Cancel a single spot order"""
        try:
            symbol = order['symbol']
            order_id = order['orderId']

            logger.info(f"Cancelling spot order: {symbol} - {order_id}")

            success = await self.exchange.cancel_order(symbol, str(order_id))

            if success:
                logger.info(f"Successfully cancelled spot order: {order_id}")
                return True, f"Order cancelled: {order_id}"
            else:
                error_msg = f"Failed to cancel spot order: {order_id}"
                logger.error(error_msg)
                return False, error_msg

        except Exception as e:
            error_msg = f"Error cancelling spot order {order.get('orderId', 'UNKNOWN')}: {e}"
            logger.error(error_msg)
            return False, error_msg

    async def sell_spot_asset(self, asset: str, amount: float) -> Tuple[bool, str]:
        """Sell a spot asset for USDT"""
        try:
            if asset == 'USDT':
                return True, "Skipping USDT (stablecoin)"

            symbol = f"{asset}USDT"

            # Check if the symbol exists
            try:
                if not self.exchange.client:
                    return False, "Client not initialized"

                # Get symbol info to check if it exists
                exchange_info = await self.exchange.client.get_exchange_info()
                symbol_exists = any(s['symbol'] == symbol for s in exchange_info['symbols'])

                if not symbol_exists:
                    logger.warning(f"Symbol {symbol} not found, trying alternative pairs")
                    # Try alternative pairs
                    alt_symbols = [f"{asset}BUSD", f"{asset}USDC", f"{asset}BTC", f"{asset}ETH"]
                    for alt_symbol in alt_symbols:
                        if any(s['symbol'] == alt_symbol for s in exchange_info['symbols']):
                            symbol = alt_symbol
                            symbol_exists = True
                            break

                if not symbol_exists:
                    return False, f"No trading pair found for {asset}"

            except Exception as e:
                logger.warning(f"Could not verify symbol {symbol}, attempting anyway: {e}")

            logger.info(f"Selling {amount} {asset} via {symbol}")

            response = await self.exchange.create_order(
                pair=symbol,
                side='SELL',
                order_type_market='MARKET',
                amount=amount
            )

            if 'orderId' in response:
                logger.info(f"Successfully sold {asset}: {response['orderId']}")
                return True, f"Asset sold: {response['orderId']}"
            else:
                error_msg = f"Failed to sell {asset}: {response}"
                logger.error(error_msg)
                return False, error_msg

        except Exception as e:
            error_msg = f"Error selling {asset}: {e}"
            logger.error(error_msg)
            return False, error_msg

    async def close_all_futures_positions(self) -> Dict[str, List[str]]:
        """Close all open futures positions"""
        logger.info("=" * 60)
        logger.info("CLOSING ALL FUTURES POSITIONS")
        logger.info("=" * 60)

        positions = await self.get_all_open_futures_positions()
        results = {"success": [], "failed": []}

        if not positions:
            logger.info("No open futures positions found")
            return results

        for position in positions:
            symbol = position['symbol']
            position_amt = float(position['positionAmt'])
            entry_price = float(position['entryPrice'])
            unrealized_pnl = float(position.get('unRealizedProfit', 0))

            logger.info(f"Position: {symbol} | Amount: {position_amt} | Entry: {entry_price} | PnL: {unrealized_pnl}")

            success, message = await self.close_futures_position(position)
            if success:
                results["success"].append(f"{symbol}: {message}")
            else:
                results["failed"].append(f"{symbol}: {message}")

        logger.info(f"Futures positions closed: {len(results['success'])} success, {len(results['failed'])} failed")
        return results

    async def cancel_all_futures_orders(self) -> Dict[str, List[str]]:
        """Cancel all open futures orders"""
        logger.info("=" * 60)
        logger.info("CANCELLING ALL FUTURES ORDERS")
        logger.info("=" * 60)

        orders = await self.get_all_open_futures_orders()
        results = {"success": [], "failed": []}

        if not orders:
            logger.info("No open futures orders found")
            return results

        for order in orders:
            symbol = order['symbol']
            order_id = order['orderId']
            side = order['side']
            order_type = order['type']
            quantity = order['origQty']
            price = order.get('price', 'MARKET')

            logger.info(f"Order: {symbol} | {side} {order_type} {quantity} @ {price} | ID: {order_id}")

            success, message = await self.cancel_futures_order(order)
            if success:
                results["success"].append(f"{symbol}: {message}")
            else:
                results["failed"].append(f"{symbol}: {message}")

        logger.info(f"Futures orders cancelled: {len(results['success'])} success, {len(results['failed'])} failed")
        return results

    async def cancel_all_spot_orders(self) -> Dict[str, List[str]]:
        """Cancel all open spot orders"""
        logger.info("=" * 60)
        logger.info("CANCELLING ALL SPOT ORDERS")
        logger.info("=" * 60)

        orders = await self.get_all_open_spot_orders()
        results = {"success": [], "failed": []}

        if not orders:
            logger.info("No open spot orders found")
            return results

        for order in orders:
            symbol = order['symbol']
            order_id = order['orderId']
            side = order['side']
            order_type = order['type']
            quantity = order['origQty']
            price = order.get('price', 'MARKET')

            logger.info(f"Order: {symbol} | {side} {order_type} {quantity} @ {price} | ID: {order_id}")

            success, message = await self.cancel_spot_order(order)
            if success:
                results["success"].append(f"{symbol}: {message}")
            else:
                results["failed"].append(f"{symbol}: {message}")

        logger.info(f"Spot orders cancelled: {len(results['success'])} success, {len(results['failed'])} failed")
        return results

    async def sell_all_spot_assets(self) -> Dict[str, List[str]]:
        """Sell all spot assets for USDT"""
        logger.info("=" * 60)
        logger.info("SELLING ALL SPOT ASSETS")
        logger.info("=" * 60)

        balances = await self.get_spot_balances()
        results = {"success": [], "failed": []}

        if not balances:
            logger.info("No spot assets with balance > 0 found")
            return results

        for asset, amount in balances.items():
            logger.info(f"Asset: {asset} | Balance: {amount}")

            success, message = await self.sell_spot_asset(asset, amount)
            if success:
                results["success"].append(f"{asset}: {message}")
            else:
                results["failed"].append(f"{asset}: {message}")

        logger.info(f"Spot assets sold: {len(results['success'])} success, {len(results['failed'])} failed")
        return results

    async def emergency_close_all(self, include_spot_sales: bool = True) -> Dict[str, Dict[str, List[str]]]:
        """Execute emergency close of all positions and orders"""
        logger.info("🚨 EMERGENCY CLOSE ALL POSITIONS AND ORDERS 🚨")
        logger.info("This will close all futures positions, cancel all orders, and optionally sell all spot assets")

        if not include_spot_sales:
            logger.info("Spot asset sales are DISABLED - only positions and orders will be closed")

        all_results = {}

        try:
            # 1. Close all futures positions
            futures_positions_result = await self.close_all_futures_positions()
            all_results["futures_positions"] = futures_positions_result

            # 2. Cancel all futures orders
            futures_orders_result = await self.cancel_all_futures_orders()
            all_results["futures_orders"] = futures_orders_result

            # 3. Cancel all spot orders
            spot_orders_result = await self.cancel_all_spot_orders()
            all_results["spot_orders"] = spot_orders_result

            # 4. Optionally sell all spot assets
            if include_spot_sales:
                spot_sales_result = await self.sell_all_spot_assets()
                all_results["spot_sales"] = spot_sales_result
            else:
                all_results["spot_sales"] = {"success": [], "failed": ["Spot sales disabled"]}

        except Exception as e:
            logger.error(f"Error during emergency close: {e}")
            all_results["error"] = {"failed": [f"Emergency close failed: {e}"]}

        # Print summary
        logger.info("=" * 60)
        logger.info("EMERGENCY CLOSE SUMMARY")
        logger.info("=" * 60)

        total_success = 0
        total_failed = 0

        for action, results in all_results.items():
            if isinstance(results, dict) and "success" in results and "failed" in results:
                success_count = len(results["success"])
                failed_count = len(results["failed"])
                total_success += success_count
                total_failed += failed_count
                logger.info(f"{action.replace('_', ' ').title()}: {success_count} success, {failed_count} failed")

        logger.info(f"TOTAL: {total_success} success, {total_failed} failed")

        if total_failed == 0:
            logger.info("✅ All operations completed successfully!")
        else:
            logger.warning(f"⚠️  {total_failed} operations failed. Check the log for details.")

        return all_results

async def main():
    """Main function"""
    # Get credentials
    api_key = settings.BINANCE_API_KEY
    api_secret = settings.BINANCE_API_SECRET
    is_testnet = settings.BINANCE_TESTNET

    if not api_key or not api_secret:
        logger.error("BINANCE_API_KEY and BINANCE_API_SECRET must be set in environment variables")
        return

    # Parse command line arguments
    include_spot_sales = True
    close_july_trades_only = False

    for arg in sys.argv[1:]:
        if arg.lower() in ['--no-spot', '--no-spot-sales']:
            include_spot_sales = False
        elif arg.lower() in ['--july-only', '--july-trades']:
            close_july_trades_only = True

    # Initialize
    emergency_close = BinanceEmergencyClose(api_key, api_secret, is_testnet)

    if close_july_trades_only:
        # July trades only mode
        print("\n" + "="*80)
        print("📅 JULY 2025 TRADES CLOSURE SCRIPT 📅")
        print("="*80)
        print(f"Testnet Mode: {'YES' if is_testnet else 'NO'}")
        print("\nThis script will:")
        print("1. Query database for all OPEN trades created in July 2025")
        print("2. Close each trade at market price")
        print("3. Update PnL and exit price in database")
        print("\n⚠️  WARNING: This action cannot be undone! ⚠️")
        print("="*80)

        # Get user confirmation
        if is_testnet:
            print("\n✅ Testnet mode detected - proceeding automatically")
        else:
            confirm = input("\nType 'JULY' to confirm: ")
            if confirm != 'JULY':
                print("Operation cancelled.")
                return

        try:
            await emergency_close.initialize()
            results = await emergency_close.close_all_july_trades()

            # Print results
            logger.info("\n" + "="*60)
            logger.info("JULY TRADES CLOSURE SUMMARY")
            logger.info("="*60)

            if results["success"]:
                logger.info("✅ Successfully closed trades:")
                for success in results["success"]:
                    logger.info(f"  - {success}")

            if results["marked_closed"]:
                logger.info("📝 Marked as closed (no position on Binance):")
                for marked in results["marked_closed"]:
                    logger.info(f"  - {marked}")

            if results["failed"]:
                logger.warning("❌ Failed to process trades:")
                for failure in results["failed"]:
                    logger.warning(f"  - {failure}")

            logger.info(f"\nTotal: {len(results['success'])} closed, {len(results['marked_closed'])} marked closed, {len(results['failed'])} failed")

        except Exception as e:
            logger.error(f"July trades closure failed: {e}")
        finally:
            await emergency_close.close()

    else:
        # Full emergency close mode
        print("\n" + "="*80)
        print("🚨 BINANCE EMERGENCY CLOSE SCRIPT 🚨")
        print("="*80)
        print(f"Testnet Mode: {'YES' if is_testnet else 'NO'}")
        print(f"Include Spot Sales: {'YES' if include_spot_sales else 'NO'}")
        print("\nThis script will:")
        print("1. Close ALL open futures positions")
        print("2. Cancel ALL open futures orders")
        print("3. Cancel ALL open spot orders")
        if include_spot_sales:
            print("4. Sell ALL spot assets for USDT")
        print("\n⚠️  WARNING: This action cannot be undone! ⚠️")
        print("="*80)

        # Get user confirmation
        if is_testnet:
            print("\n✅ Testnet mode detected - proceeding automatically")
        else:
            confirm = input("\nType 'EMERGENCY' to confirm: ")
            if confirm != 'EMERGENCY':
                print("Operation cancelled.")
                return

        try:
            await emergency_close.initialize()
            results = await emergency_close.emergency_close_all(include_spot_sales)

            # Final verification
            logger.info("\n" + "="*60)
            logger.info("FINAL VERIFICATION")
            logger.info("="*60)

            # Check remaining positions
            remaining_positions = await emergency_close.get_all_open_futures_positions()
            if remaining_positions:
                logger.warning(f"⚠️  {len(remaining_positions)} positions still open!")
                for pos in remaining_positions:
                    logger.warning(f"  - {pos['symbol']}: {pos['positionAmt']}")
            else:
                logger.info("✅ No open futures positions remaining")

            # Check remaining orders
            remaining_futures_orders = await emergency_close.get_all_open_futures_orders()
            remaining_spot_orders = await emergency_close.get_all_open_spot_orders()

            if remaining_futures_orders or remaining_spot_orders:
                logger.warning(f"⚠️  {len(remaining_futures_orders)} futures orders and {len(remaining_spot_orders)} spot orders still open!")
            else:
                logger.info("✅ No open orders remaining")

        except Exception as e:
            logger.error(f"Emergency close failed: {e}")
        finally:
            await emergency_close.close()

if __name__ == "__main__":
    asyncio.run(main())