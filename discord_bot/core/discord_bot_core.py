"""
Discord Bot Core Orchestrator

This module contains the main Discord bot orchestrator that coordinates
all bot functionality and delegates specific responsibilities to other modules.
"""

import logging
import asyncio
from typing import Dict, Any, Optional, Tuple
from datetime import datetime, timezone

from .bot_config import BotConfig
from .bot_initializer import BotInitializer

logger = logging.getLogger(__name__)


class DiscordBotCore:
    """
    Main Discord bot orchestrator that coordinates all bot functionality.
    
    Responsibilities:
    - Coordinate between different bot components
    - Handle high-level bot operations
    - Manage bot lifecycle
    - Provide unified interface for bot operations
    """
    
    def __init__(self):
        """Initialize the Discord bot core."""
        self.config = BotConfig()
        self.initializer = BotInitializer(self.config)
        self.components = self.initializer.get_all_components()
        
        # Set up component references for easy access
        self.supabase = self.components['supabase']
        self.db_manager = self.components['db_manager']
        self.price_service = self.components['price_service']
        self.binance_exchange = self.components['binance_exchange']
        self.trading_engine = self.components['trading_engine']
        self.signal_parser = self.components['signal_parser']
        self.telegram_notifications = self.components['telegram_notifications']
        self.websocket_manager = self.components['websocket_manager']
        
        # Set the bot reference in WebSocket manager
        self.websocket_manager.bot = self
        
        logger.info(f"DiscordBotCore initialized with {'AI' if hasattr(self.signal_parser, 'client') and self.signal_parser.client else 'simple'} Signal Parser")
        
    async def start_websocket_sync(self) -> bool:
        """
        Start WebSocket real-time sync.
        
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            if hasattr(self.websocket_manager, 'start_sync'):
                success = await self.websocket_manager.start_sync()
                if success:
                    logger.info("WebSocket real-time sync started successfully")
                    return True
                else:
                    logger.error("Failed to start WebSocket sync")
                    return False
            else:
                logger.error("WebSocket manager does not have start_sync method")
                return False
        except Exception as e:
            logger.error(f"Error starting WebSocket sync: {e}")
            return False
            
    def get_websocket_status(self) -> dict:
        """
        Get WebSocket manager status.
        
        Returns:
            dict: WebSocket status information
        """
        if hasattr(self.websocket_manager, 'get_status'):
            return self.websocket_manager.get_status()
        else:
            return {
                'running': False,
                'initialized': False,
                'error': 'WebSocket manager not available'
            }
            
    async def close(self) -> None:
        """Close the bot and clean up resources."""
        try:
            if hasattr(self.websocket_manager, 'close'):
                await self.websocket_manager.close()
            logger.info("DiscordBotCore closed successfully")
        except Exception as e:
            logger.error(f"Error closing DiscordBotCore: {e}")
            
    def get_component(self, component_name: str) -> Any:
        """
        Get a specific component by name.
        
        Args:
            component_name: Name of the component to retrieve
            
        Returns:
            The requested component
            
        Raises:
            ValueError: If component not found
        """
        return self.initializer.get_component(component_name)
        
    def is_ready(self) -> bool:
        """
        Check if the bot is ready and all components are initialized.
        
        Returns:
            bool: True if ready, False otherwise
        """
        return self.initializer.is_initialized()
        
    def get_status(self) -> Dict[str, Any]:
        """
        Get comprehensive bot status information.
        
        Returns:
            dict: Bot status information
        """
        return {
            'initialized': self.is_ready(),
            'testnet': self.config.is_testnet(),
            'websocket_status': self.get_websocket_status(),
            'components': list(self.components.keys()),
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
