import os
import logging
from dotenv import load_dotenv

def reload_env():
    """Reload environment variables from .env file."""
    load_dotenv(override=True)  # override=True forces reload

    # Update global variables with new values
    global BINANCE_API_KEY, BINANCE_API_SECRET, BINANCE_TESTNET
    global KUCOIN_API_KEY, KUCOIN_API_SECRET, KUCOIN_API_PASSPHRASE, KUCOIN_TESTNET
    global SUPABASE_URL, SUPABASE_KEY
    global OPENAI_API_KEY
    global TELEGRAM_BOT_TOKEN, TELEGRAM_NOTIFICATION_CHAT_ID

    # Reload all environment variables
    BINANCE_API_KEY = os.getenv("BINANCE_API_KEY")
    BINANCE_API_SECRET = os.getenv("BINANCE_API_SECRET")
    BINANCE_TESTNET = os.getenv("BINANCE_TESTNET", "True").lower() == "true"

    KUCOIN_API_KEY = os.getenv("KUCOIN_API_KEY")
    KUCOIN_API_SECRET = os.getenv("KUCOIN_API_SECRET")
    KUCOIN_API_PASSPHRASE = os.getenv("KUCOIN_API_PASSPHRASE")
    KUCOIN_TESTNET = False

    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
    SUPABASE_URL = os.getenv("SUPABASE_URL")
    SUPABASE_KEY = os.getenv("SUPABASE_KEY")

    # Telegram Bot Configuration (for notifications)
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "YOUR_TELEGRAM_BOT_TOKEN")
    TELEGRAM_NOTIFICATION_CHAT_ID = os.getenv("TELEGRAM_NOTIFICATION_CHAT_ID", "")

    logging.info("Environment variables reloaded successfully")
    if BINANCE_API_KEY:
        logging.info(f"Using Binance API Key: {BINANCE_API_KEY[:10]}...{BINANCE_API_KEY[-5:]}")
    else:
        logging.info("Using Binance API Key: None")


# Force reload on import with override=True to ensure fresh values
load_dotenv(override=True)

# Binance
BINANCE_API_KEY = os.getenv("BINANCE_API_KEY")
BINANCE_API_SECRET = os.getenv("BINANCE_API_SECRET")
BINANCE_TESTNET = os.getenv("BINANCE_TESTNET", "True").lower() == "true"

# KuCoin
KUCOIN_API_KEY = os.getenv("KUCOIN_API_KEY")
KUCOIN_API_SECRET = os.getenv("KUCOIN_API_SECRET")
KUCOIN_API_PASSPHRASE = os.getenv("KUCOIN_API_PASSPHRASE")
KUCOIN_TESTNET = False

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

# Take Profit Configuration
DEFAULT_TP_PERCENTAGE = float(os.getenv("DEFAULT_TP_PERCENTAGE", "5.0").replace('%', ''))
SIGNAL_TP_POSITION_PERCENTAGE = float(os.getenv("SIGNAL_TP_POSITION_PERCENTAGE", "50.0").replace('%', ''))
TP_AUDIT_INTERVAL = int(os.getenv("TP_AUDIT_INTERVAL", "30"))

# Telegram Bot Configuration (for notifications)
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "YOUR_TELEGRAM_BOT_TOKEN")
TELEGRAM_NOTIFICATION_CHAT_ID = os.getenv("TELEGRAM_NOTIFICATION_CHAT_ID", "")

# Fee Calculator Configuration
USE_FIXED_FEE_CALCULATOR = os.getenv("USE_FIXED_FEE_CALCULATOR", "True").lower() == "true"
FIXED_FEE_RATE = float(os.getenv("FIXED_FEE_RATE", "0.0002"))

# Target Traders Configuration
_RAW_TRADERS = os.getenv("TARGET_TRADERS", "")
TARGET_TRADERS = [
    t.strip().strip('"').strip("'")
    for t in _RAW_TRADERS.split(",")
    if t.strip().strip('"').strip("'")
]

# Inactivity Alert Configuration
INACTIVITY_ALERT_ENABLED = os.getenv("INACTIVITY_ALERT_ENABLED", "True").lower() == "true"
INACTIVITY_THRESHOLD_HOURS = int(os.getenv("INACTIVITY_THRESHOLD_HOURS", "12"))
INACTIVITY_ALERT_COOLDOWN_HOURS = int(os.getenv("INACTIVITY_ALERT_COOLDOWN_HOURS", "12"))
INACTIVITY_ALERT_MESSAGE = os.getenv("INACTIVITY_ALERT_MESSAGE", "Discord is awefully silet today zzz")