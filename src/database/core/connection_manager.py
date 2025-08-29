"""
Database Connection Manager

This module manages database connections and provides connection pooling.
"""

import asyncio
import logging
from typing import Optional, Dict, Any
from contextlib import asynccontextmanager
from supabase import create_client, Client
from supabase.lib.client_options import ClientOptions

from src.database.core.database_config import database_config

logger = logging.getLogger(__name__)

class DatabaseConnectionManager:
    """Manages database connections and provides connection pooling."""
    
    def __init__(self, config=None):
        """Initialize the connection manager."""
        self.config = config or database_config
        self._client: Optional[Client] = None
        self._connection_pool: Dict[str, Client] = {}
        self._lock = asyncio.Lock()
        
    async def initialize(self) -> bool:
        """Initialize the database connection."""
        try:
            if not self.config.supabase_url or not self.config.supabase_key:
                logger.error("Database configuration missing: SUPABASE_URL or SUPABASE_KEY")
                return False
            
            # Create client options
            options = ClientOptions(
                schema="public",
                headers={},
                auto_refresh_token=True,
                persist_session=True,
                detect_session_in_url=True
            )
            
            # Create Supabase client
            self._client = create_client(
                self.config.supabase_url,
                self.config.supabase_key,
                options=options
            )
            
            # Test connection
            await self._test_connection()
            
            logger.info("Database connection initialized successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize database connection: {e}")
            return False
    
    async def _test_connection(self) -> bool:
        """Test the database connection."""
        try:
            # Simple query to test connection
            result = self._client.table("trades").select("id").limit(1).execute()
            logger.debug("Database connection test successful")
            return True
        except Exception as e:
            logger.error(f"Database connection test failed: {e}")
            return False
    
    def get_client(self) -> Optional[Client]:
        """Get the database client."""
        return self._client
    
    async def get_connection(self, name: str = "default") -> Optional[Client]:
        """Get a database connection from the pool."""
        async with self._lock:
            if name not in self._connection_pool:
                # Create new connection
                if not await self.initialize():
                    return None
                self._connection_pool[name] = self._client
            
            return self._connection_pool[name]
    
    async def release_connection(self, name: str = "default") -> None:
        """Release a database connection back to the pool."""
        async with self._lock:
            if name in self._connection_pool:
                # For Supabase, we don't need to explicitly close connections
                # The client handles connection management
                pass
    
    async def close_all_connections(self) -> None:
        """Close all database connections."""
        async with self._lock:
            self._connection_pool.clear()
            self._client = None
            logger.info("All database connections closed")
    
    async def health_check(self) -> bool:
        """Perform health check on database connection."""
        try:
            if not self._client:
                return False
            
            # Test connection with a simple query
            result = self._client.table("trades").select("id").limit(1).execute()
            return True
            
        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            return False
    
    def get_connection_status(self) -> Dict[str, Any]:
        """Get connection status information."""
        return {
            "initialized": self._client is not None,
            "pool_size": len(self._connection_pool),
            "config": {
                "url": self.config.supabase_url[:20] + "..." if self.config.supabase_url else None,
                "timeout": self.config.connection_timeout,
                "max_retries": self.config.max_retries
            }
        }

# Global connection manager instance
connection_manager = DatabaseConnectionManager()

@asynccontextmanager
async def get_db_connection(name: str = "default"):
    """Context manager for database connections."""
    connection = await connection_manager.get_connection(name)
    try:
        yield connection
    finally:
        await connection_manager.release_connection(name)
