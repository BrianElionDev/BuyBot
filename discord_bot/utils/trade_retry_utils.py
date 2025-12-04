"""
Trade Retry Utilities for Discord Bot

This module processes trades and alerts from configured traders.
All database queries are filtered based on trader configuration.
"""

import asyncio
import logging
import os
import json
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, List, Tuple
from dotenv import load_dotenv
from supabase import create_client, Client
from config import settings
from discord_bot.discord_bot import DiscordBot
from src.services.trader_config_service import trader_config_service
from src.exchange.kucoin.kucoin_symbol_converter import KucoinSymbolConverter

# --- Setup ---
load_dotenv()
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Initialize symbol converter for KuCoin
_symbol_converter = KucoinSymbolConverter()

def get_trader_filter(trader: Optional[str] = None) -> Dict[str, str]:
    """Get the trader filter for database queries."""
    if trader:
        return {"trader": trader}
    return {}

def get_24hr_cutoff_iso():
  now = datetime.now(timezone.utc)
  cutoff = now - timedelta(hours=24)
  return cutoff.isoformat()

# --- Helper to initialize clients ---
def initialize_clients() -> tuple[Optional[DiscordBot], Optional[Client]]:
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    if not url or not key:
        logging.error("Supabase URL or key not found in .env file.")
        return None, None
    supabase: Client = create_client(url, key)
    bot = DiscordBot()
    return bot, supabase

def safe_parse_exchange_response(exchange_response: str) -> dict:
    """Safely parse exchange_response field (JSON or plain text)."""
    if isinstance(exchange_response, dict):
        return exchange_response
    elif isinstance(exchange_response, str):
        if not exchange_response or exchange_response.strip() == '':
            return {}
        try:
            return json.loads(exchange_response.strip())
        except (json.JSONDecodeError, ValueError):
            return {"error": exchange_response.strip()}
    else:
        return {}

# Backward-compatible alias
def safe_parse_binance_response(binance_response: str) -> dict:
    return safe_parse_exchange_response(binance_response)


def extract_order_info_from_exchange_response(exchange_response: str) -> tuple[Optional[str], Optional[str]]:
    """Extract orderId and symbol from exchange_response (generic)."""
    try:
        data = safe_parse_exchange_response(exchange_response)
        order_id = str(data.get('orderId', ''))
        symbol = data.get('symbol', '')
        if order_id and symbol:
            return order_id, symbol
        return None, None
    except Exception as e:
        logging.error(f"Error extracting generic order info: {e}")
        return None, None

async def process_pending_trades(bot: DiscordBot, supabase: Client):
    """
    Find all trades with status 'pending' and process them (and their alerts).
    """
    logging.info("--- Processing pending trades ---")
    try:
        cutoff = get_24hr_cutoff_iso()
        supported_traders = await trader_config_service.get_supported_traders()
        all_trades = []

        for trader in supported_traders:
            response = supabase.from_("trades").select("*").eq("status", "pending").eq("trader", trader).gte("timestamp", cutoff).execute()
            trader_trades = response.data or []
            all_trades.extend(trader_trades)
            logging.info(f"Found {len(trader_trades)} pending trades from {trader}.")

        trades = all_trades
        logging.info(f"Total pending trades from all supported traders: {len(trades)}")
    except Exception as e:
        logging.error(f"Error fetching pending trades: {e}")
        return
    for trade in trades:
        discord_id = trade.get("discord_id")
        if not discord_id:
            continue
        await process_single_trade(bot, supabase, discord_id)
        await asyncio.sleep(2)

async def process_cooldown_trades(bot: DiscordBot, supabase: Client):
    """
    Find all trades with binance_response matching 'Trade cooldown active for ...' and retry them.
    """
    logging.info("--- Processing cooldown trades ---")
    cooldown_pattern = "Trade cooldown active for%"
    try:
        cutoff = get_24hr_cutoff_iso()
        supported_traders = await trader_config_service.get_supported_traders()
        all_trades = []

        for trader in supported_traders:
            response = supabase.from_("trades").select("*").like("binance_response", cooldown_pattern).eq("trader", trader).gte("timestamp", cutoff).execute()
            trader_trades = response.data or []
            all_trades.extend(trader_trades)
            logging.info(f"Found {len(trader_trades)} cooldown trades from {trader}.")

        trades = all_trades
        logging.info(f"Total cooldown trades from all supported traders: {len(trades)}")
    except Exception as e:
        logging.error(f"Error fetching cooldown trades: {e}")
        return
    for trade in trades:
        discord_id = trade.get("discord_id")
        if not discord_id:
            continue
        await process_single_trade(bot, supabase, discord_id)
        await asyncio.sleep(2)

async def process_empty_binance_response_trades(bot: DiscordBot, supabase: Client):
    """
    Find all trades with empty binance_response from all supported traders and retry them.
    """
    logging.info("--- Processing trades with empty binance_response from all supported traders ---")
    try:
        cutoff = get_24hr_cutoff_iso()
        # Use DB-backed supported traders list (fallback handled in service)
        supported_traders = await trader_config_service.get_supported_traders()
        all_trades = []

        for trader in supported_traders:
            response = supabase.from_("trades").select("*").filter("binance_response", "eq", "").eq("trader", trader).gte("timestamp", cutoff).execute()
            trader_trades = response.data or []
            all_trades.extend(trader_trades)
            logging.info(f"Found {len(trader_trades)} trades with empty binance_response from {trader}.")

        trades = all_trades
        logging.info(f"Total trades with empty binance_response from all supported traders: {len(trades)}")
    except Exception as e:
        logging.error(f"Error fetching trades with empty binance_response: {e}")
        return
    for trade in trades:
        discord_id = trade.get("discord_id")
        if not discord_id:
            continue
        await process_single_trade(bot, supabase, discord_id)
        await asyncio.sleep(2)

async def process_margin_insufficient_trades(bot: DiscordBot, supabase: Client):
    """
    Find all trades with binance_response containing APIError(code=-2019) (margin insufficient) from @Johnny in the last 24 hours and retry them.
    """
    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=24)
    cutoff_iso = cutoff.isoformat()
    logging.info("--- Processing margin insufficient trades from all supported traders ---")
    pattern = '%APIError(code=-2019)%'
    try:
        supported_traders = await trader_config_service.get_supported_traders()
        all_trades = []

        for trader in supported_traders:
            response = supabase.from_("trades").select("*").like("binance_response", pattern).eq("trader", trader).gte("timestamp", cutoff_iso).execute()
            trader_trades = response.data or []
            all_trades.extend(trader_trades)
            logging.info(f"Found {len(trader_trades)} margin insufficient trades from {trader}.")

        trades = all_trades
        logging.info(f"Total margin insufficient trades from all supported traders: {len(trades)}")
    except Exception as e:
        logging.error(f"Error fetching margin insufficient trades: {e}")
        return
    for trade in trades:
        discord_id = trade.get("discord_id")
        if not discord_id:
            continue
        await process_single_trade(bot, supabase, discord_id)
        await asyncio.sleep(2)

async def process_single_trade(bot: DiscordBot, supabase: Client, discord_id: str):
    """
    Processes a single trade by discord_id, including its alerts.
    """
    logging.info(f"--- Processing Discord ID: {discord_id} ---")
    try:
        response = supabase.from_("trades").select("*").eq("discord_id", discord_id).single().execute()
        trade = response.data
        if not trade:
            logging.error(f"No trade found with discord_id: {discord_id}")
            return
    except Exception as e:
        logging.error(f"Failed to fetch trade from Supabase: {e}")
        return
    # Re-process the initial trade signal
    initial_signal_data = {
        "timestamp": trade.get("timestamp"),
        "content": trade.get("content"),
        "discord_id": trade.get("discord_id"),
        "trader": trade.get("trader"),
        "structured": trade.get("structured"),
    }
    if not all(initial_signal_data.values()):
        logging.error(f"Skipping initial signal for trade ID {trade.get('id')} due to missing data.")
    else:
        try:
            from discord_bot.models import InitialDiscordSignal
            # Remove the price_threshold_override as it's not part of the model
            signal_data = {k: v for k, v in initial_signal_data.items() if k != 'price_threshold_override'}
            # Type assertion since we already checked all values are not None
            signal_model = InitialDiscordSignal(**signal_data)  # type: ignore
            result = await bot.process_initial_signal(signal_model)
            if result.get("status") == "success":
                logging.info(f"Successfully re-processed initial signal.")
            else:
                logging.error(f"Failed to re-process initial signal. Reason: {result.get('message')}")
        except Exception as e:
            logging.error(f"Error while re-processing initial signal: {e}", exc_info=True)
    # Process any corresponding alerts
    try:
        alert_response = supabase.from_("alerts").select("*").eq("trade", discord_id).execute()
        alerts = alert_response.data or []
        if not alerts:
            logging.info("No corresponding alerts found for this trade.")
        else:
            logging.info(f"Found {len(alerts)} alert(s) to process.")
            for alert in sorted(alerts, key=lambda x: x.get('timestamp') or ''):
                alert_id = alert.get('id')
                alert_signal_data = {
                    "timestamp": alert.get("timestamp"),
                    "content": alert.get("content"),
                    "discord_id": alert.get("discord_id"),
                    "trader": alert.get("trader"),
                    "trade": alert.get("trade"),
                }
                if not all(alert_signal_data.values()):
                    logging.warning(f"Skipping alert ID {alert_id} due to missing data.")
                    continue
                try:
                    result = await bot.process_update_signal(alert_signal_data)
                    if result.get("status") == "success":
                        logging.info(f"Successfully re-processed alert ID {alert_id}.")
                    else:
                        logging.error(f"Failed to re-process alert ID {alert_id}. Reason: {result.get('message')}")
                except Exception as e:
                    logging.error(f"Error while processing alert ID {alert_id}: {e}", exc_info=True)
    except Exception as e:
        logging.error(f"Failed to fetch or process alerts: {e}")

async def sync_trade_statuses_with_binance(bot: DiscordBot, supabase: Client):
    """
    Enhanced sync method that treats Binance as the source of truth.
    This replaces the old sync method with comprehensive database synchronization.
    """
    from datetime import datetime, timedelta, timezone
    import json

    logging.info("🔄 Enhanced Binance to Database Sync")
    logging.info("=" * 50)

    try:
        # Get data from both sources
        logging.info("📊 Fetching data...")

        # Get Binance data
        binance_orders = await bot.binance_exchange.get_all_open_futures_orders()
        binance_positions = await bot.binance_exchange.get_futures_position_information()

        # Get database trades from last 7 days (optimized for performance)
        cutoff = datetime.now(timezone.utc) - timedelta(days=7)
        cutoff_iso = cutoff.isoformat()
        response = supabase.from_("trades").select("*").gte("created_at", cutoff_iso).execute()
        db_trades = response.data or []

        logging.info(f"Found {len(binance_orders)} open orders on Binance")
        logging.info(f"Found {len(binance_positions)} active positions on Binance")
        logging.info(f"Found {len(db_trades)} trades in database (all statuses)")

        # Validate database accuracy
        logging.info("🔍 Validating database accuracy...")
        issues = await validate_database_accuracy_enhanced(bot, binance_orders, binance_positions, db_trades)

        # Sync orders
        logging.info("🔄 Syncing orders...")
        await sync_orders_to_database_enhanced(bot, supabase, binance_orders, db_trades)

        # Sync positions
        logging.info("🔄 Syncing positions...")
        await sync_positions_to_database_enhanced(bot, supabase, binance_positions, db_trades)

        # Cleanup closed positions
        logging.info("🧹 Cleaning up closed positions...")
        await cleanup_closed_positions_enhanced(bot, supabase, binance_positions, db_trades)

        # Sync closed trades from history
        logging.info("📜 Syncing closed trades from history...")
        await sync_closed_trades_from_history_enhanced(bot, supabase, db_trades)

        # Backfill PnL and exit price data from Binance history
        logging.info("📊 Backfilling PnL and exit price data from Binance history...")
        await backfill_trades_from_binance_history(bot, supabase, days=30)

        # Final validation
        logging.info("🔍 Final validation...")
        final_issues = await validate_database_accuracy_enhanced(bot, binance_orders, binance_positions, db_trades)

        logging.info("✅ Enhanced sync completed!")
        logging.info(f"Binance Orders: {len(binance_orders)}")
        logging.info(f"Binance Positions: {len(binance_positions)}")
        logging.info(f"Database Trades: {len(db_trades)}")
        logging.info(f"Initial Issues: {len(issues)}")
        logging.info(f"Final Issues: {len(final_issues)}")

    except Exception as e:
        logging.error(f"Error in enhanced sync: {e}", exc_info=True)


async def sync_trade_statuses_with_kucoin(bot: DiscordBot, supabase: Client):
    """
    Enhanced sync method for KuCoin orders to get actual execution details.
    """
    from datetime import datetime, timedelta, timezone
    import json

    logging.info("🔄 Enhanced KuCoin to Database Sync")
    logging.info("=" * 50)

    try:
        # Get data from both sources
        logging.info("📊 Fetching KuCoin data...")

        # Initialize KuCoin exchange if not available
        if not hasattr(bot, 'kucoin_exchange') or bot.kucoin_exchange is None:
            from src.exchange.kucoin.kucoin_exchange import KucoinExchange
            bot.kucoin_exchange = KucoinExchange(api_key=settings.KUCOIN_API_KEY or "", api_secret=settings.KUCOIN_API_SECRET or "", api_passphrase=settings.KUCOIN_API_PASSPHRASE or "", is_testnet=False)
            await bot.kucoin_exchange.initialize()

        # Get KuCoin data
        kucoin_orders = await bot.kucoin_exchange.get_all_open_futures_orders()
        kucoin_positions = await bot.kucoin_exchange.get_futures_position_information()

        # Get database trades from last 7 days (optimized for performance)
        cutoff = datetime.now(timezone.utc) - timedelta(days=7)
        cutoff_iso = cutoff.isoformat()
        response = supabase.from_("trades").select("*").gte("created_at", cutoff_iso).eq("exchange", "kucoin").execute()
        db_trades = response.data or []

        logging.info(f"Found {len(kucoin_orders)} open orders on KuCoin")
        logging.info(f"Found {len(kucoin_positions)} active positions on KuCoin")
        logging.info(f"Found {len(db_trades)} KuCoin trades in database (all statuses)")

        # Sync orders to get actual execution details
        logging.info("🔄 Syncing KuCoin orders...")
        await sync_kucoin_orders_to_database_enhanced(bot, supabase, kucoin_orders, db_trades)

        # Sync positions
        logging.info("🔄 Syncing KuCoin positions...")
        await sync_kucoin_positions_to_database_enhanced(bot, supabase, kucoin_positions, db_trades)

        logging.info("✅ Enhanced KuCoin sync completed!")
        logging.info(f"KuCoin Orders: {len(kucoin_orders)}")
        logging.info(f"KuCoin Positions: {len(kucoin_positions)}")
        logging.info(f"Database Trades: {len(db_trades)}")

    except Exception as e:
        logging.error(f"Error in enhanced KuCoin sync: {e}", exc_info=True)


