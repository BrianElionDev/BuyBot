import os
import logging
from typing import Optional, Dict, Any
from supabase import create_client, Client
from dotenv import load_dotenv
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# --- Supabase setup ---
url: Optional[str] = os.environ.get("SUPABASE_URL")
key: Optional[str] = os.environ.get("SUPABASE_KEY")

if not url or not key:
    logger.warning("Supabase URL or Key not found in environment variables. Database functionality will be disabled.")
    supabase: Optional[Client] = None
else:
    try:
        supabase: Client = create_client(url, key)
        logger.info("Successfully connected to Supabase.")
    except Exception as e:
        logger.error(f"Failed to connect to Supabase: {e}", exc_info=True)
        supabase = None


async def find_active_trade_by_symbol(symbol: str) -> Optional[Dict[str, Any]]:
    """
    Finds the most recent active trade for a given coin symbol.
    """
    if not supabase:
        logger.error("Supabase client not available.")
        return None

    try:
        # Look for trades with status 'OPEN' for this symbol
        response = supabase.from_("trades").select("*").eq("coin_symbol", symbol).eq("status", "OPEN").order("timestamp", desc=True).limit(1).execute()

        if response.data:
            logger.info(f"Found active trade for {symbol}: ID {response.data[0]['id']}")
            return response.data[0]
        else:
            logger.info(f"No active trade found for {symbol}.")
            return None
    except Exception as e:
        logger.error(f"Error querying for active trade for {symbol}: {e}", exc_info=True)
        return None

async def find_trade_by_timestamp(timestamp: str) -> Optional[Dict[str, Any]]:
    """
    Find trade by timestamp match using a time range for robustness.
    This handles millisecond precision issues.
    """
    if not supabase:
        logger.error("Supabase client not available.")
        return None

    try:
        # 1. Clean the timestamp string
        clean_timestamp_str = timestamp.replace('T', ' ').rstrip('Z')
        logger.info(f"Querying for timestamp: original='{timestamp}', cleaned='{clean_timestamp_str}'")

        # 2. Convert to datetime object
        dt_object = datetime.fromisoformat(clean_timestamp_str)

        # 3. Create a small time range (e.g., one millisecond) to handle precision differences
        start_time = dt_object
        end_time = dt_object + timedelta(milliseconds=1)

        # 4. Use gte (>=) and lt (<) for the range query
        response = supabase.from_("trades").select("*") \
            .gte("timestamp", start_time.isoformat()) \
            .lt("timestamp", end_time.isoformat()) \
            .order("timestamp", desc=True).limit(1).execute()

        if response.data:
            logger.info(f"Found trade by timestamp range for {clean_timestamp_str}: ID {response.data[0]['id']}")
            return response.data[0]
        else:
            logger.info(f"No trade found in timestamp range for: {clean_timestamp_str}")
            return None

    except Exception as e:
        logger.error(f"Error finding trade by timestamp: {e}", exc_info=True)
        return None

async def find_trade_by_content(content: str) -> Optional[Dict[str, Any]]:
    """
    Find trade by exact content string match.
    Used for initial signals that don't have a trade reference.
    DEPRECATED: Use find_trade_by_timestamp instead.
    """
    if not supabase:
        logger.error("Supabase client not available.")
        return None

    try:
        # Find trade by exact content match, get the most recent one
        response = supabase.from_("trades").select("*").eq("content", content).order("timestamp", desc=True).limit(1).execute()

        if response.data:
            logger.info(f"Found trade by content: ID {response.data[0]['id']}")
            return response.data[0]
        else:
            logger.info(f"No trade found for content: {content[:50]}...")
            return None

    except Exception as e:
        logger.error(f"Error finding trade by content: {e}", exc_info=True)
        return None

