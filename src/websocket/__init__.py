"""
WebSocket module for real-time Binance futures data streaming.
Handles user data streams, market data, and automatic reconnection.
"""

from binance_websocket_manager import BinanceWebSocketManager
from websocket_config import WebSocketConfig

__all__ = ['BinanceWebSocketManager', 'WebSocketConfig']