def extract_symbol_from_trade(trade: dict) -> Optional[str]:
    """
    Extract symbol from trade with fallback logic for missing coin_symbol.
    """
    # First try coin_symbol field
    symbol = trade.get('coin_symbol')

    # If coin_symbol is None, try to extract from parsed_signal
    if not symbol and trade.get('parsed_signal'):
        try:
            parsed_signal = trade['parsed_signal']
            if isinstance(parsed_signal, str):
                parsed_signal = json.loads(parsed_signal)
            symbol = parsed_signal.get('coin_symbol')
        except (json.JSONDecodeError, TypeError):
            pass

    # If still no symbol, try to extract from binance_response
    if not symbol and (trade.get('exchange_response') or trade.get('binance_response')):
        try:
            raw = trade.get('exchange_response') or trade.get('binance_response') or ""
            if not isinstance(raw, str):
                try:
                    raw = json.dumps(raw)
                except Exception:
                    raw = str(raw)
            order_details = extract_order_details_from_response(raw)
            symbol = order_details.get('symbol')
            if symbol and symbol.endswith('USDT'):
                symbol = symbol[:-4]  # Remove USDT suffix
        except Exception:
            pass

    return symbol


def extract_order_details_from_response(exchange_response: str) -> dict:
    """
    Extract order details from exchange_response with robust error handling.
    """
    try:
        response_data = safe_parse_exchange_response(exchange_response)

        if not isinstance(response_data, dict):
            return {}

        # Safely convert numeric fields
        return {
            'orderId': response_data.get('orderId'),
            'symbol': response_data.get('symbol'),
            'status': response_data.get('status'),
            'clientOrderId': response_data.get('clientOrderId'),
            'price': float(response_data.get('price', 0)) if response_data.get('price') else 0.0,
            'avgPrice': float(response_data.get('avgPrice', 0)) if response_data.get('avgPrice') else 0.0,
            'origQty': float(response_data.get('origQty', 0)) if response_data.get('origQty') else 0.0,
            'executedQty': float(response_data.get('executedQty', 0)) if response_data.get('executedQty') else 0.0,
            'cumQty': float(response_data.get('cumQty', 0)) if response_data.get('cumQty') else 0.0,
            'cumQuote': float(response_data.get('cumQuote', 0)) if response_data.get('cumQuote') else 0.0,
            'timeInForce': response_data.get('timeInForce'),
            'type': response_data.get('type'),
            'side': response_data.get('side'),
            'updateTime': int(response_data.get('updateTime', 0)) if response_data.get('updateTime') else 0,
            'rp': float(response_data.get('rp', 0)) if response_data.get('rp') else 0.0
        }
    except Exception as e:
        logging.warning(f"Error extracting order details: {e}")
        return {}


async def validate_database_accuracy_enhanced(bot: DiscordBot, binance_orders: list, binance_positions: list, db_trades: list) -> list:
    """Validate database accuracy against Binance data"""
    logging.info("Starting database accuracy validation...")

    issues_found = []

    # Check for orders in database but not on Binance
    db_order_ids = set()
    for trade in db_trades:
        ex_resp = trade.get('exchange_response') or trade.get('binance_response', '')
        if ex_resp:
            order_details = extract_order_details_from_response(ex_resp)
            order_id = order_details.get('orderId')
            if order_id:
                db_order_ids.add(str(order_id))

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
            symbol = extract_symbol_from_trade(trade)
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
        logging.warning("Database accuracy issues found:")
        for issue in issues_found:
            logging.warning(f"  - {issue}")
    else:
        logging.info("Database accuracy validation passed - no issues found")

    return issues_found


async def sync_orders_to_database_enhanced(bot: DiscordBot, supabase: Client, binance_orders: list, db_trades: list):
    """Sync Binance orders to database"""
    logging.info("Starting order sync...")

    # Create lookup for database trades by orderId
    db_trades_by_order_id = {}
    for trade in db_trades:
        # Try sync_order_response first, then fallback to exchange_response
        sync_order_response = trade.get('sync_order_response', '')
        ex_resp = trade.get('exchange_response') or trade.get('binance_response', '')

        if sync_order_response:
            order_details = extract_order_details_from_response(sync_order_response)
            order_id = order_details.get('orderId')
            if order_id:
                db_trades_by_order_id[str(order_id)] = trade
        elif ex_resp:
            order_details = extract_order_details_from_response(ex_resp)
            order_id = order_details.get('orderId')
            if order_id:
                db_trades_by_order_id[str(order_id)] = trade

    updates_made = 0
    current_time = datetime.now(timezone.utc).isoformat()

    for order in binance_orders:
        order_id = str(order.get('orderId', ''))
        if not order_id:
            continue

        if order_id in db_trades_by_order_id:
            db_trade = db_trades_by_order_id[order_id]
            try:
                # Update order information with sync_order_response
                update_data = {
                    'order_status': order.get('status'),
                    'executed_qty': float(order.get('executedQty', 0)),
                    'avg_price': float(order.get('avgPrice', 0)),
                    'last_order_sync': current_time,
                    'updated_at': current_time,
                    'sync_order_response': json.dumps(order)
                }

                supabase.table("trades").update(update_data).eq("id", db_trade['id']).execute()
                updates_made += 1
                logging.info(f"Updated order for trade {db_trade['id']} ({order.get('symbol')})")

            except Exception as e:
                logging.error(f"Error updating order for trade {db_trade['id']}: {e}")
        else:
            logging.warning(f"Order {order_id} ({order.get('symbol')}) not found in database")

    logging.info(f"Order sync completed: {updates_made} updates made")


async def sync_kucoin_orders_to_database_enhanced(bot: DiscordBot, supabase: Client, kucoin_orders: list, db_trades: list):
    """Sync KuCoin orders to database"""
    logging.info("Starting KuCoin order sync...")

    # Import centralized status manager
    from src.core.status_manager import StatusManager

    # Create lookup for database trades by orderId
    db_trades_by_order_id = {}
    db_trades_by_symbol_time = {}

    for trade in db_trades:
        # Try sync_order_response first, then fallback to exchange_response
        sync_order_response = trade.get('sync_order_response', '')
        ex_resp = trade.get('exchange_response') or trade.get('kucoin_response', '')

        order_id = None
        if sync_order_response:
            order_details = extract_order_details_from_response(sync_order_response)
            order_id = order_details.get('orderId')
        elif ex_resp:
            order_details = extract_order_details_from_response(ex_resp)
            order_id = order_details.get('orderId')

        if order_id:
            db_trades_by_order_id[str(order_id)] = trade
        else:
            # For trades missing order_id, index by symbol and creation time (within 5 minutes)
            coin_symbol = trade.get('coin_symbol', '')
            created_at = trade.get('created_at', '')
            if coin_symbol and created_at:
                try:
                    # datetime and timezone are imported at top of file
                    created_dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                    key = f"{coin_symbol}_{created_dt.timestamp()}"
                    db_trades_by_symbol_time[key] = trade
                except Exception:
                    pass

    updates_made = 0
    # datetime and timezone are imported at top of file
    current_time = datetime.now(timezone.utc).isoformat()

    for order in kucoin_orders:
        order_id = str(order.get('orderId', ''))
        if not order_id:
            continue

        if order_id in db_trades_by_order_id:
            db_trade = db_trades_by_order_id[order_id]
            try:
                # Extract KuCoin-specific fields and map to exchange-independent fields
                filled_size = float(order.get('filledSize', 0))
                filled_value = float(order.get('filledValue', 0))
                orig_qty = float(order.get('origQty', 0))

                # Calculate average price from filled value and size
                avg_price = 0.0
                if filled_size > 0 and filled_value > 0:
                    avg_price = filled_value / filled_size
                elif orig_qty > 0 and order.get('price'):
                    avg_price = float(order.get('price', 0))

                # Get KuCoin order status and map it using centralized StatusManager
                kucoin_status = order.get('status', 'NEW')
                mapped_order_status, mapped_position_status = StatusManager.map_exchange_to_internal(
                    kucoin_status, filled_size
                )

                # Calculate position size - prioritize origQty/executedQty (asset quantity) over filledSize (contract size)
                position_size = None

                # Check for executedQty first (already asset quantity from get_order_status)
                executed_qty = order.get('executedQty')
                if executed_qty and float(executed_qty) > 0:
                    position_size = float(executed_qty)
                    logging.info(f"Using executedQty as position_size (asset quantity): {position_size}")
                elif orig_qty > 0:
                    # For NEW orders, use origQty (this represents actual asset quantity)
                    position_size = orig_qty
                    logging.info(f"Using origQty as position_size (asset quantity): {position_size}")
                elif filled_size > 0:
                    # For filled orders, convert contract size to asset quantity
                    try:
                        contract_multiplier = float(order.get('contract_multiplier', 1) or 1)
                    except (TypeError, ValueError):
                        contract_multiplier = 1.0
                    position_size = float(filled_size) * contract_multiplier
                    logging.info(f"Converted KuCoin contracts to assets: {filled_size} contracts × {contract_multiplier} = {position_size} assets")

                # Update order information with proper status mapping
                update_data = {
                    'order_status': mapped_order_status,
                    'status': mapped_position_status,  # Use mapped position status
                    'last_order_sync': current_time,
                    'updated_at': current_time,
                    'sync_order_response': json.dumps(order)
                }

                # If we have clear execution evidence, reconcile misleading NEW -> FILLED
                try:
                    if (mapped_position_status in ['CLOSED', 'OPEN', 'ACTIVE']) and (filled_size > 0 or (avg_price and avg_price > 0)):
                        # Treat as FILLED order lifecycle
                        update_data['order_status'] = 'FILLED'
                except Exception:
                    pass

                # Only update position_size and entry_price if we have valid values
                if position_size and position_size > 0:
                    update_data['position_size'] = f"{position_size:.8f}"
                if avg_price and avg_price > 0:
                    update_data['entry_price'] = f"{avg_price:.8f}"
                    update_data.setdefault('price_source', 'kucoin_order_status')

                # Update exchange-specific fields for KuCoin
                if avg_price and avg_price > 0:
                    update_data['entry_price'] = f"{avg_price:.8f}"
                    update_data.setdefault('price_source', 'kucoin_order_status')
                if kucoin_status in ['FILLED', 'DONE']:
                    update_data['exit_price'] = f"{avg_price:.8f}"
                    update_data['price_source'] = 'kucoin_order_status'

                # For closed trades missing exit_price, try to get from trade history
                if (db_trade.get('status') == 'CLOSED' and
                    not db_trade.get('exit_price') and
                    not db_trade.get('exit_price')):
                    try:
                        symbol = extract_symbol_from_trade(db_trade)
                        if symbol and bot.kucoin_exchange:
                            kucoin_symbol = _convert_to_kucoin_futures_symbol(symbol)
                            trade_history = await bot.kucoin_exchange.get_user_trades(symbol=kucoin_symbol)
                            matching_trades = [t for t in trade_history if str(t.get('orderId', '')) == order_id]
                            if matching_trades:
                                last_trade = matching_trades[-1]
                                exit_price = float(last_trade.get('price', 0))
                                if exit_price > 0:
                                    update_data['exit_price'] = f"{exit_price:.8f}"
                                    update_data['price_source'] = 'kucoin_user_trades'
                                    update_data['exit_price'] = f"{exit_price:.8f}"

                                    # Do NOT compute KuCoin PnL here to avoid duplication/overlap; use dedicated reconciliation
                                    pass
                    except Exception as e:
                        logging.warning(f"Could not get trade history for KuCoin trade {db_trade['id']}: {e}")

                # Ensure exchange_response is stored for future syncs
                if not update_data.get('exchange_response'):
                    update_data['exchange_response'] = json.dumps(order)

                supabase.table("trades").update(update_data).eq("id", db_trade['id']).execute()
                updates_made += 1
                logging.info(f"Updated KuCoin order for trade {db_trade['id']} ({order.get('symbol')}) - Status: {kucoin_status} -> {mapped_order_status}/{mapped_position_status}, Size: {filled_size}, Price: {avg_price}")

            except Exception as e:
                logging.error(f"Error updating KuCoin order for trade {db_trade['id']}: {e}")
        else:
            # Try to match by symbol and timestamp if order_id not found
            order_symbol = order.get('symbol', '')
            order_time = order.get('time', 0) or order.get('createdAt', 0)

            if order_symbol and order_time:
                # Try to find matching trade by symbol and approximate time
                matching_trade = None
                for trade in db_trades:
                    coin_symbol = trade.get('coin_symbol', '')
                    if not coin_symbol:
                        continue

                    # Convert to KuCoin symbol format
                    kucoin_symbol = _convert_to_kucoin_futures_symbol(coin_symbol)
                    if kucoin_symbol != order_symbol:
                        continue

                    # Check if time is within 10 minutes
                    try:
                        created_at = trade.get('created_at', '')
                        if created_at:
                            # datetime and timezone are imported at top of file
                            created_dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                            order_dt = datetime.fromtimestamp(order_time / 1000 if order_time > 1e10 else order_time, tz=timezone.utc)
                            time_diff = abs((created_dt - order_dt).total_seconds())

                            if time_diff < 600:  # Within 10 minutes
                                matching_trade = trade
                                break
                    except Exception:
                        pass

                if matching_trade:
                    try:
                        # Update trade with order information
                        # datetime and timezone are imported at top of file
                        update_data = {
                            'exchange_order_id': str(order_id),
                            'exchange_response': json.dumps(order),
                            'sync_order_response': json.dumps(order),
                            'last_order_sync': datetime.now(timezone.utc).isoformat(),
                            'updated_at': datetime.now(timezone.utc).isoformat()
                        }

                        # Extract order details
                        filled_size = float(order.get('filledSize', 0))
                        filled_value = float(order.get('filledValue', 0))
                        kucoin_status = order.get('status', 'NEW')

                        mapped_order_status, mapped_position_status = StatusManager.map_exchange_to_internal(
                            kucoin_status, filled_size
                        )
                        update_data['order_status'] = mapped_order_status
                        update_data['status'] = mapped_position_status

                        if filled_size > 0:
                            update_data['position_size'] = f"{filled_size:.8f}"
                        if filled_value > 0 and filled_size > 0:
                            avg_price = filled_value / filled_size
                            update_data['entry_price'] = f"{avg_price:.8f}"
                            update_data['entry_price'] = f"{avg_price:.8f}"

                        supabase.table("trades").update(update_data).eq("id", matching_trade['id']).execute()
                        updates_made += 1
                        logging.info(f"✅ Matched and updated KuCoin trade {matching_trade['id']} by symbol+time for order {order_id}")
                    except Exception as e:
                        logging.error(f"Error updating matched KuCoin trade {matching_trade['id']}: {e}")
                else:
                    logging.warning(f"KuCoin order {order_id} ({order_symbol}) not found in database (tried order_id and symbol+time matching)")

    logging.info(f"KuCoin order sync completed: {updates_made} updates made")


