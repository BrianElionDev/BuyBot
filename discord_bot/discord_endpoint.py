from fastapi import APIRouter, HTTPException, BackgroundTasks, Body
from pydantic import BaseModel
from typing import Dict, List, Optional, Any
import logging
from ..bot.discord_bot import DiscordBot

logger = logging.getLogger(__name__)
router = APIRouter()

# In a real application, you'd manage this instance better (e.g., singleton)
discord_bot = DiscordBot()

class DiscordSignal(BaseModel):
    timestamp: str
    content: Dict
    structured: str

class DiscordSignalBatch(BaseModel):
    signals: List[DiscordSignal]

async def process_signal_background(signal: DiscordSignal):
    """Process a signal in the background."""
    try:
        success, message = await discord_bot.process_signal(signal.dict())
        if not success:
            logger.error(f"Failed to process signal: {message}")
    except Exception as e:
        logger.error(f"Error processing signal in background: {str(e)}")

@router.post("/discord/signal")
async def receive_signal(signal: DiscordSignal, background_tasks: BackgroundTasks):
    """
    Receive a single Discord signal.

    Args:
        signal: The Discord signal to process
        background_tasks: FastAPI background tasks

    Returns:
        Dict containing processing status
    """
    try:
        # Add signal processing to background tasks
        background_tasks.add_task(process_signal_background, signal)

        return {
            "status": "success",
            "message": "Signal received and queued for processing"
        }
    except Exception as e:
        logger.error(f"Error receiving signal: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/discord/signals")
async def receive_signals(signals: DiscordSignalBatch, background_tasks: BackgroundTasks):
    """
    Receive multiple Discord signals.

    Args:
        signals: Batch of Discord signals to process
        background_tasks: FastAPI background tasks

    Returns:
        Dict containing processing status
    """
    try:
        # Add each signal to background tasks
        for signal in signals.signals:
            background_tasks.add_task(process_signal_background, signal)

        return {
            "status": "success",
            "message": f"{len(signals.signals)} signals received and queued for processing"
        }
    except Exception as e:
        logger.error(f"Error receiving signals: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/webhook", status_code=200)
async def handle_discord_webhook(payload: Dict[str, Any] = Body(...)):
    """
    Handles incoming signals from a Discord webhook.
    The payload is expected to be a list of signal objects.
    """
    logger.info(f"Received webhook payload: {payload}")
    if not isinstance(payload, list):
        raise HTTPException(status_code=400, detail="Payload must be a list of signals.")

    # We can process multiple signals in parallel
    for signal_data in payload:
        try:
            success, message = await discord_bot.process_signal(signal_data)
            if success:
                logger.info(f"Signal processed successfully: {message}")
            else:
                logger.warning(f"Failed to process signal: {message}")
        except Exception as e:
            logger.error(f"Error processing a signal from webhook: {e}", exc_info=True)
            # Continue to next signal

    return {"status": "Webhook processed"}