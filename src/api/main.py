"""
Main API Entry Point

This module serves as the main entry point for the API.
"""

from src.api.core.api_server import app

# Export the app for uvicorn
__all__ = ["app"]