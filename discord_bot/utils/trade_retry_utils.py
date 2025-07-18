import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Optional
from dotenv import load_dotenv
from supabase import create_client, Client
from discord_bot.discord_bot import DiscordBot

# --- Setup ---
load_dotenv()
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def get_24hr_cutoff_iso():
  now = datetime.now(timezone.utc)
  cutoff = now - timedelta(hours=24)
  return cutoff.isoformat()

# --- Helper to initialize clients ---
def initialize_clients() -> tuple[Optional[DiscordBot], Optional[Client]]:
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    if not url or not key:
        logging.error("Supabase URL or key not found in .env file.")
        return None, None
    supabase: Client = create_client(url, key)
    bot = DiscordBot()
    return bot, supabase

async def process_pending_trades(bot: DiscordBot, supabase: Client):
    """
    Find all trades with status 'pending' and process them (and their alerts).
    """
    logging.info("--- Processing pending trades ---")
    try:
        cutoff = get_24hr_cutoff_iso()
        response = supabase.from_("trades").select("*").eq("status", "pending").gte("timestamp", cutoff).execute()
        trades = response.data or []
        logging.info(f"Found {len(trades)} pending trades.")
    except Exception as e:
        logging.error(f"Error fetching pending trades: {e}")
        return
    for trade in trades:
        discord_id = trade.get("discord_id")
        if not discord_id:
            continue
        await process_single_trade(bot, supabase, discord_id)
        await asyncio.sleep(2)

async def process_cooldown_trades(bot: DiscordBot, supabase: Client):
    """
    Find all trades with binance_response matching 'Trade cooldown active for ...' and retry them.
    """
    logging.info("--- Processing cooldown trades ---")
    cooldown_pattern = "Trade cooldown active for%"
    try:
        cutoff = get_24hr_cutoff_iso()
        response = supabase.from_("trades").select("*").like("binance_response", cooldown_pattern).gte("timestamp", cutoff).execute()
        trades = response.data or []
        logging.info(f"Found {len(trades)} cooldown trades.")
    except Exception as e:
        logging.error(f"Error fetching cooldown trades: {e}")
        return
    for trade in trades:
        discord_id = trade.get("discord_id")
        if not discord_id:
            continue
        await process_single_trade(bot, supabase, discord_id)
        await asyncio.sleep(2)

async def process_empty_binance_response_trades(bot: DiscordBot, supabase: Client):
    """
    Find all trades with empty binance_response and timestamp >= '2025-07-14T00:00:00.000Z', then retry them.
    """
    logging.info("--- Processing trades with empty binance_response ---")
    try:
        cutoff = get_24hr_cutoff_iso()
        response = supabase.from_("trades").select("*").filter("binance_response", "eq", "").gte("timestamp", cutoff).execute()
        trades = response.data or []
        logging.info(f"Found {len(trades)} trades with empty binance_response.")
    except Exception as e:
        logging.error(f"Error fetching trades with empty binance_response: {e}")
        return
    for trade in trades:
        discord_id = trade.get("discord_id")
        if not discord_id:
            continue
        await process_single_trade(bot, supabase, discord_id)
        await asyncio.sleep(2)

async def process_margin_insufficient_trades(bot: DiscordBot, supabase: Client):
    """
    Find all trades with binance_response containing APIError(code=-2019) (margin insufficient) in the last 24 hours and retry them.
    """
    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=24)
    cutoff_iso = cutoff.isoformat()
    logging.info("--- Processing margin insufficient trades ---")
    pattern = '%APIError(code=-2019)%'
    try:
        response = supabase.from_("trades").select("*").like("binance_response", pattern).gte("timestamp", cutoff_iso).execute()
        trades = response.data or []
        logging.info(f"Found {len(trades)} margin insufficient trades.")
    except Exception as e:
        logging.error(f"Error fetching margin insufficient trades: {e}")
        return
    for trade in trades:
        discord_id = trade.get("discord_id")
        if not discord_id:
            continue
        await process_single_trade(bot, supabase, discord_id)
        await asyncio.sleep(2)

async def process_single_trade(bot: DiscordBot, supabase: Client, discord_id: str):
    """
    Processes a single trade by discord_id, including its alerts.
    """
    logging.info(f"--- Processing Discord ID: {discord_id} ---")
    try:
        response = supabase.from_("trades").select("*").eq("discord_id", discord_id).single().execute()
        trade = response.data
        if not trade:
            logging.error(f"No trade found with discord_id: {discord_id}")
            return
    except Exception as e:
        logging.error(f"Failed to fetch trade from Supabase: {e}")
        return
    # Re-process the initial trade signal
    initial_signal_data = {
        "timestamp": trade.get("timestamp"),
        "content": trade.get("content"),
        "discord_id": trade.get("discord_id"),
        "trader": trade.get("trader"),
        "structured": trade.get("structured"),
    }
    if not all(initial_signal_data.values()):
        logging.error(f"Skipping initial signal for trade ID {trade.get('id')} due to missing data.")
    else:
        try:
            initial_signal_data['price_threshold_override'] = 99999
            result = await bot.process_initial_signal(initial_signal_data)
            if result.get("status") == "success":
                logging.info(f"Successfully re-processed initial signal.")
            else:
                logging.error(f"Failed to re-process initial signal. Reason: {result.get('message')}")
        except Exception as e:
            logging.error(f"Error while re-processing initial signal: {e}", exc_info=True)
    # Process any corresponding alerts
    try:
        alert_response = supabase.from_("alerts").select("*").eq("trade", discord_id).execute()
        alerts = alert_response.data or []
        if not alerts:
            logging.info("No corresponding alerts found for this trade.")
        else:
            logging.info(f"Found {len(alerts)} alert(s) to process.")
            for alert in sorted(alerts, key=lambda x: x.get('timestamp') or ''):
                alert_id = alert.get('id')
                alert_signal_data = {
                    "timestamp": alert.get("timestamp"),
                    "content": alert.get("content"),
                    "discord_id": alert.get("discord_id"),
                    "trader": alert.get("trader"),
                    "trade": alert.get("trade"),
                }
                if not all(alert_signal_data.values()):
                    logging.warning(f"Skipping alert ID {alert_id} due to missing data.")
                    continue
                try:
                    result = await bot.process_update_signal(alert_signal_data)
                    if result.get("status") == "success":
                        logging.info(f"Successfully re-processed alert ID {alert_id}.")
                    else:
                        logging.error(f"Failed to re-process alert ID {alert_id}. Reason: {result.get('message')}")
                except Exception as e:
                    logging.error(f"Error while processing alert ID {alert_id}: {e}", exc_info=True)
    except Exception as e:
        logging.error(f"Failed to fetch or process alerts: {e}")