"""
Centralized Logging Configuration

This module provides a production-ready logging system with separate handlers
for different log types to improve debugging and monitoring capabilities.

Log Categories:
- WebSocket: Console only, reduced verbosity
- Endpoints: File-based, detailed request/response logging
- Trade Processing: File-based, step-by-step trade execution logs
- Errors: File-based, critical errors only
- General: File-based, application-wide logs
"""

import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional


class ProductionLoggingConfig:
    """Production-ready logging configuration with separated log streams."""

    def __init__(self, log_dir: str = "logs"):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(exist_ok=True)

        # Create timestamped log files for better organization
        timestamp = datetime.now().strftime("%Y%m%d")
        self.log_files = {
            'endpoints': self.log_dir / f"endpoints_{timestamp}.log",
            'trade_processing': self.log_dir / f"trade_processing_{timestamp}.log",
            'websocket': self.log_dir / f"websocket_{timestamp}.log",
            'errors': self.log_dir / f"errors_{timestamp}.log",
            'general': self.log_dir / f"trading_bot_{timestamp}.log"
        }

        self._setup_loggers()

    def _setup_loggers(self):
        """Set up all logger configurations."""
        # Clear any existing handlers
        logging.getLogger().handlers.clear()

        # Configure root logger
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.INFO)

        # Suppress DEBUG logging from external libraries

        # Create formatters
        self._create_formatters()

        # Set up handlers
        self._setup_handlers()

        # Configure specific loggers
        self._configure_specific_loggers()

    def _create_formatters(self):
        """Create formatters for different log types."""
        # Detailed formatter for files
        self.file_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )

        # Simple formatter for console
        self.console_formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - %(message)s',
            datefmt='%H:%M:%S'
        )

        # Trade processing formatter (more readable)
        self.trade_formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - %(message)s',
            datefmt='%H:%M:%S'
        )

    def _setup_handlers(self):
        """Set up file and console handlers."""
        # General application logs (file only)
        general_handler = logging.FileHandler(
            self.log_files['general'],
            encoding='utf-8'
        )
        general_handler.setLevel(logging.INFO)
        general_handler.setFormatter(self.file_formatter)

        # Endpoint logs (file only)
        endpoint_handler = logging.FileHandler(
            self.log_files['endpoints'],
            encoding='utf-8'
        )
        endpoint_handler.setLevel(logging.INFO)
        endpoint_handler.setFormatter(self.file_formatter)

        # Trade processing logs (file only)
        trade_handler = logging.FileHandler(
            self.log_files['trade_processing'],
            encoding='utf-8'
        )
        trade_handler.setLevel(logging.INFO)
        trade_handler.setFormatter(self.trade_formatter)

        # Error logs (file only)
        error_handler = logging.FileHandler(
            self.log_files['errors'],
            encoding='utf-8'
        )
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(self.file_formatter)

        # WebSocket logs (console only)
        websocket_handler = logging.StreamHandler(sys.stdout)
        websocket_handler.setLevel(logging.WARNING)  # Reduced verbosity
        websocket_handler.setFormatter(self.console_formatter)

        # Store handlers for specific logger assignment
        self.handlers = {
            'general': general_handler,
            'endpoints': endpoint_handler,
            'trade_processing': trade_handler,
            'errors': error_handler,
            'websocket': websocket_handler
        }

    def _configure_specific_loggers(self):
        """Configure specific loggers with appropriate handlers."""
        # WebSocket loggers (console only, reduced verbosity)
        websocket_loggers = [
            'src.websocket',
            'src.websocket.core',
            'src.websocket.handlers',
            'discord_bot.websocket'
        ]

        for logger_name in websocket_loggers:
            logger = logging.getLogger(logger_name)
            logger.setLevel(logging.WARNING)
            logger.addHandler(self.handlers['websocket'])
            logger.propagate = False

        # Endpoint loggers (file only)
        endpoint_loggers = [
            'discord_bot.endpoints',
            'discord_bot.endpoints.discord_endpoint'
        ]

        for logger_name in endpoint_loggers:
            logger = logging.getLogger(logger_name)
            logger.setLevel(logging.INFO)
            logger.addHandler(self.handlers['endpoints'])
            logger.propagate = False

        # Trade processing loggers (file only)
        trade_loggers = [
            'discord_bot.signal_processing',
            'discord_bot.signal_processing.signal_processor',
            'discord_bot.signal_processing.signal_parser',
            'discord_bot.signal_processing.signal_validator',
            'discord_bot.discord_bot',
            'src.exchange.kucoin.kucoin_trading_engine',
            'src.bot.risk_management',
            'src.bot.order_management'
        ]

        for logger_name in trade_loggers:
            logger = logging.getLogger(logger_name)
            logger.setLevel(logging.INFO)
            logger.addHandler(self.handlers['trade_processing'])
            logger.propagate = False

        # Error loggers (file only)
        error_loggers = [
            'src.exchange',
            'src.core',
            'src.bot'
        ]

        for logger_name in error_loggers:
            logger = logging.getLogger(logger_name)
            logger.setLevel(logging.ERROR)
            logger.addHandler(self.handlers['errors'])
            logger.propagate = False

        # General application loggers
        general_loggers = [
            'discord_bot',
            'src.services',
            'scripts'
        ]

        for logger_name in general_loggers:
            logger = logging.getLogger(logger_name)
            logger.setLevel(logging.INFO)
            logger.addHandler(self.handlers['general'])
            logger.propagate = False

    def get_logger(self, name: str) -> logging.Logger:
        """Get a logger with appropriate configuration."""
        return logging.getLogger(name)

    def log_trade_step(self, step: str, trade_id: str, details: str = ""):
        """Log a trade processing step with consistent formatting."""
        logger = logging.getLogger('discord_bot.signal_processing')
        message = f"[TRADE {trade_id}] {step}"
        if details:
            message += f" - {details}"
        logger.info(message)

    def log_endpoint_request(self, method: str, endpoint: str, status: int, duration: float):
        """Log endpoint requests with consistent formatting."""
        logger = logging.getLogger('discord_bot.endpoints')
        logger.info(f"[{method}] {endpoint} - {status} - {duration:.3f}s")

    def log_websocket_event(self, event_type: str, message: str):
        """Log WebSocket events with reduced verbosity."""
        logger = logging.getLogger('src.websocket')
        logger.warning(f"[WS] {event_type}: {message}")


def setup_production_logging(log_dir: str = "logs") -> ProductionLoggingConfig:
    """Set up production logging configuration."""
    return ProductionLoggingConfig(log_dir)


def get_trade_logger() -> logging.Logger:
    """Get logger specifically for trade processing."""
    return logging.getLogger('discord_bot.signal_processing')


def get_endpoint_logger() -> logging.Logger:
    """Get logger specifically for endpoints."""
    return logging.getLogger('discord_bot.endpoints')


def get_websocket_logger() -> logging.Logger:
    """Get logger specifically for WebSocket events."""
    return logging.getLogger('src.websocket')


def get_error_logger() -> logging.Logger:
    """Get logger specifically for errors."""
    return logging.getLogger('src.exchange')
