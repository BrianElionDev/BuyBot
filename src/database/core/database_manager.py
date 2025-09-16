"""
Core Database Manager

This module provides core database operations and utilities.
"""

import logging
import time
from typing import Optional, Dict, Any, List, Union
from datetime import datetime, timezone
from supabase import Client

from src.database.core.database_config import database_config
from src.database.core.connection_manager import connection_manager

logger = logging.getLogger(__name__)

class DatabaseManager:
    """Core database manager providing common database operations."""

    def __init__(self, client: Optional[Client] = None):
        """Initialize the database manager."""
        self.client = client
        self.config = database_config
        self._query_cache: Dict[str, Any] = {}
        self._cache_timestamps: Dict[str, float] = {}

    async def initialize(self) -> bool:
        """Initialize the database manager."""
        try:
            if not self.client:
                await connection_manager.initialize()
                self.client = connection_manager.get_client()

            if not self.client:
                logger.error("Failed to initialize database client")
                return False

            logger.info("Database manager initialized successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize database manager: {e}")
            return False

    def _get_cache_key(self, table: str, operation: str, **kwargs) -> str:
        """Generate cache key for queries."""
        key_parts = [table, operation]
        for k, v in sorted(kwargs.items()):
            key_parts.append(f"{k}:{v}")
        return "|".join(key_parts)

    def _is_cache_valid(self, cache_key: str) -> bool:
        """Check if cache entry is still valid."""
        if not self.config.enable_cache:
            return False

        if cache_key not in self._cache_timestamps:
            return False

        cache_age = time.time() - self._cache_timestamps[cache_key]
        return cache_age < self.config.cache_ttl

    def _update_cache(self, cache_key: str, data: Any) -> None:
        """Update cache with new data."""
        if not self.config.enable_cache:
            return

        # Implement LRU cache eviction
        if len(self._query_cache) >= self.config.max_cache_size:
            # Remove oldest entry
            oldest_key = min(self._cache_timestamps.keys(), key=lambda k: self._cache_timestamps[k])
            del self._query_cache[oldest_key]
            del self._cache_timestamps[oldest_key]

        self._query_cache[cache_key] = data
        self._cache_timestamps[cache_key] = time.time()

    def _get_from_cache(self, cache_key: str) -> Optional[Any]:
        """Get data from cache if valid."""
        if not self.config.enable_cache:
            return None

        if self._is_cache_valid(cache_key):
            return self._query_cache.get(cache_key)

        # Remove invalid cache entry
        if cache_key in self._query_cache:
            del self._query_cache[cache_key]
            del self._cache_timestamps[cache_key]

        return None

    async def execute_query(self, query_builder, cache_key: Optional[str] = None) -> Dict[str, Any]:
        """Execute a database query with optional caching."""
        start_time = time.time()

        try:
            # Check cache first
            if cache_key:
                cached_result = self._get_from_cache(cache_key)
                if cached_result is not None:
                    logger.info(f"Cache hit for key: {cache_key}")
                    return cached_result

            # Execute query
            if self.config.enable_query_logging:
                logger.info(f"Executing query: {query_builder}")

            result = query_builder.execute()

            # Log slow queries
            query_time = time.time() - start_time
            if self.config.log_slow_queries and query_time > self.config.slow_query_threshold:
                logger.warning(f"Slow query detected: {query_time:.3f}s")

            # Update cache
            if cache_key:
                self._update_cache(cache_key, result)

            return result

        except Exception as e:
            logger.error(f"Database query failed: {e}")
            raise

    async def insert(self, table: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Insert data into a table."""
        try:
            query = self.client.table(table).insert(data)
            result = await self.execute_query(query)
            logger.info(f"Inserted data into {table}: {result}")
            return result
        except Exception as e:
            logger.error(f"Failed to insert data into {table}: {e}")
            raise

    async def select(self, table: str, columns: Optional[List[str]] = None,
                    filters: Optional[Dict[str, Any]] = None,
                    order_by: Optional[str] = None,
                    limit: Optional[int] = None,
                    cache_key: Optional[str] = None) -> Dict[str, Any]:
        """Select data from a table."""
        try:
            query = self.client.table(table)

            if columns:
                query = query.select(",".join(columns))
            else:
                query = query.select("*")

            # Apply filters
            if filters:
                for key, value in filters.items():
                    if isinstance(value, dict):
                        # Handle complex filters like range queries
                        for op, val in value.items():
                            query = query.filter(key, op, val)
                    else:
                        query = query.eq(key, value)

            # Apply ordering
            if order_by:
                query = query.order(order_by)

            # Apply limit
            if limit:
                query = query.limit(limit)

            result = await self.execute_query(query, cache_key)
            return result

        except Exception as e:
            logger.error(f"Failed to select data from {table}: {e}")
            raise

    async def update(self, table: str, data: Dict[str, Any],
                    filters: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Update data in a table."""
        try:
            query = self.client.table(table).update(data)

            # Apply filters
            if filters:
                for key, value in filters.items():
                    query = query.eq(key, value)

            result = await self.execute_query(query)
            logger.info(f"Updated data in {table}: {result}")
            return result

        except Exception as e:
            logger.error(f"Failed to update data in {table}: {e}")
            raise

    async def delete(self, table: str, filters: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Delete data from a table."""
        try:
            query = self.client.table(table).delete()

            # Apply filters
            if filters:
                for key, value in filters.items():
                    query = query.eq(key, value)

            result = await self.execute_query(query)
            logger.info(f"Deleted data from {table}: {result}")
            return result

        except Exception as e:
            logger.error(f"Failed to delete data from {table}: {e}")
            raise

    async def count(self, table: str, filters: Optional[Dict[str, Any]] = None) -> int:
        """Count records in a table."""
        try:
            query = self.client.table(table).select("id", count="exact")

            # Apply filters
            if filters:
                for key, value in filters.items():
                    query = query.eq(key, value)

            result = await self.execute_query(query)
            return result.get("count", 0)

        except Exception as e:
            logger.error(f"Failed to count records in {table}: {e}")
            raise

    def clear_cache(self) -> None:
        """Clear the query cache."""
        self._query_cache.clear()
        self._cache_timestamps.clear()
        logger.info("Database query cache cleared")

    async def health_check(self) -> bool:
        """Perform health check on database."""
        try:
            result = await self.count("trades", {"id": 0})  # Should return 0
            return True
        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            return False

    def get_stats(self) -> Dict[str, Any]:
        """Get database manager statistics."""
        return {
            "cache_size": len(self._query_cache),
            "cache_hits": 0,  # TODO: Implement cache hit tracking
            "config": {
                "enable_cache": self.config.enable_cache,
                "cache_ttl": self.config.cache_ttl,
                "max_cache_size": self.config.max_cache_size,
                "enable_query_logging": self.config.enable_query_logging
            }
        }
