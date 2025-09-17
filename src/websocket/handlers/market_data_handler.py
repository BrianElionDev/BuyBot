"""
Market data handler for processing market-related WebSocket events.
Handles ticker, trade, and depth data from Binance WebSocket streams.
"""

import logging
from typing import Dict, Any, Optional
from datetime import datetime

from .handler_models import MarketData

logger = logging.getLogger(__name__)

class MarketDataHandler:
    """
    Handles market data events from WebSocket streams.
    """

    def __init__(self):
        """Initialize market data handler."""
        self.price_cache: Dict[str, float] = {}
        self.last_update: Dict[str, datetime] = {}

    async def handle_ticker_event(self, event_data: Dict[str, Any]) -> Optional[MarketData]:
        """
        Handle ticker events.

        Args:
            event_data: Raw ticker event data

        Returns:
            Optional[MarketData]: Processed market data
        """
        try:
            symbol = event_data.get('s')  # Symbol
            price = float(event_data.get('c', 0))  # Close price
            volume = float(event_data.get('v', 0))  # Volume
            event_time = datetime.fromtimestamp(event_data.get('E', 0) / 1000)

            # Update price cache
            if symbol is not None:
                self.price_cache[symbol] = price
                self.last_update[symbol] = event_time

            market_data = MarketData(
                symbol=symbol if symbol is not None else "",
                price=price,
                quantity=volume,
                trade_time=event_time,
                event_type='ticker'
            )

            logger.info(f"Processed ticker event for {symbol}: {price}")
            return market_data

        except Exception as e:
            logger.error(f"Error processing ticker event: {e}")
            return None

    async def handle_trade_event(self, event_data: Dict[str, Any]) -> Optional[MarketData]:
        """
        Handle trade events.

        Args:
            event_data: Raw trade event data

        Returns:
            Optional[MarketData]: Processed market data
        """
        try:
            symbol = event_data.get('s')  # Symbol
            price = float(event_data.get('p', 0))  # Price
            quantity = float(event_data.get('q', 0))  # Quantity
            trade_time = datetime.fromtimestamp(event_data.get('T', 0) / 1000)

            # Update price cache
            if symbol is not None:
                self.price_cache[symbol] = price
                self.last_update[symbol] = trade_time

            market_data = MarketData(
                symbol=symbol if symbol is not None else "",
                price=price,
                quantity=quantity,
                trade_time=trade_time,
                event_type='trade'
            )

            logger.info(f"Processed trade event for {symbol}: {price} x {quantity}")
            return market_data

        except Exception as e:
            logger.error(f"Error processing trade event: {e}")
            return None

    async def handle_depth_event(self, event_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Handle depth (order book) events.

        Args:
            event_data: Raw depth event data

        Returns:
            Optional[Dict]: Processed depth data
        """
        try:
            symbol = event_data.get('s')  # Symbol
            event_time = datetime.fromtimestamp(event_data.get('E', 0) / 1000)

            # Process bids and asks
            bids = event_data.get('b', [])  # Bids
            asks = event_data.get('a', [])  # Asks

            depth_data = {
                'symbol': symbol,
                'bids': bids,
                'asks': asks,
                'event_time': event_time,
                'event_type': 'depth'
            }

            logger.info(f"Processed depth event for {symbol}")
            return depth_data

        except Exception as e:
            logger.error(f"Error processing depth event: {e}")
            return None

    def get_latest_price(self, symbol: str) -> Optional[float]:
        """
        Get the latest price for a symbol.

        Args:
            symbol: Trading symbol

        Returns:
            Optional[float]: Latest price or None if not available
        """
        return self.price_cache.get(symbol)

    def get_last_update_time(self, symbol: str) -> Optional[datetime]:
        """
        Get the last update time for a symbol.

        Args:
            symbol: Trading symbol

        Returns:
            Optional[datetime]: Last update time or None if not available
        """
        return self.last_update.get(symbol)

    def get_all_prices(self) -> Dict[str, float]:
        """
        Get all cached prices.

        Returns:
            Dict: Symbol to price mapping
        """
        return self.price_cache.copy()

    def clear_cache(self, symbol: Optional[str] = None):
        """
        Clear price cache.

        Args:
            symbol: Symbol to clear, or None to clear all
        """
        if symbol:
            self.price_cache.pop(symbol, None)
            self.last_update.pop(symbol, None)
            logger.info(f"Cleared cache for {symbol}")
        else:
            self.price_cache.clear()
            self.last_update.clear()
            logger.info("Cleared all price cache")
