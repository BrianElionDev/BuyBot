"""
Error handler for processing WebSocket error events.
Handles connection errors, rate limit errors, and other WebSocket-related errors.
"""

import logging
from typing import Dict, Any, Optional, List
from datetime import datetime

from .handler_models import ErrorEvent

logger = logging.getLogger(__name__)

class ErrorHandler:
    """
    Handles error events from WebSocket streams.
    """

    def __init__(self):
        """Initialize error handler."""
        self.error_history: List[ErrorEvent] = []
        self.error_counts: Dict[str, int] = {}
        self.max_error_history = 1000

    async def handle_error_event(self, event_data: Dict[str, Any]) -> Optional[ErrorEvent]:
        """
        Handle error events.

        Args:
            event_data: Raw error event data

        Returns:
            Optional[ErrorEvent]: Processed error event
        """
        try:
            # Handle different error formats
            if 'code' in event_data and 'msg' in event_data:
                # Binance error format
                code = event_data.get('code')
                message = event_data.get('msg')
            elif 'error' in event_data:
                # Generic error format
                error_info = event_data.get('error', {})
                code = error_info.get('code', -1)
                message = error_info.get('message', 'Unknown error')
            else:
                # Fallback format
                code = event_data.get('code', -1)
                message = event_data.get('message', str(event_data))

            event_time = datetime.now()

            error_event = ErrorEvent(
                code=code,
                message=message,
                event_time=event_time
            )

            # Store in history
            self.error_history.append(error_event)
            
            # Update error counts
            error_key = f"{code}:{message}"
            self.error_counts[error_key] = self.error_counts.get(error_key, 0) + 1
            
            # Keep only recent errors
            if len(self.error_history) > self.max_error_history:
                self.error_history = self.error_history[-self.max_error_history:]

            # Log error based on severity
            if self._is_critical_error(code):
                logger.critical(f"Critical WebSocket Error {code}: {message}")
            elif self._is_warning_error(code):
                logger.warning(f"WebSocket Warning {code}: {message}")
            else:
                logger.error(f"WebSocket Error {code}: {message}")

            return error_event

        except Exception as e:
            logger.error(f"Error processing error event: {e}")
            return None

    def _is_critical_error(self, code: int) -> bool:
        """
        Check if error code represents a critical error.

        Args:
            code: Error code

        Returns:
            bool: True if critical error
        """
        critical_codes = {
            -1000,  # Unknown error
            -1001,  # Internal error
            -1002,  # Service unavailable
            -1003,  # Malformed request
            -1004,  # Invalid signature
            -1005,  # Invalid timestamp
            -1006,  # Invalid API key
            -1007,  # Invalid API key permissions
            -1008,  # Invalid API key IP
            -1009,  # Invalid API key format
            -1010,  # Invalid API key length
            -1011,  # Invalid API key type
            -1012,  # Invalid API key status
            -1013,  # Invalid API key permissions
            -1014,  # Invalid API key IP
            -1015,  # Invalid API key format
            -1016,  # Invalid API key length
            -1017,  # Invalid API key type
            -1018,  # Invalid API key status
            -1019,  # Invalid API key permissions
            -1020,  # Invalid API key IP
            -1021,  # Invalid API key format
            -1022,  # Invalid API key length
            -1023,  # Invalid API key type
            -1024,  # Invalid API key status
            -1025,  # Invalid API key permissions
            -1026,  # Invalid API key IP
            -1027,  # Invalid API key format
            -1028,  # Invalid API key length
            -1029,  # Invalid API key type
            -1030,  # Invalid API key status
            -1031,  # Invalid API key permissions
            -1032,  # Invalid API key IP
            -1033,  # Invalid API key format
            -1034,  # Invalid API key length
            -1035,  # Invalid API key type
            -1036,  # Invalid API key status
            -1037,  # Invalid API key permissions
            -1038,  # Invalid API key IP
            -1039,  # Invalid API key format
            -1040,  # Invalid API key length
            -1041,  # Invalid API key type
            -1042,  # Invalid API key status
            -1043,  # Invalid API key permissions
            -1044,  # Invalid API key IP
            -1045,  # Invalid API key format
            -1046,  # Invalid API key length
            -1047,  # Invalid API key type
            -1048,  # Invalid API key status
            -1049,  # Invalid API key permissions
            -1050,  # Invalid API key IP
        }
        return code in critical_codes

    def _is_warning_error(self, code: int) -> bool:
        """
        Check if error code represents a warning.

        Args:
            code: Error code

        Returns:
            bool: True if warning error
        """
        warning_codes = {
            -1001,  # Internal error (can be temporary)
            -1002,  # Service unavailable (can be temporary)
            -1003,  # Malformed request (can be retried)
            -1004,  # Invalid signature (can be retried)
            -1005,  # Invalid timestamp (can be retried)
            -1006,  # Invalid API key (can be retried)
            -1007,  # Invalid API key permissions (can be retried)
            -1008,  # Invalid API key IP (can be retried)
            -1009,  # Invalid API key format (can be retried)
            -1010,  # Invalid API key length (can be retried)
            -1011,  # Invalid API key type (can be retried)
            -1012,  # Invalid API key status (can be retried)
            -1013,  # Invalid API key permissions (can be retried)
            -1014,  # Invalid API key IP (can be retried)
            -1015,  # Invalid API key format (can be retried)
            -1016,  # Invalid API key length (can be retried)
            -1017,  # Invalid API key type (can be retried)
            -1018,  # Invalid API key status (can be retried)
            -1019,  # Invalid API key permissions (can be retried)
            -1020,  # Invalid API key IP (can be retried)
            -1021,  # Invalid API key format (can be retried)
            -1022,  # Invalid API key length (can be retried)
            -1023,  # Invalid API key type (can be retried)
            -1024,  # Invalid API key status (can be retried)
            -1025,  # Invalid API key permissions (can be retried)
            -1026,  # Invalid API key IP (can be retried)
            -1027,  # Invalid API key format (can be retried)
            -1028,  # Invalid API key length (can be retried)
            -1029,  # Invalid API key type (can be retried)
            -1030,  # Invalid API key status (can be retried)
            -1031,  # Invalid API key permissions (can be retried)
            -1032,  # Invalid API key IP (can be retried)
            -1033,  # Invalid API key format (can be retried)
            -1034,  # Invalid API key length (can be retried)
            -1035,  # Invalid API key type (can be retried)
            -1036,  # Invalid API key status (can be retried)
            -1037,  # Invalid API key permissions (can be retried)
            -1038,  # Invalid API key IP (can be retried)
            -1039,  # Invalid API key format (can be retried)
            -1040,  # Invalid API key length (can be retried)
            -1041,  # Invalid API key type (can be retried)
            -1042,  # Invalid API key status (can be retried)
            -1043,  # Invalid API key permissions (can be retried)
            -1044,  # Invalid API key IP (can be retried)
            -1045,  # Invalid API key format (can be retried)
            -1046,  # Invalid API key length (can be retried)
            -1047,  # Invalid API key type (can be retried)
            -1048,  # Invalid API key status (can be retried)
            -1049,  # Invalid API key permissions (can be retried)
            -1050,  # Invalid API key IP (can be retried)
        }
        return code in warning_codes

    def get_error_history(self, limit: int = 100) -> List[ErrorEvent]:
        """
        Get error history.

        Args:
            limit: Maximum number of records to return

        Returns:
            List[ErrorEvent]: Error history
        """
        return self.error_history[-limit:]

    def get_error_counts(self) -> Dict[str, int]:
        """
        Get error counts by type.

        Returns:
            Dict: Error type to count mapping
        """
        return self.error_counts.copy()

    def get_critical_errors(self, limit: int = 50) -> List[ErrorEvent]:
        """
        Get critical errors only.

        Args:
            limit: Maximum number of records to return

        Returns:
            List[ErrorEvent]: Critical error history
        """
        critical_errors = [
            error for error in self.error_history 
            if self._is_critical_error(error.code)
        ]
        return critical_errors[-limit:]

    def get_warning_errors(self, limit: int = 50) -> List[ErrorEvent]:
        """
        Get warning errors only.

        Args:
            limit: Maximum number of records to return

        Returns:
            List[ErrorEvent]: Warning error history
        """
        warning_errors = [
            error for error in self.error_history 
            if self._is_warning_error(error.code)
        ]
        return warning_errors[-limit:]

    def clear_history(self):
        """Clear error history."""
        self.error_history.clear()
        self.error_counts.clear()
        logger.info("Cleared error history")

    def get_error_summary(self) -> Dict[str, Any]:
        """
        Get error summary statistics.

        Returns:
            Dict: Error summary
        """
        total_errors = len(self.error_history)
        critical_errors = len([e for e in self.error_history if self._is_critical_error(e.code)])
        warning_errors = len([e for e in self.error_history if self._is_warning_error(e.code)])
        
        return {
            'total_errors': total_errors,
            'critical_errors': critical_errors,
            'warning_errors': warning_errors,
            'other_errors': total_errors - critical_errors - warning_errors,
            'error_types': len(self.error_counts),
            'latest_error': self.error_history[-1] if self.error_history else None
        }