async def sync_kucoin_positions_to_database_enhanced(bot: DiscordBot, supabase: Client, kucoin_positions: list, db_trades: list):
    """Sync KuCoin positions to database"""
    logging.info("Starting KuCoin position sync...")

    # Create lookup for database trades by symbol
    db_trades_by_symbol = {}
    for trade in db_trades:
        coin_symbol = trade.get('coin_symbol', '')
        if coin_symbol:
            # Convert to KuCoin symbol format (e.g., BTC -> XBTUSDTM, ETH -> ETHUSDTM)
            kucoin_symbol = _convert_to_kucoin_futures_symbol(coin_symbol)
            if kucoin_symbol not in db_trades_by_symbol:
                db_trades_by_symbol[kucoin_symbol] = []
            db_trades_by_symbol[kucoin_symbol].append(trade)

    updates_made = 0
    current_time = datetime.now(timezone.utc).isoformat()
    active_symbols = set()

    for position in kucoin_positions:
        symbol = position.get('symbol', '')
        if not symbol:
            continue
        if symbol in db_trades_by_symbol:
            active_symbols.add(symbol)
            matching_trades = db_trades_by_symbol[symbol]
            for trade in matching_trades:
                try:
                    # Convert contract size to asset quantity
                    contract_size = abs(float(position.get('size', 0)))
                    contract_multiplier = 1.0

                    # Get contract multiplier for this symbol
                    try:
                        coin_symbol = trade.get('coin_symbol', '')
                        if coin_symbol and bot.kucoin_exchange:
                            trading_pair = f"{coin_symbol.upper()}-USDT"
                            filters = await bot.kucoin_exchange.get_futures_symbol_filters(trading_pair)
                            if filters and 'multiplier' in filters:
                                try:
                                    contract_multiplier = float(filters['multiplier'])
                                except (TypeError, ValueError):
                                    contract_multiplier = 1.0
                    except Exception as e:
                        logging.warning(f"Could not get contract multiplier for {symbol}: {e}")

                    # Calculate asset quantity
                    asset_quantity = contract_size * contract_multiplier

                    # Update position information
                    update_data = {
                        'position_size': asset_quantity,  # Store asset quantity, not contract count
                        'mark_price': float(position.get('markPrice', 0)),
                        # Do not write unrealized_pnl to trades (column not in schema, and we avoid PnL for unfilled)
                        'last_mark_sync': current_time,
                        'updated_at': current_time
                    }

                    # Update exchange-specific fields for KuCoin
                    kucoin_entry = float(position.get('entryPrice', 0))
                    update_data['entry_price'] = kucoin_entry
                    if not trade.get('entry_price') and kucoin_entry:
                        update_data['entry_price'] = kucoin_entry

                    # Set position size if missing
                    if not trade.get('position_size') and asset_quantity > 0:
                        update_data['position_size'] = str(asset_quantity)

                    # If trade is not ACTIVE/OPEN, mark ACTIVE when we see a live position
                    status = str(trade.get('status', '')).upper()
                    if status not in ['ACTIVE', 'OPEN'] and abs(float(position.get('size', 0))) > 0:
                        update_data['status'] = 'ACTIVE'

                    supabase.table("trades").update(update_data).eq("id", trade['id']).execute()
                    updates_made += 1
                    logging.info(f"Updated KuCoin position for trade {trade['id']} ({symbol}) - Size: {position.get('size')}, Mark: {position.get('markPrice')}")

                except Exception as e:
                    logging.error(f"Error updating KuCoin position for trade {trade['id']}: {e}")

    # Detect and mark CLOSED for previously ACTIVE symbols no longer present
    try:
        from src.core.unified_status_updater import update_trade_status_safely
        from src.core.data_enrichment import enrich_trade_data_before_close

        for symbol, matching_trades in db_trades_by_symbol.items():
            if symbol in active_symbols:
                continue
            for trade in matching_trades:
                try:
                    status = str(trade.get('status', '')).upper()
                    closed_at = trade.get('closed_at')

                    # Close trade if: status is ACTIVE/OPEN OR if closed_at is set but status isn't CLOSED
                    should_close = (
                        status in ['ACTIVE', 'OPEN'] or
                        (closed_at is not None and status not in ['CLOSED', 'CANCELLED', 'FAILED'])
                    )

                    if not should_close:
                        continue

                    # Check if this is a failed trade that never executed
                    exchange_response = trade.get('exchange_response')
                    is_failed = False
                    if exchange_response:
                        if isinstance(exchange_response, list):
                            response_str = ' '.join(str(x) for x in exchange_response)
                        else:
                            response_str = str(exchange_response)
                        if 'Trade execution failed' in response_str or 'execution failed' in response_str.lower():
                            is_failed = True

                    if is_failed:
                        # Mark as FAILED, not CLOSED
                        update_data = {
                            'status': 'FAILED',
                            'order_status': 'FAILED',
                            'is_active': False,
                            'updated_at': datetime.now(timezone.utc).isoformat()
                        }
                        supabase.table("trades").update(update_data).eq("id", trade['id']).execute()
                        updates_made += 1
                        logging.info(f"Marked KuCoin trade {trade['id']} ({symbol}) as FAILED (never executed)")
                    else:
                        # Step 1: Enrich trade data before closing
                        enriched_data = await enrich_trade_data_before_close(trade, bot, supabase)

                        # Step 2: Use unified status update system
                        success, status_update_data = await update_trade_status_safely(
                            supabase=supabase,
                            trade_id=trade['id'],
                            trade=trade,
                            force_closed=True,
                            bot=bot
                        )

                        if not success:
                            logging.warning(f"Failed to update status safely for KuCoin trade {trade['id']}, using fallback")
                            status_update_data = {
                                'status': 'CLOSED',
                                'order_status': 'FILLED',
                                'is_active': False
                            }

                        # Merge enriched data and status update
                        close_update = {**enriched_data, **status_update_data}
                        close_update['is_active'] = False  # Always set is_active to false when closing

                        # Set defaults only if data is truly missing
                        if not close_update.get('exit_price'):
                            if not trade.get('exit_price') and not trade.get('exit_price'):
                                close_update['exit_price'] = '0'
                                close_update['exit_price'] = '0'
                        if not close_update.get('pnl_usd'):
                            if trade.get('pnl_usd') in [None, 0, '0', '0.0']:
                                close_update['pnl_usd'] = '0'
                        if not close_update.get('net_pnl'):
                            if not trade.get('net_pnl'):
                                close_update['net_pnl'] = '0'

                        # Set closed_at timestamp
                        try:
                            from discord_bot.utils.timestamp_manager import ensure_closed_at
                            await ensure_closed_at(supabase, trade['id'])
                            logging.info(f"✅ Set closed_at timestamp for KuCoin trade {trade['id']} via cleanup closure")
                        except Exception as e:
                            logging.warning(f"Could not set closed_at timestamp for KuCoin trade {trade['id']}: {e}")

                        supabase.table("trades").update(close_update).eq("id", trade['id']).execute()
                        updates_made += 1
                        logging.info(f"Marked KuCoin trade {trade['id']} ({symbol}) as CLOSED with enriched data")
                except Exception as e:
                    logging.error(f"Error marking trade {trade['id']} as CLOSED: {e}")
    except Exception as e:
        logging.error(f"Closed-position detection failed: {e}")

    logging.info(f"KuCoin position sync completed: {updates_made} updates made")


async def sync_positions_to_database_enhanced(bot: DiscordBot, supabase: Client, binance_positions: list, db_trades: list):
    """Sync Binance positions to database"""
    logging.info("Starting position sync...")

    # Create lookup for database trades by symbol
    db_trades_by_symbol = {}
    for trade in db_trades:
        symbol = extract_symbol_from_trade(trade)
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
                        # Write unified mark snapshot fields
                        'mark_price': mark_price,
                        'last_mark_sync': current_time,
                        # Do not write unrealized_pnl to trades (column not in schema, and we avoid PnL for unfilled)
                        'updated_at': current_time
                    }

                    supabase.table("trades").update(update_data).eq("id", db_trade['id']).execute()
                    updates_made += 1
                    logging.info(f"Updated position for trade {db_trade['id']} ({symbol})")

                except Exception as e:
                    logging.error(f"Error updating position for trade {db_trade['id']}: {e}")
        else:
            logging.warning(f"Position for {symbol} not found in database")

    logging.info(f"Position sync completed: {updates_made} updates made")


async def cleanup_closed_positions_enhanced(bot: DiscordBot, supabase: Client, binance_positions: list, db_trades: list):
    """Mark trades as closed if position is no longer active on Binance.

    Uses unified status update system and data enrichment pipeline to ensure
    complete and consistent data before closing trades.
    """
    logging.info("Starting cleanup of closed positions...")

    from src.core.unified_status_updater import update_trade_status_safely
    from src.core.data_enrichment import enrich_trade_data_before_close

    # Get all symbols with active positions on Binance
    active_symbols = {pos.get('symbol') for pos in binance_positions if float(pos.get('positionAmt', 0)) != 0}

    # Find database trades that should be marked as closed
    trades_to_close = []
    for trade in db_trades:
        status = str(trade.get('status', '')).upper()
        closed_at = trade.get('closed_at')

        # Get symbol with fallback logic
        symbol = extract_symbol_from_trade(trade)

        # Close trade if:
        # 1. Symbol not in active positions AND status is ACTIVE/OPEN/PENDING, OR
        # 2. closed_at is set but status isn't CLOSED/CANCELLED/FAILED (regardless of active positions)
        should_close = (
            symbol and (
                (symbol not in active_symbols and status in ['ACTIVE', 'OPEN', 'PENDING']) or
                (closed_at is not None and status not in ['CLOSED', 'CANCELLED', 'FAILED'])
            )
        )

        if should_close:
            trades_to_close.append(trade)

    updates_made = 0

    for trade in trades_to_close:
        try:
            # Step 1: Enrich trade data before closing (query exchange for missing data)
            enriched_data = await enrich_trade_data_before_close(trade, bot, supabase)

            # Step 2: Use unified status update system
            success, status_update_data = await update_trade_status_safely(
                supabase=supabase,
                trade_id=trade['id'],
                trade=trade,
                force_closed=True,
                bot=bot
            )

            if not success:
                logging.warning(f"Failed to update status safely for trade {trade['id']}, using fallback")
                status_update_data = {
                    'status': 'CLOSED',
                    'order_status': 'FILLED',
                    'is_active': False
                }

            # Merge enriched data and status update
            update_data = {**enriched_data, **status_update_data}
            update_data['is_active'] = False  # Always set is_active to false when closing

            # Set defaults only if data is truly missing (not 0 from enrichment)
            if not update_data.get('exit_price'):
                if not trade.get('exit_price'):
                    update_data['exit_price'] = '0'

            if not update_data.get('pnl_usd'):
                current_pnl = trade.get('pnl_usd')
                if current_pnl is None or float(current_pnl) == 0:
                    update_data['pnl_usd'] = '0'

            if not update_data.get('net_pnl'):
                if not trade.get('net_pnl'):
                    update_data['net_pnl'] = '0'

            # Set closed_at timestamp when trade is marked as closed
            try:
                from discord_bot.utils.timestamp_manager import ensure_closed_at
                await ensure_closed_at(supabase, trade['id'])
                logging.info(f"✅ Set closed_at timestamp for trade {trade['id']} via cleanup closure")
            except Exception as e:
                logging.warning(f"Could not set closed_at timestamp for trade {trade['id']}: {e}")

            supabase.table("trades").update(update_data).eq("id", trade['id']).execute()
            updates_made += 1
            logging.info(f"Marked trade {trade['id']} ({extract_symbol_from_trade(trade)}) as CLOSED with enriched data")

        except Exception as e:
            logging.error(f"Error marking trade {trade['id']} as closed: {e}")

    logging.info(f"Cleanup completed: {updates_made} trades marked as closed")


