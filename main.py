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
    import sys
    import os

    # Create logs directory if it doesn't exist
    os.makedirs('logs', exist_ok=True)

    # Configure console handler with UTF-8 encoding for Windows compatibility
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.DEBUG)

    # Configure file handler with UTF-8 encoding
    file_handler = logging.FileHandler('logs/trading_bot.log', encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)

    # Create formatter
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    console_handler.setFormatter(formatter)
    file_handler.setFormatter(formatter)

    # Configure root logger
    logging.basicConfig(
        level=logging.DEBUG,
        handlers=[console_handler, file_handler]
    )

    # Set Windows console to UTF-8 if on Windows
    if sys.platform.startswith('win'):
        try:
            # Try to set console to UTF-8 mode
            import locale
            locale.setlocale(locale.LC_ALL, 'en_US.UTF-8')
        except:
            pass
        try:
            # For Windows 10+ - enable UTF-8 mode
            os.system('chcp 65001 >nul 2>&1')
        except:
            pass

    logging.getLogger('telethon').setLevel(logging.WARNING)
    logging.getLogger('aiohttp').setLevel(logging.WARNING)

def main():
    """Main entry point for the trading bot"""
    setup_logging()
    logger = logging.getLogger(__name__)

    # Initialize components
    trading_engine = TradingEngine()
    telegram_monitor = TelegramMonitor(trading_engine, config)

    try:
        logger.info("[STARTUP] Starting Rubicon Whale Tracker Bot")
        logger.info(f"Monitoring group: {config.TARGET_GROUP_ID}")
        logger.info("Filtering for messages containing: 'Trade detected'")
        telegram_monitor.start()
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Bot error: {e}")
    finally:
        telegram_monitor.stop()
        logger.info("Bot shutdown complete")

if __name__ == "__main__":
    main()