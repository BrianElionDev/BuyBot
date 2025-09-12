"""
Database Utilities

Helper functions and utilities for database operations.
"""

import logging
from typing import Dict, Any, Optional
from datetime import datetime, timezone
import json

logger = logging.getLogger(__name__)


class DatabaseUtils:
    """Utility functions for database operations."""
    
    @staticmethod
    def parse_timestamp(timestamp_str: str) -> Optional[datetime]:
        """Parse timestamp string to datetime object."""
        try:
            if not timestamp_str:
                return None
            
            # Handle different timestamp formats
            if timestamp_str.endswith('Z'):
                timestamp_str = timestamp_str.replace('Z', '+00:00')
            
            return datetime.fromisoformat(timestamp_str)
        except Exception as e:
            logger.warning(f"Error parsing timestamp {timestamp_str}: {e}")
            return None
    
    @staticmethod
    def format_timestamp(dt: datetime) -> str:
        """Format datetime object to ISO string."""
        try:
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.isoformat()
        except Exception as e:
            logger.error(f"Error formatting timestamp {dt}: {e}")
            return datetime.now(timezone.utc).isoformat()
    
    @staticmethod
    def parse_json_field(json_str: str) -> Optional[Dict[str, Any]]:
        """Parse JSON string to dictionary."""
        try:
            if not json_str:
                return None
            
            if isinstance(json_str, dict):
                return json_str
            
            return json.loads(json_str)
        except Exception as e:
            logger.warning(f"Error parsing JSON field {json_str}: {e}")
            return None
    
    @staticmethod
    def format_json_field(data: Dict[str, Any]) -> Optional[str]:
        """Format dictionary to JSON string."""
        try:
            if not data:
                return None
            
            return json.dumps(data)
        except Exception as e:
            logger.error(f"Error formatting JSON field {data}: {e}")
            return None
    
    @staticmethod
    def validate_trade_data(trade_data: Dict[str, Any]) -> bool:
        """Validate trade data structure."""
        required_fields = ['discord_id', 'trader', 'content']
        
        for field in required_fields:
            if field not in trade_data or not trade_data[field]:
                logger.error(f"Missing required field in trade data: {field}")
                return False
        
        return True
    
    @staticmethod
    def validate_alert_data(alert_data: Dict[str, Any]) -> bool:
        """Validate alert data structure."""
        required_fields = ['discord_id', 'content']
        
        for field in required_fields:
            if field not in alert_data or not alert_data[field]:
                logger.error(f"Missing required field in alert data: {field}")
                return False
        
        return True
    
    @staticmethod
    def sanitize_data(data: Dict[str, Any]) -> Dict[str, Any]:
        """Sanitize data for database storage."""
        sanitized = {}
        
        for key, value in data.items():
            if value is not None:
                # Handle datetime objects
                if isinstance(value, datetime):
                    sanitized[key] = DatabaseUtils.format_timestamp(value)
                # Handle dictionaries
                elif isinstance(value, dict):
                    sanitized[key] = DatabaseUtils.format_json_field(value)
                # Handle other types
                else:
                    sanitized[key] = value
        
        return sanitized
    
    @staticmethod
    def desanitize_data(data: Dict[str, Any]) -> Dict[str, Any]:
        """Desanitize data from database storage."""
        desanitized = {}
        
        for key, value in data.items():
            if value is not None:
                # Handle timestamp fields
                if key in ['timestamp', 'created_at', 'updated_at', 'closed_at']:
                    desanitized[key] = DatabaseUtils.parse_timestamp(value)
                # Handle JSON fields
                elif key in ['parsed_signal', 'binance_response', 'parsed_alert']:
                    desanitized[key] = DatabaseUtils.parse_json_field(value)
                # Handle other fields
                else:
                    desanitized[key] = value
        
        return desanitized
    
    @staticmethod
    def create_update_dict(**kwargs) -> Dict[str, Any]:
        """Create an update dictionary with current timestamp."""
        update_dict = kwargs.copy()
        update_dict['updated_at'] = datetime.now(timezone.utc).isoformat()
        return update_dict
    
    @staticmethod
    def get_current_timestamp() -> str:
        """Get current timestamp in ISO format."""
        return datetime.now(timezone.utc).isoformat()
    
    @staticmethod
    def is_valid_uuid(uuid_string: str) -> bool:
        """Check if string is a valid UUID."""
        try:
            import uuid
            uuid.UUID(uuid_string)
            return True
        except ValueError:
            return False
    
    @staticmethod
    def generate_alert_hash(discord_id: str, content: str) -> str:
        """Generate a hash for alert deduplication."""
        import hashlib
        return hashlib.sha256(f"{discord_id}:{content}".encode()).hexdigest()
