"""
Discord Bot Configuration Management

This module handles all configuration-related functionality for the Discord bot,
including environment variable loading, API key validation, and component configuration.
"""

import os
import logging
from typing import Optional, Dict, Any
from dotenv import load_dotenv
from supabase import create_client, Client

from config import settings

logger = logging.getLogger(__name__)


class BotConfig:
    """
    Manages Discord bot configuration and initialization.
    
    Responsibilities:
    - Load and validate environment variables
    - Initialize external service connections
    - Provide configuration validation
    - Manage component configuration
    """
    
    def __init__(self):
        """Initialize bot configuration."""
        self._load_environment()
        self._validate_configuration()
        
    def _load_environment(self) -> None:
        """Load environment variables from .env file."""
        load_dotenv()
        logger.info("Environment variables loaded")
        
    def _validate_configuration(self) -> None:
        """Validate that all required configuration is present."""
        required_settings = [
            ('BINANCE_API_KEY', settings.BINANCE_API_KEY),
            ('BINANCE_API_SECRET', settings.BINANCE_API_SECRET),
            ('SUPABASE_URL', settings.SUPABASE_URL),
            ('SUPABASE_KEY', settings.SUPABASE_KEY),
        ]
        
        missing_settings = []
        for setting_name, setting_value in required_settings:
            if not setting_value:
                missing_settings.append(setting_name)
                
        if missing_settings:
            error_msg = f"Missing required configuration: {', '.join(missing_settings)}"
            logger.critical(error_msg)
            raise ValueError(error_msg)
            
        logger.info("Configuration validation passed")
        
    def get_binance_config(self) -> Dict[str, Any]:
        """Get Binance API configuration."""
        return {
            'api_key': settings.BINANCE_API_KEY,
            'api_secret': settings.BINANCE_API_SECRET,
            'is_testnet': settings.BINANCE_TESTNET
        }
        
    def get_supabase_config(self) -> Dict[str, Any]:
        """Get Supabase configuration."""
        return {
            'url': settings.SUPABASE_URL,
            'key': settings.SUPABASE_KEY
        }
        
    def get_telegram_config(self) -> Dict[str, Any]:
        """Get Telegram configuration."""
        return {
            'bot_token': settings.TELEGRAM_BOT_TOKEN,
            'chat_id': settings.TELEGRAM_NOTIFICATION_CHAT_ID
        }
        
    def create_supabase_client(self) -> Client:
        """Create and return a Supabase client."""
        config = self.get_supabase_config()
        return create_client(config['url'], config['key'])
        
    def is_testnet(self) -> bool:
        """Check if running in testnet mode."""
        return settings.BINANCE_TESTNET
        
    def get_logging_config(self) -> Dict[str, Any]:
        """Get logging configuration."""
        return {
            'level': logging.INFO,
            'format': '%(asctime)s - %(name)s - %(levelname)s - [DiscordBot] - %(message)s'
        }
