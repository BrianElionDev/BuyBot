import time
import logging
from typing import Dict, Optional, Tuple
from supabase import create_client, Client

logger = logging.getLogger(__name__)

DEFAULT_CACHE_TTL_SECONDS = 120


class RuntimeConfig:
  def __init__(self, supabase_url: str, supabase_key: str, cache_ttl: int = DEFAULT_CACHE_TTL_SECONDS):
    self.supabase: Client = create_client(supabase_url, supabase_key)
    self.cache_ttl = cache_ttl
    self._cache: Dict[Tuple[str, str], Tuple[float, float]] = {}

  def _is_cache_valid(self, timestamp: float) -> bool:
    return time.time() - timestamp < self.cache_ttl

  async def get_trader_exchange_config(self, trader_id: str, exchange: str) -> Optional[Dict[str, float]]:
    cache_key = (trader_id, exchange)

    # Cache hit
    if cache_key in self._cache:
      leverage, timestamp = self._cache[cache_key]
      if self._is_cache_valid(timestamp):
        logger.debug(f"Using cached leverage for {trader_id} on {exchange}: {leverage}")
        return {"leverage": leverage}

    # Fetch from Supabase
    try:
      response = self.supabase.table("trader_exchange_config").select("leverage").eq("trader_id", trader_id).eq("exchange", exchange).single().execute()
      data = getattr(response, 'data', None)
      if data:
        leverage = float(data.get("leverage", 1))
        self._cache[cache_key] = (leverage, time.time())
        logger.info(f"Fetched leverage from Supabase for {trader_id} on {exchange}: {leverage}")
        return {"leverage": leverage}
      else:
        logger.warning(f"No leverage config found for {trader_id} on {exchange}. Using 1x.")
        return {"leverage": 1.0}
    except Exception as e:
      logger.error(f"Error fetching leverage for {trader_id} on {exchange}: {e}")
      return {"leverage": 1.0}

  def clear_cache(self, trader_id: Optional[str] = None, exchange: Optional[str] = None):
    if trader_id and exchange:
      self._cache.pop((trader_id, exchange), None)
    else:
      self._cache.clear()


runtime_config = None


def init_runtime_config(supabase_url: str, supabase_key: str, cache_ttl: int = DEFAULT_CACHE_TTL_SECONDS):
  global runtime_config
  runtime_config = RuntimeConfig(supabase_url, supabase_key, cache_ttl)