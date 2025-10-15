import os
import logging
from typing import Set, Optional
from supabase import create_client, Client

logger = logging.getLogger(__name__)


class TraderFilter:
    """Filter traders based on Supabase trader_exchange_config table."""

    def __init__(self):
        self._trader_cache: Optional[Set[str]] = None
        self._cache_loaded = False
        self._supabase: Optional[Client] = None
        self._init_supabase()

    def _init_supabase(self):
        """Initialize Supabase client."""
        try:
            url = os.getenv("SUPABASE_URL", "").strip()
            key = os.getenv("SUPABASE_KEY", "").strip()
            if url and key:
                self._supabase = create_client(url, key)
            else:
                logger.warning("SUPABASE_URL or SUPABASE_KEY not set. Trader filter disabled.")
        except Exception as e:
            logger.error(f"Failed to initialize Supabase client: {e}")

    def _load_trader_cache(self) -> Set[str]:
        """Load trader list from Supabase trader_exchange_config table."""
        if self._cache_loaded:
            return self._trader_cache or set()

        if not self._supabase:
            self._cache_loaded = True
            return set()

        try:
            response = self._supabase.table("trader_exchange_config").select("trader_id").execute()
            data = getattr(response, 'data', []) or []

            traders = set()
            for row in data:
                trader_id = row.get('trader_id', '').strip()
                if trader_id:
                    normalized = trader_id.lstrip('@')
                    traders.add(trader_id)  # Original
                    traders.add(normalized)  # Without @
                    traders.add(f"@{normalized}")  # With @

            self._trader_cache = traders
            self._cache_loaded = True
            logger.info(f"Loaded {len(traders)} trader variations for filtering")
            return traders

        except Exception as e:
            logger.error(f"Failed to load trader cache: {e}")
            self._cache_loaded = True
            return set()

    def should_notify(self, trader: str) -> bool:
        """Check if trader should receive notifications."""
        if not trader:
            return False

        traders = self._load_trader_cache()
        return str(trader).strip() in traders


# Global instance
_trader_filter = TraderFilter()


def should_notify_trader(trader: str) -> bool:
    """Check if trader should receive notifications."""
    return _trader_filter.should_notify(trader)
