import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
  """
  Configuration settings for the trading bot
  ALL SENSITIVE INFORMATION IS LOADED FROM ENVIRONMENT VARIABLES
  """

  # Telegram Configuration
  TELEGRAM_API_ID: int = int(os.getenv("TELEGRAM_API_ID", 0))
  TELEGRAM_API_HASH: str = os.getenv("TELEGRAM_API_HASH", "")
  TELEGRAM_PHONE: str = os.getenv("TELEGRAM_PHONE", "")
  TARGET_GROUP: str = os.getenv("TARGET_GROUP", "")
  TARGET_BOT: str = os.getenv("TARGET_BOT", "")

  # EXCHANGE CONFIGURATION
  EXCHANGE: str = os.getenv("EXCHANGE", "yobit").lower()
  YOBIT_API_KEY: str = os.getenv("YOBIT_API_KEY", "")
  YOBIT_API_SECRET: str = os.getenv("YOBIT_API_SECRET", "")
  BASE_CURRENCY: str = os.getenv("BASE_CURRENCY", "usd").lower()


  # Trading Parameters
  RISK_PERCENTAGE: float = float(os.getenv("RISK_PERCENTAGE", 1.0))
  MINIMUM_TRADE_AMOUNT: float = float(os.getenv("MINIMUM_TRADE_AMOUNT", 10.0))
  SLIPPAGE_PERCENTAGE: float = float(os.getenv("SLIPPAGE_PERCENTAGE", 1.0))

   # --- CoinGecko Configuration ---
    # Base URL for the CoinGecko API
  COINGECKO_API_URL: str = "https://api.coingecko.com/api/v3"
    # CoinGecko API rate limit delay in seconds (e.g., 2 seconds for free tier 30 calls/min)
  COINGECKO_RATE_LIMIT_DELAY: float = float(os.getenv("COINGECKO_RATE_LIMIT_DELAY", 2.0))

    # --- Logging Configuration ---
    # Logging level (e.g., INFO, DEBUG, WARNING, ERROR)
  LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO").upper()
    # Path to the log file
  LOG_FILE: str = os.getenv("LOG_FILE", "bot.log")

# Create a settings instance to be imported throughout the application
settings = Settings()

# Basic validation for critical settings
if not settings.TELEGRAM_API_ID or not settings.TELEGRAM_API_HASH or not settings.TELEGRAM_PHONE:
    raise ValueError("Telegram API ID, API Hash, and Phone Number must be set in environment variables.")
if not settings.TARGET_GROUP or not settings.TARGET_BOT:
    raise ValueError("Target Telegram Group and Bot Username must be set in environment variables.")
if settings.EXCHANGE == "yobit" and (not settings.YOBIT_API_KEY or not settings.YOBIT_API_SECRET):
    raise ValueError("YoBit API Key and Secret must be set for YoBit exchange.")
