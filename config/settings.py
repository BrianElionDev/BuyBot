import os
import logging
from dotenv import load_dotenv

load_dotenv()

# Telegram
TELEGRAM_API_ID = int(os.getenv("TELEGRAM_API_ID", "0"))
TELEGRAM_API_HASH = os.getenv("TELEGRAM_API_HASH")
TELEGRAM_PHONE = os.getenv("TELEGRAM_PHONE")
TARGET_GROUP_ID = int(os.getenv("TARGET_GROUP_ID", "0"))  # The ID of the group to monitor
NOTIFICATION_GROUP_ID = int(os.getenv("NOTIFICATION_GROUP_ID", "0"))  # The ID of the group to send notifications to

# YoBit
YOBIT_API_KEY = os.getenv("YOBIT_API_KEY")
YOBIT_API_SECRET = os.getenv("YOBIT_API_SECRET")

# Trading
RISK_PERCENTAGE = float(os.getenv("RISK_PERCENTAGE", "2.0"))
MIN_TRADE_AMOUNT = float(os.getenv("MIN_TRADE_AMOUNT", "10.0"))
MAX_TRADE_AMOUNT = float(os.getenv("MAX_TRADE_AMOUNT", "100.0"))
PRICE_THRESHOLD = float(os.getenv("PRICE_THRESHOLD", "5.0"))  # % price difference
TRADE_COOLDOWN = int(os.getenv("TRADE_COOLDOWN", "300"))  # seconds

# Setup logging
def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler('logs/trading_bot.log')
        ]
    )
    logging.getLogger('telethon').setLevel(logging.WARNING)
    logging.getLogger('aiohttp').setLevel(logging.WARNING)