async def sync_closed_trades_from_history_enhanced(bot: DiscordBot, supabase: Client, db_trades: list):
    """Sync closed trades from Binance history"""
    logging.info("Starting closed trades sync from history...")

    updates_made = 0
    current_time = datetime.now(timezone.utc).isoformat()

    for trade in db_trades:
        try:
            # Get symbol from trade
            symbol = extract_symbol_from_trade(trade)
            if not symbol:
                continue

            # Get order ID
            order_id = None
            if trade.get('exchange_order_id'):
                order_id = trade.get('exchange_order_id')
            elif trade.get('binance_response'):
                order_details = extract_order_details_from_response(trade['binance_response'])
                order_id = order_details.get('orderId')

            if not order_id:
                continue

            # Get order history from Binance
            try:
                if bot.binance_exchange and bot.binance_exchange.client:
                    order_history = await bot.binance_exchange.client.futures_get_all_orders(
                        symbol=f"{symbol}USDT",
                        limit=10,
                        startTime=int((datetime.now(timezone.utc) - timedelta(hours=48)).timestamp() * 1000)
                    )
                else:
                    raise Exception("Binance client not initialized")

                # Find matching order
                matching_order = None
                for order in order_history:
                    if str(order.get('orderId')) == str(order_id):
                        matching_order = order
                        break

                if matching_order:
                    order_status = matching_order.get('status')

                    # Use centralized status mapping
                    from src.core.status_manager import StatusManager

                    # Get position size for proper status mapping
                    position_size = float(matching_order.get('executedQty', 0))
                    mapped_order_status, mapped_position_status = StatusManager.map_exchange_to_internal(
                        order_status, position_size
                    )

                    update_data = {
                        'order_status': mapped_order_status,
                        'status': mapped_position_status,
                        'updated_at': current_time
                    }

                    # Extract P&L from exchange_response or sync_order_response if available
                    try:
                        for resp_field in ['exchange_response', 'sync_order_response']:
                            resp_data = trade.get(resp_field)
                            if resp_data:
                                parsed_resp = safe_parse_exchange_response(resp_data) if isinstance(resp_data, str) else resp_data
                                if isinstance(parsed_resp, dict):
                                    rp = parsed_resp.get('rp')
                                    if rp is not None:
                                        rp_value = float(rp)
                                        # Only update if pnl_usd is missing or zero
                                        current_pnl = trade.get('pnl_usd')
                                        if current_pnl is None or float(current_pnl) == 0:
                                            update_data['pnl_usd'] = rp_value
                                            update_data['pnl_source'] = resp_field
                                            logging.info(f"Extracted P&L {rp_value} from {resp_field} for trade {trade['id']}")
                                        break
                    except Exception as e:
                        logging.warning(f"Could not extract P&L from stored responses for trade {trade['id']}: {e}")

                    # For filled orders, check if position is still open and update accordingly
                    if order_status == 'FILLED':
                        try:
                            positions = await bot.binance_exchange.get_futures_position_information()
                            position_open = any(
                                pos.get('symbol') == f"{symbol}USDT" and
                                float(pos.get('positionAmt', 0)) != 0
                                for pos in positions
                            )

                            if not position_open:
                                # Position is closed, update status and exit price
                                update_data['status'] = 'CLOSED'
                                update_data['exit_price'] = f"{float(matching_order.get('avgPrice', 0)):.8f}"
                                update_data['price_source'] = 'binance_order_history'
                        except Exception:
                            # If we can't check position, keep the mapped status from StatusManager
                            pass

                    elif order_status == 'NEW':
                        update_data = {
                            'status': 'PENDING',
                            'updated_at': current_time
                        }

                    else:
                        continue

                    # Update the trade
                    supabase.table("trades").update(update_data).eq("id", trade['id']).execute()
                    updates_made += 1
                    logging.info(f"Updated trade {trade['id']} status to {update_data.get('status')}")

            except Exception as e:
                logging.warning(f"Error getting order history for trade {trade['id']}: {e}")
                continue

        except Exception as e:
            logging.error(f"Error processing trade {trade.get('id')}: {e}")

    logging.info(f"Closed trades sync completed: {updates_made} updates made")

# Removed check_order_status_on_binance - replaced by enhanced sync method

# Removed update_trade_as_filled - replaced by enhanced sync method

async def update_trade_as_canceled(supabase: Client, trade_id: int, status: str):
    """Update trade as canceled"""
    now = datetime.now(timezone.utc).isoformat()
    updates = {
        "status": "CANCELED",
        "sync_order_response": f"Order canceled on {now}",
        "updated_at": now
    }
    await update_trade_status(supabase, trade_id, updates)

async def update_trade_as_expired(supabase: Client, trade_id: int, status: str):
    """Update trade as expired"""
    now = datetime.now(timezone.utc).isoformat()
    updates = {
        "status": "EXPIRED",
        "sync_order_response": f"Order expired on {now}",
        "updated_at": now
    }
    await update_trade_status(supabase, trade_id, updates)

async def update_trade_as_closed(supabase: Client, trade_id: int, reason: str):
    """Update trade as closed with reason"""
    now = datetime.now(timezone.utc).isoformat()
    updates = {
        "status": "CLOSED",
        "sync_order_response": f"Trade closed: {reason} on {now}",
        "updated_at": now
    }
    await update_trade_status(supabase, trade_id, updates)

async def update_trade_status(supabase: Client, trade_id: int, updates: dict):
    """Helper function to update trade status"""
    try:
        supabase.from_("trades").update(updates).eq("id", trade_id).execute()
    except Exception as e:
        logging.error(f"Error updating trade {trade_id}: {e}")

def calculate_pnl(entry_price: float, exit_price: float, position_size: float, position_type: str, fees: float = 0.001) -> float:
    """
    Calculate PnL for a trade as an actual value (USD), not a percentage.
    Args:
        entry_price: Price when position was opened
        exit_price: Price when position was closed
        position_size: Size of the position
        position_type: 'LONG' or 'SHORT'
        fees: Trading fees as decimal (default 0.1%)
    Returns:
        PnL as a value (USD)
    """
    if position_type.upper() == 'LONG':
        pnl = (exit_price - entry_price) * position_size
    else:
        pnl = (entry_price - exit_price) * position_size
    # Optionally subtract fees as a value
    fee_value = (entry_price + exit_price) * position_size * fees
    pnl -= fee_value
    return round(pnl, 2)

async def update_trade_with_exit_data(supabase: Client, trade_id: int, exit_price: float, exit_reason: str):
    """
    Update trade with exit price and calculate PnL.

    Args:
        trade_id: Database trade ID
        exit_price: Price when position was closed
        exit_reason: Reason for exit (TP1, TP2, SL, manual_close, etc.)
    """
    try:
        # Get the trade data
        response = supabase.from_("trades").select("*").eq("id", trade_id).single().execute()
        trade = response.data

        if not trade:
            logging.error(f"Trade {trade_id} not found")
            return

        # Extract required data
        parsed_signal = trade.get('parsed_signal', {})
        entry_prices = parsed_signal.get('entry_prices', [])
        position_type = parsed_signal.get('position_type', 'LONG')
        position_size = trade.get('position_size', 0)

        if not entry_prices or not position_size:
            logging.warning(f"Trade {trade_id} missing entry price or position size")
            return

        entry_price = float(entry_prices[0])  # Use first entry price

        # Calculate PnL
        pnl_value = calculate_pnl(entry_price, exit_price, position_size, position_type)

        # Update database
        now = datetime.now(timezone.utc).isoformat()
        updates = {
            "exit_price": exit_price,
            "pnl": pnl_value,
            "status": "CLOSED",
            "sync_order_response": f"Position closed: {exit_reason} at {exit_price} (PnL: {pnl_value:.2f})",
            "updated_at": now
        }

        await update_trade_status(supabase, trade_id, updates)
        logging.info(f"Trade {trade_id} updated with exit price {exit_price}, PnL: {pnl_value:.2f}")

    except Exception as e:
        logging.error(f"Error updating trade {trade_id} with exit data: {e}")

async def process_exit_alert_with_pnl(bot: DiscordBot, supabase: Client, alert_data: dict, trade_id: int):
    """
    Process an exit alert and update PnL/exit_price.

    Args:
        alert_data: Alert data containing exit information
        trade_id: Database trade ID
    """
    try:
        # Get current market price for the symbol
        symbol = alert_data.get('coin_symbol', '')
        if not symbol:
            logging.warning(f"Alert missing coin symbol for trade {trade_id}")
            return

        # Get current price from price service
        current_price = await bot.price_service.get_price(symbol)
        if not current_price:
            logging.warning(f"Could not get current price for {symbol}")
            return

        exit_reason = alert_data.get('action_type', 'manual_close')

        # Update trade with exit data
        await update_trade_with_exit_data(supabase, trade_id, current_price, exit_reason)

    except Exception as e:
        logging.error(f"Error processing exit alert for trade {trade_id}: {e}")


async def sync_pnl_data_with_binance(bot, supabase):
    """Sync P&L data from Binance Futures API to Supabase using orderId"""
    try:
        logging.info("Starting P&L data sync with Binance...")

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

        logging.info(f"Processing {len(trades)} trades across {len(trades_by_symbol)} symbols")

        for symbol, symbol_trades in trades_by_symbol.items():
            try:
                trading_pair = f"{symbol}USDT"

                # Check if symbol is supported before making API calls
                is_supported = await bot.binance_exchange.is_futures_symbol_supported(trading_pair)
                if not is_supported:
                    logging.warning(f"Symbol {trading_pair} not supported, skipping P&L sync for {len(symbol_trades)} trades")
                    continue

                # Get all user trades for this symbol (limit to last 1000 to avoid rate limits)
                user_trades = await bot.binance_exchange.get_user_trades(symbol=trading_pair, limit=1000)

                if not user_trades:
                    logging.info(f"No user trades found for {trading_pair}")
                    continue

                logging.info(f"Found {len(user_trades)} user trades for {trading_pair}")

                # Create lookup by orderId for fast matching
                trades_by_order_id = {trade.get('orderId'): trade for trade in user_trades if trade.get('orderId')}

                # Process each trade for this symbol
                for trade in symbol_trades:
                    try:
                        # Extract orderId from sync_order_response or exchange_response
                        sync_order_response = trade.get('sync_order_response', '')
                        ex_resp = trade.get('exchange_response') or trade.get('binance_response', '')
                        order_id = None

                        # Try sync_order_response first, then fallback to exchange_response
                        if isinstance(sync_order_response, dict) and 'orderId' in sync_order_response:
                            order_id = sync_order_response['orderId']
                        elif isinstance(sync_order_response, str):
                            # Try to parse JSON response
                            try:
                                import json
                                response_data = json.loads(sync_order_response)
                                order_id = response_data.get('orderId')
                            except:
                                pass

                        # Fallback to exchange_response if sync_order_response doesn't have orderId
                        if not order_id:
                            if isinstance(ex_resp, dict) and 'orderId' in ex_resp:
                                order_id = ex_resp['orderId']
                            elif isinstance(ex_resp, str):
                                # Try to parse JSON response
                                try:
                                    import json
                                    response_data = json.loads(ex_resp)
                                    order_id = response_data.get('orderId')
                                except:
                                    pass

                        if not order_id:
                            logging.warning(f"Trade {trade['id']} missing orderId in sync_order_response or binance_response, skipping")
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
                                'last_pnl_sync': datetime.now(timezone.utc).isoformat()
                            }

                            if update_trade_pnl(supabase, trade['id'], pnl_data):
                                logging.info(f"Updated P&L data for trade {trade['id']} (orderId: {order_id}): Entry={entry_price}, Realized={realized_pnl}, Unrealized={unrealized_pnl}")
                            else:
                                logging.error(f"Failed to update P&L data for trade {trade['id']}")
                        else:
                            logging.warning(f"No matching trade found for orderId {order_id} in {trading_pair}")

                    except Exception as e:
                        logging.error(f"Failed to sync P&L for trade {trade.get('id')}: {e}")
                        continue

            except Exception as e:
                logging.error(f"Failed to sync P&L for symbol {symbol}: {e}")
                continue

        logging.info("P&L data sync completed")

    except Exception as e:
        logging.error(f"Error in P&L data sync: {e}")


async def backfill_trades_from_binance_history(bot, supabase, days: int = 30, symbol: str = ""):
    """
    Backfill trades table with PnL and exit price data from Binance history using order lifecycle matching.
    This improved version uses the exact order lifecycle (created_at to modified_at) for accurate P&L tracking.
    """
    logging.info(f"🔄 Starting enhanced trade backfill from Binance history for last {days} days")

    try:
        # Get trades needing backfill
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        cutoff_iso = cutoff.isoformat()

        # Query for closed BINANCE trades missing PnL or exit price data
        # IMPORTANT: limit to Binance so we don't accidentally backfill KuCoin trades
        response = (
            supabase
            .from_("trades")
            .select("*")
            .eq("status", "CLOSED")
            .eq("exchange", "binance")
            .gte("created_at", cutoff_iso)
            .execute()
        )
        trades = response.data or []

        # Filter for trades missing PnL or exit price, or missing coin_symbol
        trades_needing_backfill = []
        for trade in trades:
            # Extra safety: only process Binance trades here
            if str(trade.get('exchange', '')).lower() != 'binance':
                continue
            pnl = trade.get('pnl_usd')
            exit_price = trade.get('exit_price')
            coin_symbol = trade.get('coin_symbol')

            # Include if missing PnL or exit price, or if missing coin_symbol but has data to extract it
            missing_data = (pnl is None or pnl == 0 or exit_price is None or exit_price == 0)
            missing_symbol = not coin_symbol and (trade.get('parsed_signal') or trade.get('binance_response'))

            if missing_data or missing_symbol:
                trades_needing_backfill.append(trade)

        if not trades_needing_backfill:
            logging.info("No trades need backfilling")
            return

        logging.info(f"Found {len(trades_needing_backfill)} trades needing backfill")

        # Process each trade using order lifecycle matching
        trades_updated = 0
        for trade in trades_needing_backfill:
            try:
                success = await backfill_single_trade_with_lifecycle(bot, supabase, trade)
                if success:
                    trades_updated += 1
                await asyncio.sleep(0.1)  # Rate limiting
            except Exception as e:
                logging.error(f"Error backfilling trade {trade.get('id')}: {e}")

        logging.info(f"✅ Enhanced backfill completed: {trades_updated}/{len(trades_needing_backfill)} trades updated")

    except Exception as e:
        logging.error(f"Error in enhanced trade backfill: {e}", exc_info=True)


