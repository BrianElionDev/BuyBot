#!/usr/bin/env python3
"""
P&L Testing with Order Lifecycle Matching

This script uses the exact order lifecycle (created_at to modified_at) 
to filter income history and get accurate P&L for each trade.

The process:
1. Get trade from database with created_at and modified_at
2. Use this time range to filter Binance income history
3. Match income records that occurred during the actual trade lifecycle

Usage:
    python scripts/test_pnl_with_order_lifecycle.py --symbol ETH --days 7
"""

import asyncio
import argparse
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple
import json
from pathlib import Path

# Add project root to path
import sys
sys.path.append(str(Path(__file__).parent.parent))

from src.exchange.binance_exchange import BinanceExchange
from discord_bot.utils.trade_retry_utils import calculate_pnl
from discord_bot.discord_bot import DiscordBot
import config.settings as settings

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class OrderLifecyclePnLTester:
    """Test P&L using exact order lifecycle for matching."""
    
    def __init__(self, api_key: str, api_secret: str, testnet: bool = False):
        self.binance_exchange = BinanceExchange(api_key, api_secret, testnet)
        self.testnet = testnet
        self.bot = None
        self.supabase = None
    
    async def initialize(self):
        """Initialize clients."""
        try:
            await self.binance_exchange._init_client()
            
            # Initialize bot and database
            self.bot = DiscordBot()
            self.supabase = self.bot.supabase
            
            logger.info("✅ All clients initialized successfully")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to initialize clients: {e}")
            return False
    
    async def get_database_trades(self, symbol: str = "", days: int = 30) -> List[Dict]:
        """Get trades from database with created_at and modified_at."""
        try:
            if not self.supabase:
                logger.error("Supabase client not initialized")
                return []
            
            # Calculate cutoff date
            cutoff = datetime.now(timezone.utc) - timedelta(days=days)
            cutoff_iso = cutoff.isoformat()
            
            # Query for trades with both timestamps
            query = self.supabase.from_("trades").select("*").gte("created_at", cutoff_iso)
            
            if symbol:
                query = query.eq("coin_symbol", symbol)
            
            response = query.execute()
            trades = response.data or []
            
            logger.info(f"Found {len(trades)} database trades")
            return trades
            
        except Exception as e:
            logger.error(f"Error fetching database trades: {e}")
            return []
    
    async def get_income_for_trade_period(self, symbol: str, start_time: int, end_time: int) -> List[Dict]:
        """Get income history for a specific trade period."""
        try:
            logger.info(f"Fetching {symbol}USDT income from {start_time} to {end_time}")
            
            # Add buffer time (1 hour before and after) to catch related income
            buffer_time = 60 * 60 * 1000  # 1 hour in milliseconds
            search_start = start_time - buffer_time
            search_end = end_time + buffer_time
            
            all_incomes = []
            chunk_start = search_start
            
            while chunk_start < search_end:
                chunk_end = min(chunk_start + (7 * 24 * 60 * 60 * 1000), search_end)
                
                try:
                    chunk_incomes = await self.binance_exchange.get_income_history(
                        symbol=f"{symbol}USDT",
                        start_time=chunk_start,
                        end_time=chunk_end,
                        limit=1000,
                    )
                    all_incomes.extend(chunk_incomes)
                    await asyncio.sleep(0.5)  # Rate limiting
                except Exception as e:
                    logger.error(f"Error fetching chunk income: {e}")
                
                chunk_start = chunk_end
            
            # Filter to exact trade period
            filtered_incomes = []
            for income in all_incomes:
                income_time = income.get('time')
                if income_time and start_time <= int(income_time) <= end_time:
                    filtered_incomes.append(income)
            
            logger.info(f"Found {len(filtered_incomes)} income records within trade period")
            return filtered_incomes
            
        except Exception as e:
            logger.error(f"Error getting income for trade period: {e}")
            return []
    
    def parse_timestamp(self, timestamp_str: str) -> Optional[int]:
        """Parse timestamp string to milliseconds."""
        try:
            # Handle ISO format
            if 'T' in timestamp_str:
                dt = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                return int(dt.timestamp() * 1000)
            
            # Handle Unix timestamp
            if timestamp_str.isdigit():
                ts = int(timestamp_str)
                # If it's seconds, convert to milliseconds
                if ts < 1000000000000:  # Before year 2001
                    ts *= 1000
                return ts
            
            return None
        except Exception:
            return None
    
    def get_order_lifecycle(self, db_trade: Dict) -> Tuple[Optional[int], Optional[int], Optional[int]]:
        """Get order start, end, and duration in milliseconds."""
        try:
            created_at = db_trade.get('created_at') or db_trade.get('createdAt')
            modified_at = db_trade.get('updated_at') or db_trade.get('updatedAt') or db_trade.get('modified_at')
            
            if not created_at:
                logger.warning(f"Trade {db_trade.get('id')} has no created_at timestamp")
                return None, None, None
            
            start_time = self.parse_timestamp(str(created_at))
            if not start_time:
                logger.warning(f"Trade {db_trade.get('id')} has invalid created_at: {created_at}")
                return None, None, None
            
            # If no modified_at, use created_at (order not completed yet)
            if not modified_at:
                end_time = start_time
                duration = 0
                logger.info(f"Trade {db_trade.get('id')} has no modified_at - order not completed")
            else:
                end_time = self.parse_timestamp(str(modified_at))
                if not end_time:
                    end_time = start_time
                    duration = 0
                    logger.warning(f"Trade {db_trade.get('id')} has invalid modified_at: {modified_at}")
                else:
                    duration = end_time - start_time
            
            return start_time, end_time, duration
            
        except Exception as e:
            logger.error(f"Error getting order lifecycle: {e}")
            return None, None, None
    
    def determine_trade_status(self, db_trade: Dict) -> str:
        """Determine if trade is open, closed, or unknown."""
        status = db_trade.get('status', '').upper()
        exit_price = db_trade.get('exit_price')
        
        if status in ['CLOSED', 'FILLED', 'COMPLETED']:
            return 'CLOSED'
        elif exit_price and float(exit_price) > 0:
            return 'CLOSED'
        elif status in ['OPEN', 'PENDING', 'PARTIALLY_FILLED']:
            return 'OPEN'
        else:
            return 'UNKNOWN'
    
    def calculate_expected_pnl_range(self, position_size: float, entry_price: float, 
                                   exit_price: float, position_type: str) -> Tuple[float, float]:
        """Calculate expected P&L range based on position size and prices."""
        try:
            if not all([position_size, entry_price, exit_price]):
                return 0.0, 0.0
            
            position_size = float(position_size)
            entry_price = float(entry_price)
            exit_price = float(exit_price)
            
            # Calculate base P&L
            if position_type.upper() == 'LONG':
                base_pnl = (exit_price - entry_price) * position_size
            else:  # SHORT
                base_pnl = (entry_price - exit_price) * position_size
            
            # Add 0.1% fee (entry + exit)
            fee = (entry_price + exit_price) * position_size * 0.001
            
            # Expected range: base P&L ± 20% for slippage and market conditions
            min_pnl = base_pnl - fee - (abs(base_pnl) * 0.2)
            max_pnl = base_pnl - fee + (abs(base_pnl) * 0.2)
            
            return min_pnl, max_pnl
            
        except Exception as e:
            logger.error(f"Error calculating expected P&L range: {e}")
            return 0.0, 0.0
    
    async def match_trades_with_income_by_lifecycle(self, db_trades: List[Dict]) -> List[Dict]:
        """Match trades using exact order lifecycle."""
        matched_trades = []
        
        # Sort trades by start time for better processing
        sorted_trades = sorted(db_trades, key=lambda t: self.get_order_lifecycle(t)[0] or 0)
        
        for db_trade in sorted_trades:
            trade_id = db_trade.get('id')
            symbol = db_trade.get('coin_symbol', '')
            position_size = db_trade.get('position_size')
            entry_price = db_trade.get('entry_price')
            exit_price = db_trade.get('exit_price')
            position_type = db_trade.get('signal_type', 'LONG')
            
            # Get order lifecycle
            start_time, end_time, duration = self.get_order_lifecycle(db_trade)
            
            if not start_time:
                logger.warning(f"Trade {trade_id} has no valid timestamps, skipping")
                continue
            
            # Determine trade status
            trade_status = self.determine_trade_status(db_trade)
            
            # Calculate expected P&L range
            min_expected_pnl, max_expected_pnl = self.calculate_expected_pnl_range(
                position_size, entry_price, exit_price, position_type
            )
            
            # Log order lifecycle
            duration_hours = duration / (1000 * 60 * 60) if duration else 0
            start_dt = datetime.fromtimestamp(start_time / 1000, tz=timezone.utc)
            end_dt = datetime.fromtimestamp(end_time / 1000, tz=timezone.utc)
            
            logger.info(f"Trade {trade_id} ({symbol}): Order lifecycle")
            logger.info(f"  Start: {start_dt.strftime('%Y-%m-%d %H:%M:%S')} UTC")
            logger.info(f"  End: {end_dt.strftime('%Y-%m-%d %H:%M:%S')} UTC")
            logger.info(f"  Duration: {duration_hours:.1f} hours")
            logger.info(f"  Status: {trade_status}")
            
            # Get income records for this specific trade period
            income_records = await self.get_income_for_trade_period(symbol, start_time, end_time)
            
            if not income_records:
                logger.info(f"Trade {trade_id} ({symbol}): No income records found during order lifecycle")
                
                # Add trade with no income
                matched_trade = {
                    'db_trade': db_trade,
                    'matching_incomes': [],
                    'total_realized_pnl': 0.0,
                    'total_commission': 0.0,
                    'total_funding_fee': 0.0,
                    'trade_start': start_time,
                    'trade_end': end_time,
                    'trade_duration': duration,
                    'trade_status': trade_status,
                    'expected_pnl_range': (min_expected_pnl, max_expected_pnl)
                }
                matched_trades.append(matched_trade)
                continue
            
            # Group income records by type
            income_by_type = {}
            for income in income_records:
                if not isinstance(income, dict):
                    continue
                
                income_type = income.get('incomeType') or income.get('type')
                if not income_type:
                    continue
                
                if income_type not in income_by_type:
                    income_by_type[income_type] = []
                income_by_type[income_type].append(income)
            
            logger.info(f"Trade {trade_id} ({symbol}): Found income types: {list(income_by_type.keys())}")
            
            # Match income records to this trade
            matched_incomes = []
            total_realized_pnl = 0.0
            total_commission = 0.0
            total_funding_fee = 0.0
            
            for income_type, incomes in income_by_type.items():
                for income in incomes:
                    income_time = income.get('time')
                    if not income_time:
                        continue
                    
                    try:
                        income_timestamp = int(income_time)
                        income_value = float(income.get('income', 0.0))
                        
                        # Calculate time from order start
                        time_from_start = (income_timestamp - start_time) / (1000 * 60)  # minutes
                        
                        # Log each income record
                        logger.info(f"  ✅ {income_type}: {income_value:.6f} "
                                   f"(+{time_from_start:.1f} min from order start)")
                        
                        # Add to totals
                        if income_type == 'REALIZED_PNL':
                            total_realized_pnl += income_value
                        elif income_type == 'COMMISSION':
                            total_commission += income_value
                        elif income_type == 'FUNDING_FEE':
                            total_funding_fee += income_value
                        
                        matched_incomes.append({
                            'income': income,
                            'type': income_type,
                            'time_from_start': time_from_start,
                            'timestamp': income_timestamp,
                            'value': income_value
                        })
                    
                    except Exception as e:
                        logger.error(f"Error processing income record: {e}")
                        continue
            
            # Log matching results
            logger.info(f"Trade {trade_id} ({symbol}): Summary")
            logger.info(f"  Position Size: {position_size}, Expected P&L Range: [{min_expected_pnl:.6f}, {max_expected_pnl:.6f}]")
            logger.info(f"  REALIZED_PNL: {total_realized_pnl:.6f}")
            logger.info(f"  COMMISSION: {total_commission:.6f}")
            logger.info(f"  FUNDING_FEE: {total_funding_fee:.6f}")
            logger.info(f"  Total Income Records: {len(matched_incomes)}")
            
            # Check if P&L is within expected range
            if min_expected_pnl <= total_realized_pnl <= max_expected_pnl:
                logger.info(f"  ✅ P&L within expected range")
            else:
                logger.info(f"  ⚠️ P&L outside expected range")
            
            matched_trade = {
                'db_trade': db_trade,
                'matching_incomes': matched_incomes,
                'total_realized_pnl': total_realized_pnl,
                'total_commission': total_commission,
                'total_funding_fee': total_funding_fee,
                'trade_start': start_time,
                'trade_end': end_time,
                'trade_duration': duration,
                'trade_status': trade_status,
                'expected_pnl_range': (min_expected_pnl, max_expected_pnl)
            }
            
            matched_trades.append(matched_trade)
        
        logger.info(f"✅ Processed {len(matched_trades)} trades with order lifecycle matching")
        return matched_trades
    
    def calculate_manual_pnl(self, db_trade: Dict) -> float:
        """Calculate P&L manually for comparison."""
        try:
            entry_price = db_trade.get('entry_price')
            exit_price = db_trade.get('exit_price')
            position_size = db_trade.get('position_size')
            position_type = db_trade.get('signal_type', 'LONG')
            
            # Handle None values
            if entry_price is None or position_size is None or exit_price is None:
                logger.warning(f"Missing data for trade {db_trade.get('id')}: "
                             f"entry_price={entry_price}, exit_price={exit_price}, position_size={position_size}")
                return 0.0
            
            entry_price = float(entry_price)
            exit_price = float(exit_price)
            position_size = float(position_size)
            
            if entry_price > 0 and position_size > 0 and exit_price > 0:
                return calculate_pnl(entry_price, exit_price, position_size, position_type)
            else:
                return 0.0
        except Exception as e:
            logger.error(f"Error calculating manual P&L: {e}")
            return 0.0
    
    def analyze_matched_trades(self, matched_trades: List[Dict]) -> Dict:
        """Analyze matched trades and compare P&L calculations."""
        analysis = {
            'total_trades': len(matched_trades),
            'trades_with_pnl': 0,
            'trades_with_commission': 0,
            'trades_with_funding': 0,
            'closed_trades': 0,
            'open_trades': 0,
            'trades_with_income': 0,
            'exact_matches': 0,
            'close_matches': 0,
            'large_discrepancies': 0,
            'position_size_matches': 0,
            'total_binance_pnl': 0.0,
            'total_manual_pnl': 0.0,
            'total_commission': 0.0,
            'total_funding_fee': 0.0,
            'total_duration_hours': 0.0,
            'detailed_results': []
        }
        
        for matched in matched_trades:
            db_trade = matched['db_trade']
            binance_pnl = matched['total_realized_pnl']
            commission = matched['total_commission']
            funding_fee = matched['total_funding_fee']
            trade_status = matched['trade_status']
            duration = matched['trade_duration']
            expected_range = matched['expected_pnl_range']
            
            # Count trade types
            if trade_status == 'CLOSED':
                analysis['closed_trades'] += 1
            elif trade_status == 'OPEN':
                analysis['open_trades'] += 1
            
            # Count trades with income
            if len(matched['matching_incomes']) > 0:
                analysis['trades_with_income'] += 1
            
            # Calculate manual P&L
            manual_pnl = self.calculate_manual_pnl(db_trade)
            
            # Check if P&L is within expected range
            min_expected, max_expected = expected_range
            if min_expected <= binance_pnl <= max_expected:
                analysis['position_size_matches'] += 1
            
            # Compare
            diff = abs(binance_pnl - manual_pnl)
            
            if binance_pnl != 0:
                analysis['trades_with_pnl'] += 1
                
                if diff < 0.01:
                    analysis['exact_matches'] += 1
                elif diff < 0.1:
                    analysis['close_matches'] += 1
                else:
                    analysis['large_discrepancies'] += 1
            
            if commission != 0:
                analysis['trades_with_commission'] += 1
            
            if funding_fee != 0:
                analysis['trades_with_funding'] += 1
            
            analysis['total_binance_pnl'] += binance_pnl
            analysis['total_manual_pnl'] += manual_pnl
            analysis['total_commission'] += commission
            analysis['total_funding_fee'] += funding_fee
            analysis['total_duration_hours'] += duration / (1000 * 60 * 60) if duration else 0
            
            # Store detailed result
            result = {
                'trade_id': db_trade.get('id'),
                'symbol': db_trade.get('coin_symbol'),
                'status': trade_status,
                'entry_price': db_trade.get('entry_price'),
                'exit_price': db_trade.get('exit_price'),
                'position_size': db_trade.get('position_size'),
                'position_type': db_trade.get('signal_type'),
                'binance_pnl': binance_pnl,
                'manual_pnl': manual_pnl,
                'commission': commission,
                'funding_fee': funding_fee,
                'difference': diff,
                'income_count': len(matched['matching_incomes']),
                'expected_range': expected_range,
                'within_range': min_expected <= binance_pnl <= max_expected,
                'duration_hours': duration / (1000 * 60 * 60) if duration else 0
            }
            analysis['detailed_results'].append(result)
        
        return analysis
    
    def print_results(self, analysis: Dict):
        """Print detailed analysis results."""
        print("\n" + "="*80)
        print("P&L MATCHING USING ORDER LIFECYCLE")
        print("="*80)
        
        print(f"\n📊 SUMMARY:")
        print(f"   Total trades analyzed: {analysis['total_trades']}")
        print(f"   Closed trades: {analysis['closed_trades']}")
        print(f"   Open trades: {analysis['open_trades']}")
        print(f"   Trades with income: {analysis['trades_with_income']}")
        print(f"   Trades with P&L: {analysis['trades_with_pnl']}")
        print(f"   Trades with commission: {analysis['trades_with_commission']}")
        print(f"   Trades with funding fees: {analysis['trades_with_funding']}")
        print(f"   Position size matches: {analysis['position_size_matches']}")
        print(f"   Exact matches (0.01 tolerance): {analysis['exact_matches']}")
        print(f"   Close matches (0.1 tolerance): {analysis['close_matches']}")
        print(f"   Large discrepancies (>0.1): {analysis['large_discrepancies']}")
        print(f"   Total order duration: {analysis['total_duration_hours']:.1f} hours")
        
        if analysis['trades_with_pnl'] > 0:
            accuracy_rate = (analysis['exact_matches'] + analysis['close_matches']) / analysis['trades_with_pnl'] * 100
            position_accuracy = analysis['position_size_matches'] / analysis['trades_with_pnl'] * 100
            income_rate = analysis['trades_with_income'] / analysis['total_trades'] * 100
            print(f"   Overall accuracy rate: {accuracy_rate:.1f}%")
            print(f"   Position size accuracy: {position_accuracy:.1f}%")
            print(f"   Income matching rate: {income_rate:.1f}%")
        
        print(f"\n💰 P&L TOTALS:")
        print(f"   Total Binance P&L: {analysis['total_binance_pnl']:.6f} USDT")
        print(f"   Total Manual P&L: {analysis['total_manual_pnl']:.6f} USDT")
        print(f"   Total Commission: {analysis['total_commission']:.6f} USDT")
        print(f"   Total Funding Fees: {analysis['total_funding_fee']:.6f} USDT")
        print(f"   Net P&L: {analysis['total_binance_pnl'] - analysis['total_commission']:.6f} USDT")
        
        print(f"\n📋 DETAILED COMPARISONS:")
        print(f"{'TradeID':<8} {'Symbol':<8} {'Status':<8} {'Duration':<8} {'Entry':<8} {'Exit':<8} {'Size':<6} {'Binance':<12} {'Manual':<12} {'Diff':<8} {'Range':<8} {'Income':<6}")
        print("-" * 130)
        
        for result in analysis['detailed_results'][:15]:  # Show first 15
            entry_price = result['entry_price'] or 0
            exit_price = result['exit_price'] or 0
            position_size = result['position_size'] or 0
            duration_hours = result['duration_hours']
            range_indicator = "✓" if result['within_range'] else "✗"
            
            print(f"{result['trade_id']:<8} {result['symbol']:<8} {result['status']:<8} "
                  f"{duration_hours:<8.1f} {entry_price:<8.2f} {exit_price:<8.2f} {position_size:<6.3f} "
                  f"{result['binance_pnl']:<12.6f} {result['manual_pnl']:<12.6f} "
                  f"{result['difference']:<8.6f} {range_indicator:<8} {result['income_count']:<6}")
        
        if len(analysis['detailed_results']) > 15:
            print(f"... and {len(analysis['detailed_results']) - 15} more trades")
        
        # Show largest discrepancies
        if analysis['large_discrepancies'] > 0:
            print(f"\n⚠️  LARGEST DISCREPANCIES:")
            large_discrepancies = [r for r in analysis['detailed_results'] if r['difference'] > 0.1]
            large_discrepancies.sort(key=lambda x: x['difference'], reverse=True)
            
            for result in large_discrepancies[:5]:
                print(f"   Trade {result['trade_id']} ({result['symbol']}, {result['status']}, "
                      f"Duration: {result['duration_hours']:.1f}h): "
                      f"Binance={result['binance_pnl']:.6f}, Manual={result['manual_pnl']:.6f}, "
                      f"Diff={result['difference']:.6f}, In Range: {result['within_range']}")


