#!/usr/bin/env python3
"""
Backfill script to correct KuCoin position_size values in the database.

This script fixes historical trades where position_size was stored as contract count
instead of asset quantity. It can:
1. Query exchange for order details
2. Extract from stored exchange responses
3. Calculate from contract size using multiplier
"""

import asyncio
import json
import logging
import sys
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
from decimal import Decimal

# Add project root to path
sys.path.insert(0, '/home/ngigi/Documents/Brayo/cryptolens/rubicon-trading-bot')

from supabase import create_client, Client
from config.settings import SUPABASE_URL, SUPABASE_KEY
from src.exchange.kucoin.kucoin_exchange import KucoinExchange
from src.exchange.kucoin.kucoin_symbol_converter import symbol_converter
from config.settings import KUCOIN_API_KEY, KUCOIN_API_SECRET, KUCOIN_API_PASSPHRASE, KUCOIN_TESTNET

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def safe_parse_json(data: Any) -> Optional[Any]:
    """Safely parse JSON data. Returns dict, list, or None."""
    if not data:
        return None
    if isinstance(data, (dict, list)):
        return data
    if isinstance(data, str):
        try:
            parsed = json.loads(data)
            return parsed if isinstance(parsed, (dict, list)) else None
        except (json.JSONDecodeError, ValueError):
            return None
    return None


async def get_contract_multiplier(
    kucoin_exchange: KucoinExchange,
    coin_symbol: str
) -> int:
    """Get contract multiplier for a symbol."""
    try:
        trading_pair = f"{coin_symbol.upper()}-USDT"
        filters = await kucoin_exchange.get_futures_symbol_filters(trading_pair)
        if filters and 'multiplier' in filters:
            return int(filters['multiplier'])
    except Exception as e:
        logger.warning(f"Could not get contract multiplier for {coin_symbol}: {e}")
    return 1


def extract_position_size_from_response(
    response_data: Any,
    contract_multiplier: int = 1
) -> Optional[float]:
    """
    Extract position size (asset quantity) from exchange response.

    Priority:
    1. executedQty (already asset quantity)
    2. origQty (already asset quantity)
    3. filledSize * contract_multiplier (convert contract to asset)
    """
    parsed = safe_parse_json(response_data)
    if not parsed:
        return None

    # Handle list responses (error messages, etc.)
    if isinstance(parsed, list):
        # Check if it's an error message array like ["Trade execution failed: ..."]
        if len(parsed) > 0 and isinstance(parsed[0], str):
            logger.debug(f"Response is error message list: {parsed[0]}")
            return None
        # If it's a list of dicts, try first element
        if len(parsed) > 0 and isinstance(parsed[0], dict):
            parsed = parsed[0]
        else:
            return None

    # Must be a dict at this point
    if not isinstance(parsed, dict):
        return None

    # Priority 1: executedQty (already asset quantity)
    executed_qty = parsed.get('executedQty') or parsed.get('executed_qty')
    if executed_qty:
        try:
            return float(executed_qty)
        except (ValueError, TypeError):
            pass

    # Priority 2: origQty
    # NOTE: In old responses, origQty might be contract count (before our fix)
    # We'll return it as-is and let the caller check if it needs conversion
    orig_qty = parsed.get('origQty')
    if orig_qty:
        try:
            return float(orig_qty)
        except (ValueError, TypeError):
            pass

    # Priority 3: filledSize (contract size) - convert to asset quantity
    filled_size = parsed.get('filledSize')
    if filled_size:
        try:
            filled_size_float = float(filled_size)
            # Get multiplier from response if available
            multiplier = parsed.get('contract_multiplier', contract_multiplier)
            if multiplier and multiplier > 1:
                return filled_size_float * multiplier
            return filled_size_float
        except (ValueError, TypeError):
            pass

    return None


