from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
import logging

# This is a placeholder import. The actual bot instance will be passed in.
from src.bot.telegram_bot import TelegramBot

logger = logging.getLogger(__name__)

class Notification(BaseModel):
    message: str

def create_notification_router(bot: TelegramBot) -> APIRouter:
    router = APIRouter()

    @router.post("/notify", status_code=202)
    async def send_notification(notification: Notification):
        """
        Receives a message and sends it to the Telegram notification group.
        """
        try:
            logger.info(f"Received API request to send notification: {notification.message[:50]}...")
            await bot._send_notification(notification.message)
            return {"status": "Notification sent"}
        except Exception as e:
            logger.error(f"API failed to send notification: {e}")
            raise HTTPException(status_code=500, detail="Failed to send notification")

    return router