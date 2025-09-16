#!/usr/bin/env python3
"""
Rubicon Trading Bot - Main Entry Point
"""
import asyncio
import logging
import sys
import os

def setup_logging():
    """Configure logging for the application."""
    from config.logging_config import setup_production_logging

    # Set up production logging
    logging_config = setup_production_logging()

    # Set Windows console to UTF-8 if on Windows
    if sys.platform.startswith('win'):
        try:
            import locale
            locale.setlocale(locale.LC_ALL, 'en_US.UTF-8')
        except:
            pass
        try:
            os.system('chcp 65001 >nul 2>&1')
        except:
            pass

    # Reduce noise from third-party libraries
    logging.getLogger('telethon').setLevel(logging.WARNING)
    logging.getLogger('aiohttp').setLevel(logging.WARNING)
    logging.getLogger('uvicorn').setLevel(logging.WARNING)
    logging.getLogger('websockets').setLevel(logging.WARNING)
    logging.getLogger('kucoin_universal_sdk').setLevel(logging.WARNING)

def main():
    """Main entry point for the trading bot."""
    try:
        # Import and start the Discord bot service
        from discord_bot.main import app
        import uvicorn

        logger.info("🚀 Starting Rubicon Trading Bot (Discord Service)...")
        logger.info("📡 Service will be available at: http://127.0.0.1:8001")
        logger.info("🔗 API Documentation: http://127.0.0.1:8001/docs")

        # Start the FastAPI server
        uvicorn.run(app, host="127.0.0.1", port=8001, log_level="info")

    except KeyboardInterrupt:
        logger.info("🛑 Shutting down...")
    except Exception as e:
        logger.error(f"❌ Error in main: {str(e)}")
        raise

if __name__ == "__main__":
    setup_logging()
    logger = logging.getLogger(__name__)
    main()