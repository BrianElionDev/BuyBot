#!/usr/bin/env python3
"""
Debug specific trade 31072 to understand P&L calculation.
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

async def debug_trade_31072():
    bot = DiscordBot()
    
    try:
        # Fetch trade 31087
        response = bot.supabase.from_("trades").select("*").eq("id", 31087).execute()
        trade = response.data[0] if response.data else None
        
        if not trade:
            print("❌ Trade 31087 not found")
            return
        
        print(f"=== DEBUGGING TRADE 31087 ===")
        print(f"Symbol: {trade.get('coin_symbol')}")
        
        # Get order lifecycle
        start_time, end_time, duration = get_order_lifecycle(trade)
        print(f"Order lifecycle:")
        print(f"  Start: {start_time} ({datetime.fromtimestamp(start_time/1000, tz=timezone.utc)})")
        print(f"  End: {end_time} ({datetime.fromtimestamp(end_time/1000, tz=timezone.utc)})")
        print(f"  Duration: {duration} ms ({duration/1000/60:.1f} minutes)")
        
        print(f"\n=== CURRENT DATABASE VALUES ===")
        print(f"pnl_usd: {trade.get('pnl_usd')}")
        print(f"net_pnl: {trade.get('net_pnl')}")
        print(f"Previous value was: 1.360480")
        
        # Fetch income records with extended window to catch final P&L
        symbol = trade.get('coin_symbol', 'ETH')
        
        # Extend end time by 1 minute to catch final P&L at close time
        # Don't extend start time - we want to start exactly when trade was created
        extended_end_time = end_time + (60 * 1000)  # Add 1 minute
        
        print(f"Original start time: {start_time} ({datetime.fromtimestamp(start_time/1000, tz=timezone.utc)})")
        print(f"Original end time: {end_time} ({datetime.fromtimestamp(end_time/1000, tz=timezone.utc)})")
        print(f"Extended end time: {extended_end_time} ({datetime.fromtimestamp(extended_end_time/1000, tz=timezone.utc)})")
        
        income_records = await get_income_for_trade_period(bot, symbol, start_time, extended_end_time)
        
        print(f"\n=== INCOME RECORDS ===")
        print(f"Found {len(income_records)} income records")
        print(f"Income records: {income_records}")
        
        # Calculate P&L
        total_realized_pnl = 0.0
        total_commission = 0.0
        total_funding_fee = 0.0
        
        for income in income_records:
            if not isinstance(income, dict):
                continue
            
            income_type = income.get('incomeType') or income.get('type')
            income_value = float(income.get('income', 0.0))
            timestamp = income.get('time', 0)
            time_str = datetime.fromtimestamp(timestamp/1000, tz=timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
            
            print(f"  {time_str} - {income_type}: {income_value}")
            
            if income_type == 'REALIZED_PNL':
                total_realized_pnl += income_value
            elif income_type == 'COMMISSION':
                total_commission += income_value
            elif income_type == 'FUNDING_FEE':
                total_funding_fee += income_value
        
        print(f"\n=== P&L CALCULATION ===")
        print(f"Total REALIZED_PNL: {total_realized_pnl}")
        print(f"Total COMMISSION: {total_commission}")
        print(f"Total FUNDING_FEE: {total_funding_fee}")
        print(f"NET P&L: {total_realized_pnl + total_commission + total_funding_fee}")
        
    except Exception as e:
        print(f"Error: {e}")
    finally:
        await bot.close()

if __name__ == "__main__":
    import asyncio
    asyncio.run(debug_trade_31072())
