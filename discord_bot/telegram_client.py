import httpx
import logging

logger = logging.getLogger(__name__)

# The URL should ideally be in a config file
TELEGRAM_SERVICE_URL = "http://127.0.0.1:8000/api/v1/notify"

async def send_telegram_notification(message: str):
    """
    Sends a notification message to the Telegram Bot Service.
    """
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                TELEGRAM_SERVICE_URL,
                json={"message": message},
                timeout=10.0
            )
            response.raise_for_status()  # Raise an exception for bad status codes
            logger.info("Successfully sent notification to Telegram service.")
        except httpx.RequestError as e:
            logger.error(f"Failed to send notification to Telegram service: {e}")