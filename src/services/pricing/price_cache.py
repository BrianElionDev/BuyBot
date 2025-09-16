import logging
from typing import Optional, Dict
from datetime import datetime, timedelta
from .price_models import PriceCacheEntry, PriceServiceConfig

logger = logging.getLogger(__name__)


class PriceCache:
    """Manages caching of price data to improve performance"""

    def __init__(self, config: Optional[PriceServiceConfig] = None):
        """Initialize the price cache"""
        self.config = config or PriceServiceConfig()
        self._cache: Dict[str, PriceCacheEntry] = {}
        self._coin_cache: Dict[str, str] = {}  # symbol -> coin_id cache

        # Preload common cryptocurrency mappings
        self._preload_common_coins()

    def _preload_common_coins(self) -> None:
        """Preload common cryptocurrency mappings to avoid incorrect resolutions"""
        common_coins = {
            # Major cryptocurrencies
            "BTC": "bitcoin", "ETH": "ethereum", "SOL": "solana", "BNB": "binancecoin",
            "XRP": "ripple", "ADA": "cardano", "AVAX": "avalanche-2", "DOGE": "dogecoin",
            "DOT": "polkadot", "SHIB": "shiba-inu", "MATIC": "matic-network",
            "LINK": "chainlink", "UNI": "uniswap", "ATOM": "cosmos", "LTC": "litecoin",
            "XLM": "stellar", "ALGO": "algorand", "ARB": "arbitrum", "FIL": "filecoin",
            "ICP": "internet-computer", "TRX": "tron", "NEAR": "near", "OP": "optimism",
            "APT": "aptos",

            # DeFi & Exchange tokens
            "AAVE": "aave", "COMP": "compound-governance-token", "MKR": "maker",
            "SNX": "havven", "YFI": "yearn-finance", "CRV": "curve-dao-token",
            "SUSHI": "sushi", "1INCH": "1inch", "BAL": "balancer", "RUNE": "thorchain",

            # Wrapped tokens
            "WBTC": "wrapped-bitcoin", "WETH": "weth",

            # Other popular tokens
            "MANA": "decentraland", "SAND": "the-sandbox", "APE": "apecoin", "LDO": "lido-dao",

            # Stablecoins
            "USDT": "tether", "USDC": "usd-coin", "BUSD": "binance-usd",
            "DAI": "dai", "TUSD": "true-usd", "USDD": "usdd", "USDP": "paxos-standard",

            # Name variations & full names
            "SOLANA": "solana", "ETHEREUM": "ethereum", "BITCOIN": "bitcoin",
            "CARDANO": "cardano", "DOGECOIN": "dogecoin", "SHIBA": "shiba-inu",
            "SHIBAINU": "shiba-inu", "SHIBA INU": "shiba-inu",
        }

        self._coin_cache.update({k.upper(): v for k, v in common_coins.items()})
        logger.info(f"Preloaded {len(common_coins)} common coin mappings")

    def get_cached_price(self, symbol: str) -> Optional[float]:
        """Get cached price for a symbol if it's still valid"""
        if not symbol:
            return None

        symbol = symbol.upper().strip()
        cache_entry = self._cache.get(symbol)

        if not cache_entry:
            return None

        # Check if cache entry is still valid
        if self._is_cache_valid(cache_entry):
            logger.info(f"Cache hit for {symbol}: ${cache_entry.price}")
            return cache_entry.price

        # Remove expired cache entry
        logger.info(f"Cache expired for {symbol}, removing")
        del self._cache[symbol]
        return None

    def set_cached_price(self, symbol: str, price: float, ttl: Optional[int] = None) -> None:
        """Cache price for a symbol with specified TTL"""
        if not symbol or price <= 0:
            return

        symbol = symbol.upper().strip()
        cache_ttl = ttl or self.config.cache_ttl

        cache_entry = PriceCacheEntry(
            price=price,
            timestamp=datetime.now(),
            ttl=cache_ttl
        )

        self._cache[symbol] = cache_entry
        logger.info(f"Cached price for {symbol}: ${price} (TTL: {cache_ttl}s)")

    def get_cached_coin_id(self, symbol: str) -> Optional[str]:
        """Get cached coin ID for a symbol"""
        if not symbol:
            return None

        symbol = symbol.upper().strip()
        return self._coin_cache.get(symbol)

    def set_cached_coin_id(self, symbol: str, coin_id: str) -> None:
        """Cache coin ID mapping for a symbol"""
        if not symbol or not coin_id:
            return

        symbol = symbol.upper().strip()
        self._coin_cache[symbol] = coin_id
        logger.info(f"Cached coin ID mapping: {symbol} -> {coin_id}")

    def _is_cache_valid(self, cache_entry: PriceCacheEntry) -> bool:
        """Check if a cache entry is still valid"""
        now = datetime.now()
        expiry_time = cache_entry.timestamp + timedelta(seconds=cache_entry.ttl)
        return now < expiry_time

    def clear_expired_cache(self) -> int:
        """Clear expired cache entries and return count of cleared entries"""
        now = datetime.now()
        expired_keys = []

        for symbol, cache_entry in self._cache.items():
            if not self._is_cache_valid(cache_entry):
                expired_keys.append(symbol)

        for key in expired_keys:
            del self._cache[key]

        if expired_keys:
            logger.info(f"Cleared {len(expired_keys)} expired cache entries")

        return len(expired_keys)

    def clear_all_cache(self) -> None:
        """Clear all cached data"""
        price_count = len(self._cache)
        coin_count = len(self._coin_cache)

        self._cache.clear()
        self._coin_cache.clear()

        # Re-preload common coins
        self._preload_common_coins()

        logger.info(f"Cleared all cache: {price_count} prices, {coin_count} coin mappings")

    def get_cache_stats(self) -> Dict[str, int]:
        """Get cache statistics"""
        return {
            'cached_prices': len(self._cache),
            'cached_coin_mappings': len(self._coin_cache),
            'total_cache_entries': len(self._cache) + len(self._coin_cache)
        }

    def is_symbol_cached(self, symbol: str) -> bool:
        """Check if a symbol has cached price data"""
        if not symbol:
            return False

        symbol = symbol.upper().strip()
        cache_entry = self._cache.get(symbol)

        if not cache_entry:
            return False

        return self._is_cache_valid(cache_entry)
