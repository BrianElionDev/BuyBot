"""
Discord Bot Component Initializer

This module handles the initialization of all Discord bot components,
including external services, internal components, and dependencies.
"""

import logging
from typing import Optional, Tuple, Any
from supabase import Client

from src.bot.trading_engine import TradingEngine
from src.services.pricing.price_service import PriceService
from src.exchange import BinanceExchange
from src.exchange.kucoin import KucoinExchange
from src.services.notifications.telegram_service import TelegramService
from discord_bot.database import DatabaseManager
from discord_bot.signal_processing import DiscordSignalParser
from discord_bot.websocket import DiscordBotWebSocketManager

from .bot_config import BotConfig

logger = logging.getLogger(__name__)


class BotInitializer:
    """
    Handles initialization of all Discord bot components.

    Responsibilities:
    - Initialize external service connections
    - Create and configure internal components
    - Establish component dependencies
    - Provide component access
    """

    def __init__(self, config: BotConfig):
        """Initialize the bot initializer with configuration."""
        self.config = config
        self.components = {}
        self._initialize_components()

    def _initialize_components(self) -> None:
        """Initialize all bot components in the correct order."""
        try:
            # 1. Initialize Supabase client
            self._initialize_supabase()

            # 2. Initialize database manager
            self._initialize_database_manager()

            # 3. Initialize price service
            self._initialize_price_service()

            # 4. Initialize Binance exchange
            self._initialize_binance_exchange()

            # 5. Initialize KuCoin exchange
            self._initialize_kucoin_exchange()

            # 6. Initialize trading engine
            self._initialize_trading_engine()

            # 6. Initialize signal parser
            self._initialize_signal_parser()

            # 7. Initialize Telegram notifications
            self._initialize_telegram_notifications()

            # 8. Initialize WebSocket manager
            self._initialize_websocket_manager()

            logger.info("All Discord bot components initialized successfully")

        except Exception as e:
            logger.error(f"Failed to initialize bot components: {e}")
            raise

    def _initialize_supabase(self) -> None:
        """Initialize Supabase client."""
        try:
            supabase_client = self.config.create_supabase_client()
            self.components['supabase'] = supabase_client
            logger.info("Supabase client initialized")
        except Exception as e:
            logger.error(f"Failed to initialize Supabase client: {e}")
            raise

    def _initialize_database_manager(self) -> None:
        """Initialize database manager."""
        try:
            supabase_client = self.components['supabase']
            db_manager = DatabaseManager(supabase_client)
            self.components['db_manager'] = db_manager
            logger.info("Database manager initialized")
        except Exception as e:
            logger.error(f"Failed to initialize database manager: {e}")
            raise

    def _initialize_price_service(self) -> None:
        """Initialize price service."""
        try:
            price_service = PriceService()
            self.components['price_service'] = price_service
            logger.info("Price service initialized")
        except Exception as e:
            logger.error(f"Failed to initialize price service: {e}")
            raise

    def _initialize_binance_exchange(self) -> None:
        """Initialize Binance exchange."""
        try:
            binance_config = self.config.get_binance_config()
            binance_exchange = BinanceExchange(
                api_key=binance_config['api_key'],
                api_secret=binance_config['api_secret'],
                is_testnet=binance_config['is_testnet']
            )
            self.components['binance_exchange'] = binance_exchange
            logger.info("Binance exchange initialized")
        except Exception as e:
            logger.error(f"Failed to initialize Binance exchange: {e}")
            raise

    def _initialize_kucoin_exchange(self) -> None:
        """Initialize KuCoin exchange."""
        try:
            kucoin_config = self.config.get_kucoin_config()
            # Only initialize if all KuCoin credentials are available
            if all([kucoin_config['api_key'], kucoin_config['api_secret'], kucoin_config['api_passphrase']]):
                kucoin_exchange = KucoinExchange(
                    api_key=kucoin_config['api_key'],
                    api_secret=kucoin_config['api_secret'],
                    api_passphrase=kucoin_config['api_passphrase'],
                    is_testnet=kucoin_config['is_testnet']
                )
                self.components['kucoin_exchange'] = kucoin_exchange
                logger.info("KuCoin exchange initialized")
            else:
                logger.warning("KuCoin credentials incomplete - KuCoin exchange not initialized")
                self.components['kucoin_exchange'] = None
        except Exception as e:
            logger.error(f"Failed to initialize KuCoin exchange: {e}")
            self.components['kucoin_exchange'] = None

    def _initialize_trading_engine(self) -> None:
        """Initialize trading engine."""
        try:
            trading_engine = TradingEngine(
                price_service=self.components['price_service'],
                binance_exchange=self.components['binance_exchange'],
                db_manager=self.components['db_manager']
            )
            self.components['trading_engine'] = trading_engine
            logger.info("Trading engine initialized")
        except Exception as e:
            logger.error(f"Failed to initialize trading engine: {e}")
            raise

    def _initialize_signal_parser(self) -> None:
        """Initialize signal parser."""
        try:
            signal_parser = DiscordSignalParser()
            self.components['signal_parser'] = signal_parser
            logger.info("Signal parser initialized")
        except Exception as e:
            logger.error(f"Failed to initialize signal parser: {e}")
            raise

    def _initialize_telegram_notifications(self) -> None:
        """Initialize Telegram notification service."""
        try:
            telegram_config = self.config.get_telegram_config()
            telegram_notifications = TelegramService()
            self.components['telegram_notifications'] = telegram_notifications
            logger.info("Telegram notification service initialized")
        except Exception as e:
            logger.error(f"Failed to initialize Telegram notification service: {e}")
            raise

    def _initialize_websocket_manager(self) -> None:
        """Initialize WebSocket manager."""
        try:
            websocket_manager = DiscordBotWebSocketManager(
                bot=None,  # Will be set by DiscordBotCore
                db_manager=self.components['db_manager']
            )
            self.components['websocket_manager'] = websocket_manager
            logger.info("WebSocket manager initialized")
        except Exception as e:
            logger.error(f"Failed to initialize WebSocket manager: {e}")
            # Don't raise here, just log the error and continue
            self.components['websocket_manager'] = None

    def get_component(self, component_name: str) -> Any:
        """Get a specific component by name."""
        if component_name not in self.components:
            raise ValueError(f"Component '{component_name}' not found")
        return self.components[component_name]

    def get_all_components(self) -> dict:
        """Get all initialized components."""
        return self.components.copy()

    def is_initialized(self) -> bool:
        """Check if all components are initialized."""
        required_components = [
            'supabase', 'db_manager', 'price_service', 'binance_exchange',
            'trading_engine', 'signal_parser', 'telegram_notifications', 'websocket_manager'
        ]
        return all(component in self.components for component in required_components)
