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
    # Create logs directory if it doesn't exist
    os.makedirs('logs', exist_ok=True)

    # Configure console handler with UTF-8 encoding
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)

    # Configure file handler with UTF-8 encoding
    file_handler = logging.FileHandler('logs/trading_bot.log', encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)

    # Create formatter with emoji support
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