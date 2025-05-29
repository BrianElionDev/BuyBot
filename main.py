# crypto-signal-bot/main.py

import asyncio
import logging
import sys
import os

# Add the project root to the Python path to allow absolute imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from config.settings import settings
from telegram_monitor.bot_listener import TelegramSignalMonitor
from exchanges.yobit import YoBitExchange
from trading.trading_engine import TradingEngine

# Configure logging
def setup_logging():
    """
    Sets up the logging configuration for the application.
    Logs messages to both console and a file.
    """
    log_level = getattr(logging, settings.LOG_LEVEL, logging.INFO)
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout), # Log to console
            logging.FileHandler(settings.LOG_FILE) # Log to file
        ]
    )
    # Set specific loggers to WARNING or ERROR if they are too verbose
    logging.getLogger('telethon').setLevel(logging.WARNING)
    logging.getLogger('aiohttp').setLevel(logging.WARNING)
    logging.getLogger('asyncio').setLevel(logging.WARNING)

async def main():
    """
    Main function to initialize and start the cryptocurrency trading bot.
    It sets up logging, initializes exchange and trading components,
    and starts the Telegram signal monitor.
    """
    setup_logging()
    logger = logging.getLogger(__name__)
    logger.info("🚀 Starting Automated Crypto Trading Bot...")

    # Initialize exchange (YoBit for now)
    # In a more complex system, you might use a factory pattern here
    # to select the exchange based on settings.EXCHANGE
    exchange = YoBitExchange()

    # Initialize trading engine, injecting the exchange dependency
    trading_engine = TradingEngine(exchange)

    # Initialize Telegram monitor, injecting the trading engine dependency
    monitor = TelegramSignalMonitor(trading_engine)

    try:
        # Start the Telegram monitoring loop
        await monitor.start()
    except Exception as e:
        logger.critical(f"Bot encountered a critical error and stopped: {e}", exc_info=True)
    finally:
        # Ensure all aiohttp sessions are closed gracefully
        await trading_engine.close_all_sessions()
        logger.info("Bot stopped. All sessions closed.")

if __name__ == "__main__":

    asyncio.run(main())