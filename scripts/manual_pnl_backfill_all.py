#!/usr/bin/env python3
"""
Manual P&L Backfill Script - Backfills ALL trades including those with existing P&L

This script forces backfill of P&L and exit price data for ALL closed trades,
regardless of whether they already have P&L data. Useful for:
- Getting more accurate P&L data from Binance income history
- Re-calculating P&L with improved methods
- Fixing trades with incorrect P&L data

Usage:
    python scripts/manual_pnl_backfill_all.py --symbol ETH --days 30
    python scripts/manual_pnl_backfill_all.py --all-symbols --days 60
    python scripts/manual_pnl_backfill_all.py --force-update --days 7
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

from discord_bot.discord_bot import DiscordBot
from discord_bot.utils.trade_retry_utils import (
    get_order_lifecycle,
    get_income_for_trade_period,
    extract_symbol_from_trade
)
import config.settings as settings

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class ManualPnLBackfiller:
    """Manual P&L backfiller that processes ALL trades."""
    
    def __init__(self, testnet: bool = False):
        self.testnet = testnet
        self.bot = None
        self.supabase = None
    
    async def initialize(self):
        """Initialize bot and database."""
        try:
            # Initialize bot
            self.bot = DiscordBot()
            self.supabase = self.bot.supabase
            
            # Initialize Binance client if needed
            if not self.bot.binance_exchange.client:
                await self.bot.binance_exchange._init_client()
            
            logger.info("✅ Bot and database initialized successfully")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to initialize: {e}")
            return False
    
    async def get_all_closed_trades(self, symbol: str = "", days: int = 30) -> List[Dict]:
        """Get ALL closed trades from database, regardless of existing P&L."""
        try:
            if not self.supabase:
                logger.error("Supabase client not initialized")
                return []
            
            # Calculate cutoff date
            cutoff = datetime.now(timezone.utc) - timedelta(days=days)
            cutoff_iso = cutoff.isoformat()
            
            # Query for ALL closed trades (not just missing P&L)
            query = self.supabase.from_("trades").select("*").eq("status", "CLOSED").gte("created_at", cutoff_iso)
            
            if symbol:
                query = query.eq("coin_symbol", symbol)
            
            response = query.execute()
            trades = response.data or []
            
            logger.info(f"Found {len(trades)} closed trades for backfill")
            return trades
            
        except Exception as e:
            logger.error(f"Error fetching database trades: {e}")
            return []
    
    async def backfill_single_trade_manual(self, trade: Dict) -> Dict:
        """Backfill a single trade manually and return detailed results."""
        try:
            trade_id = trade.get('id')
            original_pnl = trade.get('pnl_usd')
            original_exit_price = trade.get('binance_exit_price')
            
            # Use the enhanced symbol extraction function
            symbol = extract_symbol_from_trade(trade)
            
            if not symbol:
                return {
                    'trade_id': trade_id,
                    'symbol': None,
                    'success': False,
                    'error': 'Missing symbol',
                    'original_pnl': original_pnl,
                    'original_exit_price': original_exit_price,
                    'new_pnl': None,
                    'new_exit_price': None,
                    'income_count': 0
                }
            
            # Get order lifecycle (uses updated_at as fallback when closed_at is missing)
            start_time, end_time, duration = get_order_lifecycle(trade)
            
            if not start_time:
                return {
                    'trade_id': trade_id,
                    'symbol': symbol,
                    'success': False,
                    'error': 'No valid timestamps',
                    'original_pnl': original_pnl,
                    'original_exit_price': original_exit_price,
                    'new_pnl': None,
                    'new_exit_price': None,
                    'income_count': 0
                }
            
            # Get income records for this specific trade period
            income_records = await get_income_for_trade_period(self.bot, symbol, start_time, end_time)
            
            if not income_records:
                return {
                    'trade_id': trade_id,
                    'symbol': symbol,
                    'success': False,
                    'error': 'No income records found',
                    'original_pnl': original_pnl,
                    'original_exit_price': original_exit_price,
                    'new_pnl': None,
                    'new_exit_price': None,
                    'income_count': 0
                }
            
            # Calculate P&L components from Binance income history
            total_realized_pnl = 0.0
            total_commission = 0.0
            total_funding_fee = 0.0
            exit_price = 0.0
            
            # Process all income records
            for income in income_records:
                if not isinstance(income, dict):
                    continue
                
                income_type = income.get('incomeType') or income.get('type')
                income_value = float(income.get('income', 0.0))
                
                if income_type == 'REALIZED_PNL':
                    total_realized_pnl += income_value
                    # Track the latest price from realized P&L records
                    if income.get('price'):
                        exit_price = float(income.get('price', 0.0))
                elif income_type == 'COMMISSION':
                    total_commission += income_value
                elif income_type == 'FUNDING_FEE':
                    total_funding_fee += income_value
            
            # Calculate NET P&L (what Binance position history shows)
            net_pnl = total_realized_pnl + total_commission + total_funding_fee
            
            # Prepare update data
            update_data = {
                'updated_at': datetime.now(timezone.utc).isoformat()
            }
            
            # Only fix missing closed_at for historical trades (backfill scenario)
            # Import timestamp manager for historical fixes
            if not trade.get('closed_at') and trade.get('status') == 'CLOSED':
                from discord_bot.utils.timestamp_manager import fix_historical_timestamps
                await fix_historical_timestamps(self.bot.supabase, trade_id)
            
            # Always update P&L if we have income records from Binance
            if len(income_records) > 0:
                # Store REALIZED_PNL only in pnl_usd (existing column)
                update_data['pnl_usd'] = str(total_realized_pnl)
                
                # Only add new columns if they exist in the database
                # Note: These columns need to be added to the database schema first
                update_data['net_pnl'] = str(net_pnl)
                # update_data['commission'] = str(total_commission)
                # update_data['funding_fee'] = str(total_funding_fee)
            
            # Always update exit price if we have one from realized P&L records
            if exit_price > 0:
                update_data['binance_exit_price'] = str(exit_price)
            
            # Also update coin_symbol if it was missing and we extracted it
            if not trade.get('coin_symbol') and symbol:
                update_data['coin_symbol'] = symbol
            
            # Update database
            if len(update_data) > 1:  # More than just updated_at
                response = self.supabase.from_("trades").update(update_data).eq("id", trade_id).execute()
                if response.data:
                    return {
                        'trade_id': trade_id,
                        'symbol': symbol,
                        'success': True,
                        'error': None,
                        'original_pnl': original_pnl,
                        'original_exit_price': original_exit_price,
                        'new_pnl': total_realized_pnl,  # REALIZED_PNL only (stored in pnl_usd)
                        'new_net_pnl': net_pnl,  # NET P&L including fees (calculated but not stored)
                        'new_exit_price': exit_price,
                        'income_count': len(income_records),
                        'total_income_records': len(income_records),
                        'batches': len([r for r in income_records if isinstance(r, dict) and (r.get('incomeType') or r.get('type')) == 'REALIZED_PNL']),
                        'realized_pnl': total_realized_pnl,
                        'commission': total_commission,
                        'funding_fee': total_funding_fee
                    }
            
            return {
                'trade_id': trade_id,
                'symbol': symbol,
                'success': False,
                'error': 'No data to update',
                'original_pnl': original_pnl,
                'original_exit_price': original_exit_price,
                'new_pnl': total_realized_pnl,  # REALIZED_PNL only
                'new_net_pnl': net_pnl,  # NET P&L including fees
                'new_exit_price': exit_price,
                'income_count': len(income_records)
            }
            
        except Exception as e:
            logger.error(f"Error backfilling trade {trade.get('id')}: {e}")
            return {
                'trade_id': trade.get('id'),
                'symbol': trade.get('coin_symbol'),
                'success': False,
                'error': str(e),
                'original_pnl': trade.get('pnl_usd'),
                'original_exit_price': trade.get('binance_exit_price'),
                'new_pnl': None,
                'new_exit_price': None,
                'income_count': 0
            }
    
    async def backfill_all_trades(self, symbol: str = "", days: int = 30) -> Dict:
        """Backfill ALL trades regardless of existing P&L data."""
        try:
            logger.info(f"🔄 Starting manual P&L backfill for ALL trades ({symbol or 'all symbols'}) over {days} days")
            
            # Get all closed trades
            all_trades = await self.get_all_closed_trades(symbol, days)
            
            if not all_trades:
                logger.warning("No closed trades found")
                return {'status': 'no_trades', 'results': []}
            
            # Process each trade
            results = []
            successful_updates = 0
            total_pnl_change = 0.0
            total_exit_price_changes = 0
            
            for i, trade in enumerate(all_trades):
                logger.info(f"Processing trade {i+1}/{len(all_trades)}: {trade.get('id')}")
                
                result = await self.backfill_single_trade_manual(trade)
                results.append(result)
                
                if result['success']:
                    successful_updates += 1
                    
                    # Track changes
                    if result['original_pnl'] is not None and result['new_pnl'] is not None:
                        pnl_change = result['new_pnl'] - float(result['original_pnl'])
                        total_pnl_change += pnl_change
                    
                    if result['original_exit_price'] is not None and result['new_exit_price'] is not None:
                        if result['new_exit_price'] != float(result['original_exit_price']):
                            total_exit_price_changes += 1
                
                await asyncio.sleep(0.1)  # Rate limiting
            
            # Analyze results
            analysis = {
                'total_trades': len(all_trades),
                'successful_updates': successful_updates,
                'success_rate': (successful_updates / len(all_trades)) * 100 if all_trades else 0,
                'total_pnl_change': total_pnl_change,
                'total_exit_price_changes': total_exit_price_changes,
                'results': results
            }
            
            return analysis
            
        except Exception as e:
            logger.error(f"Error in manual backfill: {e}")
            return {'status': 'error', 'error': str(e), 'results': []}
    
    def print_results(self, analysis: Dict):
        """Print detailed backfill results."""
        print("\n" + "="*80)
        print("MANUAL P&L BACKFILL RESULTS (ALL TRADES)")
        print("="*80)
        
        if analysis.get('status') == 'no_trades':
            print("❌ No closed trades found for backfill")
            return
        
        if analysis.get('status') == 'error':
            print(f"❌ Backfill failed: {analysis.get('error')}")
            return
        
        print(f"\n📊 SUMMARY:")
        print(f"   Total trades processed: {analysis['total_trades']}")
        print(f"   Successful updates: {analysis['successful_updates']}")
        print(f"   Success rate: {analysis['success_rate']:.1f}%")
        print(f"   Total P&L change: {analysis['total_pnl_change']:.6f} USDT")
        print(f"   Exit price changes: {analysis['total_exit_price_changes']}")
        
        # Show detailed results for first 15 trades
        print(f"\n📋 DETAILED RESULTS (First 15):")
        print(f"{'TradeID':<8} {'Symbol':<8} {'Success':<8} {'Batches':<8} {'Old PnL':<12} {'New PnL':<12} {'Net PnL':<12} {'Change':<10} {'Old Exit':<10} {'New Exit':<10}")
        print("-" * 120)
        
        for result in analysis['results'][:15]:
            success_indicator = "✅" if result['success'] else "❌"
            old_pnl = result['original_pnl'] or 0
            new_pnl = result['new_pnl'] or 0  # REALIZED_PNL only
            new_net_pnl = result.get('new_net_pnl', 0)  # NET P&L including fees
            pnl_change = new_pnl - old_pnl if old_pnl is not None and new_pnl is not None else 0
            old_exit = result['original_exit_price'] or 0
            new_exit = result['new_exit_price'] or 0
            batches = result.get('batches', result.get('income_count', 0))
            
            print(f"{result['trade_id']:<8} {result['symbol']:<8} {success_indicator:<8} "
                  f"{batches:<8} {old_pnl:<12.6f} {new_pnl:<12.6f} {new_net_pnl:<12.6f} "
                  f"{pnl_change:<10.6f} {old_exit:<10.2f} {new_exit:<10.2f}")
            
            # Show P&L breakdown for successful trades
            if result['success'] and 'realized_pnl' in result:
                realized = result.get('realized_pnl', 0)
                commission = result.get('commission', 0)
                funding = result.get('funding_fee', 0)
                print(f"           Breakdown: Realized={realized:.6f}, Commission={commission:.6f}, Funding={funding:.6f}")
                print(f"           P&L: pnl_usd={realized:.6f}, net_pnl={realized+commission+funding:.6f}")
        
        if len(analysis['results']) > 15:
            print(f"... and {len(analysis['results']) - 15} more trades")
        
        # Show largest P&L changes
        successful_results = [r for r in analysis['results'] if r['success'] and r['original_pnl'] is not None and r['new_pnl'] is not None]
        if successful_results:
            print(f"\n💰 LARGEST P&L CHANGES:")
            pnl_changes = []
            for result in successful_results:
                pnl_change = result['new_pnl'] - float(result['original_pnl'])
                pnl_changes.append((result, pnl_change))
            
            pnl_changes.sort(key=lambda x: abs(x[1]), reverse=True)
            
            for result, change in pnl_changes[:5]:
                batches = result.get('batches', result.get('income_count', 0))
                realized = result.get('realized_pnl', 0)
                commission = result.get('commission', 0)
                funding = result.get('funding_fee', 0)
                net_pnl = result.get('new_net_pnl', realized + commission + funding)
                print(f"   Trade {result['trade_id']} ({result['symbol']}): "
                      f"{result['original_pnl']:.6f} → {result['new_pnl']:.6f} (REALIZED_PNL) "
                      f"→ {net_pnl:.6f} (NET P&L) "
                      f"(Change: {change:+.6f}, {batches} batches)")
                print(f"           Breakdown: Realized={realized:.6f}, Commission={commission:.6f}, Funding={funding:.6f}")
                print(f"           Database: pnl_usd={result['new_pnl']:.6f}, net_pnl={net_pnl:.6f}")
        
        # Show error summary
        errors = [r for r in analysis['results'] if not r['success']]
        if errors:
            print(f"\n⚠️  ERROR SUMMARY:")
            error_counts = {}
            for error in errors:
                error_msg = error.get('error', 'Unknown error')
                error_counts[error_msg] = error_counts.get(error_msg, 0) + 1
            
            for error_msg, count in error_counts.items():
                print(f"   {error_msg}: {count} trades")


async def main():
    """Main function."""
    parser = argparse.ArgumentParser(description="Manual P&L backfill for ALL trades")
    parser.add_argument("--symbol", type=str, help="Trading symbol (e.g., ETH, BTC)")
    parser.add_argument("--days", type=int, default=30, help="Number of days to analyze (default: 30)")
    parser.add_argument("--all-symbols", action="store_true", help="Process all symbols")
    parser.add_argument("--testnet", action="store_true", help="Use testnet")
    parser.add_argument("--force-update", action="store_true", help="Force update even if data exists")
    
    args = parser.parse_args()
    
    # Initialize backfiller
    backfiller = ManualPnLBackfiller(args.testnet)
    
    if not await backfiller.initialize():
        return
    
    try:
        # Backfill all trades
        analysis = await backfiller.backfill_all_trades(args.symbol, args.days)
        
        # Print results
        backfiller.print_results(analysis)
        
    except Exception as e:
        logger.error(f"Error during backfill: {e}")
    
    print("\n✅ Manual P&L backfill completed")


if __name__ == "__main__":
    asyncio.run(main())
