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
        """Update trade with original exchange response and extract key fields."""
        try:
            # Get current trade data for validation
            current_trade = await self.get_trade_by_id(trade_id)

            updates = {
                # Store unified exchange_response for UI/notifications
                'exchange_response': original_response,
                'updated_at': datetime.now(timezone.utc).isoformat()
            }

            # Extract and store the exchange_order_id from the response
            if isinstance(original_response, dict) and 'order_id' in original_response:
                updates['exchange_order_id'] = str(original_response['order_id'])
                logger.info(f"Stored exchange_order_id {original_response['order_id']} for trade {trade_id}")
            elif isinstance(original_response, dict) and 'orderId' in original_response:
                # Handle direct Binance API response format
                updates['exchange_order_id'] = str(original_response['orderId'])
                logger.info(f"Stored exchange_order_id {original_response['orderId']} for trade {trade_id}")

            # Extract stop_loss_order_id if available
            if isinstance(original_response, dict) and 'stop_loss_order_id' in original_response:
                updates['stop_loss_order_id'] = str(original_response['stop_loss_order_id'])
                logger.info(f"Stored stop_loss_order_id {original_response['stop_loss_order_id']} for trade {trade_id}")

            # Extract entry price and position size from the response
            if isinstance(original_response, dict):
                # For MARKET orders, use avgPrice if available, otherwise use price
                entry_price = None
                if 'avgPrice' in original_response and original_response['avgPrice']:
                    entry_price = float(original_response['avgPrice'])
                elif 'price' in original_response and original_response['price']:
                    entry_price = float(original_response['price'])

                if entry_price and entry_price > 0:
                    updates['entry_price'] = entry_price
                    logger.info(f"Stored entry_price {entry_price} for trade {trade_id}")

                # Extract position size (quantity)
                position_size = None
                if 'executedQty' in original_response and original_response['executedQty']:
                    position_size = float(original_response['executedQty'])
                elif 'origQty' in original_response and original_response['origQty']:
                    position_size = float(original_response['origQty'])

                if position_size and position_size > 0:
                    updates['position_size'] = position_size
                    logger.info(f"Stored position_size {position_size} for trade {trade_id}")

            # Update trade status from "pending" to the status from response (set both status and order_status)
            if isinstance(original_response, dict) and 'status' in original_response:
                response_status = original_response['status']
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
