"""
Price range handling utilities for trading operations.
"""

import logging
from typing import List, Optional, Tuple

from src.core.constants import ORDER_TYPE_MARKET, ORDER_TYPE_LIMIT, POSITION_TYPE_LONG, POSITION_TYPE_SHORT

logger = logging.getLogger(__name__)


class PriceRangeHandler:
    """Handles price range logic for different order types."""

    @staticmethod
    def handle_price_range_logic(
        entry_prices: Optional[List[float]],
        order_type: str,
        position_type: str,
        current_price: float
    ) -> Tuple[Optional[float], str]:
        """
        Handle price range logic for different order types.

        Args:
            entry_prices: List of entry prices (can be a range)
            order_type: MARKET or LIMIT
            position_type: LONG or SHORT
            current_price: Current market price

        Returns:
            Tuple of (effective_price, decision_reason)
        """
        if not entry_prices or len(entry_prices) == 0:
            return current_price, "No entry prices provided, using current market price"

        # Single price (no range)
        if len(entry_prices) == 1:
            return entry_prices[0], "Single entry price provided"

        # Price range detected
        if len(entry_prices) == 2:
            return PriceRangeHandler._handle_two_price_range(
                entry_prices, order_type, position_type, current_price
            )

        # More than 2 prices (complex range or multiple entry points)
        if len(entry_prices) > 2:
            return PriceRangeHandler._handle_multiple_prices(
                entry_prices, order_type, position_type, current_price
            )

        # Fallback
        return current_price, "Fallback to current market price"

    @staticmethod
    def _handle_two_price_range(
        entry_prices: List[float],
        order_type: str,
        position_type: str,
        current_price: float
    ) -> Tuple[Optional[float], str]:
        """Handle two-price range logic."""
        lower_bound = min(entry_prices)
        upper_bound = max(entry_prices)

        if order_type.upper() == ORDER_TYPE_MARKET:
            return PriceRangeHandler._handle_market_order_range(
                lower_bound, upper_bound, position_type, current_price
            )
        elif order_type.upper() == ORDER_TYPE_LIMIT:
            return PriceRangeHandler._handle_limit_order_range(
                lower_bound, upper_bound, position_type, current_price
            )
        else:
            # Unknown order type
            return entry_prices[0], f"Unknown order type '{order_type}' - using first price {entry_prices[0]:.8f}"

    @staticmethod
    def _handle_market_order_range(
        lower_bound: float,
        upper_bound: float,
        position_type: str,
        current_price: float
    ) -> Tuple[Optional[float], str]:
        """Handle market order with price range."""
        if position_type.upper() == POSITION_TYPE_LONG:
            # For long positions, only execute if current price is at or below the upper bound
            if current_price <= upper_bound:
                return current_price, f"Market order - executing at current price ${current_price:.8f} (within range ${lower_bound:.8f}-${upper_bound:.8f})"
            else:
                return None, f"Market order REJECTED - current price ${current_price:.8f} above range ${lower_bound:.8f}-${upper_bound:.8f}"
        elif position_type.upper() == POSITION_TYPE_SHORT:
            # For short positions, only execute if current price is at or above the lower bound
            if current_price >= lower_bound:
                return current_price, f"Market order - executing at current price ${current_price:.8f} (within range ${lower_bound:.8f}-${upper_bound:.8f})"
            else:
                return None, f"Market order REJECTED - current price ${current_price:.8f} below range ${lower_bound:.8f}-${upper_bound:.8f}"
        else:
            # Unknown position type - execute at current price
            return current_price, f"Market order - executing at current price ${current_price:.8f} (unknown position type)"

    @staticmethod
    def _handle_limit_order_range(
        lower_bound: float,
        upper_bound: float,
        position_type: str,
        current_price: float
    ) -> Tuple[float, str]:
        """Handle limit order with price range."""
        if position_type.upper() == POSITION_TYPE_LONG:
            # For long positions, place limit at upper bound (best buy price)
            effective_price = upper_bound
            reason = f"Long limit order - placing at upper bound ${upper_bound:.8f} (range: ${lower_bound:.8f}-${upper_bound:.8f})"

            # Add context about current price relative to range
            if current_price > upper_bound:
                reason += f" - Current price ${current_price:.8f} above range, waiting for entry"
            elif current_price < lower_bound:
                reason += f" - Current price ${current_price:.8f} below range, order may fill immediately"
            else:
                reason += f" - Current price ${current_price:.8f} within range"

        elif position_type.upper() == POSITION_TYPE_SHORT:
            effective_price = lower_bound
            reason = f"Short limit order - placing at lower bound ${lower_bound:.8f} (range: ${lower_bound:.8f}-${upper_bound:.8f})"

            # Add context about current price relative to range
            if current_price < lower_bound:
                reason += f" - Current price ${current_price:.8f} below range, waiting for entry"
            elif current_price > upper_bound:
                reason += f" - Current price ${current_price:.8f} above range, order may fill immediately"
            else:
                reason += f" - Current price ${current_price:.8f} within range"
        else:
            # Default to first price for unknown position types
            effective_price = lower_bound  # Use lower bound as fallback
            reason = f"Unknown position type '{position_type}' - using lower bound ${effective_price:.8f}"

        return effective_price, reason

    @staticmethod
    def _handle_multiple_prices(
        entry_prices: List[float],
        order_type: str,
        position_type: str,
        current_price: float
    ) -> Tuple[float, str]:
        """Handle multiple entry prices."""
        if order_type.upper() == ORDER_TYPE_MARKET:
            return current_price, f"Market order with multiple prices - executing at current price ${current_price:.8f}"
        else:
            # For limit orders, use the most favorable price based on position type
            if position_type.upper() == POSITION_TYPE_LONG:
                effective_price = min(entry_prices)  # Best buy price
                reason = f"Long limit order with multiple prices - using lowest price ${effective_price:.8f}"
            elif position_type.upper() == POSITION_TYPE_SHORT:
                effective_price = max(entry_prices)  # Best sell price
                reason = f"Short limit order with multiple prices - using highest price ${effective_price:.8f}"
            else:
                effective_price = entry_prices[0]
                reason = f"Unknown position type with multiple prices - using first price ${effective_price:.8f}"

            return effective_price, reason
