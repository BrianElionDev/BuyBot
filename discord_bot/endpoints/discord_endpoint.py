"""
Discord Endpoint Module
This module contains the Discord API endpoint for backward compatibility.
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field
from typing import Optional
from discord_bot.discord_bot import discord_bot
from discord_bot.models import InitialDiscordSignal
from config.logging_config import get_endpoint_logger, get_trade_logger
from discord_bot.utils.activity_monitor import ActivityMonitor

logger = get_endpoint_logger()
trade_logger = get_trade_logger()
router = APIRouter()
class DiscordUpdateSignal(BaseModel):
    timestamp: str
    content: str
    trade: str = Field(..., description="Reference to original trade signal_id")
    discord_id: str
    trader: Optional[str] = None
    structured: Optional[str] = None # Not always present in updates

async def process_initial_signal_background(signal: InitialDiscordSignal):
    """Process an initial signal in the background ."""
    try:
        logger.info(f"[ENDPOINT] Processing initial signal from {signal.trader} (ID: {signal.discord_id})")
        result = await discord_bot.process_initial_signal(signal)
        if result.get("status") != "success":
            logger.error(f"[ENDPOINT] Failed to process initial signal: {result.get('message')}")

            logger.info("[ENDPOINT] Signal processing failed - bot already sent notification")
        else:
            logger.info(f"[ENDPOINT] Initial signal processed successfully: {result.get('message')}")
    except Exception as e:
        logger.error(f"[ENDPOINT] Error processing initial signal in background: {str(e)}")

        logger.info("[ENDPOINT] Signal processing exception - bot should have sent notification")

async def process_update_signal_background(signal: DiscordUpdateSignal):
    """Process an update signal in the background."""
    try:
        logger.info(f"[ENDPOINT] Processing update signal for trade {signal.trade} from {signal.trader}")
        result = await discord_bot.process_update_signal(signal.model_dump())
        if result.get("status") != "success":
            logger.error(f"[ENDPOINT] Failed to process update signal: {result.get('message')}")
        else:
            logger.info(f"[ENDPOINT] Update signal processed successfully: {result.get('message')}")
    except Exception as e:
        logger.error(f"[ENDPOINT] Error processing update signal in background: {str(e)}")

@router.post("/discord/signal", summary="Receive an initial trade signal")
async def receive_initial_signal(signal: InitialDiscordSignal, background_tasks: BackgroundTasks):
    """
    Receives an initial Discord signal to open a new trade.

    This endpoint should be used when a new trade is announced. It finds a pre-existing
    trade row in the database by its timestamp, parses the content using AI to determine
    trade parameters, and executes the trade via the trading engine.
    """
    import time
    start_time = time.time()

    logger.info("[ENDPOINT] Entry signal notification will be handled by bot processing")

    try:
        logger.info(f"[ENDPOINT] Received initial signal from {signal.trader} (ID: {signal.discord_id})")
        ActivityMonitor.mark_activity("entry")

        # Process signal in background
        background_tasks.add_task(process_initial_signal_background, signal)

        duration = time.time() - start_time
        logger.info(f"[ENDPOINT] Initial signal queued for processing in {duration:.3f}s")

        return {
            "status": "success",
            "message": "Initial signal received and queued for processing"
        }
    except Exception as e:
        duration = time.time() - start_time
        logger.error(f"[ENDPOINT] Error receiving initial signal after {duration:.3f}s: {str(e)}")

        logger.error(f"[ENDPOINT] Endpoint failed, bot processing may still handle notifications")

        raise HTTPException(status_code=500, detail=str(e))

@router.post("/discord/signal/update", summary="Receive a trade update signal")
async def receive_update_signal(signal: DiscordUpdateSignal, background_tasks: BackgroundTasks):
    """
    Receives a follow-up signal to update an existing trade.

    This endpoint handles updates for trades that are already active, such as
    "stop loss hit" or "position closed". It finds the original trade using the
    `trade` (signal_id) field and updates its status in the database.
    """
    import time
    start_time = time.time()

    logger.info("[ENDPOINT] Update signal notification will be handled by bot processing")

    try:
        logger.info(f"[ENDPOINT] Received update signal for trade {signal.trade} from {signal.trader}")
        ActivityMonitor.mark_activity("update")

        background_tasks.add_task(process_update_signal_background, signal)

        duration = time.time() - start_time
        logger.info(f"[ENDPOINT] Update signal queued for processing in {duration:.3f}s")

        return {
            "status": "success",
            "message": "Update signal received and queued for processing"
        }
    except Exception as e:
        duration = time.time() - start_time
        logger.error(f"[ENDPOINT] Error receiving update signal after {duration:.3f}s: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/discord/signal/update/test", summary="Receive a trade update signal")
async def receive_update_signal_test(signal: DiscordUpdateSignal):
    """
    Receives a follow-up signal to update an existing trade.

    This endpoint handles updates for trades that are already active, such as
    "stop loss hit" or "position closed". It finds the original trade using the
    `trade` (signal_id) field and updates its status in the database.
    """
    try:
        result = discord_bot.parse_alert_content(signal.content)
        return {
            "status": "success",
            "data": result,
        }
    except Exception as e:
        logger.error(f"Error receiving update signal: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
