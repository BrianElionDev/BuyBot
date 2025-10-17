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
    self._cache: Dict[Tuple[str, str], Tuple[float, float, float]] = {}

  def _is_cache_valid(self, timestamp: float) -> bool:
    return time.time() - timestamp < self.cache_ttl

  async def get_trader_exchange_config(self, trader_id: str, exchange: str) -> Optional[Dict[str, float]]:
    cache_key = (trader_id, exchange)

    # Cache hit
    if cache_key in self._cache:
      leverage, position_size, timestamp = self._cache[cache_key]
      if self._is_cache_valid(timestamp):
        logger.debug(f"Using cached config for {trader_id} on {exchange}: leverage={leverage}x, position_size=${position_size}")
        return {"leverage": leverage, "position_size": position_size}

    # Fetch from Supabase
    try:
      response = self.supabase.table("trader_exchange_config").select("leverage, position_size").eq("trader_id", trader_id).eq("exchange", exchange).single().execute()
      data = getattr(response, 'data', None)
      if data:
        leverage = float(data.get("leverage", 1))
        position_size = float(data.get("position_size", 100.0))
        self._cache[cache_key] = (leverage, position_size, time.time())
        logger.info(f"Fetched config from Supabase for {trader_id} on {exchange}: leverage={leverage}x, position_size=${position_size}")
        return {"leverage": leverage, "position_size": position_size}
      else:
        logger.warning(f"No config found for {trader_id} on {exchange}. Using defaults: leverage=1x, position_size=$100.")
        return {"leverage": 1.0, "position_size": 100.0}
    except Exception as e:
      logger.error(f"Error fetching config for {trader_id} on {exchange}: {e}")
      return {"leverage": 1.0, "position_size": 100.0}

  def clear_cache(self, trader_id: Optional[str] = None, exchange: Optional[str] = None):
    if trader_id and exchange:
      self._cache.pop((trader_id, exchange), None)
    else:
      self._cache.clear()


runtime_config = None


def init_runtime_config(supabase_url: str, supabase_key: str, cache_ttl: int = DEFAULT_CACHE_TTL_SECONDS):
  global runtime_config
  runtime_config = RuntimeConfig(supabase_url, supabase_key, cache_ttl)