def get_order_lifecycle(db_trade: Dict) -> Tuple[Optional[int], Optional[int], Optional[int]]:
    """Get order start, end, and duration in milliseconds using created_at to updated_at range."""
    try:
        # Get timestamps from database - prefer snake_case
        created_at = db_trade.get('created_at') or db_trade.get('createdAt')
        updated_at = db_trade.get('updated_at') or db_trade.get('updatedAt')

        if not created_at:
            logging.warning(f"Trade {db_trade.get('id')} has no created_at timestamp")
            return None, None, None

        # Parse start time (created_at)
        if isinstance(created_at, str):
            if 'T' in created_at:
                dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                start_time = int(dt.timestamp() * 1000)
            else:
                start_time = int(float(created_at) * 1000)
        else:
            start_time = int(created_at.timestamp() * 1000)

        # Prefer closed_at for end time; fallback to updated_at; finally created_at
        closed_at = db_trade.get('closed_at')
        candidate_end = closed_at or updated_at

        if not candidate_end:
            # Fallback to created_at if neither closed_at nor updated_at exists
            end_time = start_time
            duration = 0
            logging.warning(f"Trade {db_trade.get('id')} has no closed_at/updated_at - using created_at as end time")
        else:
            if isinstance(candidate_end, str):
                if 'T' in candidate_end:
                    dt = datetime.fromisoformat(candidate_end.replace('Z', '+00:00'))
                    end_time = int(dt.timestamp() * 1000)
                else:
                    end_time = int(float(candidate_end) * 1000)
            else:
                end_time = int(candidate_end.timestamp() * 1000)
            duration = end_time - start_time

        logging.info(f"Trade {db_trade.get('id')} lifecycle: {start_time} to {end_time} (duration: {duration}ms)")
        return start_time, end_time, duration

    except Exception as e:
        logging.error(f"Error getting order lifecycle: {e}")
        return None, None, None


async def get_income_for_trade_period(
    bot,
    symbol: str,
    start_time: int,
    end_time: int,
    *,
    expand: bool = False,
    buffer_before_ms: int = 0,
    buffer_after_ms: int = 5000,  # Tighter default buffer to avoid overlap
) -> List[Dict]:
    """Get income history for a specific trade period.

    By default this is STRICT: only records whose time lies within [start_time, end_time]
    are returned. Set expand=True to allow a wider search window when nothing is found.
    """
    try:
        # Validate symbol before making API call
        if not symbol or len(symbol) < 2 or len(symbol) > 10:
            logging.warning(f"Invalid symbol '{symbol}' - skipping income fetch")
            return []

        # Check if symbol is likely a valid trading pair
        # Most valid symbols are 3-6 characters and contain only letters/numbers
        if not symbol.isalnum():
            logging.warning(f"Symbol '{symbol}' contains invalid characters - skipping income fetch")
            return []

        # Common invalid symbols that appear in the database
        invalid_symbols = {
            'APE', 'BT', 'ARC', 'AUCTION', 'AEVO', 'AERO', 'BANANAS31', 'APT', 'AAVE',
            'ARKM', 'ARB', 'ALT', 'BNX', 'BILLY', 'AI16Z', 'BLAST', 'BSW', 'B2', 'API3',
            'BON', 'AIXBT', 'AI', '1000BONK', 'ANIME', 'ARK', 'BOND', 'ANYONE', 'ADA',
            'ALCH', 'BERA', 'ALU', 'ALGO', 'BONK', 'AGT', 'AVAX', 'AIN', 'ATOM',
            '1000RATS', 'BMT', 'BB', 'AR', 'BENDOG', 'AVA', '0X0', 'BRETT', 'BANANA',
            '1000TURBO', 'M', 'PUMPFUN', 'SPX', 'MYX', 'MOG', 'PENGU', 'SPK', 'CRV',
            'HYPE', 'MAGIC', 'ZRC', 'FARTCOIN', 'IP', 'SYN', 'SKATE', 'SOON', 'PUMP'
        }

        if symbol.upper() in invalid_symbols:
            logging.warning(f"Symbol '{symbol}' is in invalid symbols list - skipping income fetch")
            return []

        logging.info(f"Fetching {symbol}USDT income from {start_time} to {end_time}")

        async def fetch_window(window_start: int, window_end: int) -> List[Dict]:
            all_incomes_local: List[Dict] = []
            chunk_start_local = window_start
            while chunk_start_local < window_end:
                chunk_end_local = min(chunk_start_local + (7 * 24 * 60 * 60 * 1000), window_end)
                try:
                    chunk_incomes_local = await bot.binance_exchange.get_income_history(
                        symbol=f"{symbol}USDT",
                        start_time=chunk_start_local,
                        end_time=chunk_end_local,
                        limit=1000,
                    )
                    all_incomes_local.extend(chunk_incomes_local)
                    await asyncio.sleep(0.5)  # Rate limiting
                except Exception as e:
                    logging.error(f"Error fetching chunk income: {e}")
                chunk_start_local = chunk_end_local
            return all_incomes_local

        # Strict window by default; optional minimal buffer can be provided by caller
        search_start = start_time - max(0, int(buffer_before_ms))
        search_end = end_time + max(0, int(buffer_after_ms))

        all_incomes = await fetch_window(search_start, search_end)

        # Filter to trade period with buffer
        # Include buffer in the filtering to catch final P&L records
        filter_start = search_start
        filter_end = search_end

        filtered_incomes = []
        for income in all_incomes:
            if not isinstance(income, dict):
                continue

            income_time = income.get('time')
            if income_time and filter_start <= int(income_time) <= filter_end:
                filtered_incomes.append(income)

        logging.info(f"Found {len(filtered_incomes)} income records within trade period")
        return filtered_incomes

    except Exception as e:
        logging.error(f"Error getting income for trade period: {e}")
        return []


async def backfill_single_trade_with_lifecycle(bot, supabase, trade: Dict) -> Optional[bool]:
    """Backfill a single trade using order lifecycle matching with income history."""
    try:
        trade_id = trade.get('id')
        if not trade_id:
            return False

        # This helper is Binance-specific (uses binance_exchange income and trades).
        # Do NOT attempt to backfill non-Binance trades here.
        exchange_name = str(trade.get('exchange', '')).lower()
        if exchange_name != 'binance':
            return False

        # Use the enhanced symbol extraction function
        symbol = extract_symbol_from_trade(trade)

        if not symbol:
            logging.warning(f"Trade {trade_id} missing symbol - cannot backfill")
            return False

        # Get order lifecycle
        start_time, end_time, duration = get_order_lifecycle(trade)

        if not start_time:
            logging.warning(f"Trade {trade_id} has no valid timestamps")
            return False

        if end_time is None:
            logging.warning(f"Trade {trade_id} has no valid end time")
            return False

        income_records = await get_income_for_trade_period(bot, symbol, start_time, end_time)

        if not income_records:
            logging.info(f"Trade {trade_id} ({symbol}): No income records found during order lifecycle")
            # Fallback path: compute PnL from entry/exit and size when income is missing
            fallback_update = {
                'updated_at': datetime.now(timezone.utc).isoformat()
            }

            try:
                # Resolve entry price
                entry_price = float(trade.get('entry_price') or 0.0)
                # Resolve position size
                size_raw = trade.get('position_size')
                position_size = float(size_raw) if size_raw is not None else 0.0
                # Resolve side
                position_type = str(trade.get('signal_type') or '').upper()

                exit_price_val = float(trade.get('exit_price') or 0.0)
                price_source_str: Optional[str] = None

                # If missing exit price, try to fetch last trade fill price during lifecycle
                if exit_price_val <= 0 and hasattr(bot, 'binance_exchange') and bot.binance_exchange:
                    try:
                        # Use account trades endpoint for symbol & window
                        trades_hist = await bot.binance_exchange.get_user_trades(symbol=f"{symbol}USDT", start_time=start_time, end_time=end_time)
                        if trades_hist:
                            last_trade = trades_hist[-1]
                            price_candidate = last_trade.get('price') or last_trade.get('p')
                            if price_candidate:
                                exit_price_val = float(price_candidate)
                                price_source_str = 'binance_user_trades_fallback'
                    except Exception as e:
                        logging.warning(f"Failed to fetch user trades for {symbol}: {e}")

                # As last resort, use mark price
                if exit_price_val <= 0 and hasattr(bot, 'binance_exchange') and bot.binance_exchange:
                    try:
                        mp = await bot.binance_exchange.get_futures_mark_price(f"{symbol}USDT")
                        if mp:
                            exit_price_val = float(mp)
                            price_source_str = 'binance_mark_price_fallback'
                    except Exception as e:
                        logging.warning(f"Failed to fetch mark price for {symbol}: {e}")

                # Compute pnl if we have required inputs
                if entry_price > 0 and exit_price_val > 0 and position_size > 0 and position_type in ['LONG', 'SHORT']:
                    if position_type == 'LONG':
                        pnl = (exit_price_val - entry_price) * position_size
                    else:
                        pnl = (entry_price - exit_price_val) * position_size

                    # Only update if pnl_usd is missing/zero
                    pnl_existing = trade.get('pnl_usd')
                    if pnl_existing is None or float(pnl_existing) == 0.0:
                        fallback_update['pnl_usd'] = str(pnl)
                        # If no net_pnl, mirror pnl
                        if not trade.get('net_pnl'):
                            fallback_update['net_pnl'] = str(pnl)

                    # Persist exit price if we derived it
                    if not trade.get('exit_price') and exit_price_val > 0:
                        fallback_update['exit_price'] = str(exit_price_val)
                        if price_source_str:
                            fallback_update['price_source'] = price_source_str

                # Update if we prepared any fields
                if len(fallback_update) > 1:
                    response = supabase.from_("trades").update(fallback_update).eq("id", trade_id).execute()
                    if response.data:
                        logging.info(f"✅ Fallback backfill updated trade {trade_id}: exit={fallback_update.get('exit_price')} pnl={fallback_update.get('pnl_usd')}")
                        return True
            except Exception as e:
                logging.error(f"Fallback P&L computation failed for trade {trade_id}: {e}")

            return False

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

        # Calculate NET P&L (including fees)
        net_pnl = total_realized_pnl + total_commission + total_funding_fee

        # Count REALIZED_PNL records for logging
        realized_pnl_records = [r for r in income_records if isinstance(r, dict) and (r.get('incomeType') or r.get('type')) == 'REALIZED_PNL']

        if not realized_pnl_records:
            logging.info(f"Trade {trade_id} ({symbol}): No REALIZED_PNL records found")
            return False

        # Prepare update data
        update_data = {
            'updated_at': datetime.now(timezone.utc).isoformat()
        }

        # Only fix missing closed_at for historical trades (backfill scenario)
        # Don't set closed_at during normal operation - let WebSocket handle it
        if not trade.get('closed_at') and trade.get('status') == 'CLOSED':
            # Import timestamp manager for historical fixes only
            from discord_bot.utils.timestamp_manager import fix_historical_timestamps
            await fix_historical_timestamps(supabase, trade_id)
            logging.info(f"✅ Fixed historical closed_at for trade {trade_id}")

        # Update P&L if we have income records from Binance
        if len(income_records) > 0:
            # Store REALIZED_PNL in pnl_usd (existing column)
            update_data['pnl_usd'] = str(total_realized_pnl)

            # Store NET P&L (including fees) in net_pnl (existing column)
            update_data['net_pnl'] = str(net_pnl)

            # Update last sync timestamp
            update_data['last_pnl_sync'] = datetime.now(timezone.utc).isoformat()

            logging.info(f"✅ Updated trade {trade_id} - P&L: {total_realized_pnl:.6f} (REALIZED_PNL), NET P&L: {net_pnl:.6f} (from {len(realized_pnl_records)} batches)")

        # Update exit price if we have one from realized P&L records
        if exit_price > 0:
            update_data['exit_price'] = str(exit_price)
            update_data['price_source'] = 'binance_income_history'
            logging.info(f"✅ Updated trade {trade_id} - Exit Price: {exit_price:.6f}")

        # Also update coin_symbol if it was missing and we extracted it
        if not trade.get('coin_symbol') and symbol:
            update_data['coin_symbol'] = symbol
            logging.info(f"✅ Updated trade {trade_id} - Added coin_symbol: {symbol}")

        # Update database
        if len(update_data) > 1:  # More than just updated_at
            response = supabase.from_("trades").update(update_data).eq("id", trade_id).execute()
            if response.data:
                logging.info(f"✅ Successfully updated trade {trade_id}")
            return True

            return False

    except Exception as e:
        logging.error(f"Error backfilling trade {trade.get('id')} with lifecycle: {e}")
        return False


def update_trade_pnl(supabase, trade_id: int, pnl_data: dict) -> bool:
    """Update trade record with P&L data"""
    try:
        pnl_data['updated_at'] = datetime.now(timezone.utc).isoformat()
        supabase.table("trades").update(pnl_data).eq("id", trade_id).execute()
        return True
    except Exception as e:
        logging.error(f"Failed to update trade P&L: {e}")
        return False


def get_trades_needing_pnl_sync(supabase) -> list:
    """Get trades that need P&L data sync"""
    try:
        # Get trades without P&L data or with old sync timestamp
        result = supabase.table("trades").select("*").or_(
            "entry_price.is.null,last_pnl_sync.is.null"
        ).execute()
        return result.data or []
    except Exception as e:
        logging.error(f"Failed to get trades needing P&L sync: {e}")
        return []


# ============================================================================
# KUCOIN ENHANCED FUNCTIONS
# ============================================================================

