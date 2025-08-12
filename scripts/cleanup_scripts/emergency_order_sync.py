#!/usr/bin/env python3
"""
EMERGENCY ORDER SYNC SCRIPT
Critical fix for WebSocket failure - immediately syncs all order statuses from Binance.

This script addresses the critical issue where orders were filled on Binance but
the database was never updated due to WebSocket failure.
"""

import os
import sys
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv

# Add the project root to Python path
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(script_dir))
sys.path.insert(0, project_root)

from config import settings
from supabase import create_client, Client
from src.exchange.binance_exchange import BinanceExchange

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def emergency_order_sync():
    """
    Emergency sync to fix WebSocket failure - syncs all order statuses immediately.
    """
    try:
        # Load environment variables
        load_dotenv()

        # Initialize clients
        supabase_url = settings.SUPABASE_URL
        supabase_key = settings.SUPABASE_KEY
        api_key = settings.BINANCE_API_KEY
        api_secret = settings.BINANCE_API_SECRET
        is_testnet = settings.BINANCE_TESTNET

        if not all([supabase_url, supabase_key, api_key, api_secret]):
            logger.error("❌ Missing required credentials")
            return

        supabase: Client = create_client(supabase_url, supabase_key)
        exchange = BinanceExchange(api_key=api_key, api_secret=api_secret, is_testnet=is_testnet)
        await exchange._init_client()

        logger.info("🚨 EMERGENCY ORDER SYNC STARTED")
        logger.info("=" * 60)

        # Step 1: Get all trades that need status updates
        logger.info("📊 Step 1: Fetching trades needing status updates...")

        # Get trades from last 7 days that are not CLOSED
        cutoff = datetime.now(timezone.utc) - timedelta(days=7)
        cutoff_iso = cutoff.isoformat()

        response = supabase.from_("trades").select("*").neq("status", "CLOSED").gte("createdAt", cutoff_iso).execute()
        trades = response.data or []

        logger.info(f"Found {len(trades)} trades needing status updates")

        # Step 2: Get all open orders from Binance
        logger.info("📊 Step 2: Fetching open orders from Binance...")
        binance_orders = await exchange.get_all_open_futures_orders()
        logger.info(f"Found {len(binance_orders)} open orders on Binance")

        # Step 3: Get all positions from Binance
        logger.info("📊 Step 3: Fetching positions from Binance...")
        binance_positions = await exchange.get_futures_position_information()
        active_positions = [p for p in binance_positions if float(p.get('positionAmt', '0')) != 0]
        logger.info(f"Found {len(active_positions)} active positions on Binance")

        # Step 4: Sync each trade
        logger.info("🔄 Step 4: Syncing trade statuses...")
        updates_made = 0

        for trade in trades:
            try:
                trade_id = trade['id']
                discord_id = trade.get('discord_id', 'Unknown')
                coin_symbol = trade.get('coin_symbol', '')
                exchange_order_id = trade.get('exchange_order_id')

                logger.info(f"Processing trade {trade_id} ({discord_id}) - {coin_symbol}")

                # Check if we have an order ID
                if not exchange_order_id:
                    logger.warning(f"Trade {trade_id} has no exchange_order_id, skipping")
                    continue

                # Find matching order in Binance
                matching_order = None
                for order in binance_orders:
                    if str(order.get('orderId')) == str(exchange_order_id):
                        matching_order = order
                        break

                # Find matching position in Binance
                matching_position = None
                if coin_symbol:
                    symbol = f"{coin_symbol}USDT"
                    for position in active_positions:
                        if position.get('symbol') == symbol:
                            matching_position = position
                            break

                # Determine new status
                new_status = None
                new_order_status = None
                update_data = {
                    'updated_at': datetime.now(timezone.utc).isoformat()
                }

                if matching_order:
                    order_status = matching_order.get('status')
                    logger.info(f"Order {exchange_order_id} status: {order_status}")

                    if order_status == 'FILLED':
                        new_order_status = 'FILLED'
                        new_status = 'OPEN'  # Position is open

                        # Update with fill data
                        update_data.update({
                            'order_status': new_order_status,
                            'status': new_status,
                            'binance_entry_price': float(matching_order.get('avgPrice', 0)),
                            'position_size': float(matching_order.get('executedQty', 0)),
                            'sync_order_response': str(matching_order)
                        })

                    elif order_status == 'NEW':
                        new_order_status = 'NEW'
                        new_status = 'PENDING'

                        update_data.update({
                            'order_status': new_order_status,
                            'status': new_status,
                            'sync_order_response': str(matching_order)
                        })

                    elif order_status in ['CANCELED', 'EXPIRED', 'REJECTED']:
                        new_order_status = order_status
                        new_status = 'CANCELED'

                        update_data.update({
                            'order_status': new_order_status,
                            'status': new_status,
                            'sync_order_response': str(matching_order)
                        })

                # Check position data
                if matching_position:
                    position_amt = float(matching_position.get('positionAmt', 0))
                    mark_price = float(matching_position.get('markPrice', 0))
                    unrealized_pnl = float(matching_position.get('unRealizedProfit', 0))

                    logger.info(f"Position data: Size={position_amt}, Price={mark_price}, PnL={unrealized_pnl}")

                    update_data.update({
                        'position_size': abs(position_amt),
                        'binance_exit_price': mark_price,
                        'unrealized_pnl': unrealized_pnl,
                        'last_pnl_sync': datetime.now(timezone.utc).isoformat()
                    })

                    # If we have a position but no matching order, the order was filled
                    if not matching_order and position_amt != 0:
                        update_data.update({
                            'status': 'OPEN',
                            'order_status': 'FILLED'
                        })
                        logger.info(f"Order was filled but not found in open orders - marking as FILLED")

                # Update the database
                if update_data:
                    try:
                        supabase.from_("trades").update(update_data).eq("id", trade_id).execute()
                        updates_made += 1
                        logger.info(f"✅ Updated trade {trade_id} - Status: {new_status}, Order: {new_order_status}")
                    except Exception as e:
                        logger.error(f"❌ Failed to update trade {trade_id}: {e}")

                # Rate limiting
                await asyncio.sleep(0.1)

            except Exception as e:
                logger.error(f"❌ Error processing trade {trade.get('id')}: {e}")
                continue

        # Step 5: Final summary
        logger.info("=" * 60)
        logger.info("🎯 EMERGENCY SYNC SUMMARY")
        logger.info("=" * 60)
        logger.info(f"📊 Trades processed: {len(trades)}")
        logger.info(f"✅ Updates made: {updates_made}")
        logger.info(f"📈 Binance orders: {len(binance_orders)}")
        logger.info(f"💰 Active positions: {len(active_positions)}")
        logger.info("=" * 60)

        # Step 6: Verify critical trades
        logger.info("🔍 Step 6: Verifying critical trades...")
        critical_trades = supabase.from_("trades").select("*").eq("coin_symbol", "ETH").neq("status", "CLOSED").execute()

        if critical_trades.data:
            logger.info(f"Found {len(critical_trades.data)} ETH trades still not CLOSED:")
            for trade in critical_trades.data:
                logger.info(f"  - Trade {trade['id']}: Status={trade.get('status')}, Order={trade.get('order_status')}")

        logger.info("🚨 EMERGENCY SYNC COMPLETED")

    except Exception as e:
        logger.error(f"❌ Fatal error in emergency sync: {e}")
        raise
    finally:
        if 'exchange' in locals():
            await exchange.close_client()

async def main():
    """Main function."""
    print("🚨 EMERGENCY ORDER SYNC - CRITICAL FIX")
    print("=" * 50)
    print("This script will immediately sync all order statuses")
    print("to fix the WebSocket failure issue.")
    print("=" * 50)

    response = input("\n⚠️  This is an emergency fix. Continue? (yes/no): ")
    if response.lower() not in ['yes', 'y']:
        print("❌ Emergency sync cancelled")
        return

    await emergency_order_sync()

if __name__ == "__main__":
    asyncio.run(main())
