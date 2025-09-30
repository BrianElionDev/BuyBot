"""
Structured logging configuration for the trading bot.
"""

import logging
import json
import sys
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from dataclasses import dataclass, asdict


@dataclass
class LogContext:
    """Context information for structured logging."""
    trade_id: Optional[str] = None
    symbol: Optional[str] = None
    exchange: Optional[str] = None
    operation: Optional[str] = None
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    request_id: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class StructuredFormatter(logging.Formatter):
    """Custom formatter for structured JSON logging."""

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as structured JSON."""
        log_entry = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Add exception information if present
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)

        # Add context information if present
        if hasattr(record, 'context') and record.context:
            context_dict = asdict(record.context) if isinstance(record.context, LogContext) else record.context
            log_entry["context"] = context_dict

        # Add any additional fields
        for key, value in record.__dict__.items():
            if key not in ['name', 'msg', 'args', 'levelname', 'levelno', 'pathname',
                          'filename', 'module', 'lineno', 'funcName', 'created',
                          'msecs', 'relativeCreated', 'thread', 'threadName',
                          'processName', 'process', 'getMessage', 'exc_info',
                          'exc_text', 'stack_info', 'context']:
                log_entry[key] = value

        return json.dumps(log_entry, default=str)


class ContextualLogger:
    """Logger that maintains context across operations."""

    def __init__(self, name: str, context: Optional[LogContext] = None):
        self.logger = logging.getLogger(name)
        self.context = context or LogContext()

    def _log_with_context(self, level: int, msg: str, *args, **kwargs):
        """Log message with context information."""
        extra = kwargs.get('extra', {})
        extra['context'] = self.context
        kwargs['extra'] = extra
        self.logger.log(level, msg, *args, **kwargs)

    def debug(self, msg: str, *args, **kwargs):
        """Log debug message with context."""
        self._log_with_context(logging.DEBUG, msg, *args, **kwargs)

    def info(self, msg: str, *args, **kwargs):
        """Log info message with context."""
        self._log_with_context(logging.INFO, msg, *args, **kwargs)

    def warning(self, msg: str, *args, **kwargs):
        """Log warning message with context."""
        self._log_with_context(logging.WARNING, msg, *args, **kwargs)

    def error(self, msg: str, *args, **kwargs):
        """Log error message with context."""
        self._log_with_context(logging.ERROR, msg, *args, **kwargs)

    def critical(self, msg: str, *args, **kwargs):
        """Log critical message with context."""
        self._log_with_context(logging.CRITICAL, msg, *args, **kwargs)

    def with_context(self, **context_updates) -> 'ContextualLogger':
        """Create new logger with updated context."""
        new_context = LogContext(
            trade_id=context_updates.get('trade_id', self.context.trade_id),
            symbol=context_updates.get('symbol', self.context.symbol),
            exchange=context_updates.get('exchange', self.context.exchange),
            operation=context_updates.get('operation', self.context.operation),
            user_id=context_updates.get('user_id', self.context.user_id),
            session_id=context_updates.get('session_id', self.context.session_id),
            request_id=context_updates.get('request_id', self.context.request_id),
            metadata=context_updates.get('metadata', self.context.metadata)
        )
        return ContextualLogger(self.logger.name, new_context)


def setup_structured_logging(
    level: str = "INFO",
    output_format: str = "json",
    log_file: Optional[str] = None
) -> None:
    """Set up structured logging for the application."""

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper()))

    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Create console handler
    console_handler = logging.StreamHandler(sys.stdout)

    if output_format == "json":
        formatter = StructuredFormatter()
    else:
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )

    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # Create file handler if specified
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

    # Set specific logger levels
    logging.getLogger('asyncio').setLevel(logging.WARNING)
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('websockets').setLevel(logging.WARNING)


def get_logger(name: str, context: Optional[LogContext] = None) -> ContextualLogger:
    """Get a contextual logger instance."""
    return ContextualLogger(name, context)


# Trade-specific logging utilities
def log_trade_operation(
    logger: ContextualLogger,
    operation: str,
    trade_id: str,
    symbol: str,
    exchange: str,
    success: bool,
    details: Optional[Dict[str, Any]] = None
) -> None:
    """Log trade operation with structured context."""
    context = LogContext(
        trade_id=trade_id,
        symbol=symbol,
        exchange=exchange,
        operation=operation,
        metadata=details or {}
    )

    contextual_logger = logger.with_context(**asdict(context))

    if success:
        contextual_logger.info(
            f"Trade operation '{operation}' completed successfully",
            operation=operation,
            success=success
        )
    else:
        contextual_logger.error(
            f"Trade operation '{operation}' failed",
            operation=operation,
            success=success
        )


def log_exchange_operation(
    logger: ContextualLogger,
    operation: str,
    exchange: str,
    symbol: Optional[str] = None,
    success: bool = True,
    response_time_ms: Optional[float] = None,
    error: Optional[str] = None
) -> None:
    """Log exchange operation with structured context."""
    context = LogContext(
        exchange=exchange,
        symbol=symbol,
        operation=operation,
        metadata={
            "response_time_ms": response_time_ms,
            "error": error
        }
    )

    contextual_logger = logger.with_context(**asdict(context))

    if success:
        contextual_logger.info(
            f"Exchange operation '{operation}' completed",
            operation=operation,
            success=success,
            response_time_ms=response_time_ms
        )
    else:
        contextual_logger.error(
            f"Exchange operation '{operation}' failed: {error}",
            operation=operation,
            success=success,
            error=error
        )
