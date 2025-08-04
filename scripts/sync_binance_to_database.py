#!/usr/bin/env python3
"""
Binance to Database Sync
Syncs Binance data to database with accuracy as top priority
Uses Binance as source of truth, not database state
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple
import os
from dotenv import load_dotenv
import sys

# Add the src directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.exchange.binance_exchange import BinanceExchange
from supabase import create_client, Client

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class BinanceDatabaseSync:
    def __init__(self):
        load_dotenv()
        self.binance_exchange = None
        self.supabase = None

    async def initialize(self):
        """Initialize connections to Binance and Supabase"""
        try:
            # Initialize Binance
            api_key = os.getenv('BINANCE_API_KEY')
            api_secret = os.getenv('BINANCE_API_SECRET')
            is_testnet = os.getenv('BINANCE_TESTNET', 'True').lower() == 'true'

            if not api_key or not api_secret:
                logger.error("Binance API credentials not found!")
                return False

            self.binance_exchange = BinanceExchange(api_key, api_secret, is_testnet)
            await self.binance_exchange._init_client()

            # Initialize Supabase
            supabase_url = os.getenv('SUPABASE_URL')
            supabase_key = os.getenv('SUPABASE_KEY')

            if not supabase_url or not supabase_key:
                logger.error("Supabase credentials not found!")
                return False

            self.supabase = create_client(supabase_url, supabase_key)

            logger.info(f"Connected to Binance {'Testnet' if is_testnet else 'Mainnet'} and Supabase")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize connections: {e}")
            return False

    async def get_binance_orders(self) -> List[Dict]:
        """Get all open orders from Binance"""
        try:
            orders = await self.binance_exchange.get_all_open_futures_orders()
            logger.info(f"Found {len(orders)} open orders on Binance")
            return orders
        except Exception as e:
            logger.error(f"Error fetching Binance orders: {e}")
            return []

    async def get_binance_positions(self) -> List[Dict]:
        """Get all positions from Binance"""
        try:
            positions = await self.binance_exchange.get_futures_position_information()

            # Filter active positions (non-zero size)
            active_positions = [
                pos for pos in positions
                if float(pos.get('positionAmt', 0)) != 0
            ]

            logger.info(f"Found {len(active_positions)} active positions on Binance")
            return active_positions
        except Exception as e:
            logger.error(f"Error fetching Binance positions: {e}")
            return []

    async def get_binance_user_trades(self, symbol: str = "", limit: int = 1000, from_id: int = 0,
                                    start_time: int = 0, end_time: int = 0) -> List[Dict]:
        """Get user trade history from Binance"""
        try:
            trades = await self.binance_exchange.get_user_trades(
                symbol=symbol,
                limit=limit,
                from_id=from_id,
                start_time=start_time,
                end_time=end_time
            )
            logger.info(f"Found {len(trades)} user trades from Binance")
            return trades
        except Exception as e:
            logger.error(f"Error fetching Binance user trades: {e}")
            return []

    async def get_binance_order_history(self, symbol: str = "", limit: int = 500,
                                      start_time: int = 0, end_time: int = 0) -> List[Dict]:
        """Get order history from Binance (including closed orders)"""
        try:
            # Get all orders (open and closed) for the symbol
            await self.binance_exchange._init_client()
            assert self.binance_exchange.client is not None

            params = {'limit': limit}
            if symbol:
                params['symbol'] = symbol
            if start_time != 0:
                params['startTime'] = start_time
            if end_time != 0:
                params['endTime'] = end_time

            orders = await self.binance_exchange.client.futures_get_all_orders(**params)
            logger.info(f"Found {len(orders)} orders (including closed) from Binance")
            return orders
        except Exception as e:
            logger.error(f"Error fetching Binance order history: {e}")
            return []

    async def get_database_trades(self) -> List[Dict]:
        """Get all trades from database"""
        try:
            # get all trades from the last 48 hours, regardless of status
            # This includes OPEN, CLOSED, FAILED, etc. to handle incorrect statuses
            response = self.supabase.table("trades").select("*").gte("createdAt", datetime.now(timezone.utc) - timedelta(hours=48)).execute()
            trades = response.data if response.data else []
            logger.info(f"Found {len(trades)} trades in database (all statuses)")
            return trades
        except Exception as e:
            logger.error(f"Error fetching database trades: {e}")
            return []

    def safe_parse_binance_response(self, binance_response: str) -> Dict:
        """Safely parse binance_response field which is stored as text but may contain JSON."""
        if isinstance(binance_response, dict):
            return binance_response
        elif isinstance(binance_response, str):
            # Handle empty or invalid strings
            if not binance_response or binance_response.strip() == '':
                return {}

            # Try to parse as JSON
            try:
                return json.loads(binance_response.strip())
            except (json.JSONDecodeError, ValueError):
                # If it's not valid JSON, treat it as a plain text error message
                return {"error": binance_response.strip()}
        else:
            return {}

    def extract_order_info(self, binance_response: str) -> Tuple[Optional[str], Optional[str]]:
        """Extract orderId and symbol from binance_response JSON text"""
        try:
            # Use safe parsing
            response_data = self.safe_parse_binance_response(binance_response)

            order_id = str(response_data.get('orderId', ''))
            symbol = response_data.get('symbol', '')

            # Validate we got meaningful data
            if order_id and order_id != '0' and symbol:
                logger.debug(f"Successfully extracted orderId={order_id}, symbol={symbol}")
                return order_id, symbol
            else:
                logger.debug(f"No valid order data found in response")
                return None, None

        except Exception as e:
            logger.warning(f"Could not extract order info from response: {e}")
            return None, None

    def extract_order_details(self, binance_response: str) -> Dict:
        """Extract comprehensive order details from binance_response JSON text"""
        try:
            # Use safe parsing
            response_data = self.safe_parse_binance_response(binance_response)

            # Extract all relevant fields with safe conversion
            return {
                'orderId': str(response_data.get('orderId', '')),
                'symbol': response_data.get('symbol', ''),
                'status': response_data.get('status', ''),
                'clientOrderId': response_data.get('clientOrderId', ''),
                'price': float(response_data.get('price', 0)) if response_data.get('price') else 0.0,
                'avgPrice': float(response_data.get('avgPrice', 0)) if response_data.get('avgPrice') else 0.0,
                'origQty': float(response_data.get('origQty', 0)) if response_data.get('origQty') else 0.0,
                'executedQty': float(response_data.get('executedQty', 0)) if response_data.get('executedQty') else 0.0,
                'cumQty': float(response_data.get('cumQty', 0)) if response_data.get('cumQty') else 0.0,
                'cumQuote': float(response_data.get('cumQuote', 0)) if response_data.get('cumQuote') else 0.0,
                'timeInForce': response_data.get('timeInForce', ''),
                'type': response_data.get('type', ''),
                'side': response_data.get('side', ''),
                'reduceOnly': response_data.get('reduceOnly', False),
                'closePosition': response_data.get('closePosition', False),
                'positionSide': response_data.get('positionSide', ''),
                'stopPrice': float(response_data.get('stopPrice', 0)) if response_data.get('stopPrice') else 0.0,
                'workingType': response_data.get('workingType', ''),
                'priceProtect': response_data.get('priceProtect', False),
                'origType': response_data.get('origType', ''),
                'updateTime': int(response_data.get('updateTime', 0)) if response_data.get('updateTime') else 0
            }

        except Exception as e:
            logger.warning(f"Could not extract order details from response: {e}")
            return {}

    def calculate_position_pnl(self, position: Dict) -> Tuple[float, float]:
        """Calculate realized and unrealized PnL for a position"""
        try:
            position_amt = float(position.get('positionAmt', 0))
            entry_price = float(position.get('entryPrice', 0))
            mark_price = float(position.get('markPrice', 0))
            unrealized_pnl = float(position.get('unRealizedProfit', 0))

            # For realized PnL, we need to look at closed positions
            # This is a simplified calculation - in reality, you'd need trade history
            realized_pnl = 0.0  # Would need to calculate from trade history

            return realized_pnl, unrealized_pnl
        except Exception as e:
            logger.error(f"Error calculating PnL: {e}")
            return 0.0, 0.0

    def calculate_trade_pnl(self, entry_price: float, exit_price: float, quantity: float, side: str) -> float:
        """Calculate PnL for a closed trade"""
        try:
            if entry_price <= 0 or exit_price <= 0 or quantity <= 0:
                return 0.0

            if side.upper() == 'LONG':
                # Long position: profit when exit_price > entry_price
                pnl = (exit_price - entry_price) * quantity
            elif side.upper() == 'SHORT':
                # Short position: profit when entry_price > exit_price
                pnl = (entry_price - exit_price) * quantity
            else:
                return 0.0

            return pnl
        except Exception as e:
            logger.error(f"Error calculating trade PnL: {e}")
            return 0.0

    async def sync_orders_to_database(self, binance_orders: List[Dict], db_trades: List[Dict]):
        """Sync Binance orders to database"""
        logger.info("Starting order sync...")

        # Create lookup for database trades by orderId (from both exchange_order_id and binance_response)
        db_trades_by_order_id = {}
        for trade in db_trades:
            # Try exchange_order_id first
            order_id = trade.get('exchange_order_id')
            if order_id:
                db_trades_by_order_id[str(order_id)] = trade

            # Also try to extract from binance_response
            binance_response = trade.get('binance_response', '')
            if binance_response:
                order_details = self.extract_order_details(binance_response)
                extracted_order_id = order_details.get('orderId')
                if extracted_order_id and extracted_order_id not in db_trades_by_order_id:
                    db_trades_by_order_id[extracted_order_id] = trade
                    logger.debug(f"Found trade {trade['id']} with order {extracted_order_id} ({order_details.get('symbol')})")

        updates_made = 0

        for binance_order in binance_orders:
            order_id = str(binance_order.get('orderId', ''))
            symbol = binance_order.get('symbol', '')
            status = binance_order.get('status', '')

            if not order_id or not symbol:
                continue

            # Check if this order exists in our database
            if order_id in db_trades_by_order_id:
                db_trade = db_trades_by_order_id[order_id]
                trade_id = db_trade['id']

                # Update order status and response
                try:
                    update_data = {
                        'order_status_response': json.dumps(binance_order),
                        'updated_at': datetime.now(timezone.utc).isoformat(),
                        'sync_error_count': 0,
                        'sync_issues': [],
                        'manual_verification_needed': False
                    }

                    # Update status based on order status
                    if status == 'FILLED':
                        update_data['status'] = 'OPEN'  # Position is now open
                        # Get current price for exit calculation
                        try:
                            current_price = await self.binance_exchange.get_order_status(symbol, order_id)
                            if current_price and current_price.get('avgPrice'):
                                update_data['binance_exit_price'] = float(current_price['avgPrice'])
                        except Exception as e:
                            logger.warning(f"Could not get exit price for {symbol}: {e}")

                    elif status in ['CANCELED', 'EXPIRED', 'REJECTED']:
                        update_data['status'] = 'FAILED'
                    elif status == 'NEW':
                        update_data['status'] = 'PENDING'  # Order is still pending

                    # Update the trade
                    self.supabase.table("trades").update(update_data).eq("id", trade_id).execute()
                    updates_made += 1
                    logger.info(f"Updated trade {trade_id} (order {order_id}) - status: {status}")

                except Exception as e:
                    logger.error(f"Error updating trade {trade_id}: {e}")
            else:
                logger.warning(f"Order {order_id} ({symbol}) not found in database")

        logger.info(f"Order sync completed: {updates_made} updates made")

    async def sync_positions_to_database(self, binance_positions: List[Dict], db_trades: List[Dict]):
        """Sync Binance positions to database"""
        logger.info("Starting position sync...")

        # Create lookup for database trades by symbol
        db_trades_by_symbol = {}
        for trade in db_trades:
            # First try coin_symbol field
            symbol = trade.get('coin_symbol')

            # If coin_symbol is None, try to extract from parsed_signal
            if not symbol and trade.get('parsed_signal'):
                try:
                    parsed_signal = trade['parsed_signal']
                    if isinstance(parsed_signal, str):
                        import json
                        parsed_signal = json.loads(parsed_signal)
                    symbol = parsed_signal.get('coin_symbol')
                except (json.JSONDecodeError, TypeError):
                    pass

            # If still no symbol, try to extract from binance_response
            if not symbol and trade.get('binance_response'):
                try:
                    order_details = self.extract_order_details(trade['binance_response'])
                    symbol = order_details.get('symbol')
                    if symbol and symbol.endswith('USDT'):
                        symbol = symbol[:-4]  # Remove USDT suffix
                except Exception:
                    pass

            if symbol:
                if symbol not in db_trades_by_symbol:
                    db_trades_by_symbol[symbol] = []
                db_trades_by_symbol[symbol].append(trade)

        updates_made = 0
        current_time = datetime.now(timezone.utc).isoformat()

        for position in binance_positions:
            symbol = position.get('symbol', '')
            position_amt = float(position.get('positionAmt', 0))
            mark_price = float(position.get('markPrice', 0))
            unrealized_pnl = float(position.get('unRealizedProfit', 0))

            if not symbol or position_amt == 0:
                continue

            # Find corresponding trades in database
            if symbol in db_trades_by_symbol:
                for db_trade in db_trades_by_symbol[symbol]:
                    try:
                        # Update position information
                        update_data = {
                            'position_size': abs(position_amt),
                            'binance_exit_price': mark_price,
                            'unrealized_pnl': unrealized_pnl,
                            'last_pnl_sync': current_time,
                            'updated_at': current_time,
                            'sync_error_count': 0,
                            'sync_issues': [],
                            'manual_verification_needed': False
                        }

                        # If position is closed (zero size), update status
                        if position_amt == 0:
                            update_data['status'] = 'CLOSED'
                            # Calculate realized PnL (simplified)
                            entry_price = db_trade.get('entry_price', 0)
                            if entry_price and mark_price:
                                if db_trade.get('signal_type', '').upper() == 'LONG':
                                    realized_pnl = (mark_price - entry_price) * abs(position_amt)
                                else:
                                    realized_pnl = (entry_price - mark_price) * abs(position_amt)
                                update_data['realized_pnl'] = realized_pnl
                                update_data['pnl_usd'] = realized_pnl

                        # Update the trade
                        self.supabase.table("trades").update(update_data).eq("id", db_trade['id']).execute()
                        updates_made += 1
                        logger.info(f"Updated position for trade {db_trade['id']} ({symbol})")

                    except Exception as e:
                        logger.error(f"Error updating position for trade {db_trade['id']}: {e}")
            else:
                logger.warning(f"Position for {symbol} not found in database")

        logger.info(f"Position sync completed: {updates_made} updates made")

    async def cleanup_closed_positions(self, binance_positions: List[Dict], db_trades: List[Dict]):
        """Mark trades as closed if position is no longer active on Binance"""
        logger.info("Starting cleanup of closed positions...")

        # Get all symbols with active positions on Binance
        active_symbols = {pos.get('symbol') for pos in binance_positions if float(pos.get('positionAmt', 0)) != 0}

        # Find database trades that should be marked as closed
        trades_to_close = []
        for trade in db_trades:
            status = trade.get('status', '')

            if status != 'OPEN' or not trade.get('exchange_order_id'):
                continue

            # Get symbol with fallback logic
            symbol = trade.get('coin_symbol')

            # If coin_symbol is None, try to extract from parsed_signal
            if not symbol and trade.get('parsed_signal'):
                try:
                    parsed_signal = trade['parsed_signal']
                    if isinstance(parsed_signal, str):
                        import json
                        parsed_signal = json.loads(parsed_signal)
                    symbol = parsed_signal.get('coin_symbol')
                except (json.JSONDecodeError, TypeError):
                    pass

            # If still no symbol, try to extract from binance_response
            if not symbol and trade.get('binance_response'):
                try:
                    order_details = self.extract_order_details(trade['binance_response'])
                    symbol = order_details.get('symbol')
                    if symbol and symbol.endswith('USDT'):
                        symbol = symbol[:-4]  # Remove USDT suffix
                except Exception:
                    pass

            # If trade is OPEN but symbol is not in active positions
            if (symbol and symbol not in active_symbols):
                trades_to_close.append(trade)

        updates_made = 0
        current_time = datetime.now(timezone.utc).isoformat()

        for trade in trades_to_close:
            try:
                update_data = {
                    'status': 'CLOSED',
                    'updated_at': current_time,
                    'sync_issues': ['Position closed on Binance but not in database'],
                    'manual_verification_needed': True
                }

                self.supabase.table("trades").update(update_data).eq("id", trade['id']).execute()
                updates_made += 1
                logger.info(f"Marked trade {trade['id']} ({trade.get('coin_symbol')}) as CLOSED")

            except Exception as e:
                logger.error(f"Error closing trade {trade['id']}: {e}")

                logger.info(f"Cleanup completed: {updates_made} trades marked as closed")

    async def sync_closed_trades_from_history(self, db_trades: List[Dict]):
        """Sync closed trades using order history and trade history"""
        logger.info("Starting closed trades sync from history...")

        # Get time range for the last 48 hours
        end_time = int(datetime.now(timezone.utc).timestamp() * 1000)
        start_time = int((datetime.now(timezone.utc) - timedelta(hours=48)).timestamp() * 1000)

        updates_made = 0

        # Group database trades by symbol for efficient processing
        trades_by_symbol = {}
        for trade in db_trades:
            symbol = trade.get('coin_symbol')
            if symbol:
                if symbol not in trades_by_symbol:
                    trades_by_symbol[symbol] = []
                trades_by_symbol[symbol].append(trade)

        for symbol, symbol_trades in trades_by_symbol.items():
            try:
                trading_pair = f"{symbol}USDT"
                logger.info(f"Processing closed trades for {trading_pair}")

                # Get order history for this symbol
                order_history = await self.get_binance_order_history(
                    symbol=trading_pair,
                    limit=500,
                    start_time=start_time,
                    end_time=end_time
                )

                # Get user trades for this symbol
                user_trades = await self.get_binance_user_trades(
                    symbol=trading_pair,
                    limit=1000,
                    start_time=start_time,
                    end_time=end_time
                )

                # Create lookup for user trades by orderId
                trades_by_order_id = {trade.get('orderId'): trade for trade in user_trades if trade.get('orderId')}

                # Process each database trade for this symbol
                for db_trade in symbol_trades:
                    try:
                        # Extract order ID from database trade
                        binance_response = db_trade.get('binance_response', '')
                        if not binance_response:
                            continue

                        order_details = self.extract_order_details(binance_response)
                        order_id = order_details.get('orderId')

                        if not order_id:
                            continue

                        # Find this order in order history
                        order_info = None
                        for order in order_history:
                            if str(order.get('orderId')) == order_id:
                                order_info = order
                                break

                        # Find corresponding user trades
                        user_trade_info = trades_by_order_id.get(int(order_id))

                        # Update trade if it's closed or has incorrect status
                        if order_info:
                            order_status = order_info.get('status')
                            # Handle various order statuses
                            if order_status == 'FILLED':
                                # Order is filled, check if position is still open
                                position_still_open = any(
                                    pos.get('symbol') == trading_pair and
                                    float(pos.get('positionAmt', 0)) != 0
                                    for pos in await self.get_binance_positions()
                                )

                                if position_still_open:
                                    # Position is still open, update status to OPEN
                                    update_data = {
                                        'status': 'OPEN',
                                        'order_status_response': json.dumps(order_info),
                                        'updated_at': datetime.now(timezone.utc).isoformat(),
                                        'sync_error_count': 0,
                                        'sync_issues': [],
                                        'manual_verification_needed': False
                                    }
                                else:
                                    # Position is closed, update status to CLOSED
                                    update_data = {
                                        'status': 'CLOSED',
                                        'order_status_response': json.dumps(order_info),
                                        'updated_at': datetime.now(timezone.utc).isoformat(),
                                        'sync_error_count': 0,
                                        'sync_issues': [],
                                        'manual_verification_needed': False
                                    }
                            elif order_status in ['CANCELED', 'EXPIRED', 'REJECTED']:
                                # Order was cancelled/expired
                                update_data = {
                                    'status': 'FAILED',
                                    'order_status_response': json.dumps(order_info),
                                    'updated_at': datetime.now(timezone.utc).isoformat(),
                                    'sync_error_count': 0,
                                    'sync_issues': [],
                                    'manual_verification_needed': False
                                }
                            elif order_status == 'NEW':
                                # Order is still pending
                                update_data = {
                                    'status': 'PENDING',
                                    'order_status_response': json.dumps(order_info),
                                    'updated_at': datetime.now(timezone.utc).isoformat(),
                                    'sync_error_count': 0,
                                    'sync_issues': [],
                                    'manual_verification_needed': False
                                }
                            else:
                                # Unknown status, skip
                                continue

                            # Set exit price and PnL if we have user trade data
                            if user_trade_info:
                                price = float(user_trade_info.get('price', 0))
                                qty = float(user_trade_info.get('qty', 0))
                                realized_pnl = float(user_trade_info.get('realizedPnl', 0))

                                if price > 0:
                                    update_data['binance_exit_price'] = price

                                # Use Binance realized PnL if available, otherwise calculate
                                if realized_pnl != 0:
                                    update_data['realized_pnl'] = realized_pnl
                                    update_data['pnl_usd'] = realized_pnl
                                else:
                                    # Calculate PnL from entry and exit prices
                                    entry_price = db_trade.get('entry_price', 0)
                                    signal_type = db_trade.get('signal_type', 'LONG')
                                    if entry_price and price > 0:
                                        calculated_pnl = self.calculate_trade_pnl(
                                            float(entry_price), price, qty, signal_type
                                        )
                                        update_data['realized_pnl'] = calculated_pnl
                                        update_data['pnl_usd'] = calculated_pnl

                            # Update the trade
                            self.supabase.table("trades").update(update_data).eq("id", db_trade['id']).execute()
                            updates_made += 1
                            logger.info(f"Updated closed trade {db_trade['id']} ({symbol}) - status: {order_info.get('status')}")

                    except Exception as e:
                        logger.error(f"Error processing trade {db_trade['id']}: {e}")

            except Exception as e:
                logger.error(f"Error processing symbol {symbol}: {e}")

        logger.info(f"Closed trades sync completed: {updates_made} updates made")

    def test_json_parsing_with_sample_data(self):
        """Test JSON parsing with various sample data to debug issues"""
        print("🧪 Testing JSON parsing with sample data...")

        # Test cases
        test_cases = [
            ("", "Empty string"),
            ("null", "Null string"),
            ("None", "None string"),
            ("undefined", "Undefined string"),
            ("{}", "Empty JSON object"),
            ('{"orderId": "123", "symbol": "BTCUSDT"}', "Valid JSON"),
            ('{"orderId": 123, "symbol": "BTCUSDT"}', "Valid JSON with numeric orderId"),
            ('{"orderId": "0", "symbol": "BTCUSDT"}', "Zero orderId"),
            ('{"orderId": "", "symbol": "BTCUSDT"}', "Empty orderId"),
            ('{"symbol": "BTCUSDT"}', "Missing orderId"),
            ('{"orderId": "123"}', "Missing symbol"),
            ('invalid json', "Invalid JSON"),
            ('{"orderId": "5514939545","symbol":"BTCUSDT","status":"NEW","clientOrderId":"1400559676516601996","price":"0.00","avgPrice":"0.00","origQty":"0.001","executedQty":"0.000","cumQty":"0.000","cumQuote":"0.00000","timeInForce":"GTC","type":"MARKET","reduceOnly":false,"closePosition":false,"side":"BUY","positionSide":"BOTH","stopPrice":"0.00","workingType":"CONTRACT_PRICE","priceProtect":false,"origType":"MARKET","priceMatch":"NONE","selfTradePreventionMode":"EXPIRE_MAKER","goodTillDate":0,"updateTime":1754034213228}', "Real sample data")
        ]

        for test_data, description in test_cases:
            print(f"\n📝 Testing: {description}")
            print(f"   Input: {test_data[:100]}{'...' if len(test_data) > 100 else ''}")

            # Test extract_order_info
            order_id, symbol = self.extract_order_info(test_data)
            print(f"   extract_order_info result: orderId={order_id}, symbol={symbol}")

            # Test extract_order_details
            details = self.extract_order_details(test_data)
            if details:
                print(f"   extract_order_details result: orderId={details.get('orderId')}, symbol={details.get('symbol')}, status={details.get('status')}")
            else:
                print(f"   extract_order_details result: empty")

    async def validate_database_accuracy(self, binance_orders: List[Dict], binance_positions: List[Dict], db_trades: List[Dict]):
        """Validate database accuracy against Binance data"""
        logger.info("Starting database accuracy validation...")

        issues_found = []

        # Check for orders in database but not on Binance
        db_order_ids = set()
        for trade in db_trades:
            binance_response = trade.get('binance_response', '')
            if binance_response:
                order_details = self.extract_order_details(binance_response)
                order_id = order_details.get('orderId')
                if order_id:
                    db_order_ids.add(order_id)

        binance_order_ids = {str(order.get('orderId', '')) for order in binance_orders}

        # Orders in DB but not on Binance (should be closed/filled)
        missing_on_binance = db_order_ids - binance_order_ids
        if missing_on_binance:
            issues_found.append(f"Orders in database but not on Binance: {missing_on_binance}")

        # Check position consistency
        active_symbols = {pos.get('symbol') for pos in binance_positions if float(pos.get('positionAmt', 0)) != 0}

        # Build db_active_symbols with fallback logic for missing coin_symbol
        db_active_symbols = set()
        for trade in db_trades:
            if trade.get('status') == 'OPEN':
                # First try coin_symbol field
                symbol = trade.get('coin_symbol')

                # If coin_symbol is None, try to extract from parsed_signal
                if not symbol and trade.get('parsed_signal'):
                    try:
                        parsed_signal = trade['parsed_signal']
                        if isinstance(parsed_signal, str):
                            import json
                            parsed_signal = json.loads(parsed_signal)
                        symbol = parsed_signal.get('coin_symbol')
                    except (json.JSONDecodeError, TypeError):
                        pass

                # If still no symbol, try to extract from binance_response
                if not symbol and trade.get('binance_response'):
                    try:
                        order_details = self.extract_order_details(trade['binance_response'])
                        symbol = order_details.get('symbol')
                        if symbol and symbol.endswith('USDT'):
                            symbol = symbol[:-4]  # Remove USDT suffix
                    except Exception:
                        pass

                if symbol:
                    db_active_symbols.add(symbol)

        # Symbols with positions on Binance but not marked OPEN in DB
        binance_only = active_symbols - db_active_symbols
        if binance_only:
            issues_found.append(f"Positions on Binance but not OPEN in database: {binance_only}")

        # Symbols marked OPEN in DB but no position on Binance
        db_only = db_active_symbols - active_symbols
        if db_only:
            issues_found.append(f"Trades marked OPEN in database but no position on Binance: {db_only}")

        if issues_found:
            logger.warning("Database accuracy issues found:")
            for issue in issues_found:
                logger.warning(f"  - {issue}")
        else:
            logger.info("Database accuracy validation passed - no issues found")

        return issues_found
        """Test JSON parsing with sample binance_response data"""
        print("🧪 Testing JSON parsing with sample data...")

        # Sample data from your example
        sample_response = '''{"orderId":5514939545,"symbol":"BTCUSDT","status":"NEW","clientOrderId":"1400559676516601996","price":"0.00","avgPrice":"0.00","origQty":"0.001","executedQty":"0.000","cumQty":"0.000","cumQuote":"0.00000","timeInForce":"GTC","type":"MARKET","reduceOnly":false,"closePosition":false,"side":"BUY","positionSide":"BOTH","stopPrice":"0.00","workingType":"CONTRACT_PRICE","priceProtect":false,"origType":"MARKET","priceMatch":"NONE","selfTradePreventionMode":"EXPIRE_MAKER","goodTillDate":0,"updateTime":1754034213228}'''

        # Test basic extraction
        order_id, symbol = self.extract_order_info(sample_response)
        print(f"Basic extraction: orderId={order_id}, symbol={symbol}")

        # Test detailed extraction
        order_details = self.extract_order_details(sample_response)
        print(f"Detailed extraction:")
        print(f"  Order ID: {order_details.get('orderId')}")
        print(f"  Symbol: {order_details.get('symbol')}")
        print(f"  Status: {order_details.get('status')}")
        print(f"  Client Order ID: {order_details.get('clientOrderId')}")
        print(f"  Type: {order_details.get('type')}")
        print(f"  Side: {order_details.get('side')}")
        print(f"  Quantity: {order_details.get('origQty')}")
        print(f"  Executed: {order_details.get('executedQty')}")
        print(f"  Price: {order_details.get('price')}")
        print(f"  Avg Price: {order_details.get('avgPrice')}")
        print(f"  Update Time: {order_details.get('updateTime')}")

        return order_details

    async def run_full_sync(self):
        """Run complete sync from Binance to database"""
        print("🔄 Binance to Database Sync")
        print("=" * 50)

        if not await self.initialize():
            return

        try:
            # Get data from both sources
            print("📊 Fetching data...")
            binance_orders = await self.get_binance_orders()
            binance_positions = await self.get_binance_positions()
            db_trades = await self.get_database_trades()

            # Validate accuracy first
            print("🔍 Validating database accuracy...")
            issues = await self.validate_database_accuracy(binance_orders, binance_positions, db_trades)

            # Run syncs
            print("🔄 Syncing orders...")
            await self.sync_orders_to_database(binance_orders, db_trades)

            print("🔄 Syncing positions...")
            await self.sync_positions_to_database(binance_positions, db_trades)

            print("🧹 Cleaning up closed positions...")
            await self.cleanup_closed_positions(binance_positions, db_trades)

            print("📜 Syncing closed trades from history...")
            await self.sync_closed_trades_from_history(db_trades)

            # Final validation
            print("🔍 Final validation...")
            final_issues = await self.validate_database_accuracy(binance_orders, binance_positions, db_trades)

            print(f"\n✅ Sync completed!")
            print(f"Binance Orders: {len(binance_orders)}")
            print(f"Binance Positions: {len(binance_positions)}")
            print(f"Database Trades: {len(db_trades)}")
            print(f"Initial Issues: {len(issues)}")
            print(f"Final Issues: {len(final_issues)}")

        except Exception as e:
            logger.error(f"Error during sync: {e}")
        finally:
            if self.binance_exchange:
                await self.binance_exchange.close_client()

async def main():
    """Main function"""
    import argparse

    parser = argparse.ArgumentParser(description='Binance to Database Sync')
    parser.add_argument('--test-json', action='store_true',
                        help='Test JSON parsing with sample data')

    args = parser.parse_args()

    sync = BinanceDatabaseSync()

    if args.test_json:
        # Test JSON parsing without requiring connections
        sync.test_json_parsing_with_sample_data()
    else:
        await sync.run_full_sync()

if __name__ == "__main__":
    asyncio.run(main())