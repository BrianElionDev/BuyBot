"""
Data Enrichment Pipeline

This module enriches trade data by querying exchanges for missing information
before closing trades, ensuring complete data (exit prices, PNL, order status).
"""

import logging
import json
from typing import Optional, Dict, Any
from datetime import datetime, timezone
from supabase import Client

from src.core.response_normalizer import normalize_exchange_response

logger = logging.getLogger(__name__)


async def enrich_trade_data_before_close(
    trade: Dict[str, Any],
    bot: Optional[Any],
    supabase: Client
) -> Dict[str, Any]:
    """
    Enrich trade data by querying exchange for missing information before closing.

    This function:
    1. Queries exchange for order status if order_status is PENDING
    2. Queries exchange trade history for exit price if missing
    3. Extracts PNL from exchange responses (all exchanges)
    4. Calculates PNL from entry/exit if missing

    Args:
        trade: Trade data from database
        bot: DiscordBot instance with exchange connections
        supabase: Supabase client

    Returns:
        Dictionary with enriched data to update
    """
    enriched_data: Dict[str, Any] = {}

    try:
        exchange_name = str(trade.get('exchange', '')).lower()
        trade_id = trade.get('id')

        # 1. Query order status if missing or PENDING
        if trade.get('order_status') in [None, 'PENDING', 'NEW']:
            order_status = await _query_order_status(trade, bot)
            if order_status:
                enriched_data['order_status'] = order_status

        # 2. Extract PNL from stored exchange responses (all exchanges)
        pnl_data = await _extract_pnl_from_responses(trade, exchange_name)
        if pnl_data:
            if 'pnl_usd' in pnl_data and pnl_data['pnl_usd']:
                current_pnl = trade.get('pnl_usd')
                if current_pnl is None or float(current_pnl) == 0:
                    enriched_data['pnl_usd'] = pnl_data['pnl_usd']
                    enriched_data['pnl_source'] = pnl_data.get('pnl_source', 'exchange_response')
                    if 'net_pnl' in pnl_data:
                        enriched_data['net_pnl'] = pnl_data['net_pnl']

        # 3. Query exit price from exchange if missing
        if not trade.get('exit_price') or float(trade.get('exit_price', 0)) == 0:
            exit_price = await _query_exit_price(trade, bot, exchange_name)
            if exit_price and exit_price > 0:
                enriched_data['exit_price'] = exit_price
                if exchange_name == 'binance':
                    enriched_data['binance_exit_price'] = exit_price
                elif exchange_name == 'kucoin':
                    enriched_data['exit_price'] = exit_price

        # 4. Calculate PNL from entry/exit if we have both but PNL is missing
        if (not enriched_data.get('pnl_usd') and
            trade.get('entry_price') and
            enriched_data.get('exit_price')):
            pnl = await _calculate_pnl_from_prices(
                trade,
                float(enriched_data['exit_price'])
            )
            if pnl is not None:
                enriched_data['pnl_usd'] = pnl
                enriched_data['pnl_source'] = 'calculated'

        # 5. Ensure exchange_response is stored if missing
        if not trade.get('exchange_response') and bot:
            exchange_response = await _fetch_exchange_response(trade, bot, exchange_name)
            if exchange_response:
                enriched_data['exchange_response'] = json.dumps(exchange_response)

        logger.info(f"Enriched trade {trade_id} with: {list(enriched_data.keys())}")

    except Exception as e:
        logger.error(f"Error enriching trade data for trade {trade.get('id')}: {e}")

    return enriched_data


