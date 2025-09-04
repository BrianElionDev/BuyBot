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

            response = self.supabase.table("trades").update(updates).eq("id", trade_id).execute()
            if response.data and len(response.data) > 0:
                logger.info(f"Updated trade {trade_id} successfully")
                return True
            return False
        except Exception as e:
            logger.error(f"Error updating trade {trade_id}: {e}")
            return False

    async def update_trade_with_original_response(self, trade_id: int, original_response: Dict[str, Any]) -> bool:
        """Update trade with original Binance response."""
        try:
            updates = {
                'binance_response': original_response,
                'updated_at': datetime.now(timezone.utc).isoformat()
            }
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

                binance_response = trade.get('binance_response', '')
                if binance_response and order_id in str(binance_response):
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
