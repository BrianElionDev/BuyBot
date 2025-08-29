"""
API Configuration Module

This module contains configuration settings for the API layer.
"""

from dataclasses import dataclass
from typing import List, Optional
import os
from dotenv import load_dotenv

load_dotenv()

@dataclass
class APIConfig:
    """API configuration settings."""
    
    # Server settings
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False
    
    # CORS settings
    allowed_origins: List[str] = None
    allowed_credentials: bool = True
    allowed_methods: List[str] = None
    allowed_headers: List[str] = None
    
    # API settings
    title: str = "Trading Bot API"
    version: str = "1.0.0"
    description: str = "API for Rubicon Trading Bot"
    
    # Rate limiting
    rate_limit_requests: int = 100
    rate_limit_window: int = 60  # seconds
    
    def __post_init__(self):
        """Initialize default values."""
        if self.allowed_origins is None:
            self.allowed_origins = ["*"]  # In production, replace with specific origins
        
        if self.allowed_methods is None:
            self.allowed_methods = ["*"]
        
        if self.allowed_headers is None:
            self.allowed_headers = ["*"]
        
        # Override with environment variables if present
        self.host = os.getenv("API_HOST", self.host)
        self.port = int(os.getenv("API_PORT", str(self.port)))
        self.debug = os.getenv("API_DEBUG", str(self.debug)).lower() == "true"

# Global API configuration instance
api_config = APIConfig()
