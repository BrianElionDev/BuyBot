from dataclasses import dataclass
from typing import Optional, Dict, List
from datetime import datetime, timezone


@dataclass
class CoinData:
    """Data model for coin information"""
    id: str
    symbol: str
    name: str
    market_cap_rank: Optional[int] = None
    market_cap: Optional[float] = None
    is_legitimate: bool = True


@dataclass
class PriceData:
    """Data model for price information"""
    coin_id: str
    symbol: str
    price_usd: float
    timestamp: datetime
    source: str = "coingecko"


@dataclass
class MarketData:
    """Data model for market data"""
    coin_id: str
    symbol: str
    price_usd: float
    market_cap: Optional[float] = None
    volume_24h: Optional[float] = None
    price_change_24h: Optional[float] = None
    timestamp: datetime = datetime.now(timezone.utc)


@dataclass
class PriceCacheEntry:
    """Data model for cached price data"""
    price: float
    timestamp: datetime
    ttl: int = 300  # 5 minutes default TTL


@dataclass
class PriceValidationResult:
    """Data model for price validation results"""
    is_valid: bool
    price: float
    validation_errors: List[str]
    warnings: List[str]
    timestamp: datetime


@dataclass
class PriceServiceConfig:
    """Configuration for price service"""
    rate_limit_delay: float = 1.2  # seconds between API calls
    cache_ttl: int = 300  # seconds
    max_retries: int = 3
    timeout: float = 30.0
