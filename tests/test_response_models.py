"""
Tests for standardized response models.
"""

import pytest
from datetime import datetime, timezone
from src.core.response_models import ServiceResponse, TradeOperationResult, ErrorCode


class TestServiceResponse:
    """Test cases for ServiceResponse."""

    def test_success_response_creation(self):
        """Test creation of successful response."""
        data = {"test": "data"}
        metadata = {"operation": "test"}

        response = ServiceResponse.success_response(data=data, metadata=metadata)

        assert response.success is True
        assert response.data == data
        assert response.metadata == metadata
        assert response.error is None
        assert response.error_code is None
        assert isinstance(response.timestamp, datetime)

    def test_error_response_creation(self):
        """Test creation of error response."""
        error_msg = "Test error"
        error_code = ErrorCode.VALIDATION_ERROR
        metadata = {"operation": "test"}

        response = ServiceResponse.error_response(
            error=error_msg,
            error_code=error_code,
            metadata=metadata
        )

        assert response.success is False
        assert response.error == error_msg
        assert response.error_code == error_code
        assert response.metadata == metadata
        assert response.data is None
        assert isinstance(response.timestamp, datetime)

    def test_to_dict_success(self):
        """Test conversion to dictionary for successful response."""
        data = {"test": "data"}
        response = ServiceResponse.success_response(data=data)
        result = response.to_dict()

        assert result["success"] is True
        assert result["data"] == data
        assert "timestamp" in result
        assert "error" not in result
        assert "error_code" not in result

    def test_to_dict_error(self):
        """Test conversion to dictionary for error response."""
        error_msg = "Test error"
        error_code = ErrorCode.VALIDATION_ERROR
        response = ServiceResponse.error_response(error=error_msg, error_code=error_code)
        result = response.to_dict()

        assert result["success"] is False
        assert result["error"] == error_msg
        assert result["error_code"] == error_code.value
        assert "timestamp" in result
        assert "data" not in result


class TestTradeOperationResult:
    """Test cases for TradeOperationResult."""

    def test_success_result_creation(self):
        """Test creation of successful trade operation result."""
        trade_id = "test_trade_123"
        order_id = "test_order_456"
        position_size = 1.5
        entry_price = 100.0
        exit_price = 105.0
        exchange_response = {"orderId": order_id}

        result = TradeOperationResult.success_result(
            trade_id=trade_id,
            order_id=order_id,
            position_size=position_size,
            entry_price=entry_price,
            exit_price=exit_price,
            exchange_response=exchange_response
        )

        assert result.success is True
        assert result.trade_id == trade_id
        assert result.order_id == order_id
        assert result.position_size == position_size
        assert result.entry_price == entry_price
        assert result.exit_price == exit_price
        assert result.exchange_response == exchange_response
        assert result.error is None
        assert result.error_code is None
        assert isinstance(result.timestamp, datetime)

    def test_error_result_creation(self):
        """Test creation of error trade operation result."""
        error_msg = "Order failed"
        error_code = ErrorCode.ORDER_FAILED
        trade_id = "test_trade_123"

        result = TradeOperationResult.error_result(
            error=error_msg,
            error_code=error_code,
            trade_id=trade_id
        )

        assert result.success is False
        assert result.error == error_msg
        assert result.error_code == error_code
        assert result.trade_id == trade_id
        assert result.order_id is None
        assert result.position_size is None
        assert result.entry_price is None
        assert result.exit_price is None
        assert result.exchange_response is None
        assert isinstance(result.timestamp, datetime)

    def test_minimal_success_result(self):
        """Test creation of minimal successful result."""
        trade_id = "test_trade_123"

        result = TradeOperationResult.success_result(trade_id=trade_id)

        assert result.success is True
        assert result.trade_id == trade_id
        assert result.order_id is None
        assert result.position_size is None
        assert result.entry_price is None
        assert result.exit_price is None
        assert result.exchange_response is None


class TestErrorCode:
    """Test cases for ErrorCode enum."""

    def test_error_code_values(self):
        """Test that error codes have proper string values."""
        assert ErrorCode.SUCCESS.value == "SUCCESS"
        assert ErrorCode.VALIDATION_ERROR.value == "VALIDATION_ERROR"
        assert ErrorCode.EXCHANGE_ERROR.value == "EXCHANGE_ERROR"
        assert ErrorCode.DATABASE_ERROR.value == "DATABASE_ERROR"
        assert ErrorCode.NETWORK_ERROR.value == "NETWORK_ERROR"
        assert ErrorCode.AUTHENTICATION_ERROR.value == "AUTHENTICATION_ERROR"
        assert ErrorCode.RATE_LIMIT_ERROR.value == "RATE_LIMIT_ERROR"
        assert ErrorCode.POSITION_NOT_FOUND.value == "POSITION_NOT_FOUND"
        assert ErrorCode.INSUFFICIENT_BALANCE.value == "INSUFFICIENT_BALANCE"
        assert ErrorCode.INVALID_SYMBOL.value == "INVALID_SYMBOL"
        assert ErrorCode.ORDER_FAILED.value == "ORDER_FAILED"
        assert ErrorCode.TIMEOUT_ERROR.value == "TIMEOUT_ERROR"
        assert ErrorCode.UNKNOWN_ERROR.value == "UNKNOWN_ERROR"

    def test_error_code_enumeration(self):
        """Test that all error codes can be enumerated."""
        error_codes = list(ErrorCode)
        assert len(error_codes) == 13  # Total number of error codes
        assert ErrorCode.SUCCESS in error_codes
        assert ErrorCode.UNKNOWN_ERROR in error_codes
