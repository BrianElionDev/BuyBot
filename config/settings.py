import os
import logging
from dotenv import load_dotenv
from typing import Optional

# Load environment variables from .env file
load_dotenv()

class Settings:
    """
    Production-grade configuration settings for the crypto trading bot.
    All sensitive information is loaded from environment variables.
    """

    # Telegram Configuration
    TELEGRAM_API_ID: int = int(os.getenv("TELEGRAM_API_ID", "0"))
    TELEGRAM_API_HASH: str = os.getenv("TELEGRAM_API_HASH", "")
    TELEGRAM_PHONE: str = os.getenv("TELEGRAM_PHONE", "")

    # Target group - specifically for Rubicon Whale Tracker
    TARGET_GROUP: str = os.getenv("TARGET_GROUP", "Rubicon Whale Tracker")

    # Exchange Configuration (YoBit)
    YOBIT_API_KEY: str = os.getenv("YOBIT_API_KEY", "")
    YOBIT_API_SECRET: str = os.getenv("YOBIT_API_SECRET", "")

    # Trading Parameters
    BASE_CURRENCY: str = os.getenv("BASE_CURRENCY", "usd").lower()
    RISK_PERCENTAGE: float = float(os.getenv("RISK_PERCENTAGE", "2.0"))  # 2% of balance per trade
    MINIMUM_TRADE_AMOUNT: float = float(os.getenv("MINIMUM_TRADE_AMOUNT", "10.0"))  # $10 minimum
    MAXIMUM_TRADE_AMOUNT: float = float(os.getenv("MAXIMUM_TRADE_AMOUNT", "100.0"))  # $100 maximum
    SLIPPAGE_TOLERANCE: float = float(os.getenv("SLIPPAGE_TOLERANCE", "2.0"))  # 2% slippage

    # Price difference threshold for trade execution
    PRICE_DIFFERENCE_THRESHOLD: float = float(os.getenv("PRICE_DIFFERENCE_THRESHOLD", "5.0"))  # 5%

    # CoinGecko Configuration
    COINGECKO_RATE_LIMIT: float = float(os.getenv("COINGECKO_RATE_LIMIT", "1.0"))  # 1 second between calls

    # Logging Configuration
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO").upper()
    LOG_FILE: str = os.getenv("LOG_FILE", "crypto_trading_bot.log")

    # Signal parsing configuration
    SIGNAL_KEYWORDS: list = ["Trade detected:", "👋 Trade detected:"]

    # Cooldown period between trades for the same token (in seconds)
    TRADE_COOLDOWN: int = int(os.getenv("TRADE_COOLDOWN", "300"))  # 5 minutes

    def validate(self) -> bool:
        """
        Validates that all required configuration values are set.

        Returns:
            bool: True if all required settings are valid, False otherwise.
        """
        errors = []

        # Required Telegram settings
        if not self.TELEGRAM_API_ID or self.TELEGRAM_API_ID == 0:
            errors.append("TELEGRAM_API_ID is required")
        if not self.TELEGRAM_API_HASH:
            errors.append("TELEGRAM_API_HASH is required")
        if not self.TELEGRAM_PHONE:
            errors.append("TELEGRAM_PHONE is required")

        # Required YoBit settings
        if not self.YOBIT_API_KEY:
            errors.append("YOBIT_API_KEY is required")
        if not self.YOBIT_API_SECRET:
            errors.append("YOBIT_API_SECRET is required")

        # Validate numeric ranges
        if self.RISK_PERCENTAGE <= 0 or self.RISK_PERCENTAGE > 100:
            errors.append("RISK_PERCENTAGE must be between 0 and 100")
        if self.MINIMUM_TRADE_AMOUNT <= 0:
            errors.append("MINIMUM_TRADE_AMOUNT must be positive")
        if self.MAXIMUM_TRADE_AMOUNT <= self.MINIMUM_TRADE_AMOUNT:
            errors.append("MAXIMUM_TRADE_AMOUNT must be greater than MINIMUM_TRADE_AMOUNT")

        if errors:
            for error in errors:
                logging.error(f"Configuration error: {error}")
            return False

        return True

# Create global settings instance
settings = Settings()

# Validate settings on import
if not settings.validate():
    raise ValueError("Invalid configuration. Please check your environment variables.")