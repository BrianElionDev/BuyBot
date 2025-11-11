"""
Trade Database Operations

Handles all trade-related database operations for the Discord bot.
"""

import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone
from supabase import Client

from ..models.trade_models import TradeModel

logger = logging.getLogger(__name__)


class TradeOperations:
    """Handles trade-related database operations."""

    def __init__(self, supabase_client: Client):
        """Initialize with Supabase client."""
        self.supabase = supabase_client

    async def find_trade_by_discord_id(self, discord_id: str) -> Optional[Dict[str, Any]]:
        """Find a trade by Discord ID."""
        try:
            response = self.supabase.table("trades").select("*").eq("discord_id", discord_id).limit(1).execute()
            if response.data and len(response.data) > 0:
                return response.data[0]
            return None
        except Exception as e:
            logger.error(f"Error finding trade by discord_id {discord_id}: {e}")
            return None

    async def save_signal_to_db(self, trade_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Save a new trade signal to the database."""
        try:
            response = self.supabase.table("trades").insert(trade_data).execute()
            if response.data and len(response.data) > 0:
                logger.info(f"Saved trade signal to database: {response.data[0]['id']}")
                return response.data[0]
            return None
        except Exception as e:
            logger.error(f"Error saving trade signal to database: {e}")
            return None

    async def update_existing_trade(self, trade_id: int, updates: Dict[str, Any], binance_execution_time: Optional[str] = None) -> bool:
        """Update an existing trade record."""
        try:
            # Use Binance execution time if provided, otherwise use current time
            if binance_execution_time:
                updates['updated_at'] = binance_execution_time
            else:
                updates['updated_at'] = datetime.now(timezone.utc).isoformat()

            # Validate status consistency before updating
            from src.database.validators.status_validator import StatusValidator
            current_trade = await self.get_trade_by_id(trade_id)
            is_valid, error_msg, corrected_updates = StatusValidator.validate_trade_update(updates, current_trade)

            if not is_valid:
                logger.error(f"Status validation failed for trade {trade_id}: {error_msg}")
                return False

            # Use corrected updates if validation made changes
            if corrected_updates != updates:
                logger.info(f"Status validation corrected updates for trade {trade_id}")
                updates = corrected_updates

            response = self.supabase.table("trades").update(updates).eq("id", trade_id).execute()
            if response.data and len(response.data) > 0:
                logger.info(f"Updated trade {trade_id} successfully")
                return True
            return False
        except Exception as e:
            logger.error(f"Error updating trade {trade_id}: {e}")
            return False

    async def update_trade_with_original_response(self, trade_id: int, original_response: Dict[str, Any]) -> bool:
        """
        Update trade with original exchange response and extract ALL available fields.

        This method extracts and stores ALL data from exchange responses as-is, including:
        - Order details (orderId, status, prices, quantities)
        - Position size and entry price
        - Commission and fees (if available in response)
        - PnL data (if available)
        - All other fields returned by the exchange
        """
        try:
            # Get current trade data for validation
            current_trade = await self.get_trade_by_id(trade_id)
            exchange_name = str(current_trade.get('exchange') or '').lower()

            # Store RAW response as-is (no normalization for storage)
            raw_response = original_response if isinstance(original_response, dict) else {}

            # Normalize response for field extraction
            try:
                from src.core.response_normalizer import normalize_exchange_response
                normalized = normalize_exchange_response(exchange_name, original_response)
            except Exception:
                normalized = raw_response

            # Store complete raw response as-is (JSON string for database)
            import json
            updates = {
                # Store COMPLETE raw exchange response as-is (no editing)
                'exchange_response': json.dumps(raw_response) if raw_response else None,
                'updated_at': datetime.now(timezone.utc).isoformat()
            }

            # Extract and store the exchange_order_id from the response
            if isinstance(normalized, dict) and 'order_id' in normalized:
                updates['exchange_order_id'] = str(normalized['order_id'])
                logger.info(f"Stored exchange_order_id {original_response['order_id']} for trade {trade_id}")
            elif isinstance(normalized, dict) and 'orderId' in normalized:
                # Handle direct Binance API response format
                updates['exchange_order_id'] = str(normalized['orderId'])
                logger.info(f"Stored exchange_order_id {normalized['orderId']} for trade {trade_id}")

            # Extract stop_loss_order_id if available
            if isinstance(original_response, dict) and 'stop_loss_order_id' in original_response:
                updates['stop_loss_order_id'] = str(original_response['stop_loss_order_id'])
                logger.info(f"Stored stop_loss_order_id {original_response['stop_loss_order_id']} for trade {trade_id}")

            # Extract entry price and position size from the response
            if isinstance(normalized, dict):
                entry_price = None
                position_size = None

                # Check for KuCoin execution details (from post-order status check)
                if 'actualEntryPrice' in normalized and normalized['actualEntryPrice']:
                    entry_price = float(normalized['actualEntryPrice'])
                    logger.info(f"Using KuCoin actual entry price: {entry_price}")
                elif 'filledSize' in normalized and 'filledValue' in normalized:
                    filled_size = float(normalized.get('filledSize', 0))
                    filled_value = float(normalized.get('filledValue', 0))
                    if filled_size > 0 and filled_value > 0:
                        entry_price = filled_value / filled_size
                        logger.info(f"Calculated KuCoin entry price from execution: {entry_price}")

                # For Binance orders, use avgPrice if available, otherwise use price
                if not entry_price:
                    if 'avgPrice' in normalized and normalized['avgPrice']:
                        entry_price = float(normalized['avgPrice'])
                    elif 'price' in normalized and normalized['price']:
                        entry_price = float(normalized['price'])

                if entry_price and entry_price > 0:
                    updates['entry_price'] = entry_price
                    logger.info(f"Stored entry_price {entry_price} for trade {trade_id}")

                position_size = None

                # Priority: executedQty (already asset quantity) > origQty (asset quantity) > filledSize (needs conversion)
                if 'executedQty' in normalized and normalized['executedQty']:
                    position_size = float(normalized['executedQty'])
                    logger.info(f"Using executedQty as position_size (asset quantity): {position_size}")
                elif 'origQty' in normalized and normalized['origQty']:
                    position_size = float(normalized['origQty'])
                    logger.info(f"Using origQty as position_size (asset quantity): {position_size}")
                elif 'filledSize' in normalized and normalized['filledSize']:
                    filled_size_contracts = float(normalized['filledSize'])

                    # Get contract multiplier from response or execution details
                    contract_multiplier = 1
                    if 'contract_multiplier' in normalized:
                        contract_multiplier = int(normalized['contract_multiplier'])
                        logger.info(f"Using contract_multiplier from response: {contract_multiplier}")
                    elif 'executionDetails' in normalized and normalized.get('executionDetails'):
                        execution_details = normalized['executionDetails']
                        if isinstance(execution_details, dict) and 'contract_multiplier' in execution_details:
                            contract_multiplier = int(execution_details['contract_multiplier'])
                        elif hasattr(execution_details, 'contract_multiplier'):
                            contract_multiplier = int(getattr(execution_details, 'contract_multiplier', 1))
                        logger.info(f"Using contract_multiplier from executionDetails: {contract_multiplier}")

                    # Convert contract size to asset quantity
                    if contract_multiplier > 1:
                        position_size = filled_size_contracts * contract_multiplier
                        logger.info(f"Converted KuCoin contracts to assets: {filled_size_contracts} contracts × {contract_multiplier} = {position_size} assets")
                    else:
                        # Fallback: assume it's already asset quantity if no multiplier
                        position_size = filled_size_contracts
                        logger.info(f"Using filledSize as position_size (no multiplier found, assuming asset quantity): {position_size}")

                if position_size and position_size > 0:
                    updates['position_size'] = position_size
                    logger.info(f"Stored position_size {position_size} for trade {trade_id}")

                # Store KuCoin-specific execution details
                if 'filledSize' in normalized or 'filledValue' in normalized:
                    if 'orderStatus' in normalized:
                        updates['order_status'] = normalized['orderStatus']

                    # Store execution details in sync_order_response for future sync operations
                    if 'executionDetails' in normalized:
                        updates['sync_order_response'] = normalized['executionDetails']
                        logger.info(f"Stored execution details in sync_order_response for trade {trade_id}")

                    logger.info(f"Stored KuCoin execution details for trade {trade_id}")

            # Update trade status from "pending" to the status from response (set both status and order_status)
            if isinstance(normalized, dict) and 'status' in normalized:
                response_status = normalized['status']
                # Use unified status mapping
                from src.core.status_manager import StatusManager
                order_status, position_status = StatusManager.map_exchange_to_internal(response_status, position_size or 0)
                updates['status'] = position_status
                updates['order_status'] = order_status
                logger.info(f"Updated trade {trade_id} status to {position_status} and order_status to {order_status}")

            # Extract position size from tp_sl_orders if available
            if isinstance(original_response, dict) and 'tp_sl_orders' in original_response:
                tp_sl_orders = original_response['tp_sl_orders']
                if isinstance(tp_sl_orders, list) and len(tp_sl_orders) > 0:
                    # Get position size from the first TP/SL order (they should all have the same size)
                    first_order = tp_sl_orders[0]
                    if 'origQty' in first_order:
                        try:
                            position_size = float(first_order['origQty'])
                            updates['position_size'] = position_size
                            logger.info(f"Stored position_size {position_size} for trade {trade_id}")
                        except (ValueError, TypeError):
                            logger.warning(f"Could not parse position_size from tp_sl_orders for trade {trade_id}")

            # COMPREHENSIVE FIELD EXTRACTION: Extract ALL available fields from exchange responses
            # This ensures we capture commission, fees, PnL, and all other data as-is from the exchange

            # Extract commission/fees from Binance response
            if exchange_name == 'binance' and isinstance(raw_response, dict):
                # Binance may include commission in order response or need separate API call
                # Check for commission in raw response
                if 'commission' in raw_response:
                    try:
                        commission = float(raw_response['commission'])
                        if commission != 0:
                            updates['commission'] = commission
                            logger.info(f"Extracted commission {commission} from Binance response for trade {trade_id}")
                    except (ValueError, TypeError):
                        pass

                # Binance order response may include: cumQuote (cumulative quote), cumQty (cumulative quantity)
                # These can be used to calculate fees if commission not directly available
                if 'cumQuote' in raw_response and 'cumQty' in raw_response:
                    try:
                        cum_quote = float(raw_response['cumQuote'])
                        # Store for potential fee calculation
                        if 'commission' not in updates:
                            logger.debug(f"Binance cumQuote available: {cum_quote} for trade {trade_id}")
                    except (ValueError, TypeError):
                        pass

            # Extract commission/fees from KuCoin response
            if exchange_name == 'kucoin' and isinstance(raw_response, dict):
                # KuCoin may include fee information in order response
                if 'fee' in raw_response:
                    try:
                        fee = float(raw_response['fee'])
                        if fee != 0:
                            updates['commission'] = fee
                            logger.info(f"Extracted commission {fee} from KuCoin response for trade {trade_id}")
                    except (ValueError, TypeError):
                        pass

                # KuCoin execution details may include fee information
                if 'executionDetails' in normalized and isinstance(normalized['executionDetails'], dict):
                    exec_details = normalized['executionDetails']
                    if 'fee' in exec_details:
                        try:
                            fee = float(exec_details['fee'])
                            if fee != 0:
                                updates['commission'] = fee
                                logger.info(f"Extracted commission {fee} from KuCoin execution details for trade {trade_id}")
                        except (ValueError, TypeError):
                            pass

            # Extract exit price if position is closed
            if isinstance(normalized, dict):
                # Check if this is a closing order (reduce_only or closePosition)
                is_close = raw_response.get('reduceOnly', False) or raw_response.get('closePosition', False)
                if is_close and 'avgPrice' in normalized:
                    try:
                        exit_price = float(normalized['avgPrice'])
                        if exit_price > 0:
                            updates['exit_price'] = exit_price
                            logger.info(f"Extracted exit_price {exit_price} from closing order for trade {trade_id}")
                    except (ValueError, TypeError):
                        pass

            # Store sync_order_response with complete normalized data for future sync operations
            if normalized:
                updates['sync_order_response'] = json.dumps(normalized)
                logger.debug(f"Stored normalized response in sync_order_response for trade {trade_id}")

            return await self.update_existing_trade(trade_id, updates)
        except Exception as e:
            logger.error(f"Error updating trade {trade_id} with original response: {e}")
            return False

    async def get_trade_by_id(self, trade_id: int) -> Optional[Dict[str, Any]]:
        """Get a trade by ID."""
        try:
            response = self.supabase.table("trades").select("*").eq("id", trade_id).limit(1).execute()
            if response.data and len(response.data) > 0:
                return response.data[0]
            return None
        except Exception as e:
            logger.error(f"Error getting trade {trade_id}: {e}")
            return None

    async def get_open_trades(self) -> List[Dict[str, Any]]:
        """Get all open trades."""
        try:
            response = self.supabase.table("trades").select("*").in_("status", ["OPEN", "PARTIALLY_CLOSED"]).execute()
            return response.data or []
        except Exception as e:
            logger.error(f"Error getting open trades: {e}")
            return []

    async def get_trades_by_trader(self, trader: str) -> List[Dict[str, Any]]:
        """Get all trades by a specific trader."""
        try:
            response = self.supabase.table("trades").select("*").eq("trader", trader).order("created_at", desc=True).execute()
            return response.data or []
        except Exception as e:
            logger.error(f"Error getting trades for trader {trader}: {e}")
            return []

    async def get_trades_by_coin_symbol(self, coin_symbol: str) -> List[Dict[str, Any]]:
        """Get all trades for a specific coin symbol."""
        try:
            response = self.supabase.table("trades").select("*").eq("coin_symbol", coin_symbol).order("created_at", desc=True).execute()
            return response.data or []
        except Exception as e:
            logger.error(f"Error getting trades for coin {coin_symbol}: {e}")
            return []

    async def get_trades_by_status(self, status: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Get all trades with a specific status."""
        try:
            response = self.supabase.table("trades").select("*").eq("status", status).order("created_at", desc=True).limit(limit).execute()
            return response.data or []
        except Exception as e:
            logger.error(f"Error getting trades with status {status}: {e}")
            return []

    async def find_trade_by_order_id(self, order_id: str) -> Optional[Dict[str, Any]]:
        """Find a trade by Binance order ID."""
        try:
            try:
                response = self.supabase.table("trades").select("*").eq("exchange_order_id", order_id).limit(1).execute()
                if response.data and len(response.data) > 0:
                    return response.data[0]
            except Exception:
                pass

            response = self.supabase.table("trades").select("*").order("created_at", desc=True).limit(100).execute()

            for trade in response.data or []:
                sync_response = trade.get('sync_order_response', '')
                if sync_response and order_id in str(sync_response):
                    return trade

                ex_resp = trade.get('exchange_response') or trade.get('binance_response', '')
                if ex_resp and order_id in str(ex_resp):
                    return trade

            return None

        except Exception as e:
            logger.error(f"Error finding trade by order ID {order_id}: {e}")
            return None

    async def delete_trade(self, trade_id: int) -> bool:
        """Delete a trade record."""
        try:
            response = self.supabase.table("trades").delete().eq("id", trade_id).execute()
            if response.data:
                logger.info(f"Deleted trade {trade_id}")
                return True
            return False
        except Exception as e:
            logger.error(f"Error deleting trade {trade_id}: {e}")
            return False

    async def update_trade_status(self, trade_id: int, status: str) -> bool:
        """Update trade status."""
        try:
            updates = {
                'status': status,
                'updated_at': datetime.now(timezone.utc).isoformat()
            }
            if status in ['CLOSED', 'CANCELLED']:
                updates['closed_at'] = datetime.now(timezone.utc).isoformat()

            return await self.update_existing_trade(trade_id, updates)
        except Exception as e:
            logger.error(f"Error updating trade {trade_id} status to {status}: {e}")
            return False

    async def update_trade_pnl(self, trade_id: int, pnl_usd: float, exit_price: float) -> bool:
        """Update trade PnL and exit price."""
        try:
            updates = {
                'pnl_usd': pnl_usd,
                'exit_price': exit_price,
                'updated_at': datetime.now(timezone.utc).isoformat()
            }
            return await self.update_existing_trade(trade_id, updates)
        except Exception as e:
            logger.error(f"Error updating trade {trade_id} PnL: {e}")
            return False

    async def enrich_trade_with_exchange_data(self, trade_id: int) -> bool:
        """
        Enrich trade with additional data from exchange APIs.

        Fetches and stores:
        - Commission from trade history/income
        - Funding fees from income history
        - PnL from position data
        - Exit price from closing orders

        This method should be called after order execution to ensure all data is captured.
        """
        try:
            trade = await self.get_trade_by_id(trade_id)
            if not trade:
                logger.error(f"Trade {trade_id} not found")
                return False

            exchange_name = str(trade.get('exchange') or '').lower()
            coin_symbol = trade.get('coin_symbol')
            exchange_order_id = trade.get('exchange_order_id')

            if not exchange_order_id or not coin_symbol:
                logger.warning(f"Cannot enrich trade {trade_id}: missing exchange_order_id or coin_symbol")
                return False

            updates = {}

            # Fetch commission and funding fees from exchange APIs
            try:
                if exchange_name == 'binance':
                    await self._enrich_binance_data(trade, updates)
                elif exchange_name == 'kucoin':
                    await self._enrich_kucoin_data(trade, updates)
            except Exception as e:
                logger.warning(f"Error enriching exchange data for trade {trade_id}: {e}")

            # Fetch position data for PnL calculation
            try:
                await self._enrich_position_data(trade, updates)
            except Exception as e:
                logger.warning(f"Error enriching position data for trade {trade_id}: {e}")

            if updates:
                updates['updated_at'] = datetime.now(timezone.utc).isoformat()
                return await self.update_existing_trade(trade_id, updates)

            return True
        except Exception as e:
            logger.error(f"Error enriching trade {trade_id} with exchange data: {e}")
            return False

    async def _enrich_binance_data(self, trade: Dict[str, Any], updates: Dict[str, Any]) -> None:
        """Enrich trade with Binance-specific data (commission, funding fees)."""
        try:
            from src.exchange.binance.binance_exchange import BinanceExchange
            from config import settings

            exchange = BinanceExchange(
                api_key=settings.BINANCE_API_KEY or "",
                api_secret=settings.BINANCE_API_SECRET or "",
                is_testnet=False
            )
            await exchange.initialize()

            coin_symbol = trade.get('coin_symbol')
            trading_pair = exchange.get_futures_trading_pair(coin_symbol) if hasattr(exchange, 'get_futures_trading_pair') else f"{coin_symbol.upper()}USDT"
            exchange_order_id = trade.get('exchange_order_id')

            # Fetch order details which may include commission
            if exchange_order_id and hasattr(exchange, 'get_order_status'):
                order_status = await exchange.get_order_status(trading_pair, exchange_order_id)
                if order_status and isinstance(order_status, dict):
                    # Binance order status may include commission
                    if 'commission' in order_status:
                        try:
                            commission = float(order_status['commission'])
                            if commission != 0:
                                updates['commission'] = commission
                                logger.info(f"Fetched Binance commission {commission} for trade {trade.get('id')}")
                        except (ValueError, TypeError):
                            pass

            # Fetch income history for funding fees (last 24 hours)
            try:
                if hasattr(exchange.client, 'futures_income'):
                    from datetime import timedelta
                    end_time = int(datetime.now(timezone.utc).timestamp() * 1000)
                    start_time = int((datetime.now(timezone.utc) - timedelta(days=1)).timestamp() * 1000)

                    income_history = await exchange.client.futures_income(
                        symbol=trading_pair,
                        incomeType='FUNDING_FEE',
                        startTime=start_time,
                        endTime=end_time
                    )

                    if income_history and isinstance(income_history, list):
                        # Sum funding fees for this symbol
                        total_funding = sum(float(item.get('income', 0)) for item in income_history if item.get('symbol') == trading_pair)
                        if total_funding != 0:
                            updates['funding_fee'] = total_funding
                            logger.info(f"Fetched Binance funding fee {total_funding} for trade {trade.get('id')}")
            except Exception as e:
                logger.debug(f"Could not fetch Binance funding fees: {e}")

            await exchange.close()
        except Exception as e:
            logger.warning(f"Error enriching Binance data: {e}")

    async def _enrich_kucoin_data(self, trade: Dict[str, Any], updates: Dict[str, Any]) -> None:
        """Enrich trade with KuCoin-specific data (commission, funding fees)."""
        try:
            from src.exchange.kucoin.kucoin_exchange import KucoinExchange
            from config import settings

            exchange = KucoinExchange(
                api_key=settings.KUCOIN_API_KEY or "",
                api_secret=settings.KUCOIN_API_SECRET or "",
                api_passphrase=settings.KUCOIN_API_PASSPHRASE or "",
                is_testnet=False
            )
            await exchange.initialize()

            coin_symbol = trade.get('coin_symbol')
            from src.exchange.kucoin.kucoin_symbol_converter import symbol_converter
            trading_pair = f"{coin_symbol.upper()}-USDT"
            kucoin_symbol = symbol_converter.convert_bot_to_kucoin_futures(trading_pair)
            exchange_order_id = trade.get('exchange_order_id')

            # Fetch order details which may include commission
            if exchange_order_id and hasattr(exchange, 'get_order_status'):
                order_status = await exchange.get_order_status(kucoin_symbol, exchange_order_id)
                if order_status and isinstance(order_status, dict):
                    # KuCoin order status may include fee
                    if 'fee' in order_status:
                        try:
                            fee = float(order_status['fee'])
                            if fee != 0:
                                updates['commission'] = fee
                                logger.info(f"Fetched KuCoin commission {fee} for trade {trade.get('id')}")
                        except (ValueError, TypeError):
                            pass

            # Fetch income history for funding fees
            try:
                if hasattr(exchange, 'get_income_history'):
                    from datetime import timedelta
                    end_time = int(datetime.now(timezone.utc).timestamp() * 1000)
                    start_time = int((datetime.now(timezone.utc) - timedelta(days=1)).timestamp() * 1000)

                    income_history = await exchange.get_income_history(
                        symbol=kucoin_symbol,
                        income_type='FUNDING_FEE',
                        start_time=start_time,
                        end_time=end_time
                    )

                    if income_history and isinstance(income_history, list):
                        # Sum funding fees for this symbol
                        total_funding = sum(float(item.get('amount', 0)) for item in income_history if item.get('symbol') == kucoin_symbol)
                        if total_funding != 0:
                            updates['funding_fee'] = total_funding
                            logger.info(f"Fetched KuCoin funding fee {total_funding} for trade {trade.get('id')}")
            except Exception as e:
                logger.debug(f"Could not fetch KuCoin funding fees: {e}")

            await exchange.close()
        except Exception as e:
            logger.warning(f"Error enriching KuCoin data: {e}")

    async def _enrich_position_data(self, trade: Dict[str, Any], updates: Dict[str, Any]) -> None:
        """Enrich trade with position data (PnL, position size)."""
        try:
            exchange_name = str(trade.get('exchange') or '').lower()
            coin_symbol = trade.get('coin_symbol')

            if not coin_symbol:
                return

            if exchange_name == 'binance':
                from src.exchange.binance.binance_exchange import BinanceExchange
                from config import settings

                exchange = BinanceExchange(
                    api_key=settings.BINANCE_API_KEY or "",
                    api_secret=settings.BINANCE_API_SECRET or "",
                    is_testnet=False
                )
                await exchange.initialize()

                trading_pair = exchange.get_futures_trading_pair(coin_symbol) if hasattr(exchange, 'get_futures_trading_pair') else f"{coin_symbol.upper()}USDT"
                positions = await exchange.get_futures_position_information()

                for position in positions:
                    if position.get('symbol') == trading_pair:
                        position_amt = float(position.get('positionAmt', 0))
                        if abs(position_amt) > 0:
                            # Position is still open
                            unrealized_pnl = float(position.get('unRealizedProfit', 0))
                            entry_price = float(position.get('entryPrice', 0))

                            if not updates.get('position_size') and abs(position_amt) > 0:
                                updates['position_size'] = abs(position_amt)

                            if not updates.get('entry_price') and entry_price > 0:
                                updates['entry_price'] = entry_price

                            # Store unrealized PnL (will be realized when position closes)
                            if unrealized_pnl != 0:
                                updates['pnl_usd'] = unrealized_pnl
                                logger.info(f"Fetched Binance unrealized PnL {unrealized_pnl} for trade {trade.get('id')}")
                        else:
                            # Position is closed - calculate realized PnL
                            # This would need to be fetched from trade history
                            logger.debug(f"Position {trading_pair} is closed, PnL should be calculated from trade history")
                        break

                await exchange.close()

            elif exchange_name == 'kucoin':
                from src.exchange.kucoin.kucoin_exchange import KucoinExchange
                from config import settings

                exchange = KucoinExchange(
                    api_key=settings.KUCOIN_API_KEY or "",
                    api_secret=settings.KUCOIN_API_SECRET or "",
                    api_passphrase=settings.KUCOIN_API_PASSPHRASE or "",
                    is_testnet=False
                )
                await exchange.initialize()

                from src.exchange.kucoin.kucoin_symbol_converter import symbol_converter
                trading_pair = f"{coin_symbol.upper()}-USDT"
                kucoin_symbol = symbol_converter.convert_bot_to_kucoin_futures(trading_pair)
                positions = await exchange.get_futures_position_information()

                for position in positions:
                    if position.get('symbol') == kucoin_symbol:
                        position_size = float(position.get('size', 0))
                        if position_size > 0:
                            # Position is still open
                            unrealized_pnl = float(position.get('unrealizedPnl', 0))
                            entry_price = float(position.get('entryPrice', 0))

                            if not updates.get('position_size') and position_size > 0:
                                updates['position_size'] = position_size

                            if not updates.get('entry_price') and entry_price > 0:
                                updates['entry_price'] = entry_price

                            # Store unrealized PnL
                            if unrealized_pnl != 0:
                                updates['pnl_usd'] = unrealized_pnl
                                logger.info(f"Fetched KuCoin unrealized PnL {unrealized_pnl} for trade {trade.get('id')}")
                        else:
                            # Position is closed
                            logger.debug(f"Position {kucoin_symbol} is closed, PnL should be calculated from trade history")
                        break

                await exchange.close()
        except Exception as e:
            logger.warning(f"Error enriching position data: {e}")
