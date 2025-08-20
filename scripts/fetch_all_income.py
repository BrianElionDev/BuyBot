#!/usr/bin/env python3
"""
Fetch all income records for ETH on 2025-08-15 to see what's available.
"""

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from discord_bot.discord_bot import DiscordBot
from datetime import datetime, timezone
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def fetch_all_income():
    bot = DiscordBot()
    
    try:
        # Trade 31072 lifecycle window
        trade_start = datetime(2025, 8, 15, 8, 53, 0, tzinfo=timezone.utc)
        trade_end = datetime(2025, 8, 15, 11, 48, 29, tzinfo=timezone.utc)
        
        start_time = int(trade_start.timestamp() * 1000)
        end_time = int(trade_end.timestamp() * 1000)
        
        print(f"=== FETCHING ETH INCOME FOR TRADE 31072 ===")
        print(f"Trade window: {trade_start} to {trade_end}")
        print(f"Search period: {datetime.fromtimestamp(start_time/1000, tz=timezone.utc)} to {datetime.fromtimestamp(end_time/1000, tz=timezone.utc)}")
        
        # Initialize Binance client if needed
        if not bot.binance_exchange.client:
            await bot.binance_exchange._init_client()
        
        # Fetch income history
        income_records = await bot.binance_exchange.get_income_history(
            symbol="ETHUSDT",
            start_time=start_time,
            end_time=end_time,
            limit=1000
        )
        
        print(f"\nFound {len(income_records)} total income records")
        
        # Filter and display REALIZED_PNL records
        realized_pnl_records = []
        commission_records = []
        funding_fee_records = []
        
        for income in income_records:
            if not isinstance(income, dict):
                continue
            
            income_type = income.get('incomeType') or income.get('type')
            income_value = float(income.get('income', 0.0))
            timestamp = income.get('time', 0)
            time_str = datetime.fromtimestamp(timestamp/1000, tz=timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
            
            if income_type == 'REALIZED_PNL':
                realized_pnl_records.append((time_str, income_value))
            elif income_type == 'COMMISSION':
                commission_records.append((time_str, income_value))
            elif income_type == 'FUNDING_FEE':
                funding_fee_records.append((time_str, income_value))
        
        print(f"\n=== REALIZED_PNL RECORDS ===")
        for time_str, value in realized_pnl_records:
            print(f"  {time_str}: {value}")
        
        print(f"\n=== COMMISSION RECORDS ===")
        for time_str, value in commission_records:
            print(f"  {time_str}: {value}")
        
        print(f"\n=== FUNDING_FEE RECORDS ===")
        for time_str, value in funding_fee_records:
            print(f"  {time_str}: {value}")
        
        # Show results
        print(f"\n=== INCOME RECORDS FOUND ===")
        if income_records:
            for income in income_records:
                if not isinstance(income, dict):
                    continue
                
                income_type = income.get('incomeType') or income.get('type')
                income_value = float(income.get('income', 0.0))
                timestamp = income.get('time', 0)
                time_str = datetime.fromtimestamp(timestamp/1000, tz=timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
                
                print(f"  {time_str} - {income_type}: {income_value}")
        else:
            print("  No income records found in trade window")
        
        # Calculate P&L
        total_realized_pnl = 0.0
        total_commission = 0.0
        total_funding_fee = 0.0
        
        for income in income_records:
            if not isinstance(income, dict):
                continue
            
            income_type = income.get('incomeType') or income.get('type')
            income_value = float(income.get('income', 0.0))
            
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
    asyncio.run(fetch_all_income())
