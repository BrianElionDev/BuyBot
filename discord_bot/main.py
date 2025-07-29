import uvicorn
from fastapi import FastAPI
import logging
from discord_bot.discord_endpoint import router as discord_router
import asyncio
from discord_bot.utils.trade_retry_utils import (
    initialize_clients,
    process_pending_trades,
    process_cooldown_trades,
    process_empty_binance_response_trades,
    process_margin_insufficient_trades,
    sync_trade_statuses_with_binance,
)
from datetime import datetime
from typing import Optional
from discord_bot.database import (
    create_trades_table,
    insert_trade,
    update_trade_pnl,
    get_trades_needing_pnl_sync,
)

# Configure logging for the Discord service
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - [DiscordSvc] - %(message)s',
    handlers=[
        logging.StreamHandler()
        # You could also add a FileHandler here for persistence
    ]
)

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    """Create and configure the FastAPI application for the Discord service."""
    app = FastAPI(title="Rubicon Trading Bot - Discord Service")

    app.include_router(discord_router, prefix="/api/v1", tags=["discord"])

    @app.get("/")
    async def root():
        return {"message": "Discord Bot Service is running"}

    @app.on_event("startup")
    async def start_background_tasks():
        asyncio.create_task(trade_retry_scheduler())

    return app

async def trade_retry_scheduler():
    bot, supabase = initialize_clients()
    if not bot or not supabase:
        logger.error("Failed to initialize clients for trade retry scheduler.")
        return
    while True:
        logger.info("[Scheduler] Starting scheduled trade retry tasks...")
        await sync_trade_statuses_with_binance(bot, supabase)
        await asyncio.sleep(24 * 60)  # 24 minutes (total 2hr cycle)
        await process_pending_trades(bot, supabase)
        await asyncio.sleep(24 * 60)  # 24 minutes
        await process_empty_binance_response_trades(bot, supabase)
        await asyncio.sleep(24 * 60)  # 24 minutes
        await process_margin_insufficient_trades(bot, supabase)
        await asyncio.sleep(24 * 60)  # 24 minutes
        await sync_pnl_data_with_binance(bot, supabase)
        await asyncio.sleep(24 * 60)  # 24 minutes

async def check_api_permissions(bot):
    """Check if API key has proper permissions for futures trading"""
    try:
        # Try to get account info to test API permissions
        account_info = await bot.binance_exchange.client.futures_account()
        if account_info:
            logger.info("API permissions check passed")
            return True
        else:
            logger.error("API permissions check failed - no account info returned")
            return False
    except Exception as e:
        logger.error(f"API permissions check failed: {e}")
        return False

async def sync_pnl_data_with_binance(bot, supabase):
    """Sync P&L data from Binance Futures API to Supabase using orderId"""
    try:
        logger.info("Starting P&L data sync with Binance...")

        # Check API permissions first
        if not await check_api_permissions(bot):
            logger.error("API permissions check failed, skipping P&L sync")
            return

        # Get trades that need P&L data sync
        trades = get_trades_needing_pnl_sync(supabase)

        # Group trades by symbol to reduce API calls
        trades_by_symbol = {}
        for trade in trades:
            symbol = trade.get('coin_symbol')
            if symbol:
                if symbol not in trades_by_symbol:
                    trades_by_symbol[symbol] = []
                trades_by_symbol[symbol].append(trade)

        logger.info(f"Processing {len(trades)} trades across {len(trades_by_symbol)} symbols")

        for symbol, symbol_trades in trades_by_symbol.items():
            try:
                trading_pair = f"{symbol}USDT"

                # Check if symbol is supported before making API calls
                is_supported = await bot.binance_exchange.is_futures_symbol_supported(trading_pair)
                if not is_supported:
                    logger.warning(f"Symbol {trading_pair} not supported, skipping P&L sync for {len(symbol_trades)} trades")
                    continue

                # Get all user trades for this symbol (limit to last 1000 to avoid rate limits)
                user_trades = await bot.binance_exchange.get_user_trades(symbol=trading_pair, limit=1000)

                if not user_trades:
                    logger.info(f"No user trades found for {trading_pair}")
                    continue

                logger.info(f"Found {len(user_trades)} user trades for {trading_pair}")

                # Create lookup by orderId for fast matching
                trades_by_order_id = {trade.get('orderId'): trade for trade in user_trades if trade.get('orderId')}

                # Process each trade for this symbol
                for trade in symbol_trades:
                    try:
                        # Extract orderId from binance_response
                        binance_response = trade.get('binance_response', '')
                        order_id = None

                        # Try to extract orderId from binance_response
                        if isinstance(binance_response, dict) and 'orderId' in binance_response:
                            order_id = binance_response['orderId']
                        elif isinstance(binance_response, str):
                            # Try to parse JSON response
                            try:
                                import json
                                response_data = json.loads(binance_response)
                                order_id = response_data.get('orderId')
                            except:
                                pass

                        if not order_id:
                            logger.warning(f"Trade {trade['id']} missing orderId in binance_response, skipping")
                            continue

                        # Find matching trade by orderId
                        matching_trade = trades_by_order_id.get(order_id)

                        if matching_trade:
                            # Extract P&L data from the matching trade
                            entry_price = float(matching_trade.get('price', 0))
                            realized_pnl = float(matching_trade.get('realizedPnl', 0))

                            # Get current position for unrealized P&L
                            positions = await bot.binance_exchange.get_position_risk(symbol=trading_pair)
                            unrealized_pnl = 0.0

                            for position in positions:
                                if position.get('symbol') == trading_pair:
                                    unrealized_pnl = float(position.get('unRealizedProfit', 0))
                                    break

                            # Update trade record using database helper
                            pnl_data = {
                                'entry_price': entry_price,
                                'exit_price': entry_price,  # For single trades, entry = exit
                                'realized_pnl': realized_pnl,
                                'unrealized_pnl': unrealized_pnl,
                                'last_pnl_sync': datetime.utcnow().isoformat()
                            }

                            if update_trade_pnl(supabase, trade['id'], pnl_data):
                                logger.info(f"Updated P&L data for trade {trade['id']} (orderId: {order_id}): Entry={entry_price}, Realized={realized_pnl}, Unrealized={unrealized_pnl}")
                            else:
                                logger.error(f"Failed to update P&L data for trade {trade['id']}")
                        else:
                            logger.warning(f"No matching trade found for orderId {order_id} in {trading_pair}")

                    except Exception as e:
                        logger.error(f"Failed to sync P&L for trade {trade.get('id')}: {e}")
                        continue

            except Exception as e:
                logger.error(f"Failed to sync P&L for symbol {symbol}: {e}")
                continue

        logger.info("P&L data sync completed")

    except Exception as e:
        logger.error(f"Error in P&L data sync: {e}")

app = create_app()

if __name__ == "__main__":
    logger.info("🚀 Starting Discord Bot Service...")
    # Run on a different port to avoid conflict with the Telegram service
    uvicorn.run(app, host="127.0.0.1", port=8001)