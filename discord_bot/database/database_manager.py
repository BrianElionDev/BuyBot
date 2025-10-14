"""
Database Manager

Main database manager that orchestrates all database operations for the Discord bot.
"""

import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone
from supabase import Client

from .operations.trade_operations import TradeOperations
from .operations.alert_operations import AlertOperations
from .utils.database_utils import DatabaseUtils

logger = logging.getLogger(__name__)


class DatabaseManager:
    """Main database manager for Discord bot operations."""

    def __init__(self, supabase_client: Client):
        """Initialize with Supabase client and operation classes."""
        self.supabase = supabase_client
        self.trade_ops = TradeOperations(supabase_client)
        self.alert_ops = AlertOperations(supabase_client)
        self.utils = DatabaseUtils()

        logger.info("DatabaseManager initialized successfully")

    # Trade Operations (delegated to TradeOperations)

    async def find_trade_by_discord_id(self, discord_id: str) -> Optional[Dict[str, Any]]:
        """Find a trade by Discord ID."""
        return await self.trade_ops.find_trade_by_discord_id(discord_id)

    async def save_signal_to_db(self, trade_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Save a new trade signal to the database."""
        # Validate data before saving
        if not self.utils.validate_trade_data(trade_data):
            logger.error("Invalid trade data provided")
            return None

        # Sanitize data for storage
        sanitized_data = self.utils.sanitize_data(trade_data)
        return await self.trade_ops.save_signal_to_db(sanitized_data)

    async def update_existing_trade(self, trade_id: int, updates: Dict[str, Any], binance_execution_time: Optional[str] = None) -> bool:
        """Update an existing trade record."""
        # Sanitize updates for storage
        sanitized_updates = self.utils.sanitize_data(updates)
        return await self.trade_ops.update_existing_trade(trade_id, sanitized_updates, binance_execution_time)

    async def update_trade_with_original_response(self, trade_id: int, original_response: Dict[str, Any]) -> bool:
        """Update trade with original Binance response."""
        return await self.trade_ops.update_trade_with_original_response(trade_id, original_response)

    async def get_trade_by_id(self, trade_id: int) -> Optional[Dict[str, Any]]:
        """Get a trade by ID."""
        trade_data = await self.trade_ops.get_trade_by_id(trade_id)
        if trade_data:
            return self.utils.desanitize_data(trade_data)
        return None

    async def find_trade_by_order_id(self, order_id: str) -> Optional[Dict[str, Any]]:
        """Find a trade by Binance order ID."""
        return await self.trade_ops.find_trade_by_order_id(order_id)

    async def get_open_trades(self) -> List[Dict[str, Any]]:
        """Get all open trades."""
        trades = await self.trade_ops.get_open_trades()
        return [self.utils.desanitize_data(trade) for trade in trades]

    async def get_trades_by_trader(self, trader: str) -> List[Dict[str, Any]]:
        """Get all trades by a specific trader."""
        trades = await self.trade_ops.get_trades_by_trader(trader)
        return [self.utils.desanitize_data(trade) for trade in trades]

    async def get_trades_by_coin_symbol(self, coin_symbol: str) -> List[Dict[str, Any]]:
        """Get all trades for a specific coin symbol."""
        trades = await self.trade_ops.get_trades_by_coin_symbol(coin_symbol)
        return [self.utils.desanitize_data(trade) for trade in trades]

    async def delete_trade(self, trade_id: int) -> bool:
        """Delete a trade record."""
        return await self.trade_ops.delete_trade(trade_id)

    async def update_trade_status(self, trade_id: int, status: str) -> bool:
        """Update trade status."""
        return await self.trade_ops.update_trade_status(trade_id, status)

    async def update_trade_pnl(self, trade_id: int, pnl_usd: float, exit_price: float) -> bool:
        """Update trade PnL and exit price."""
        return await self.trade_ops.update_trade_pnl(trade_id, pnl_usd, exit_price)

    async def update_trade_failure(self, trade_id: int, error_message: str, binance_response: str = "", sync_issues: Optional[list] = None) -> bool:
        """
        Comprehensive method to update trade when it fails.
        This ensures all error information is properly stored for debugging and sync scripts.
        """
        try:
            updates = {
                'status': 'FAILED',
                'binance_response': binance_response,
                'sync_error_count': 1,
                'manual_verification_needed': True,
                'updated_at': datetime.now(timezone.utc).isoformat()
            }

            if sync_issues is not None:
                updates['sync_issues'] = sync_issues
            else:
                updates['sync_issues'] = [f'Trade execution failed: {error_message}']

            # Update the trade
            success = await self.trade_ops.update_existing_trade(trade_id, updates)

            if success:
                logger.info(f"✅ Trade {trade_id} failure details updated successfully")
            else:
                logger.error(f"❌ Failed to update trade {trade_id} failure details")

            return success

        except Exception as e:
            logger.error(f"Error updating trade {trade_id} failure details: {e}")
            return False

    # Alert Operations (delegated to AlertOperations)

    async def save_alert_to_database(self, alert_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Save a new alert to the database."""
        # Validate data before saving
        if not self.utils.validate_alert_data(alert_data):
            logger.error("Invalid alert data provided")
            return None

        # Sanitize data for storage
        sanitized_data = self.utils.sanitize_data(alert_data)
        return await self.alert_ops.save_alert_to_database(sanitized_data)

    async def update_existing_alert(self, alert_id: int, updates: Dict[str, Any]) -> bool:
        """Update an existing alert record."""
        # Sanitize updates for storage
        sanitized_updates = self.utils.sanitize_data(updates)
        return await self.alert_ops.update_existing_alert(alert_id, sanitized_updates)

    async def update_alert_by_discord_id_or_trade(self, discord_id: str, trade: Optional[str], updates: Dict[str, Any]) -> bool:
        """Update alert by Discord ID or trade reference."""
        # Sanitize updates for storage
        sanitized_updates = self.utils.sanitize_data(updates)
        return await self.alert_ops.update_alert_by_discord_id_or_trade(discord_id, trade, sanitized_updates)

    async def get_alert_by_id(self, alert_id: int) -> Optional[Dict[str, Any]]:
        """Get an alert by ID."""
        alert_data = await self.alert_ops.get_alert_by_id(alert_id)
        if alert_data:
            return self.utils.desanitize_data(alert_data)
        return None

    async def get_alert_by_discord_id(self, discord_id: str) -> Optional[Dict[str, Any]]:
        """Get an alert by Discord ID."""
        alert_data = await self.alert_ops.get_alert_by_discord_id(discord_id)
        if alert_data:
            return self.utils.desanitize_data(alert_data)
        return None

    async def get_alerts_by_trade(self, trade: str) -> List[Dict[str, Any]]:
        """Get all alerts for a specific trade."""
        alerts = await self.alert_ops.get_alerts_by_trade(trade)
        return [self.utils.desanitize_data(alert) for alert in alerts]

    async def get_alerts_by_trader(self, trader: str) -> List[Dict[str, Any]]:
        """Get all alerts by a specific trader."""
        alerts = await self.alert_ops.get_alerts_by_trader(trader)
        return [self.utils.desanitize_data(alert) for alert in alerts]

    async def get_alerts_by_status(self, status: str) -> List[Dict[str, Any]]:
        """Get all alerts with a specific status."""
        alerts = await self.alert_ops.get_alerts_by_status(status)
        return [self.utils.desanitize_data(alert) for alert in alerts]

    async def delete_alert(self, alert_id: int) -> bool:
        """Delete an alert record."""
        return await self.alert_ops.delete_alert(alert_id)

    async def update_alert_status(self, alert_id: int, status: str) -> bool:
        """Update alert status."""
        return await self.alert_ops.update_alert_status(alert_id, status)

    async def check_duplicate_alert(self, alert_hash: str) -> bool:
        """Check if an alert hash already exists."""
        return await self.alert_ops.check_duplicate_alert(alert_hash)

    async def store_alert_hash(self, alert_hash: str) -> bool:
        """Store an alert hash to prevent duplicates."""
        return await self.alert_ops.store_alert_hash(alert_hash)

    # Utility Methods

    def generate_alert_hash(self, discord_id: str, content: str) -> str:
        """Generate a hash for alert deduplication."""
        return self.utils.generate_alert_hash(discord_id, content)

    def get_current_timestamp(self) -> str:
        """Get current timestamp in ISO format."""
        return self.utils.get_current_timestamp()

    def create_update_dict(self, **kwargs) -> Dict[str, Any]:
        """Create an update dictionary with current timestamp."""
        return self.utils.create_update_dict(**kwargs)

    # Health Check

    # Transaction History Operations

    async def get_last_transaction_sync_time(self) -> int:
        """Get the timestamp of the last synced transaction to avoid duplicates."""
        try:
            # Get the most recent transaction from the database
            response = self.supabase.table("transaction_history").select("time").order("time", desc=True).limit(1).execute()

            if response.data and len(response.data) > 0:
                last_time = response.data[0].get('time', 0)
                logger.info(f"Last sync time from database: {last_time}")

                # Handle timestampz format (ISO string timestamps)
                if isinstance(last_time, str):
                    try:
                        from datetime import datetime
                        # Parse ISO timestamp and convert to milliseconds
                        dt = datetime.fromisoformat(last_time.replace('Z', '+00:00'))
                        return int(dt.timestamp() * 1000)
                    except Exception as e:
                        logger.error(f"Error parsing timestamp {last_time}: {e}")
                        return 0
                else:
                    # Handle integer timestamps (legacy support)
                    return int(last_time) if last_time else 0
            else:
                # If no transactions exist, start from 30 days ago
                from datetime import timedelta
                default_time = int((datetime.now(timezone.utc) - timedelta(days=30)).timestamp() * 1000)
                logger.info(f"No existing transactions, starting from: {default_time}")
                return default_time

        except Exception as e:
            logger.error(f"Error getting last sync time: {e}")
            # Default to 30 days ago
            from datetime import timedelta
            default_time = int((datetime.now(timezone.utc) - timedelta(days=30)).timestamp() * 1000)
            return default_time

    async def get_transaction_history(self, symbol: str = "", start_time: int = 0, end_time: int = 0,
                                    income_type: str = "", limit: int = 1000) -> List[Dict[str, Any]]:
        """Get transaction history with optional filtering."""
        try:
            query = self.supabase.table("transaction_history").select("*")

            if symbol:
                query = query.eq("symbol", symbol)
            if start_time > 0:
                query = query.gte("time", start_time)
            if end_time > 0:
                query = query.lte("time", end_time)
            if income_type:
                query = query.eq("type", income_type)

            query = query.order("time", desc=True).limit(limit)
            response = query.execute()

            return response.data or []

        except Exception as e:
            logger.error(f"Error getting transaction history: {e}")
            return []

    async def insert_transaction_history(self, transaction_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Insert a single transaction record."""
        try:
            # Ensure exchange is set
            if 'exchange' not in transaction_data or not transaction_data.get('exchange'):
                sym = (transaction_data.get('symbol') or '').upper()
                # Heuristic: if symbol contains 'USDT' and no kucoin marker, assume binance
                transaction_data['exchange'] = 'kucoin' if '-USDT' in sym or sym.endswith('USDTM') else 'binance'
            response = self.supabase.table("transaction_history").insert(transaction_data).execute()
            if response.data and len(response.data) > 0:
                logger.info(f"Inserted transaction: {response.data[0].get('id')}")
                return response.data[0]
            return None
        except Exception as e:
            logger.error(f"Error inserting transaction: {e}")
            return None

    async def insert_transaction_history_batch(self, transactions: List[Dict[str, Any]]) -> bool:
        """Insert multiple transaction records in batch."""
        try:
            # Ensure exchange is set for all records
            for tx in transactions:
                if 'exchange' not in tx or not tx.get('exchange'):
                    sym = (tx.get('symbol') or '').upper()
                    tx['exchange'] = 'kucoin' if '-USDT' in sym or sym.endswith('USDTM') else 'binance'
            response = self.supabase.table("transaction_history").insert(transactions).execute()
            if response.data:
                logger.info(f"Inserted {len(response.data)} transactions in batch")
                return True
            return False
        except Exception as e:
            logger.error(f"Error inserting transaction batch: {e}")
            return False

    async def check_transaction_exists(self, time: str, type: str, amount: float, asset: str, symbol: str) -> bool:
        """Check if a transaction record already exists to avoid duplicates."""
        try:
            response = self.supabase.table("transaction_history").select("id").eq("time", time).eq("type", type).eq("amount", amount).eq("asset", asset).eq("symbol", symbol).execute()
            return len(response.data) > 0 if response.data else False
        except Exception as e:
            logger.error(f"Error checking transaction existence: {e}")
            return False

    async def get_transaction_count_by_exchange(self, exchange: str) -> int:
        """Get count of transactions for a specific exchange."""
        try:
            response = self.supabase.table("transaction_history").select("id", count="exact").eq("exchange", exchange).execute()
            return response.count if response.count else 0
        except Exception as e:
            logger.error(f"Error getting transaction count by exchange: {e}")
            return 0

    async def get_transaction_count_by_symbol_and_exchange(self, symbol: str, exchange: str) -> int:
        """Get count of transactions for a specific symbol and exchange."""
        try:
            response = self.supabase.table("transaction_history").select("id", count="exact").eq("symbol", symbol).eq("exchange", exchange).execute()
            return response.count if response.count else 0
        except Exception as e:
            logger.error(f"Error getting transaction count by symbol and exchange: {e}")
            return 0

    async def get_latest_transaction_time_by_exchange(self, exchange: str) -> Optional[str]:
        """Get the latest transaction time for a specific exchange."""
        try:
            response = self.supabase.table("transaction_history").select("time").eq("exchange", exchange).order("time", desc=True).limit(1).execute()
            if response.data and len(response.data) > 0:
                return response.data[0].get("time")
            return None
        except Exception as e:
            logger.error(f"Error getting latest transaction time by exchange: {e}")
            return None

    # Health Check

    async def health_check(self) -> bool:
        """Check database connectivity and health."""
        try:
            # Try a simple query to check connectivity
            response = self.supabase.table("trades").select("id").limit(1).execute()
            logger.info("Database health check passed")
            return True
        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            return False
