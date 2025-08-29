#!/usr/bin/env python3
"""
Test the updated P&L calculation with both pnl_usd and net_pnl fields.
"""

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from discord_bot.discord_bot import DiscordBot
from discord_bot.utils.trade_retry_utils import get_order_lifecycle, get_income_for_trade_period
from datetime import datetime, timezone
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def test_updated_pnl():
    bot = DiscordBot()
    
    try:
        # Fetch trade 31072
        response = bot.supabase.from_("trades").select("*").eq("id", 31072).execute()
        trade = response.data[0] if response.data else None
        
        if not trade:
            print("❌ Trade 31072 not found")
            return
        
        print(f"=== TRADE 31072 CURRENT DATA ===")
        print(f"pnl_usd: {trade.get('pnl_usd')}")
        print(f"net_pnl: {trade.get('net_pnl')}")
        print(f"commission: {trade.get('commission')}")
        print(f"funding_fee: {trade.get('funding_fee')}")
        print(f"created_at: {trade.get('created_at')}")
        print(f"closed_at: {trade.get('closed_at')}")
        
        # Get order lifecycle
        start_time, end_time, duration = get_order_lifecycle(trade)
        
        if not start_time:
            print("❌ No valid timestamps")
            return
        
        print(f"\n=== ORDER LIFECYCLE ===")
        start_dt = datetime.fromtimestamp(start_time / 1000, tz=timezone.utc)
        end_dt = datetime.fromtimestamp(end_time / 1000, tz=timezone.utc)
        print(f"Start: {start_dt}")
        print(f"End: {end_dt}")
        print(f"Duration: {duration / (1000 * 60 * 60):.1f} hours")
        
        # Get income records
        symbol = trade.get('coin_symbol', 'ETH')
        income_records = await get_income_for_trade_period(bot, symbol, start_time, end_time)
        
        print(f"\n=== INCOME RECORDS ({len(income_records)}) ===")
        
        total_realized_pnl = 0.0
        total_commission = 0.0
        total_funding_fee = 0.0
        
        for income in income_records:
            if not isinstance(income, dict):
                continue
            
            income_type = income.get('incomeType') or income.get('type')
            income_value = float(income.get('income', 0.0))
            income_time = income.get('time', 0)
            
            if income_time:
                time_str = datetime.fromtimestamp(int(income_time) / 1000, tz=timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
            else:
                time_str = "Unknown"
            
            print(f"  {time_str} - {income_type}: {income_value:.6f}")
            
            if income_type == 'REALIZED_PNL':
                total_realized_pnl += income_value
            elif income_type == 'COMMISSION':
                total_commission += income_value
            elif income_type == 'FUNDING_FEE':
                total_funding_fee += income_value
        
        # Calculate NET P&L
        net_pnl = total_realized_pnl + total_commission + total_funding_fee
        
        print(f"\n=== CALCULATED P&L ===")
        print(f"REALIZED_PNL: {total_realized_pnl:.6f}")
        print(f"COMMISSION: {total_commission:.6f}")
        print(f"FUNDING_FEE: {total_funding_fee:.6f}")
        print(f"NET P&L: {net_pnl:.6f}")
        
        print(f"\n=== DATABASE FIELDS ===")
        print(f"pnl_usd should be: {total_realized_pnl:.6f} (REALIZED_PNL only)")
        print(f"net_pnl should be: {net_pnl:.6f} (including fees)")
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    import asyncio
    asyncio.run(test_updated_pnl())
