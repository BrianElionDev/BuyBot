"""
Database Configuration Module

This module contains configuration settings for database operations.
"""

from dataclasses import dataclass
from typing import Optional, Dict, Any
import os
from dotenv import load_dotenv

load_dotenv()

@dataclass
class DatabaseConfig:
    """Database configuration settings."""
    
    # Supabase settings
    supabase_url: str
    supabase_key: str
    
    # Connection settings
    connection_timeout: int = 30
    max_retries: int = 3
    retry_delay: float = 1.0
    
    # Query settings
    default_page_size: int = 100
    max_page_size: int = 1000
    query_timeout: int = 60
    
    # Cache settings
    enable_cache: bool = True
    cache_ttl: int = 300  # seconds
    max_cache_size: int = 1000
    
    # Logging settings
    enable_query_logging: bool = False
    log_slow_queries: bool = True
    slow_query_threshold: float = 1.0  # seconds
    
    # Pool settings
    pool_size: int = 10
    max_overflow: int = 20
    
    def __post_init__(self):
        """Initialize default values from environment variables."""
        # Override with environment variables if present
        self.supabase_url = os.getenv("SUPABASE_URL", self.supabase_url)
        self.supabase_key = os.getenv("SUPABASE_KEY", self.supabase_key)
        self.connection_timeout = int(os.getenv("DB_CONNECTION_TIMEOUT", str(self.connection_timeout)))
        self.max_retries = int(os.getenv("DB_MAX_RETRIES", str(self.max_retries)))
        self.retry_delay = float(os.getenv("DB_RETRY_DELAY", str(self.retry_delay)))
        self.default_page_size = int(os.getenv("DB_DEFAULT_PAGE_SIZE", str(self.default_page_size)))
        self.max_page_size = int(os.getenv("DB_MAX_PAGE_SIZE", str(self.max_page_size)))
        self.query_timeout = int(os.getenv("DB_QUERY_TIMEOUT", str(self.query_timeout)))
        self.enable_cache = os.getenv("DB_ENABLE_CACHE", str(self.enable_cache)).lower() == "true"
        self.cache_ttl = int(os.getenv("DB_CACHE_TTL", str(self.cache_ttl)))
        self.max_cache_size = int(os.getenv("DB_MAX_CACHE_SIZE", str(self.max_cache_size)))
        self.enable_query_logging = os.getenv("DB_ENABLE_QUERY_LOGGING", str(self.enable_query_logging)).lower() == "true"
        self.log_slow_queries = os.getenv("DB_LOG_SLOW_QUERIES", str(self.log_slow_queries)).lower() == "true"
        self.slow_query_threshold = float(os.getenv("DB_SLOW_QUERY_THRESHOLD", str(self.slow_query_threshold)))
        self.pool_size = int(os.getenv("DB_POOL_SIZE", str(self.pool_size)))
        self.max_overflow = int(os.getenv("DB_MAX_OVERFLOW", str(self.max_overflow)))

# Global database configuration instance
database_config = DatabaseConfig(
    supabase_url="",
    supabase_key=""
)
