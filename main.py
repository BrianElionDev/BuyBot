#!/usr/bin/env python3
"""
Rubicon Trading Bot - Main Entry Point
"""
import asyncio
import logging
from src.bot.telegram_monitor import TelegramMonitor
from src.bot.trading_engine import TradingEngine
from config import settings as config

def setup_logging():
    """Configure logging for the application"""
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler('logs/trading_bot.log')
        ]
    )
    logging.getLogger('telethon').setLevel(logging.WARNING)
    logging.getLogger('aiohttp').setLevel(logging.WARNING)

async def main():
    """Main entry point for the trading bot"""
    setup_logging()
    logger = logging.getLogger(__name__)

    # Initialize components
    trading_engine = TradingEngine()
    telegram_monitor = TelegramMonitor(trading_engine, config)

    try:
        logger.info("🚀 Starting Rubicon Whale Tracker Bot")
        logger.info(f"Monitoring group: {config.TARGET_GROUP_ID}")
        logger.info("Filtering for messages starting with: 'Trade detected'")
        await telegram_monitor.start()
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Bot error: {e}")
    finally:
        await telegram_monitor.stop()
        await trading_engine.close()
        logger.info("Bot shutdown complete")

if __name__ == "__main__":
    asyncio.run(main())