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