async def calculate_correct_position_size(
    trade: Dict[str, Any],
    kucoin_exchange: Optional[KucoinExchange] = None
) -> Optional[float]:
    """
    Calculate correct position_size (asset quantity) for a trade.

    Tries multiple methods:
    1. Query exchange for order status
    2. Extract from exchange_response
    3. Extract from sync_order_response
    4. Convert existing position_size if it looks like contract count
    """
    coin_symbol = trade.get('coin_symbol', '')
    exchange_order_id = trade.get('exchange_order_id') or trade.get('kucoin_order_id')
    current_position_size = trade.get('position_size')

    if not coin_symbol:
        logger.warning(f"Trade {trade.get('id')} has no coin_symbol")
        return None

    contract_multiplier = 1
    if kucoin_exchange:
        contract_multiplier = await get_contract_multiplier(kucoin_exchange, coin_symbol)

    # Method 1: Query exchange for order status
    if exchange_order_id and kucoin_exchange:
        try:
            trading_pair = f"{coin_symbol.upper()}-USDT"
            kucoin_symbol = symbol_converter.convert_bot_to_kucoin_futures(trading_pair)
            order_status = await kucoin_exchange.get_order_status(kucoin_symbol, str(exchange_order_id))

            if order_status:
                # Prefer executedQty (asset quantity)
                executed_qty = order_status.get('executedQty')
                if executed_qty and float(executed_qty) > 0:
                    logger.info(f"Trade {trade.get('id')}: Got asset quantity from exchange executedQty: {executed_qty}")
                    return float(executed_qty)

                # Fallback to origQty (asset quantity)
                orig_qty = order_status.get('origQty')
                if orig_qty and float(orig_qty) > 0:
                    logger.info(f"Trade {trade.get('id')}: Got asset quantity from exchange origQty: {orig_qty}")
                    return float(orig_qty)

                # Last resort: convert filledSize
                filled_size = order_status.get('filledSize')
                multiplier = order_status.get('contract_multiplier', contract_multiplier)
                if filled_size and float(filled_size) > 0:
                    asset_qty = float(filled_size) * multiplier if multiplier > 1 else float(filled_size)
                    logger.info(f"Trade {trade.get('id')}: Converted from exchange filledSize: {filled_size} contracts × {multiplier} = {asset_qty} assets")
                    return asset_qty
        except Exception as e:
            logger.warning(f"Trade {trade.get('id')}: Could not query exchange: {e}")

    # Method 2: Extract from exchange_response
    exchange_response = trade.get('exchange_response')
    if exchange_response:
        try:
            position_size = extract_position_size_from_response(exchange_response, contract_multiplier)
            if position_size:
                # Check if extracted value looks like contract count (old data before fix)
                # Heuristic: If it's a small integer (1-100), matches current position_size,
                # and we have a multiplier > 1, it's likely contract count stored as origQty
                if (contract_multiplier > 1 and
                    position_size <= 100 and
                    position_size == int(position_size) and
                    current_position_size and
                    abs(float(current_position_size) - position_size) < 0.001):
                    # This is contract count - convert to asset quantity
                    asset_qty = position_size / contract_multiplier
                    logger.info(f"Trade {trade.get('id')}: Detected contract count in exchange_response origQty: {position_size} contracts ÷ {contract_multiplier} = {asset_qty} assets")
                    return asset_qty
                logger.info(f"Trade {trade.get('id')}: Extracted from exchange_response: {position_size}")
                return position_size
        except Exception as e:
            logger.debug(f"Trade {trade.get('id')}: Error extracting from exchange_response: {e}")

    # Method 3: Extract from sync_order_response
    sync_order_response = trade.get('sync_order_response')
    if sync_order_response:
        try:
            position_size = extract_position_size_from_response(sync_order_response, contract_multiplier)
            if position_size:
                # Same check for contract count
                if (contract_multiplier > 1 and
                    position_size <= 100 and
                    position_size == int(position_size) and
                    current_position_size and
                    abs(float(current_position_size) - position_size) < 0.001):
                    asset_qty = position_size / contract_multiplier
                    logger.info(f"Trade {trade.get('id')}: Detected contract count in sync_order_response: {position_size} contracts ÷ {contract_multiplier} = {asset_qty} assets")
                    return asset_qty
                logger.info(f"Trade {trade.get('id')}: Extracted from sync_order_response: {position_size}")
                return position_size
        except Exception as e:
            logger.debug(f"Trade {trade.get('id')}: Error extracting from sync_order_response: {e}")

    # Method 4: Check if current position_size looks like contract count and convert
    if current_position_size:
        try:
            current_size = float(current_position_size)
            # Heuristic: If position_size is a small integer (1-100) and we have a multiplier > 1,
            # it's likely contract count (old data before fix)
            if contract_multiplier > 1 and 1 <= current_size <= 100 and current_size == int(current_size):
                asset_qty = current_size / contract_multiplier
                logger.info(f"Trade {trade.get('id')}: Converting suspected contract count {current_size} contracts ÷ {contract_multiplier} = {asset_qty} assets")
                return asset_qty
        except (ValueError, TypeError):
            pass

    return None


