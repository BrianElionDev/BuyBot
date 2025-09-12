"""
Discord Signal Processing Module

This module contains the signal processing components for the Discord bot:
- SignalParser: AI-powered signal parsing
- SignalValidator: Signal validation and sanitization
- SignalProcessor: Signal processing orchestration
- SignalModels: Data models for signals
"""

from .signal_parser import DiscordSignalParser
from .signal_validator import SignalValidator
from .signal_processor import SignalProcessor
from .signal_models import (
    ParsedSignal, AlertAction, SignalValidationResult,
    SignalProcessingResult, SUPPORTED_ORDER_TYPES,
    SUPPORTED_POSITION_TYPES, SUPPORTED_ACTION_TYPES
)

__all__ = [
    'DiscordSignalParser',
    'SignalValidator',
    'SignalProcessor',
    'ParsedSignal',
    'AlertAction',
    'SignalValidationResult',
    'SignalProcessingResult',
    'SUPPORTED_ORDER_TYPES',
    'SUPPORTED_POSITION_TYPES',
    'SUPPORTED_ACTION_TYPES'
]
