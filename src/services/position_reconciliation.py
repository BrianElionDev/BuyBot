"""
Position Reconciliation Service

This service syncs position data from exchanges before critical operations
to handle race conditions and ensure data accuracy.
"""

import logging
from typing import Dict, Any, Optional, Tuple
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class PositionReconciliationService:
    """
    Service for reconciling position data from exchanges before critical operations.

    Handles race conditions where positions may close between validation and execution.
    """

    def __init__(self, exchange: Any):
        """
        Initialize position reconciliation service.

        Args:
            exchange: Exchange instance (BinanceExchange or KucoinExchange)
        """
        self.exchange = exchange
        self._position_cache: Dict[str, Dict[str, Any]] = {}
        self._cache_ttl = 5.0  # Cache positions for 5 seconds

    async def sync_position_before_action(
        self,
        coin_symbol: str,
        trade_id: Optional[int] = None,
        action: Optional[str] = None
    ) -> Tuple[bool, Dict[str, Any], str]:
        """
        Sync position data from exchange before executing a critical action.

        Args:
            coin_symbol: Trading symbol (e.g., 'BTC', 'ETH')
            trade_id: Optional trade ID for logging
            action: Optional action name for logging

        Returns:
            Tuple of (success, position_data, error_message)
            position_data contains: position_size, entry_price, position_side, has_position
        """
        try:
            # Get trading pair
            if hasattr(self.exchange, 'get_futures_trading_pair'):
                trading_pair = self.exchange.get_futures_trading_pair(coin_symbol)
            else:
                trading_pair = f"{coin_symbol.upper()}USDT"

            # Check cache first
            cache_key = f"{trading_pair}_{coin_symbol}"
            cached = self._position_cache.get(cache_key)
            if cached:
                cache_age = (datetime.now(timezone.utc) - cached['timestamp']).total_seconds()
                if cache_age < self._cache_ttl:
                    logger.debug(
                        f"Using cached position data for {coin_symbol} "
                        f"(age: {cache_age:.1f}s, trade_id: {trade_id})"
                    )
                    return True, cached['data'], ""

            # Fetch fresh position data from exchange
            positions = await self.exchange.get_futures_position_information()

            position_data = {
                'position_size': 0.0,
                'entry_price': 0.0,
                'position_side': None,
                'has_position': False,
                'unrealized_pnl': 0.0
            }

            # Find matching position
            for pos in positions:
                pos_symbol = pos.get('symbol', '')
                # Handle both Binance and KuCoin formats
                if (pos_symbol == trading_pair or
                    pos_symbol == f"{coin_symbol.upper()}USDTM" or
                    pos_symbol.replace('USDT', '') == coin_symbol.upper()):

                    # Binance uses 'positionAmt', KuCoin uses 'currentQty' or 'size'
                    position_amt = float(
                        pos.get('positionAmt',
                               pos.get('currentQty',
                                      pos.get('size', 0)))
                    )

                    if abs(position_amt) != 0:
                        position_data['has_position'] = True
                        position_data['position_size'] = abs(position_amt)
                        position_data['position_side'] = 'LONG' if position_amt > 0 else 'SHORT'

                        # Get entry price (Binance uses 'entryPrice', KuCoin uses 'avgEntryPrice')
                        entry_price = float(
                            pos.get('entryPrice',
                                   pos.get('avgEntryPrice',
                                          pos.get('entry_price', 0)))
                        )
                        position_data['entry_price'] = entry_price

                        # Get unrealized PNL
                        unrealized_pnl = float(
                            pos.get('unRealizedProfit',
                                   pos.get('unrealizedPnl',
                                          pos.get('unrealized_pnl', 0)))
                        )
                        position_data['unrealized_pnl'] = unrealized_pnl

                        # Cache the result
                        self._position_cache[cache_key] = {
                            'data': position_data.copy(),
                            'timestamp': datetime.now(timezone.utc)
                        }

                        logger.info(
                            f"Synced position for {coin_symbol} (trade_id: {trade_id}, action: {action}): "
                            f"size={position_data['position_size']}, "
                            f"entry={position_data['entry_price']}, "
                            f"side={position_data['position_side']}"
                        )
                        break

            # If no position found, still cache the result (to avoid repeated queries)
            if not position_data['has_position']:
                self._position_cache[cache_key] = {
                    'data': position_data.copy(),
                    'timestamp': datetime.now(timezone.utc)
                }
                logger.info(
                    f"No active position found for {coin_symbol} (trade_id: {trade_id}, action: {action})"
                )

            return True, position_data, ""

        except Exception as e:
            error_msg = (
                f"Error syncing position for {coin_symbol} "
                f"(trade_id: {trade_id}, action: {action}): {e}"
            )
            logger.error(error_msg, exc_info=True)
            return False, {}, error_msg

    async def validate_position_for_action(
        self,
        coin_symbol: str,
        required_size: Optional[float] = None,
        trade_id: Optional[int] = None,
        action: Optional[str] = None
    ) -> Tuple[bool, str]:
        """
        Validate that position exists and has sufficient size for an action.

        Args:
            coin_symbol: Trading symbol
            required_size: Minimum required position size (None = any size > 0)
            trade_id: Optional trade ID for logging
            action: Optional action name for logging

        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            success, position_data, error_msg = await self.sync_position_before_action(
                coin_symbol, trade_id, action
            )

            if not success:
                return False, error_msg

            if not position_data['has_position']:
                return False, (
                    f"No active position found for {coin_symbol} "
                    f"(trade_id: {trade_id}, action: {action})"
                )

            if required_size and position_data['position_size'] < required_size:
                return False, (
                    f"Insufficient position size for {coin_symbol}: "
                    f"required={required_size}, actual={position_data['position_size']} "
                    f"(trade_id: {trade_id}, action: {action})"
                )

            return True, ""

        except Exception as e:
            error_msg = (
                f"Error validating position for {coin_symbol} "
                f"(trade_id: {trade_id}, action: {action}): {e}"
            )
            logger.error(error_msg, exc_info=True)
            return False, error_msg

    def clear_cache(self, coin_symbol: Optional[str] = None):
        """
        Clear position cache.

        Args:
            coin_symbol: Optional symbol to clear specific cache entry, None to clear all
        """
        if coin_symbol:
            # Clear specific symbol cache
            trading_pair = f"{coin_symbol.upper()}USDT"
            cache_key = f"{trading_pair}_{coin_symbol}"
            if cache_key in self._position_cache:
                del self._position_cache[cache_key]
                logger.debug(f"Cleared position cache for {coin_symbol}")
        else:
            # Clear all cache
            self._position_cache.clear()
            logger.debug("Cleared all position cache")

    async def get_position_size(
        self,
        coin_symbol: str,
        trade_id: Optional[int] = None
    ) -> float:
        """
        Get current position size for a symbol.

        Args:
            coin_symbol: Trading symbol
            trade_id: Optional trade ID for logging

        Returns:
            Position size (0.0 if no position)
        """
        try:
            success, position_data, _ = await self.sync_position_before_action(
                coin_symbol, trade_id, "get_position_size"
            )
            if success:
                return position_data.get('position_size', 0.0)
            return 0.0
        except Exception as e:
            logger.error(f"Error getting position size for {coin_symbol}: {e}")
            return 0.0

    async def get_entry_price(
        self,
        coin_symbol: str,
        trade_id: Optional[int] = None
    ) -> float:
        """
        Get entry price for a position.

        Args:
            coin_symbol: Trading symbol
            trade_id: Optional trade ID for logging

        Returns:
            Entry price (0.0 if no position)
        """
        try:
            success, position_data, _ = await self.sync_position_before_action(
                coin_symbol, trade_id, "get_entry_price"
            )
            if success and position_data.get('has_position'):
                return position_data.get('entry_price', 0.0)
            return 0.0
        except Exception as e:
            logger.error(f"Error getting entry price for {coin_symbol}: {e}")
            return 0.0

