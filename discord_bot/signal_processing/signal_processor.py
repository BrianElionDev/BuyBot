"""
Discord Signal Processor

This module orchestrates the processing of Discord trading signals,
coordinating between parsing, validation, and action extraction.
"""

import logging
import time
import json
from typing import Dict, Any, Optional, Tuple
from datetime import datetime, timezone

from .signal_parser import DiscordSignalParser
from .signal_validator import SignalValidator
from .signal_models import (
    ParsedSignal, AlertAction, SignalValidationResult,
    SignalProcessingResult, SUPPORTED_ACTION_TYPES
)

logger = logging.getLogger(__name__)


class SignalProcessor:
    """
    Orchestrates Discord signal processing workflow.

    Responsibilities:
    - Coordinate signal parsing and validation
    - Handle both new trade signals and trade updates
    - Extract actions from alert content
    - Provide unified interface for signal processing
    """

    def __init__(self):
        """Initialize the signal processor."""
        self.signal_parser = DiscordSignalParser()
        self.signal_validator = SignalValidator()

    async def process_new_trade_signal(self, signal_content: str) -> SignalProcessingResult:
        """
        Process a new trade signal.

        Args:
            signal_content: Raw signal content

        Returns:
            SignalProcessingResult with parsed signal and validation info
        """
        start_time = time.time()

        try:
            # Sanitize the signal content
            sanitized_content = self.signal_validator.sanitize_signal_content(signal_content)

            # Parse the signal using AI
            parsed_data = await self.signal_parser.parse_new_trade_signal(sanitized_content)
            if not parsed_data:
                return SignalProcessingResult(
                    success=False,
                    error_message="Failed to parse signal content",
                    processing_time=time.time() - start_time
                )

            # Create ParsedSignal object
            parsed_signal = ParsedSignal.from_dict(parsed_data)
            parsed_signal.timestamp = datetime.now(timezone.utc)

            # Validate the parsed signal
            is_valid, error_message = self.signal_validator.validate_parsed_signal(parsed_data)

            if not is_valid:
                return SignalProcessingResult(
                    success=False,
                    parsed_signal=parsed_signal,
                    error_message=error_message,
                    processing_time=time.time() - start_time
                )

            return SignalProcessingResult(
                success=True,
                parsed_signal=parsed_signal,
                processing_time=time.time() - start_time
            )

        except Exception as e:
            logger.error(f"Error processing new trade signal: {e}")
            return SignalProcessingResult(
                success=False,
                error_message=str(e),
                processing_time=time.time() - start_time
            )

    async def process_trade_update_signal(self, signal_content: str, active_trade: Dict[str, Any]) -> SignalProcessingResult:
        """
        Process a trade update signal.

        Args:
            signal_content: Raw signal content
            active_trade: Active trade data

        Returns:
            SignalProcessingResult with alert action and validation info
        """
        start_time = time.time()

        try:
            # Sanitize the signal content
            sanitized_content = self.signal_validator.sanitize_signal_content(signal_content)

            # Parse the update signal using AI
            parsed_data = await self.signal_parser.parse_trade_update_signal(sanitized_content, active_trade)
            if not parsed_data:
                return SignalProcessingResult(
                    success=False,
                    error_message="Failed to parse trade update signal",
                    processing_time=time.time() - start_time
                )

            # Create AlertAction object
            alert_action = AlertAction.from_dict(parsed_data)
            alert_action.timestamp = datetime.now(timezone.utc)

            return SignalProcessingResult(
                success=True,
                alert_action=alert_action,
                processing_time=time.time() - start_time
            )

        except Exception as e:
            logger.error(f"Error processing trade update signal: {e}")
            return SignalProcessingResult(
                success=False,
                error_message=str(e),
                processing_time=time.time() - start_time
            )

    def process_alert_content(self, content: str, trade_row: Optional[Dict[str, Any]] = None) -> AlertAction:
        """
        Process alert content and extract action information.

        Args:
            content: Alert content to process
            trade_row: Optional trade row data for context

        Returns:
            AlertAction with extracted action information
        """
        try:
            # Validate alert content
            is_valid, error_message = self.signal_validator.validate_alert_content(content)
            if not is_valid:
                logger.warning(f"Invalid alert content: {error_message}")

            # Extract action from alert content
            action_data = self.signal_validator.extract_action_from_alert(content)

            # Create AlertAction object
            alert_action = AlertAction.from_dict(action_data)
            alert_action.timestamp = datetime.now(timezone.utc)

            # Add context-specific information
            if trade_row:
                alert_action.coin_symbol = trade_row.get('coin_symbol', alert_action.coin_symbol)

            return alert_action

        except Exception as e:
            logger.error(f"Error processing alert content: {e}")
            return AlertAction(
                action_type='unknown',
                content=content,
                reason=f"Error processing alert: {str(e)}",
                timestamp=datetime.now(timezone.utc)
            )

    def parse_parsed_signal(self, parsed_signal_data: Any) -> Dict[str, Any]:
        """
        Safely parse parsed_signal data which can be either a dict or JSON string.

        Args:
            parsed_signal_data: Parsed signal data (dict or JSON string)

        Returns:
            Dictionary representation of the parsed signal
        """
        if isinstance(parsed_signal_data, dict):
            return parsed_signal_data
        elif isinstance(parsed_signal_data, str):
            try:
                return json.loads(parsed_signal_data)
            except json.JSONDecodeError:
                logger.warning(f"Failed to parse parsed_signal JSON: {parsed_signal_data}")
                return {}
        else:
            logger.warning(f"Unexpected parsed_signal type: {type(parsed_signal_data)}")
            return {}

    def validate_signal_structure(self, signal: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """
        Validate signal structure using the signal parser's validation.

        Args:
            signal: Signal to validate

        Returns:
            Tuple of (is_valid, error_message)
        """
        return self.signal_parser.validate_signal(signal)

    def get_coin_symbol(self, signal_content: str) -> Optional[str]:
        """
        Extract coin symbol from signal content.

        Args:
            signal_content: Signal content to parse

        Returns:
            Extracted coin symbol or None
        """
        return self.signal_validator._extract_coin_symbol_from_content(signal_content)

    def get_processing_stats(self) -> Dict[str, Any]:
        """
        Get signal processing statistics.

        Returns:
            Dictionary with processing statistics
        """
        return {
            'supported_order_types': SUPPORTED_ORDER_TYPES,
            'supported_position_types': ['LONG', 'SHORT'],
            'supported_action_types': SUPPORTED_ACTION_TYPES,
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