async def find_trade_by_signal_id(signal_id: str) -> Optional[Dict[str, Any]]:
    """
    Find trade by signal_id field.
    Used for follow-up signals that reference the original trade.
    """
    if not supabase:
        logger.error("Supabase client not available.")
        return None

    try:
        # Find trade by signal_id - this should match the 'trade' field from follow-up signals
        response = supabase.from_("trades").select("*").eq("signal_id", signal_id).execute()

        if response.data:
            logger.info(f"Found trade by signal_id {signal_id}: ID {response.data[0]['id']}")
            return response.data[0]
        else:
            logger.info(f"No trade found for signal_id: {signal_id}")
            return None

    except Exception as e:
        logger.error(f"Error finding trade by signal_id {signal_id}: {e}", exc_info=True)
        return None

async def find_trade_by_discord_id(discord_id: str) -> Optional[Dict[str, Any]]:
    """
    Find a trade by its unique Discord message ID.
    """
    if not supabase:
        logger.error("Supabase client not available.")
        return None

    try:
        response = supabase.from_("trades").select("*").eq("discord_id", discord_id).limit(1).execute()

        if response.data:
            logger.info(f"Found trade by discord_id {discord_id}: ID {response.data[0]['id']}")
            return response.data[0]
        else:
            logger.info(f"No trade found for discord_id: {discord_id}")
            return None

    except Exception as e:
        logger.error(f"Error finding trade by discord_id {discord_id}: {e}", exc_info=True)
        return None

async def update_existing_trade(signal_id: str = None, trade_id: int = None, updates: Dict = None) -> bool:
    """
    Update an existing trade row with new information.
    Can find by signal_id or trade_id.
    """
    if not supabase:
        logger.error("Supabase client not available.")
        return False

    if not updates:
        logger.error("No updates provided.")
        return False

    try:
        if trade_id:
            # For updates using database ID
            response = supabase.from_("trades").update(updates).eq("id", trade_id).execute()
        elif signal_id:
            # For updates using signal_id
            response = supabase.from_("trades").update(updates).eq("signal_id", signal_id).execute()
        else:
            logger.error("Must provide either signal_id or trade_id")
            return False

        logger.info(f"Updated trade with: {updates}")
        return True

    except Exception as e:
        logger.error(f"Error updating trade: {e}", exc_info=True)
        return False

async def save_signal_to_db(signal_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Saves a new signal record to the database.
    """
    if not supabase:
        logger.error("Supabase client not available.")
        return None

    try:
        response = supabase.from_("trades").insert(signal_data).execute()

        if response.data:
            logger.info(f"Successfully saved signal to database. ID: {response.data[0]['id']}")
            return response.data[0]
        else:
            logger.error("Failed to save signal to database: no data returned")
            return None

    except Exception as e:
        logger.error(f"Error saving signal to database: {e}", exc_info=True)
        return None

async def save_alert_to_database(alert_data: Dict[str, Any]) -> bool:
    """
    Saves an alert record to the alerts table.
    """
    if not supabase:
        logger.error("Supabase client not available.")
        return False

    try:
        response = supabase.from_("alerts").insert(alert_data).execute()

        if response.data:
            logger.info(f"Successfully saved alert to database. ID: {response.data[0]['id']}")
            return True
        else:
            logger.error("Failed to save alert to database: no data returned")
            return False

    except Exception as e:
        logger.error(f"Error saving alert to database: {e}", exc_info=True)
        return False

async def update_existing_alert(alert_id: int, updates: Dict) -> bool:
    """
    Updates an existing alert record in the database.
    """
    if not supabase:
        logger.error("Supabase client not available.")
        return False

    if not updates:
        logger.error("No updates provided for alert.")
        return False

    try:
        response = supabase.from_("alerts").update(updates).eq("id", alert_id).execute()
        logger.info(f"Successfully updated alert ID {alert_id} with: {updates}")
        return True
    except Exception as e:
        logger.error(f"Error updating alert ID {alert_id}: {e}", exc_info=True)
        return False

async def update_trade_status(trade_group_id: str, is_active: bool):
    """
    Updates the is_active status of a trade group.
    """
    if not supabase:
        logger.error("Supabase client not available.")
        return None

    try:
        supabase.from_("trades").update({"is_active": is_active}).eq("trade_group_id", trade_group_id).execute()
        logger.info(f"Set is_active={is_active} for trade group {trade_group_id}")
    except Exception as e:
        logger.error(f"Error updating trade status for {trade_group_id}: {e}", exc_info=True)