async def _query_order_status(trade: Dict[str, Any], bot: Optional[Any]) -> Optional[str]:
    """Query exchange for order status."""
    if not bot:
        return None

    try:
        exchange_name = str(trade.get('exchange', '')).lower()
        order_id = trade.get('exchange_order_id') or trade.get('kucoin_order_id')

        if not order_id:
            return None

        symbol = trade.get('coin_symbol', '')
        if not symbol:
            return None

        if exchange_name == 'binance' and hasattr(bot, 'binance_exchange') and bot.binance_exchange:
            try:
                symbol_pair = f"{symbol}USDT"
                order_info = await bot.binance_exchange.get_order_status(symbol_pair, str(order_id))
                if order_info and isinstance(order_info, dict):
                    status = order_info.get('status', '')
                    if status:
                        return str(status).upper()
            except Exception as e:
                logger.warning(f"Could not query Binance order status: {e}")

        elif exchange_name == 'kucoin' and hasattr(bot, 'kucoin_exchange') and bot.kucoin_exchange:
            try:
                from src.exchange.kucoin.kucoin_symbol_converter import KucoinSymbolConverter
                symbol_converter = KucoinSymbolConverter()
                kucoin_symbol = symbol_converter.convert_bot_to_kucoin_futures(f"{symbol}-USDT")
                order_info = await bot.kucoin_exchange.get_order_status(kucoin_symbol, str(order_id))
                if order_info and isinstance(order_info, dict):
                    status = order_info.get('status', '')
                    if status:
                        return str(status).upper()
            except Exception as e:
                logger.warning(f"Could not query KuCoin order status: {e}")

    except Exception as e:
        logger.error(f"Error querying order status: {e}")

    return None


async def _extract_pnl_from_responses(trade: Dict[str, Any], exchange_name: str) -> Optional[Dict[str, Any]]:
    """
    Extract PNL from exchange responses (exchange-agnostic).

    Checks multiple fields:
    - Binance: 'rp' (realized profit)
    - KuCoin: 'realizedPnl', 'realized_pnl', 'pnl'
    - Generic: 'pnl', 'profit', 'realized_profit'
    """
    try:
        from discord_bot.utils.trade_retry_utils import safe_parse_exchange_response

        # Check exchange_response and sync_order_response
        for resp_field in ['exchange_response', 'sync_order_response', 'binance_response', 'kucoin_response']:
            resp_data = trade.get(resp_field)
            if not resp_data:
                continue

            parsed_resp = safe_parse_exchange_response(resp_data) if isinstance(resp_data, str) else resp_data
            if not isinstance(parsed_resp, dict):
                continue

            # Try multiple PNL field names (exchange-agnostic)
            pnl_value = None
            pnl_fields = []

            if exchange_name == 'binance':
                pnl_fields = ['rp', 'realizedPnl', 'realized_pnl', 'pnl']
            elif exchange_name == 'kucoin':
                pnl_fields = ['realizedPnl', 'realized_pnl', 'pnl', 'profit']
            else:
                pnl_fields = ['rp', 'realizedPnl', 'realized_pnl', 'pnl', 'profit', 'realized_profit']

            for field in pnl_fields:
                if field in parsed_resp:
                    try:
                        pnl_value = float(parsed_resp[field])
                        if pnl_value != 0:
                            return {
                                'pnl_usd': pnl_value,
                                'net_pnl': pnl_value,
                                'pnl_source': resp_field
                            }
                    except (ValueError, TypeError):
                        continue

            # Also check nested structures (e.g., tp_sl_orders)
            if 'tp_sl_orders' in parsed_resp and isinstance(parsed_resp['tp_sl_orders'], list):
                for order in parsed_resp['tp_sl_orders']:
                    if isinstance(order, dict):
                        for field in pnl_fields:
                            if field in order:
                                try:
                                    pnl_value = float(order[field])
                                    if pnl_value != 0:
                                        return {
                                            'pnl_usd': pnl_value,
                                            'net_pnl': pnl_value,
                                            'pnl_source': f"{resp_field}.tp_sl_orders"
                                        }
                                except (ValueError, TypeError):
                                    continue

    except Exception as e:
        logger.warning(f"Error extracting PNL from responses: {e}")

    return None


