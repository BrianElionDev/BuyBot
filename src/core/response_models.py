"""
Standardized response models for consistent error handling across services.
"""

from dataclasses import dataclass, field
from typing import Any, Optional, Dict
from datetime import datetime, timezone
from enum import Enum


class ErrorCode(Enum):
    """Standardized error codes for consistent error handling."""
    SUCCESS = "SUCCESS"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    EXCHANGE_ERROR = "EXCHANGE_ERROR"
    DATABASE_ERROR = "DATABASE_ERROR"
    NETWORK_ERROR = "NETWORK_ERROR"
    AUTHENTICATION_ERROR = "AUTHENTICATION_ERROR"
    RATE_LIMIT_ERROR = "RATE_LIMIT_ERROR"
    POSITION_NOT_FOUND = "POSITION_NOT_FOUND"
    INSUFFICIENT_BALANCE = "INSUFFICIENT_BALANCE"
    INVALID_SYMBOL = "INVALID_SYMBOL"
    ORDER_FAILED = "ORDER_FAILED"
    TIMEOUT_ERROR = "TIMEOUT_ERROR"
    UNKNOWN_ERROR = "UNKNOWN_ERROR"


@dataclass
class ServiceResponse:
    """Standardized response format for all service operations."""
    success: bool
    data: Optional[Any] = None
    error: Optional[str] = None
    error_code: Optional[ErrorCode] = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: Optional[Dict[str, Any]] = None

    @classmethod
    def success_response(cls, data: Any = None, metadata: Optional[Dict[str, Any]] = None) -> 'ServiceResponse':
        """Create a successful response."""
        return cls(
            success=True,
            data=data,
            metadata=metadata
        )

    @classmethod
    def error_response(
        cls,
        error: str,
        error_code: ErrorCode = ErrorCode.UNKNOWN_ERROR,
        metadata: Optional[Dict[str, Any]] = None
    ) -> 'ServiceResponse':
        """Create an error response."""
        return cls(
            success=False,
            error=error,
            error_code=error_code,
            metadata=metadata
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert response to dictionary format."""
        result = {
            "success": self.success,
            "timestamp": self.timestamp.isoformat(),
        }

        if self.data is not None:
            result["data"] = self.data

        if self.error is not None:
            result["error"] = self.error

        if self.error_code is not None:
            result["error_code"] = self.error_code.value

        if self.metadata is not None:
            result["metadata"] = self.metadata

        return result


@dataclass
class TradeOperationResult:
    """Specialized response for trade operations."""
    success: bool
    trade_id: Optional[str] = None
    order_id: Optional[str] = None
    position_size: Optional[float] = None
    entry_price: Optional[float] = None
    exit_price: Optional[float] = None
    error: Optional[str] = None
    error_code: Optional[ErrorCode] = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    exchange_response: Optional[Dict[str, Any]] = None

    @classmethod
    def success_result(
        cls,
        trade_id: str,
        order_id: Optional[str] = None,
        position_size: Optional[float] = None,
        entry_price: Optional[float] = None,
        exit_price: Optional[float] = None,
        exchange_response: Optional[Dict[str, Any]] = None
    ) -> 'TradeOperationResult':
        """Create a successful trade operation result."""
        return cls(
            success=True,
            trade_id=trade_id,
            order_id=order_id,
            position_size=position_size,
            entry_price=entry_price,
            exit_price=exit_price,
            exchange_response=exchange_response
        )

    @classmethod
    def error_result(
        cls,
        error: str,
        error_code: ErrorCode = ErrorCode.ORDER_FAILED,
        trade_id: Optional[str] = None
    ) -> 'TradeOperationResult':
        """Create an error trade operation result."""
        return cls(
            success=False,
            error=error,
            error_code=error_code,
            trade_id=trade_id
        )