async def main():
    """Main function."""
    parser = argparse.ArgumentParser(description="Test P&L using order lifecycle matching")
    parser.add_argument("--symbol", type=str, help="Trading symbol (e.g., ETH, BTC)")
    parser.add_argument("--days", type=int, default=30, help="Number of days to analyze (default: 30)")
    parser.add_argument("--all-symbols", action="store_true", help="Test all symbols")
    parser.add_argument("--testnet", action="store_true", help="Use testnet")
    
    args = parser.parse_args()
    
    # Get settings
    api_key = settings.BINANCE_API_KEY
    api_secret = settings.BINANCE_API_SECRET
    
    if not api_key or not api_secret:
        logger.error("❌ Binance API credentials not found in environment")
        return
    
    # Initialize tester
    tester = OrderLifecyclePnLTester(api_key, api_secret, args.testnet)
    
    if not await tester.initialize():
        return
    
    try:
        # Get database trades
        db_trades = await tester.get_database_trades(args.symbol, args.days)
        
        if not db_trades:
            logger.warning("No database trades found")
            return
        
        # Match trades using order lifecycle
        matched_trades = await tester.match_trades_with_income_by_lifecycle(db_trades)
        
        if not matched_trades:
            logger.warning("No trades processed")
            return
        
        # Analyze results
        analysis = tester.analyze_matched_trades(matched_trades)
        
        # Print results
        tester.print_results(analysis)
        
    except Exception as e:
        logger.error(f"Error during testing: {e}")
    
    print("\n✅ P&L testing using order lifecycle completed")


if __name__ == "__main__":
    asyncio.run(main())
