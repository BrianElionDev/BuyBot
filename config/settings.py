import os
import logging
from dotenv import load_dotenv

def reload_env():
    """Reload environment variables from .env file."""
    load_dotenv(override=True)  # override=True forces reload

    # Update global variables with new values
    global BINANCE_API_KEY, BINANCE_API_SECRET, BINANCE_TESTNET
    global TELEGRAM_API_ID, TELEGRAM_API_HASH, TELEGRAM_PHONE
    global TARGET_GROUP_ID, NOTIFICATION_GROUP_ID
    global SUPABASE_URL, SUPABASE_KEY
    global OPENAI_API_KEY
    # Reload all environment variables
    BINANCE_API_KEY = os.getenv("BINANCE_API_KEY")
    BINANCE_API_SECRET = os.getenv("BINANCE_API_SECRET")
    BINANCE_TESTNET = os.getenv("BINANCE_TESTNET", "True").lower() == "true"

    TELEGRAM_API_ID = int(os.getenv("TELEGRAM_API_ID", "0"))
    TELEGRAM_API_HASH = os.getenv("TELEGRAM_API_HASH")
    TELEGRAM_PHONE = os.getenv("TELEGRAM_PHONE")
    TARGET_GROUP_ID = int(os.getenv("TARGET_GROUP_ID", "0"))
    NOTIFICATION_GROUP_ID = int(os.getenv("NOTIFICATION_GROUP_ID", "0"))

    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
    SUPABASE_URL = os.getenv("SUPABASE_URL")
    SUPABASE_KEY = os.getenv("SUPABASE_KEY")

    logging.info("Environment variables reloaded successfully")
    if BINANCE_API_KEY:
        logging.info(f"Using Binance API Key: {BINANCE_API_KEY[:10]}...{BINANCE_API_KEY[-5:]}")
    else:
        logging.info("Using Binance API Key: None")


# Force reload on import with override=True to ensure fresh values
load_dotenv(override=True)

# Telegram
TELEGRAM_API_ID = int(os.getenv("TELEGRAM_API_ID", "0"))
TELEGRAM_API_HASH = os.getenv("TELEGRAM_API_HASH")
TELEGRAM_PHONE = os.getenv("TELEGRAM_PHONE")
TARGET_GROUP_ID = int(os.getenv("TARGET_GROUP_ID", "0"))
NOTIFICATION_GROUP_ID = int(os.getenv("NOTIFICATION_GROUP_ID", "0"))

# Binance
BINANCE_API_KEY = os.getenv("BINANCE_API_KEY")
BINANCE_API_SECRET = os.getenv("BINANCE_API_SECRET")
BINANCE_TESTNET = os.getenv("BINANCE_TESTNET", "True").lower() == "true"

# Supabase
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# OpenAI
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")


# Trading Parameters
RISK_PERCENTAGE = float(os.getenv("RISK_PERCENTAGE", "2.0"))
TRADE_AMOUNT = float(os.getenv("TRADE_AMOUNT", "101.0"))
TRADE_AMOUNT_PERCENTAGE = float(os.getenv("TRADE_AMOUNT_PERCENTAGE", "0"))
MIN_TRADE_AMOUNT = float(os.getenv("MIN_TRADE_AMOUNT", "10.0"))
MAX_TRADE_AMOUNT = float(os.getenv("MAX_TRADE_AMOUNT", "1000.0"))
PRICE_THRESHOLD = float(os.getenv("PRICE_THRESHOLD", "25.0"))
MEMECOIN_PRICE_THRESHOLD = float(os.getenv("MEMECOIN_PRICE_THRESHOLD", "100.0"))  # Higher threshold for memecoins
LOW_LIQUIDITY_PRICE_THRESHOLD = float(os.getenv("LOW_LIQUIDITY_PRICE_THRESHOLD", "50.0"))  # Medium threshold for low liquidity coins
SLIPPAGE_PERCENTAGE = float(os.getenv("SLIPPAGE_PERCENTAGE", "1.0"))
TRADE_COOLDOWN = int(os.getenv("TRADE_COOLDOWN", "300"))
LIMIT_ORDER_PRICE_THRESHOLD = float(os.getenv("LIMIT_ORDER_PRICE_THRESHOLD", "10.0"))  # Threshold for limit order price validation (10%)

# Telegram Bot Configuration
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "YOUR_TELEGRAM_BOT_TOKEN")

# Minimum ETH balance to maintain for gas fees
MIN_ETH_BALANCE = float(os.getenv("MIN_ETH_BALANCE", "0.01"))

# Fee Calculator Configuration
USE_FIXED_FEE_CALCULATOR = True  # Use simplified fixed fee cap instead of complex formulas
FIXED_FEE_RATE = 0.0002  # 0.02% fixed fee cap (can be 0.0002 or 0.0005)

# Trading Leverage Configuration
DEFAULT_LEVERAGE = float(os.getenv("LEVERAGE", "1"))  # Default leverage from .env, defaults to 1 if not found

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