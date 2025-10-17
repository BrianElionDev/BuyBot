import logging
import time
from typing import Literal, Optional
from datetime import datetime, timezone
import os
from src.services.notifications.telegram_service import TelegramService
from discord_bot.utils.trade_retry_utils import initialize_clients
from supabase import Client

SERVICE_NAME = os.environ.get("DISCORD_ACTIVITY_SERVICE", "discord_service")

logger = logging.getLogger(__name__)


class ActivityMonitor:
  @staticmethod
  def _get_supabase() -> Client:
    _, supabase = initialize_clients()
    if supabase is None:
      raise RuntimeError("Supabase client is not initialized")
    return supabase

  @staticmethod
  def mark_activity(kind: Literal["entry", "update"]) -> None:
    supabase = ActivityMonitor._get_supabase()
    now_iso = datetime.now(timezone.utc).isoformat()

    supabase.table("system_activity").upsert({
      "service": SERVICE_NAME,
      "last_activity_ts": now_iso,
      "last_activity_kind": kind,
      "updated_at": now_iso,
    }, on_conflict="service").execute()
    logger.info(f"[ActivityMonitor] DB activity marked: {kind}")

  @staticmethod
  async def check_and_alert() -> Optional[bool]:
    from config import settings
    if not settings.INACTIVITY_ALERT_ENABLED:
      return None

    supabase = ActivityMonitor._get_supabase()
    now = datetime.now(timezone.utc)

    try:
      resp = supabase.table("system_activity").select("last_activity_ts,last_alert_ts").eq("service", SERVICE_NAME).single().execute()
      row = (resp.data or {}) if hasattr(resp, "data") else {}
      ts = row.get("last_activity_ts")
      la = row.get("last_alert_ts")

      last_ts_dt: Optional[datetime] = None
      last_alert_dt: Optional[datetime] = None
      if ts:
        last_ts_dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
      if la:
        last_alert_dt = datetime.fromisoformat(str(la).replace("Z", "+00:00"))

      threshold = settings.INACTIVITY_THRESHOLD_HOURS * 3600
      cooldown = settings.INACTIVITY_ALERT_COOLDOWN_HOURS * 3600

      if last_ts_dt is None:
        since_sec = threshold
      else:
        since_sec = (now - last_ts_dt).total_seconds()

      last_alert_sec = (now - last_alert_dt).total_seconds() if last_alert_dt else 10**12

      if since_sec >= threshold and last_alert_sec >= cooldown:
        if not ActivityMonitor._has_configured_traders(supabase):
          logger.debug("[ActivityMonitor] No configured traders found - skipping inactivity alert")
          return None

        msg = settings.INACTIVITY_ALERT_MESSAGE or "Discord is awefully silet today zzz"
        svc = TelegramService()
        sent = await svc.send_message(msg)
        logger.info(f"[ActivityMonitor] Inactivity alert sent: {sent}")

        supabase.table("system_activity").upsert({
          "service": SERVICE_NAME,
          "last_alert_ts": now.isoformat(),
          "updated_at": now.isoformat(),
        }, on_conflict="service").execute()

        return sent

      return None
    except Exception as e:
      logger.error(f"[ActivityMonitor] check_and_alert failed: {e}", exc_info=True)
      return None

  @staticmethod
  def _has_configured_traders(supabase: Client) -> bool:
    """
    Efficiently check if any traders are configured in Supabase.
    Uses a simple count query to avoid loading all trader data.
    """
    try:
      resp = supabase.table("trader_exchange_config").select("trader_id", count="exact").limit(1).execute()
      count = getattr(resp, 'count', 0) or 0
      has_traders = count > 0
      logger.debug(f"[ActivityMonitor] Trader check: {count} traders configured")
      return has_traders
    except Exception as e:
      logger.warning(f"[ActivityMonitor] Failed to check trader config: {e}")
      return True