async def _query_exit_price(trade: Dict[str, Any], bot: Optional[Any], exchange_name: str) -> Optional[float]:
    """Query exchange trade history for exit price."""
    if not bot:
        return None

    try:
        order_id = trade.get('exchange_order_id') or trade.get('kucoin_order_id')
        symbol = trade.get('coin_symbol', '')

        if not order_id or not symbol:
            return None

        if exchange_name == 'binance' and hasattr(bot, 'binance_exchange') and bot.binance_exchange:
            try:
                symbol_pair = f"{symbol}USDT"
                order_info = await bot.binance_exchange.get_order_status(symbol_pair, str(order_id))
                if order_info and isinstance(order_info, dict):
                    avg_price = order_info.get('avgPrice') or order_info.get('avg_price')
                    if avg_price:
                        try:
                            return float(avg_price)
                        except (ValueError, TypeError):
                            pass
            except Exception as e:
                logger.warning(f"Could not query Binance exit price: {e}")

        elif exchange_name == 'kucoin' and hasattr(bot, 'kucoin_exchange') and bot.kucoin_exchange:
            try:
                from src.exchange.kucoin.kucoin_symbol_converter import KucoinSymbolConverter
                symbol_converter = KucoinSymbolConverter()
                kucoin_symbol = symbol_converter.convert_bot_to_kucoin_futures(f"{symbol}-USDT")

                # Try to get from order status first
                order_info = await bot.kucoin_exchange.get_order_status(kucoin_symbol, str(order_id))
                if order_info and isinstance(order_info, dict):
                    avg_price = order_info.get('avgPrice') or order_info.get('avg_price') or order_info.get('price')
                    if avg_price:
                        try:
                            return float(avg_price)
                        except (ValueError, TypeError):
                            pass

                # Fallback to trade history
                trade_history = await bot.kucoin_exchange.get_user_trades(symbol=kucoin_symbol)
                if trade_history:
                    matching_trades = [t for t in trade_history if str(t.get('orderId', '')) == str(order_id)]
                    if matching_trades:
                        last_trade = matching_trades[-1]
                        price = last_trade.get('price', 0)
                        if price:
                            try:
                                return float(price)
                            except (ValueError, TypeError):
                                pass
            except Exception as e:
                logger.warning(f"Could not query KuCoin exit price: {e}")

    except Exception as e:
        logger.error(f"Error querying exit price: {e}")

    return None


async def _calculate_pnl_from_prices(trade: Dict[str, Any], exit_price: float) -> Optional[float]:
    """Calculate PNL from entry and exit prices."""
    try:
        entry_price_str = trade.get('entry_price')
        if not entry_price_str:
            return None

        try:
            entry_price = float(entry_price_str)
        except (ValueError, TypeError):
            return None

        position_size_str = trade.get('position_size')
        if not position_size_str:
            return None

        try:
            position_size = float(position_size_str)
        except (ValueError, TypeError):
            return None

        if entry_price <= 0 or exit_price <= 0 or position_size <= 0:
            return None

        signal_type = str(trade.get('signal_type', 'LONG')).upper()

        if signal_type == 'LONG':
            pnl = (exit_price - entry_price) * position_size
        elif signal_type == 'SHORT':
            pnl = (entry_price - exit_price) * position_size
        else:
            return None

        return round(pnl, 2)

    except Exception as e:
        logger.warning(f"Error calculating PNL from prices: {e}")
        return None


async def _fetch_exchange_response(trade: Dict[str, Any], bot: Optional[Any], exchange_name: str) -> Optional[Dict[str, Any]]:
    """Fetch exchange response for order if missing."""
    if not bot:
        return None

    try:
        order_id = trade.get('exchange_order_id') or trade.get('kucoin_order_id')
        symbol = trade.get('coin_symbol', '')

        if not order_id or not symbol:
            return None

        if exchange_name == 'binance' and hasattr(bot, 'binance_exchange') and bot.binance_exchange:
            try:
                symbol_pair = f"{symbol}USDT"
                return await bot.binance_exchange.get_order_status(symbol_pair, str(order_id))
            except Exception as e:
                logger.warning(f"Could not fetch Binance response: {e}")

        elif exchange_name == 'kucoin' and hasattr(bot, 'kucoin_exchange') and bot.kucoin_exchange:
            try:
                from src.exchange.kucoin.kucoin_symbol_converter import KucoinSymbolConverter
                symbol_converter = KucoinSymbolConverter()
                kucoin_symbol = symbol_converter.convert_bot_to_kucoin_futures(f"{symbol}-USDT")
                return await bot.kucoin_exchange.get_order_status(kucoin_symbol, str(order_id))
            except Exception as e:
                logger.warning(f"Could not fetch KuCoin response: {e}")

    except Exception as e:
        logger.error(f"Error fetching exchange response: {e}")

    return None