async def cleanup_closed_kucoin_positions_enhanced(bot, supabase: Client, kucoin_positions: list, db_trades: list):
    """Mark KuCoin trades as closed if position is no longer active.

    Uses unified status update system and data enrichment pipeline to ensure
    complete and consistent data before closing trades.
    """
    logging.info("Starting cleanup of closed KuCoin positions...")

    from src.core.unified_status_updater import update_trade_status_safely
    from src.core.data_enrichment import enrich_trade_data_before_close

    # Get all symbols with active positions on KuCoin
    # Convert KuCoin position symbols (e.g., XBTUSDTM) to bot symbols (e.g., BTC)
    active_symbols = set()
    for pos in kucoin_positions:
        kucoin_symbol = pos.get('symbol', '')
        position_size = float(pos.get('size', 0))
        if kucoin_symbol and position_size != 0:
            # Convert KuCoin symbol to bot symbol format (XBTUSDTM -> BTC)
            bot_symbol = _symbol_converter.convert_kucoin_to_bot(kucoin_symbol)
            # Extract base symbol (BTCUSDT -> BTC)
            if bot_symbol.endswith('USDT'):
                bot_symbol = bot_symbol[:-4]
            if bot_symbol:
                active_symbols.add(bot_symbol)
                logging.debug(f"Active position: {kucoin_symbol} -> {bot_symbol}")

    logging.info(f"Active symbols on KuCoin: {active_symbols}")

    # Find database trades that should be marked as closed
    trades_to_close = []
    for trade in db_trades:
        status = str(trade.get('status', '')).upper()
        closed_at = trade.get('closed_at')
        symbol = extract_symbol_from_trade(trade)

        # Close trade if:
        # 1. Symbol not in active positions AND status is ACTIVE/OPEN/PENDING, OR
        # 2. closed_at is set but status isn't CLOSED/CANCELLED/FAILED (regardless of active positions)
        should_close = (
            symbol and (
                (symbol not in active_symbols and status in ['ACTIVE', 'OPEN', 'PENDING']) or
                (closed_at is not None and status not in ['CLOSED', 'CANCELLED', 'FAILED'])
            )
        )

        if should_close:
            trades_to_close.append(trade)
            logging.debug(f"Trade {trade.get('id')} ({symbol}) should be closed: status={status}, closed_at={closed_at}, in_active_symbols={symbol in active_symbols if symbol else False}")

    logging.info(f"Found {len(trades_to_close)} trades to close out of {len(db_trades)} total trades")

    updates_made = 0

    for trade in trades_to_close:
        try:
            # Step 1: Enrich trade data before closing (query exchange for missing data)
            enriched_data = await enrich_trade_data_before_close(trade, bot, supabase)

            # Step 2: Use unified status update system
            success, status_update_data = await update_trade_status_safely(
                supabase=supabase,
                trade_id=trade['id'],
                trade=trade,
                force_closed=True,
                bot=bot
            )

            if not success:
                logging.warning(f"Failed to update status safely for KuCoin trade {trade['id']}, using fallback")
                status_update_data = {
                    'status': 'CLOSED',
                    'order_status': 'FILLED',
                    'is_active': False
                }

            # Merge enriched data and status update
            update_data = {**enriched_data, **status_update_data}
            update_data['is_active'] = False  # Always set is_active to false when closing

            # Set defaults only if data is truly missing (not 0 from enrichment)
            if not update_data.get('exit_price'):
                if not trade.get('exit_price') and not trade.get('exit_price'):
                    update_data['exit_price'] = '0'
                    update_data['exit_price'] = '0'

            if not update_data.get('pnl_usd'):
                current_pnl = trade.get('pnl_usd')
                if current_pnl is None or float(current_pnl) == 0:
                    update_data['pnl_usd'] = '0'

            if not update_data.get('net_pnl'):
                if not trade.get('net_pnl'):
                    update_data['net_pnl'] = '0'

            # Set closed_at timestamp when trade is marked as closed
            try:
                from discord_bot.utils.timestamp_manager import ensure_closed_at
                await ensure_closed_at(supabase, trade['id'])
                logging.info(f"✅ Set closed_at timestamp for KuCoin trade {trade['id']} via cleanup closure")
            except Exception as e:
                logging.warning(f"Could not set closed_at timestamp for KuCoin trade {trade['id']}: {e}")

            supabase.table("trades").update(update_data).eq("id", trade['id']).execute()
            updates_made += 1
            logging.info(f"Marked KuCoin trade {trade['id']} ({extract_symbol_from_trade(trade)}) as CLOSED with enriched data")

        except Exception as e:
            logging.error(f"Error marking KuCoin trade {trade['id']} as closed: {e}")

    logging.info(f"KuCoin cleanup completed: {updates_made} trades marked as closed")


def _convert_to_kucoin_futures_symbol(symbol: str) -> str:
    """
    Convert bot symbol (e.g., 'BTC', 'ETH') to KuCoin futures symbol (e.g., 'XBTUSDTM', 'ETHUSDTM').

    Args:
        symbol: Base symbol from database (e.g., 'BTC', 'ETH')

    Returns:
        KuCoin futures symbol format (e.g., 'XBTUSDTM' for BTC, 'ETHUSDTM' for ETH)
    """
    if not symbol:
        return ""

    # Use the symbol converter to properly map BTC -> XBT
    kucoin_symbol = _symbol_converter.convert_bot_to_kucoin_futures(symbol)
    return kucoin_symbol


async def _get_kucoin_exit_info_from_trades(
    bot, trade: Dict, symbol: str, kucoin_symbol: str = None
) -> Optional[Dict]:
    """
    Get exit price and related info from KuCoin trade history by matching entry/exit trades.

    Returns dict with:
    - exit_price: Exit price from closing trade
    - entry_price: Entry price from opening trade (if found)
    - position_size: Position size from trades (if found)
    - total_fees: Total fees from entry and exit trades
    """
    try:
        if not bot.kucoin_exchange:
            return None

        # Get timestamps for time filtering
        created_at = trade.get('created_at')
        closed_at = trade.get('closed_at') or trade.get('updated_at')

        if not created_at:
            logging.warning(f"Trade {trade.get('id')} has no created_at timestamp")
            return None

        # Parse timestamps
        try:
            if isinstance(created_at, str):
                created_dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
            else:
                created_dt = created_at if isinstance(created_at, datetime) else datetime.now(timezone.utc)

            if closed_at:
                if isinstance(closed_at, str):
                    closed_dt = datetime.fromisoformat(closed_at.replace('Z', '+00:00'))
                else:
                    closed_dt = closed_at if isinstance(closed_at, datetime) else datetime.now(timezone.utc)
            else:
                closed_dt = datetime.now(timezone.utc)

            # Add buffer (1 hour before, 2 hours after) to catch all related trades
            start_time_ms = int((created_dt - timedelta(hours=1)).timestamp() * 1000)
            end_time_ms = int((closed_dt + timedelta(hours=2)).timestamp() * 1000)

            # Ensure end_time is not in the future and not more than 7 days from start
            now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
            max_window_ms = 7 * 24 * 60 * 60 * 1000  # 7 days in milliseconds

            # Cap end_time to now
            end_time_ms = min(end_time_ms, now_ms)

            # Ensure window is not larger than 7 days (KuCoin limit)
            if end_time_ms - start_time_ms > max_window_ms:
                start_time_ms = end_time_ms - max_window_ms

            # Ensure start_time is not too far in the past (KuCoin retention limit)
            # KuCoin typically keeps data for ~7 days, so ensure start is not older than 8 days
            min_start_ms = now_ms - (8 * 24 * 60 * 60 * 1000)
            if start_time_ms < min_start_ms:
                logging.warning(
                    f"Trade {trade.get('id')} created_at ({created_dt}) is too old (>8 days). "
                    f"KuCoin may not have trade history. Start time adjusted from {start_time_ms} to {min_start_ms}"
                )
                start_time_ms = min_start_ms
                # Re-adjust end_time if needed
                if end_time_ms - start_time_ms > max_window_ms:
                    end_time_ms = start_time_ms + max_window_ms

            # Final validation: start must be <= end
            if start_time_ms > end_time_ms:
                logging.warning(
                    f"Trade {trade.get('id')} has invalid time range: start_time ({start_time_ms}) > end_time ({end_time_ms}). "
                    f"Using last 7 days as fallback."
                )
                end_time_ms = now_ms
                start_time_ms = now_ms - max_window_ms

        except Exception as e:
            logging.warning(f"Could not parse timestamps for trade {trade.get('id')}: {e}")
            # Use a 7-day window as fallback
            now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
            end_time_ms = now_ms
            start_time_ms = now_ms - (7 * 24 * 60 * 60 * 1000)

        # Validate time range before making API call
        if start_time_ms <= 0 or end_time_ms <= 0:
            logging.warning(f"Trade {trade.get('id')} has invalid timestamps: start={start_time_ms}, end={end_time_ms}")
            return None

        if start_time_ms >= end_time_ms:
            logging.warning(
                f"Trade {trade.get('id')} has invalid time range: start={start_time_ms} >= end={end_time_ms}. "
                f"Using last 7 days as fallback."
            )
            now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
            end_time_ms = now_ms
            start_time_ms = now_ms - (7 * 24 * 60 * 60 * 1000)

        logging.info(
            f"Querying trade history for {kucoin_symbol} "
            f"from {datetime.fromtimestamp(start_time_ms/1000, tz=timezone.utc)} "
            f"to {datetime.fromtimestamp(end_time_ms/1000, tz=timezone.utc)} "
            f"(trade {trade.get('id')})"
        )

        # Convert symbol to KuCoin futures format if not provided
        if not kucoin_symbol:
            kucoin_symbol = _convert_to_kucoin_futures_symbol(symbol)

        # Get trade history for the symbol within time window
        try:
            trade_history = await bot.kucoin_exchange.get_user_trades(
                symbol=kucoin_symbol,
                start_time=start_time_ms,
                end_time=end_time_ms,
                limit=1000
            )
        except Exception as e:
            error_msg = str(e).lower()
            if 'timerangeinvalid' in error_msg or 'timerange' in error_msg:
                logging.warning(
                    f"Time range invalid for trade {trade.get('id')} ({kucoin_symbol}). "
                    f"This trade may be too old for KuCoin's retention period. "
                    f"Trying without time filter..."
                )
                # Try without time filter (just recent trades)
                try:
                    trade_history = await bot.kucoin_exchange.get_user_trades(
                        symbol=kucoin_symbol,
                        limit=1000
                    )
                    # Filter trades manually by timestamp
                    if trade_history:
                        trade_history = [
                            t for t in trade_history
                            if t.get('time', 0) >= start_time_ms and t.get('time', 0) <= end_time_ms
                        ]
                except Exception as e2:
                    logging.error(f"Failed to get trade history without time filter: {e2}")
                    trade_history = []
            else:
                raise

        if not trade_history:
            logging.info(f"No trade history found for {kucoin_symbol} in time window")
            return None

        logging.info(
            f"Retrieved {len(trade_history)} trades for {kucoin_symbol}. "
            f"Trade {trade.get('id')}: position_type={trade.get('signal_type')}, "
            f"created={created_dt}, closed={closed_dt}"
        )

        # Determine expected sides for entry and exit
        position_type = str(trade.get('signal_type') or '').upper()
        if position_type == 'LONG':
            entry_side = 'buy'
            exit_side = 'sell'
        elif position_type == 'SHORT':
            entry_side = 'sell'
            exit_side = 'buy'
        else:
            logging.warning(f"Unknown position type: {position_type}")
            return None

        logging.info(f"Looking for entry_side={entry_side}, exit_side={exit_side}")

        # Normalize sides from trade history (handle enum types)
        def normalize_side(side_value):
            if side_value is None:
                return None
            if isinstance(side_value, str):
                return side_value.lower()
            # Handle enum types
            if hasattr(side_value, 'value'):
                return str(side_value.value).lower()
            return str(side_value).lower()

        # Get order_id from trade for additional matching (if available)
        order_id = trade.get('exchange_order_id') or trade.get('kucoin_order_id')

        # Filter trades by side and time window
        entry_trades = []
        exit_trades = []
        skipped_trades = []

        for t in trade_history:
            side = normalize_side(t.get('side'))
            trade_time = t.get('time', 0)
            trade_price = float(t.get('price', 0))
            trade_size = float(t.get('size', 0))

            # Try to get time from raw_response if time is 0
            if (not trade_time or trade_time == 0) and t.get('raw_response'):
                raw = t.get('raw_response')
                if hasattr(raw, 'createdAt'):
                    trade_time = getattr(raw, 'createdAt', 0)
                elif hasattr(raw, 'time'):
                    trade_time = getattr(raw, 'time', 0)

            # Handle missing timestamps - be more lenient
            if not trade_time or trade_time == 0:
                # If no orderId match, estimate time based on trade lifecycle
                if order_id and str(t.get('orderId', '')) == str(order_id):
                    # Order matches - use created_at
                    trade_time = int(created_dt.timestamp() * 1000)
                    logging.info(
                        f"Trade {trade.get('id')}: Using created_at as time for orderId match "
                        f"(trade has price={trade_price}, size={trade_size}, side={side})"
                    )
                elif side in [entry_side, exit_side]:
                    # Side matches, use a time estimate between created and closed
                    # Prefer closer to created for entry, closer to closed for exit
                    if side == entry_side:
                        trade_time = int(created_dt.timestamp() * 1000)
                    else:
                        trade_time = int(closed_dt.timestamp() * 1000)
                    logging.info(
                        f"Trade {trade.get('id')}: Using estimated time for side={side} "
                        f"(trade has price={trade_price}, size={trade_size})"
                    )
                else:
                    skipped_trades.append({
                        'reason': 'no_time_no_side_match',
                        'side': side,
                        'price': trade_price,
                        'size': trade_size
                    })
                    continue

            # Check if trade is within our window (with some tolerance)
            trade_dt = datetime.fromtimestamp(trade_time / 1000, tz=timezone.utc)

            # Additional validation: if we have orderId, prefer matching trades
            trade_order_id = t.get('orderId')
            is_order_match = order_id and trade_order_id and str(trade_order_id) == str(order_id)

            trade_info = {
                'price': trade_price,
                'size': trade_size,
                'fee': float(t.get('fee', 0)),
                'time': trade_time,
                'datetime': trade_dt,
                'order_match': is_order_match,
                'side': side
            }

            if side == entry_side:
                entry_trades.append(trade_info)
                logging.info(
                    f"Trade {trade.get('id')}: Added entry trade - price={trade_price}, "
                    f"size={trade_size}, time={trade_dt}"
                )
            elif side == exit_side:
                exit_trades.append(trade_info)
                logging.info(
                    f"Trade {trade.get('id')}: Added exit trade - price={trade_price}, "
                    f"size={trade_size}, time={trade_dt}"
                )
            else:
                skipped_trades.append({
                    'reason': 'side_mismatch',
                    'side': side,
                    'expected_entry': entry_side,
                    'expected_exit': exit_side,
                    'price': trade_price,
                    'size': trade_size
                })

        if skipped_trades:
            logging.info(
                f"Trade {trade.get('id')}: Skipped {len(skipped_trades)} trades - "
                f"reasons: {', '.join(set(s['reason'] for s in skipped_trades))}"
            )

        logging.info(
            f"Trade {trade.get('id')}: Found {len(entry_trades)} entry trades, "
            f"{len(exit_trades)} exit trades"
        )

        # Sort by time
        entry_trades.sort(key=lambda x: x['time'])
        exit_trades.sort(key=lambda x: x['time'])

        result = {}

        # Find entry trade (first entry trade in time window, or closest to created_at)
        if entry_trades:
            # Prefer trades that match orderId if available
            matching_entry_trades = [t for t in entry_trades if t.get('order_match', False)]
            if matching_entry_trades:
                entry_trades_to_use = matching_entry_trades
            else:
                entry_trades_to_use = entry_trades

            # Find entry trade closest to created_at
            entry_trade = min(entry_trades_to_use, key=lambda t: abs((t['datetime'] - created_dt).total_seconds()))

            # Calculate weighted average entry price from all entry trades before closed_at
            entry_before_close = [t for t in entry_trades_to_use if t['datetime'] <= closed_dt]
            if not entry_before_close:
                entry_before_close = entry_trades_to_use

            if entry_before_close:
                total_entry_value = sum(t['price'] * t['size'] for t in entry_before_close)
                total_entry_size = sum(t['size'] for t in entry_before_close)
                if total_entry_size > 0:
                    result['entry_price'] = total_entry_value / total_entry_size
                    result['position_size'] = total_entry_size

        # Find exit trade (last exit trade in time window, or closest to closed_at)
        if exit_trades:
            # Prefer trades that match orderId if available
            matching_exit_trades = [t for t in exit_trades if t.get('order_match', False)]
            if matching_exit_trades:
                exit_trades_to_use = matching_exit_trades
            else:
                exit_trades_to_use = exit_trades

            # Filter exit trades that happen after entry trades
            if entry_trades:
                first_entry_time = min(t['time'] for t in entry_trades)
                exit_after_entry = [t for t in exit_trades_to_use if t['time'] >= first_entry_time]
            else:
                exit_after_entry = exit_trades_to_use

            if exit_after_entry:
                # Find exit trade closest to closed_at
                exit_trade = min(exit_after_entry, key=lambda t: abs((t['datetime'] - closed_dt).total_seconds()))
                result['exit_price'] = exit_trade['price']

                # Calculate weighted average exit price if multiple exit trades
                total_exit_value = sum(t['price'] * t['size'] for t in exit_after_entry)
                total_exit_size = sum(t['size'] for t in exit_after_entry)
                if total_exit_size > 0:
                    weighted_exit_price = total_exit_value / total_exit_size
                    result['exit_price'] = weighted_exit_price
                    if not result.get('position_size'):
                        result['position_size'] = total_exit_size

        # Calculate total fees
        total_fees = 0.0
        if entry_trades:
            total_fees += sum(t['fee'] for t in entry_trades)
        if exit_trades:
            total_fees += sum(t['fee'] for t in exit_trades)
        result['total_fees'] = total_fees

        if result.get('exit_price'):
            logging.info(
                f"Found exit info for trade {trade.get('id')}: "
                f"exit_price={result.get('exit_price')}, "
                f"entry_price={result.get('entry_price')}, "
                f"position_size={result.get('position_size')}, "
                f"fees={total_fees}"
            )

        return result if result.get('exit_price') else None

    except Exception as e:
        logging.error(f"Error getting exit info from trades for {trade.get('id')}: {e}", exc_info=True)
        return None


