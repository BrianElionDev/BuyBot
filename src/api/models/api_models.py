"""
General API Models

This module contains general API models and utilities.
"""

from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from datetime import datetime
from enum import Enum

class StatusEnum(str, Enum):
    """Status enumeration for API responses."""
    SUCCESS = "success"
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"

class TradeStatusEnum(str, Enum):
    """Trade status enumeration."""
    PENDING = "PENDING"
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"
    PARTIALLY_CLOSED = "PARTIALLY_CLOSED"

class OrderStatusEnum(str, Enum):
    """Order status enumeration."""
    NEW = "NEW"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELED = "CANCELED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"

class PositionTypeEnum(str, Enum):
    """Position type enumeration."""
    LONG = "LONG"
    SHORT = "SHORT"

class OrderTypeEnum(str, Enum):
    """Order type enumeration."""
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP_MARKET = "STOP_MARKET"
    STOP_LIMIT = "STOP_LIMIT"
    TAKE_PROFIT_MARKET = "TAKE_PROFIT_MARKET"
    TAKE_PROFIT_LIMIT = "TAKE_PROFIT_LIMIT"

class PaginationParams(BaseModel):
    """Model for pagination parameters."""
    page: int = Field(1, ge=1, description="Page number")
    size: int = Field(10, ge=1, le=100, description="Page size")
    total: Optional[int] = Field(None, description="Total number of items")

class PaginatedResponse(BaseModel):
    """Model for paginated responses."""
    items: List[Dict[str, Any]] = Field(..., description="List of items")
    pagination: PaginationParams = Field(..., description="Pagination information")
    total_pages: int = Field(..., description="Total number of pages")

class FilterParams(BaseModel):
    """Model for filter parameters."""
    start_date: Optional[str] = Field(None, description="Start date filter")
    end_date: Optional[str] = Field(None, description="End date filter")
    trader: Optional[str] = Field(None, description="Trader filter")
    coin_symbol: Optional[str] = Field(None, description="Coin symbol filter")
    status: Optional[str] = Field(None, description="Status filter")

class SortParams(BaseModel):
    """Model for sorting parameters."""
    field: str = Field(..., description="Field to sort by")
    direction: str = Field("asc", description="Sort direction (asc/desc)")

class SearchParams(BaseModel):
    """Model for search parameters."""
    query: str = Field(..., description="Search query")
    fields: Optional[List[str]] = Field(None, description="Fields to search in")

class APIError(BaseModel):
    """Model for API errors."""
    code: str = Field(..., description="Error code")
    message: str = Field(..., description="Error message")
    details: Optional[Dict[str, Any]] = Field(None, description="Error details")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Error timestamp")

class ValidationError(BaseModel):
    """Model for validation errors."""
    field: str = Field(..., description="Field with error")
    message: str = Field(..., description="Validation error message")
    value: Optional[Any] = Field(None, description="Invalid value")

class ValidationErrorResponse(BaseModel):
    """Model for validation error responses."""
    errors: List[ValidationError] = Field(..., description="List of validation errors")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Error timestamp")