async def backfill_kucoin_position_sizes(
    supabase: Client,
    kucoin_exchange: Optional[KucoinExchange] = None,
    dry_run: bool = True,
    limit: Optional[int] = None
):
    """
    Backfill position_size for all KuCoin trades.

    Args:
        supabase: Supabase client
        kucoin_exchange: Optional KuCoin exchange instance for querying
        dry_run: If True, only log what would be updated
        limit: Optional limit on number of trades to process
    """
    logger.info("Starting KuCoin position_size backfill...")
    logger.info(f"Mode: {'DRY RUN' if dry_run else 'LIVE UPDATE'}")

    # Query all KuCoin trades
    query = supabase.table("trades").select("*").eq("exchange", "kucoin")

    if limit:
        query = query.limit(limit)

    response = query.execute()
    trades = response.data if response.data else []

    logger.info(f"Found {len(trades)} KuCoin trades to process")

    updated_count = 0
    skipped_count = 0
    error_count = 0

    for trade in trades:
        trade_id = trade.get('id')
        current_position_size = trade.get('position_size')

        try:
            # Calculate correct position size
            correct_position_size = await calculate_correct_position_size(trade, kucoin_exchange)

            if correct_position_size is None:
                logger.warning(f"Trade {trade_id}: Could not determine correct position_size, skipping")
                skipped_count += 1
                continue

            # Check if update is needed
            if current_position_size:
                try:
                    current_float = float(current_position_size)
                    # Only update if there's a significant difference (> 1%)
                    if abs(current_float - correct_position_size) / max(current_float, correct_position_size, 0.0001) < 0.01:
                        logger.info(f"Trade {trade_id}: position_size already correct ({current_position_size})")
                        skipped_count += 1
                        continue
                except (ValueError, TypeError):
                    pass

            logger.info(f"Trade {trade_id}: Updating position_size from {current_position_size} to {correct_position_size}")

            if not dry_run:
                supabase.table("trades").update({
                    'position_size': f"{correct_position_size:.8f}",
                    'updated_at': datetime.now(timezone.utc).isoformat()
                }).eq("id", trade_id).execute()
                logger.info(f"Trade {trade_id}: ✅ Updated position_size to {correct_position_size}")
            else:
                logger.info(f"Trade {trade_id}: [DRY RUN] Would update position_size to {correct_position_size}")

            updated_count += 1

        except Exception as e:
            logger.error(f"Trade {trade_id}: Error processing: {e}", exc_info=True)
            error_count += 1

    logger.info("=" * 60)
    logger.info("Backfill Summary:")
    logger.info(f"  Total trades processed: {len(trades)}")
    logger.info(f"  Updated: {updated_count}")
    logger.info(f"  Skipped: {skipped_count}")
    logger.info(f"  Errors: {error_count}")
    logger.info(f"  Mode: {'DRY RUN' if dry_run else 'LIVE UPDATE'}")
    logger.info("=" * 60)


async def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description='Backfill KuCoin position_size values')
    parser.add_argument('--dry-run', action='store_true', default=True,
                       help='Dry run mode (default: True)')
    parser.add_argument('--live', action='store_true',
                       help='Enable live updates (overrides --dry-run)')
    parser.add_argument('--limit', type=int, default=None,
                       help='Limit number of trades to process')
    parser.add_argument('--no-exchange', action='store_true',
                       help='Skip querying exchange (use only stored data)')

    args = parser.parse_args()

    dry_run = not args.live if args.live else args.dry_run

    # Initialize Supabase
    if not SUPABASE_URL or not SUPABASE_KEY:
        logger.error("SUPABASE_URL and SUPABASE_KEY must be set")
        sys.exit(1)
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

    # Initialize KuCoin exchange (optional)
    kucoin_exchange = None
    if not args.no_exchange:
        if not all([KUCOIN_API_KEY, KUCOIN_API_SECRET, KUCOIN_API_PASSPHRASE]):
            logger.warning("KuCoin API credentials not fully configured, skipping exchange queries")
        else:
            try:
                # Type checker: we've verified these are not None above
                assert KUCOIN_API_KEY is not None
                assert KUCOIN_API_SECRET is not None
                assert KUCOIN_API_PASSPHRASE is not None
                kucoin_exchange = KucoinExchange(
                    KUCOIN_API_KEY,
                    KUCOIN_API_SECRET,
                    KUCOIN_API_PASSPHRASE,
                    bool(KUCOIN_TESTNET) if KUCOIN_TESTNET is not None else False
                )
                await kucoin_exchange.initialize()
                logger.info("KuCoin exchange initialized")
            except Exception as e:
                logger.warning(f"Could not initialize KuCoin exchange: {e}")
                logger.warning("Will use only stored data")

    try:
        await backfill_kucoin_position_sizes(
            supabase,
            kucoin_exchange,
            dry_run=dry_run,
            limit=args.limit
        )
    finally:
        if kucoin_exchange:
            await kucoin_exchange.close()


if __name__ == "__main__":
    asyncio.run(main())