async def backfill_kucoin_trades_from_history_enhanced(bot, supabase: Client, db_trades: list):
    """Backfill KuCoin trades with missing exit prices and position sizes from order/trade history"""
    logging.info("Starting KuCoin trade backfill from history...")

    updates_made = 0
    current_time = datetime.now(timezone.utc).isoformat()

    for trade in db_trades:
        try:
            trade_id = trade.get('id')
            symbol = extract_symbol_from_trade(trade)

            if not symbol or not trade_id:
                continue

            # Skip if already has complete data
            if (trade.get('exit_price') and trade.get('position_size') and
                trade.get('pnl_usd') not in [None, 0, '0', '0.0']):
                continue

            # Get order ID
            order_id = trade.get('exchange_order_id') or trade.get('kucoin_order_id')
            if not order_id:
                continue

            # Get order details from KuCoin
            order_details = None
            try:
                kucoin_symbol = _convert_to_kucoin_futures_symbol(symbol)
                order_details = await bot.kucoin_exchange.get_order_status(kucoin_symbol, order_id)
            except Exception as e:
                logging.warning(f"Order {order_id} not found on KuCoin (likely expired): {e}")
                # Continue to trade history approach
                order_details = None

            if not order_details:
                # Fallback: try to get data from trade history and exchange_response
                logging.info(f"Attempting fallback data extraction for trade {trade_id}")

                # Extract data from exchange_response if available
                exchange_response = trade.get('exchange_response', '')
                if exchange_response:
                    try:
                        import json
                        if isinstance(exchange_response, str):
                            resp_data = json.loads(exchange_response)
                        else:
                            resp_data = exchange_response

                        # Extract position size from origQty or filledSize
                        orig_qty = float(resp_data.get('origQty', 0))
                        filled_size = float(resp_data.get('filledSize', 0))
                        actual_entry_price = float(resp_data.get('actualEntryPrice', 0))

                        update_data = {
                            'updated_at': current_time
                        }

                        # Set position size if missing
                        if not trade.get('position_size'):
                            if filled_size > 0:
                                update_data['position_size'] = str(filled_size)
                            elif orig_qty > 0:
                                update_data['position_size'] = str(orig_qty)

                        # Set entry price if missing
                        if not trade.get('entry_price') and actual_entry_price > 0:
                            update_data['entry_price'] = str(actual_entry_price)
                            update_data['entry_price'] = str(actual_entry_price)

                        # Try to get exit price from trade history with proper matching
                        # Also update if exit_price is missing even if exit_price exists
                        is_missing_exit = (not trade.get('exit_price') or float(trade.get('exit_price', 0) or 0) == 0)
                        is_missing_kucoin_exit = (not trade.get('exit_price') or float(trade.get('exit_price', 0) or 0) == 0)

                        if trade.get('status') == 'CLOSED' and (is_missing_exit or is_missing_kucoin_exit):
                            try:
                                kucoin_symbol = _convert_to_kucoin_futures_symbol(symbol)
                                exit_info = await _get_kucoin_exit_info_from_trades(
                                    bot, trade, symbol, kucoin_symbol
                                )

                                if exit_info and exit_info.get('exit_price'):
                                    exit_price = exit_info['exit_price']
                                    update_data['exit_price'] = str(exit_price)
                                    update_data['exit_price'] = str(exit_price)

                                    # Calculate PnL if we have all required data
                                    entry_price = float(trade.get('entry_price') or actual_entry_price or exit_info.get('entry_price') or 0)
                                    pos_size = float(update_data.get('position_size') or trade.get('position_size') or exit_info.get('position_size') or 0)
                                    position_type = str(trade.get('signal_type') or '').upper()
                                    total_fees = exit_info.get('total_fees', 0.0)

                                    if entry_price > 0 and pos_size > 0 and exit_price > 0:
                                        # Do NOT compute KuCoin PnL here; reconciliation script handles realized PnL precisely
                                        pass

                                        # Update entry price if we found a better one
                                        if exit_info.get('entry_price') and exit_info['entry_price'] > 0:
                                            if not trade.get('entry_price') or trade.get('entry_price') == 0:
                                                update_data['entry_price'] = str(exit_info['entry_price'])
                                                update_data['entry_price'] = str(exit_info['entry_price'])

                                        # Update position size if we found it from trades
                                        if exit_info.get('position_size') and exit_info['position_size'] > 0:
                                            if not trade.get('position_size') or trade.get('position_size') == 0:
                                                update_data['position_size'] = str(exit_info['position_size'])
                            except Exception as e:
                                logging.warning(f"Could not get trade history for fallback: {e}", exc_info=True)

                        # Update database if we have changes
                        if len(update_data) > 1:  # More than just updated_at
                            supabase.table("trades").update(update_data).eq("id", trade_id).execute()
                            updates_made += 1
                            logging.info(f"✅ Fallback backfilled KuCoin trade {trade_id}: {list(update_data.keys())}")

                        continue
                    except Exception as e:
                        logging.error(f"Fallback extraction failed for trade {trade_id}: {e}")
                        continue

            else:
                # Order exists, extract order information
                order_status = order_details.get('status', '')
                filled_size = float(order_details.get('filledSize', 0))
                filled_value = float(order_details.get('filledValue', 0))
                actual_entry_price = float(order_details.get('actualEntryPrice', 0))

                update_data = {
                    'updated_at': current_time
                }

                # Update position size if missing
                if not trade.get('position_size') and filled_size > 0:
                    update_data['position_size'] = str(filled_size)

                # Update entry price if missing
                if not trade.get('entry_price') and actual_entry_price > 0:
                    update_data['entry_price'] = str(actual_entry_price)
                    update_data['entry_price'] = str(actual_entry_price)

                # For closed trades, try to get exit price from trade history
                # Also update if exit_price is missing even if exit_price exists
                is_missing_exit = (not trade.get('exit_price') or float(trade.get('exit_price', 0) or 0) == 0)
                is_missing_kucoin_exit = (not trade.get('exit_price') or float(trade.get('exit_price', 0) or 0) == 0)

                if trade.get('status') == 'CLOSED' and (is_missing_exit or is_missing_kucoin_exit):
                    try:
                        kucoin_symbol = _convert_to_kucoin_futures_symbol(symbol)
                        exit_info = await _get_kucoin_exit_info_from_trades(
                            bot, trade, symbol, kucoin_symbol
                        )

                        if exit_info and exit_info.get('exit_price'):
                            exit_price = exit_info['exit_price']
                            update_data['exit_price'] = str(exit_price)
                            update_data['exit_price'] = str(exit_price)

                            # Calculate PnL if we have all required data
                            entry_price = float(trade.get('entry_price') or actual_entry_price or exit_info.get('entry_price') or 0)
                            pos_size_val = float(update_data.get('position_size') or trade.get('position_size') or exit_info.get('position_size') or filled_size or 0)
                            position_type = str(trade.get('signal_type') or '').upper()
                            total_fees = exit_info.get('total_fees', 0.0)

                            if entry_price > 0 and pos_size_val > 0 and exit_price > 0:
                                # Do NOT compute KuCoin PnL here; reconciliation script handles realized PnL precisely
                                pass

                                # Update entry price if we found a better one
                                if exit_info.get('entry_price') and exit_info['entry_price'] > 0:
                                    if not trade.get('entry_price') or trade.get('entry_price') == 0:
                                        update_data['entry_price'] = str(exit_info['entry_price'])
                                        update_data['entry_price'] = str(exit_info['entry_price'])

                                # Update position size if we found it from trades
                                if exit_info.get('position_size') and exit_info['position_size'] > 0:
                                    if not trade.get('position_size') or trade.get('position_size') == 0:
                                        update_data['position_size'] = str(exit_info['position_size'])

                    except Exception as e:
                        logging.warning(f"Could not get trade history for KuCoin trade {trade_id}: {e}", exc_info=True)

                # Update database if we have changes
                if len(update_data) > 1:  # More than just updated_at
                    supabase.table("trades").update(update_data).eq("id", trade_id).execute()
                    updates_made += 1
                    logging.info(f"✅ Backfilled KuCoin trade {trade_id}: {list(update_data.keys())}")

        except Exception as e:
            logging.error(f"Error processing KuCoin trade {trade.get('id', 'unknown')}: {e}")

    logging.info(f"KuCoin backfill completed: {updates_made} trades updated")


async def sync_missing_trade_data_comprehensive(bot: DiscordBot, supabase: Client, days_back: int = 7):
    """
    Comprehensive sync to populate missing entry_price, exit_price, position_size, and pnl_usd.

    Uses existing sync functions and exchange APIs to fill missing data.
    This is the permanent solution integrated into the scheduler.

    Args:
        bot: DiscordBot instance with exchange connections
        supabase: Supabase client
        days_back: Number of days to look back for trades
    """
    logging.info("🔄 Starting comprehensive missing trade data sync...")

    try:
        from datetime import datetime, timedelta, timezone
        from src.core.data_enrichment import enrich_trade_data_before_close

        cutoff = datetime.now(timezone.utc) - timedelta(days=days_back)
        cutoff_iso = cutoff.isoformat()

        # Get all trades from the period
        response = supabase.from_("trades").select("*").gte("created_at", cutoff_iso).execute()
        all_trades = response.data or []

        logging.info(f"Found {len(all_trades)} trades to check for missing data")

        trades_updated = 0
        updates_by_field = {
            'entry_price': 0,
            'exit_price': 0,
            'position_size': 0,
            'pnl_usd': 0
        }

        for trade in all_trades:
            try:
                trade_id = trade.get('id')
                exchange = str(trade.get('exchange', '')).lower()
                status = trade.get('status', '')

                # Skip failed trades
                if status == 'FAILED':
                    continue

                update_data = {}
                needs_update = False

                # Check for missing entry_price
                entry_price = trade.get('entry_price')
                if not entry_price or float(entry_price or 0) == 0:
                    entry_price_data = await _sync_entry_price(bot, trade, exchange)
                    if entry_price_data:
                        update_data.update(entry_price_data)
                        needs_update = True
                        updates_by_field['entry_price'] += 1

                # Check for missing position_size
                position_size = trade.get('position_size')
                if not position_size or float(position_size or 0) == 0:
                    position_size_data = await _sync_position_size(bot, trade, exchange)
                    if position_size_data:
                        update_data.update(position_size_data)
                        needs_update = True
                        updates_by_field['position_size'] += 1

                # For closed trades, check exit_price and pnl_usd
                if status in ['CLOSED', 'FILLED']:
                    # Check for missing exit_price
                    exit_price = trade.get('exit_price')
                    if not exit_price or float(exit_price or 0) == 0:
                        exit_price_data = await _sync_exit_price(bot, trade, exchange)
                        if exit_price_data:
                            update_data.update(exit_price_data)
                            needs_update = True
                            updates_by_field['exit_price'] += 1

                    # Check for missing pnl_usd
                    pnl_usd = trade.get('pnl_usd')
                    if not pnl_usd or float(pnl_usd or 0) == 0:
                        pnl_data = await _sync_pnl(bot, trade, exchange, update_data)
                        if pnl_data:
                            update_data.update(pnl_data)
                            needs_update = True
                            updates_by_field['pnl_usd'] += 1

                # Use existing enrichment function as fallback
                if needs_update:
                    enriched = await enrich_trade_data_before_close(trade, bot, supabase)
                    if enriched:
                        update_data.update(enriched)

                # Update database if we have data
                if update_data:
                    update_data['updated_at'] = datetime.now(timezone.utc).isoformat()
                    supabase.table("trades").update(update_data).eq("id", trade_id).execute()
                    trades_updated += 1
                    logging.info(f"✅ Updated trade {trade_id} ({trade.get('coin_symbol')}): {list(update_data.keys())}")

            except Exception as e:
                logging.error(f"Error syncing trade {trade.get('id')}: {e}")
                continue

        logging.info(f"✅ Comprehensive sync completed: {trades_updated} trades updated")
        logging.info(f"   - entry_price: {updates_by_field['entry_price']}")
        logging.info(f"   - exit_price: {updates_by_field['exit_price']}")
        logging.info(f"   - position_size: {updates_by_field['position_size']}")
        logging.info(f"   - pnl_usd: {updates_by_field['pnl_usd']}")

        return {
            'trades_updated': trades_updated,
            'updates_by_field': updates_by_field
        }

    except Exception as e:
        logging.error(f"Error in comprehensive missing trade data sync: {e}", exc_info=True)
        return {'error': str(e)}


