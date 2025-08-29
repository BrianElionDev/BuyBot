"""
API Middleware Module

This module contains middleware components for the API layer.
"""

import time
import logging
from typing import Callable
from fastapi import Request, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.base import RequestResponseEndpoint
from starlette.types import ASGIApp

logger = logging.getLogger(__name__)

class LoggingMiddleware(BaseHTTPMiddleware):
    """Middleware for logging API requests and responses."""
    
    def __init__(self, app: ASGIApp):
        super().__init__(app)
    
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        """Log request and response information."""
        start_time = time.time()
        
        # Log request
        logger.info(f"Request: {request.method} {request.url.path}")
        
        # Process request
        response = await call_next(request)
        
        # Calculate processing time
        process_time = time.time() - start_time
        
        # Log response
        logger.info(f"Response: {response.status_code} - {process_time:.4f}s")
        
        # Add processing time to response headers
        response.headers["X-Process-Time"] = str(process_time)
        
        return response

class ErrorHandlingMiddleware(BaseHTTPMiddleware):
    """Middleware for handling API errors."""
    
    def __init__(self, app: ASGIApp):
        super().__init__(app)
    
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        """Handle errors in API requests."""
        try:
            response = await call_next(request)
            return response
        except Exception as e:
            logger.error(f"API Error: {str(e)}", exc_info=True)
            # Re-raise the exception for FastAPI to handle
            raise

def setup_cors_middleware(app, config):
    """Setup CORS middleware with configuration."""
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.allowed_origins,
        allow_credentials=config.allowed_credentials,
        allow_methods=config.allowed_methods,
        allow_headers=config.allowed_headers,
    )

def setup_middleware(app, config):
    """Setup all middleware for the API."""
    # Add CORS middleware
    setup_cors_middleware(app, config)
    
    # Add logging middleware
    app.add_middleware(LoggingMiddleware)
    
    # Add error handling middleware
    app.add_middleware(ErrorHandlingMiddleware)