async def _sync_entry_price(bot: DiscordBot, trade: Dict, exchange: str) -> Optional[Dict]:
    """Sync entry price from exchange order status."""
    try:
        order_id = trade.get('exchange_order_id') or trade.get('kucoin_order_id')
        coin_symbol = trade.get('coin_symbol')

        if not order_id or not coin_symbol:
            return None

        if exchange == 'binance' and bot.binance_exchange:
            symbol_pair = f"{coin_symbol}USDT"
            order_status = await bot.binance_exchange.get_order_status(symbol_pair, str(order_id))
            if order_status:
                avg_price = order_status.get('avgPrice') or order_status.get('avg_price')
                if avg_price and float(avg_price) > 0:
                    return {'entry_price': str(float(avg_price)), 'price_source': 'binance_order_status'}

        elif exchange == 'kucoin' and bot.kucoin_exchange:
            from src.exchange.kucoin.kucoin_symbol_converter import KucoinSymbolConverter
            symbol_converter = KucoinSymbolConverter()
            kucoin_symbol = symbol_converter.convert_bot_to_kucoin_futures(f"{coin_symbol}-USDT")
            order_status = await bot.kucoin_exchange.get_order_status(kucoin_symbol, str(order_id))
            if order_status:
                filled_size = float(order_status.get('filledSize', 0))
                filled_value = float(order_status.get('filledValue', 0))
                actual_entry_price = order_status.get('actualEntryPrice')

                if actual_entry_price and float(actual_entry_price) > 0:
                    return {'entry_price': str(float(actual_entry_price)), 'price_source': 'kucoin_order_status'}
                elif filled_size > 0 and filled_value > 0:
                    entry_price = filled_value / filled_size
                    return {'entry_price': str(entry_price), 'price_source': 'kucoin_order_status'}

        # Try to extract from stored responses
        for resp_field in ['exchange_response', 'sync_order_response']:
            resp_data = trade.get(resp_field)
            if resp_data:
                parsed = safe_parse_exchange_response(resp_data)
                if isinstance(parsed, dict):
                    if exchange == 'binance':
                        avg_price = parsed.get('avgPrice') or parsed.get('avg_price')
                        if avg_price and float(avg_price) > 0:
                            return {'entry_price': str(float(avg_price)), 'price_source': f'{exchange}_{resp_field}'}
                    elif exchange == 'kucoin':
                        filled_size = float(parsed.get('filledSize', 0))
                        filled_value = float(parsed.get('filledValue', 0))
                        if filled_size > 0 and filled_value > 0:
                            entry_price = filled_value / filled_size
                            return {'entry_price': str(entry_price), 'price_source': f'{exchange}_{resp_field}'}

        return None
    except Exception as e:
        logging.warning(f"Error syncing entry price for trade {trade.get('id')}: {e}")
        return None


async def _sync_position_size(bot: DiscordBot, trade: Dict, exchange: str) -> Optional[Dict]:
    """Sync position size from exchange order status."""
    try:
        order_id = trade.get('exchange_order_id') or trade.get('kucoin_order_id')
        coin_symbol = trade.get('coin_symbol')

        if not order_id or not coin_symbol:
            return None

        if exchange == 'binance' and bot.binance_exchange:
            symbol_pair = f"{coin_symbol}USDT"
            order_status = await bot.binance_exchange.get_order_status(symbol_pair, str(order_id))
            if order_status:
                executed_qty = order_status.get('executedQty') or order_status.get('executed_qty')
                if executed_qty and float(executed_qty) > 0:
                    return {'position_size': str(float(executed_qty))}

        elif exchange == 'kucoin' and bot.kucoin_exchange:
            from src.exchange.kucoin.kucoin_symbol_converter import KucoinSymbolConverter
            symbol_converter = KucoinSymbolConverter()
            kucoin_symbol = symbol_converter.convert_bot_to_kucoin_futures(f"{coin_symbol}-USDT")
            order_status = await bot.kucoin_exchange.get_order_status(kucoin_symbol, str(order_id))
            if order_status:
                # Prefer executedQty (already asset quantity) over filledSize (contract size)
                executed_qty = order_status.get('executedQty')
                if executed_qty and float(executed_qty) > 0:
                    return {'position_size': str(float(executed_qty))}
                # Fallback to origQty (asset quantity)
                orig_qty = order_status.get('origQty')
                if orig_qty and float(orig_qty) > 0:
                    return {'position_size': str(float(orig_qty))}
                # Last resort: convert filledSize (contract size) to asset quantity
                filled_size = order_status.get('filledSize')
                try:
                    contract_multiplier = float(order_status.get('contract_multiplier', 1) or 1)
                except (TypeError, ValueError):
                    contract_multiplier = 1.0
                if filled_size and float(filled_size) > 0:
                    asset_quantity = float(filled_size) * contract_multiplier
                    return {'position_size': str(asset_quantity)}

        # Try to extract from stored responses
        for resp_field in ['exchange_response', 'sync_order_response']:
            resp_data = trade.get(resp_field)
            if resp_data:
                parsed = safe_parse_exchange_response(resp_data)
                if isinstance(parsed, dict):
                    if exchange == 'binance':
                        executed_qty = parsed.get('executedQty') or parsed.get('executed_qty')
                        if executed_qty and float(executed_qty) > 0:
                            return {'position_size': str(float(executed_qty))}
                    elif exchange == 'kucoin':
                        # Prefer executedQty (asset quantity) over filledSize (contract size)
                        executed_qty = parsed.get('executedQty')
                        if executed_qty and float(executed_qty) > 0:
                            return {'position_size': str(float(executed_qty))}
                        # Fallback to origQty (asset quantity)
                        orig_qty = parsed.get('origQty')
                        if orig_qty and float(orig_qty) > 0:
                            return {'position_size': str(float(orig_qty))}
                        # Last resort: convert filledSize (contract size) to asset quantity
                        filled_size = parsed.get('filledSize')
                        try:
                            contract_multiplier = float(parsed.get('contract_multiplier', 1) or 1)
                        except (TypeError, ValueError):
                            contract_multiplier = 1.0
                        if filled_size and float(filled_size) > 0:
                            asset_quantity = float(filled_size) * contract_multiplier
                            return {'position_size': str(asset_quantity)}

        return None
    except Exception as e:
        logging.warning(f"Error syncing position size for trade {trade.get('id')}: {e}")
        return None


async def _sync_exit_price(bot: DiscordBot, trade: Dict, exchange: str) -> Optional[Dict]:
    """Sync exit price from exchange trade history or closing order."""
    try:
        order_id = trade.get('exchange_order_id') or trade.get('kucoin_order_id')
        coin_symbol = trade.get('coin_symbol')
        stop_loss_order_id = trade.get('stop_loss_order_id')

        if not coin_symbol:
            return None

        if exchange == 'binance' and bot.binance_exchange:
            symbol_pair = f"{coin_symbol}USDT"

            # Try to get from closing order (stop loss or manual close)
            if stop_loss_order_id:
                close_order = await bot.binance_exchange.get_order_status(symbol_pair, str(stop_loss_order_id))
                if close_order:
                    avg_price = close_order.get('avgPrice') or close_order.get('avg_price')
                    if avg_price and float(avg_price) > 0:
                        return {
                            'exit_price': str(float(avg_price)),
                            'price_source': 'binance_close_order_status'
                        }

            # Try from user trades (last trade for this symbol)
            try:
                from datetime import datetime, timedelta, timezone
                created_at = trade.get('created_at')
                if created_at:
                    created_dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                    start_time = int((created_dt - timedelta(hours=48)).timestamp() * 1000)
                    end_time = int(datetime.now(timezone.utc).timestamp() * 1000)

                    user_trades = await bot.binance_exchange.get_user_trades(
                        symbol=symbol_pair,
                        start_time=start_time,
                        end_time=end_time
                    )
                    if user_trades:
                        # Find closing trade (opposite side or reduceOnly)
                        for user_trade in reversed(user_trades):
                            if user_trade.get('reduceOnly') or user_trade.get('realizedPnl'):
                                price = user_trade.get('price') or user_trade.get('p')
                                if price and float(price) > 0:
                                    return {
                                        'exit_price': str(float(price)),
                                        'price_source': 'binance_user_trades'
                                    }
                        # Fallback to last trade
                        last_trade = user_trades[-1]
                        price = last_trade.get('price') or last_trade.get('p')
                        if price and float(price) > 0:
                            return {
                                'exit_price': str(float(price)),
                                'price_source': 'binance_user_trades'
                            }
            except Exception as e:
                logging.warning(f"Could not get exit price from user trades: {e}")

        elif exchange == 'kucoin' and bot.kucoin_exchange:
            from src.exchange.kucoin.kucoin_symbol_converter import KucoinSymbolConverter
            symbol_converter = KucoinSymbolConverter()
            kucoin_symbol = symbol_converter.convert_bot_to_kucoin_futures(f"{coin_symbol}-USDT")

            # Try from trade history
            try:
                from datetime import datetime, timedelta, timezone
                created_at = trade.get('created_at')
                if created_at:
                    created_dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                    start_time = int((created_dt - timedelta(hours=48)).timestamp() * 1000)
                    end_time = int(datetime.now(timezone.utc).timestamp() * 1000)

                    trade_history = await bot.kucoin_exchange.get_user_trades(
                        symbol=kucoin_symbol,
                        start_time=start_time,
                        end_time=end_time
                    )
                    if trade_history:
                        # Find matching order or last trade
                        if order_id:
                            matching = [t for t in trade_history if str(t.get('orderId', '')) == str(order_id)]
                            if matching:
                                price = matching[-1].get('price')
                                if price and float(price) > 0:
                                    return {'exit_price': str(float(price))}
                        # Fallback to last trade
                        last_trade = trade_history[-1]
                        price = last_trade.get('price')
                        if price and float(price) > 0:
                            return {'exit_price': str(float(price))}
            except Exception as e:
                logging.warning(f"Could not get exit price from KuCoin trade history: {e}")

        return None
    except Exception as e:
        logging.warning(f"Error syncing exit price for trade {trade.get('id')}: {e}")
        return None


async def _sync_pnl(bot: DiscordBot, trade: Dict, exchange: str, existing_updates: Dict) -> Optional[Dict]:
    """Sync PnL from exchange income history or calculate from prices."""
    try:
        coin_symbol = trade.get('coin_symbol')
        entry_price = float(existing_updates.get('entry_price') or trade.get('entry_price') or 0)
        exit_price = float(existing_updates.get('exit_price') or trade.get('exit_price') or 0)
        position_size = float(existing_updates.get('position_size') or trade.get('position_size') or 0)
        signal_type = str(trade.get('signal_type', 'LONG')).upper()

        if exchange == 'binance' and bot.binance_exchange:
            # Try to get from income history (most accurate)
            try:
                from datetime import datetime, timedelta, timezone
                created_at = trade.get('created_at')
                closed_at = trade.get('closed_at') or trade.get('updated_at')

                if created_at and closed_at:
                    created_dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                    closed_dt = datetime.fromisoformat(closed_at.replace('Z', '+00:00'))
                    start_time = int(created_dt.timestamp() * 1000)
                    end_time = int(closed_dt.timestamp() * 1000)

                    symbol_pair = f"{coin_symbol}USDT"
                    income_history = await bot.binance_exchange.get_income_history(
                        symbol=symbol_pair,
                        income_type='REALIZED_PNL',
                        start_time=start_time,
                        end_time=end_time
                    )

                    if income_history:
                        total_pnl = sum(float(inc.get('income', 0)) for inc in income_history)
                        if total_pnl != 0:
                            return {'pnl_usd': str(total_pnl), 'pnl_source': 'income_history'}
            except Exception as e:
                logging.warning(f"Could not get PnL from income history: {e}")

            # Fallback: calculate from entry/exit prices
            if entry_price > 0 and exit_price > 0 and position_size > 0:
                if signal_type == 'LONG':
                    pnl = (exit_price - entry_price) * position_size
                else:
                    pnl = (entry_price - exit_price) * position_size
                return {'pnl_usd': str(round(pnl, 2)), 'pnl_source': 'calculated'}

        elif exchange == 'kucoin' and bot.kucoin_exchange:
            # Do NOT compute KuCoin PnL here; dedicated KuCoin reconciliation/backfill
            # scripts use /api/v1/history-positions and are the single source of truth.
            # Returning None avoids attaching synthetic PnL to KuCoin trades.
            return None

        return None
    except Exception as e:
        logging.warning(f"Error syncing PnL for trade {trade.get('id')}: {e}")
        return None
