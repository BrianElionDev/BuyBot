"""
Price calculation utilities for the trading bot.

This module contains utility functions for calculating various price-related
values including stop losses, take profits, and price range logic.
"""

import logging
from typing import Optional, List, Tuple

logger = logging.getLogger(__name__)


class PriceCalculator:
    """
    Utility class for price-related calculations.
    """

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
            lower_bound = min(entry_prices)
            upper_bound = max(entry_prices)

            if order_type.upper() == "MARKET":
                # Market orders should only execute if current price is within the specified range
                if position_type.upper() == "LONG":
                    # For long positions, only execute if current price is at or below the upper bound
                    if current_price <= upper_bound:
                        return current_price, f"Market order - executing at current price ${current_price:.8f} (within range ${lower_bound:.8f}-${upper_bound:.8f})"
                    else:
                        return None, f"Market order REJECTED - current price ${current_price:.8f} above range ${lower_bound:.8f}-${upper_bound:.8f}"
                elif position_type.upper() == "SHORT":
                    # For short positions, only execute if current price is at or above the lower bound
                    if current_price >= lower_bound:
                        return current_price, f"Market order - executing at current price ${current_price:.8f} (within range ${lower_bound:.8f}-${upper_bound:.8f})"
                    else:
                        return None, f"Market order REJECTED - current price ${current_price:.8f} below range ${lower_bound:.8f}-${upper_bound:.8f}"
                else:
                    # Unknown position type - execute at current price
                    return current_price, f"Market order - executing at current price ${current_price:.8f} (unknown position type)"

            elif order_type.upper() == "LIMIT":
                if position_type.upper() == "LONG":
                    # For long positions, place limit at upper bound (best buy price)
                    effective_price = upper_bound
                    reason = f"Long limit order - placing at upper bound ${upper_bound:.8f} (range: ${lower_bound:.8f}-${upper_bound:.8f})"

                    # Optional: Only place if current price is above the range (waiting for price to drop)
                    if current_price > upper_bound:
                        reason += f" - Current price ${current_price:.8f} above range, waiting for entry"
                    elif current_price < lower_bound:
                        reason += f" - Current price ${current_price:.8f} below range, order may fill immediately"
                    else:
                        reason += f" - Current price ${current_price:.8f} within range"

                elif position_type.upper() == "SHORT":
                    # For short positions, place limit at lower bound (best sell price)
                    effective_price = lower_bound
                    reason = f"Short limit order - placing at lower bound ${lower_bound:.8f} (range: ${lower_bound:.8f}-${upper_bound:.8f})"

                    # Optional: Only place if current price is below the range (waiting for price to rise)
                    if current_price < lower_bound:
                        reason += f" - Current price ${current_price:.8f} below range, waiting for entry"
                    elif current_price > upper_bound:
                        reason += f" - Current price ${current_price:.8f} above range, order may fill immediately"
                    else:
                        reason += f" - Current price ${current_price:.8f} within range"

                else:
                    # Unknown position type - use middle of range
                    effective_price = (lower_bound + upper_bound) / 2
                    reason = f"Unknown position type - placing at middle of range ${effective_price:.8f}"

                return effective_price, reason

        # More than 2 prices - use the first one
        else:
            return entry_prices[0], f"Multiple entry prices provided, using first price: ${entry_prices[0]:.8f}"

        # Fallback - should never reach here
        return current_price, "Fallback: using current market price"

    @staticmethod
    def calculate_percentage_stop_loss(
        current_price: float,
        position_type: str,
        percentage: float
    ) -> Optional[float]:
        """
        Calculate a percentage-based stop loss price from the current market price.

        Args:
            current_price: Current market price
            position_type: The position type ('LONG' or 'SHORT')
            percentage: The percentage for stop loss calculation (e.g., 2.0 for 2%)

        Returns:
            The calculated stop loss price or None if calculation fails
        """
        try:
            # Validate percentage input
            if percentage <= 0 or percentage > 50:  # Reasonable range: 0.1% to 50%
                logger.error(f"Invalid stop loss percentage: {percentage}%. Must be between 0.1 and 50.")
                return None

            # Calculate percentage-based stop loss from current price
            if position_type.upper() == 'LONG':
                stop_loss_price = current_price * (1 - percentage / 100)  # percentage below current price
                logger.info(f"LONG position: Calculated {percentage}% stop loss. Current: {current_price}, SL: {stop_loss_price}")
            elif position_type.upper() == 'SHORT':
                stop_loss_price = current_price * (1 + percentage / 100)  # percentage above current price
                logger.info(f"SHORT position: Calculated {percentage}% stop loss. Current: {current_price}, SL: {stop_loss_price}")
            else:
                logger.error(f"Unknown position type: {position_type}")
                return None

            return stop_loss_price

        except Exception as e:
            logger.error(f"Error calculating {percentage}% stop loss: {e}")
            return None

    @staticmethod
    def calculate_5_percent_stop_loss(
        entry_price: float,
        position_type: str
    ) -> Optional[float]:
        """
        Calculate a 5% stop loss price from the entry price (supervisor requirement).

        Args:
            entry_price: The entry price for the position
            position_type: The position type ('LONG' or 'SHORT')

        Returns:
            The calculated stop loss price or None if calculation fails
        """
        try:
            if entry_price <= 0:
                logger.error(f"Invalid entry price: {entry_price}")
                return None

            # Calculate 5% stop loss from entry price (supervisor requirement)
            if position_type.upper() == 'LONG':
                stop_loss_price = entry_price * (1 - 0.05)
                logger.info(f"LONG position: Calculated 5% stop loss from entry. Entry: {entry_price}, SL: {stop_loss_price}")
            elif position_type.upper() == 'SHORT':
                stop_loss_price = entry_price * (1 + 0.05)
                logger.info(f"SHORT position: Calculated 5% stop loss from entry. Entry: {entry_price}, SL: {stop_loss_price}")
            else:
                logger.error(f"Unknown position type: {position_type}")
                return None

            return stop_loss_price

        except Exception as e:
            logger.error(f"Error calculating 5% stop loss: {e}")
            return None

    @staticmethod
    def calculate_5_percent_take_profit(
        entry_price: float,
        position_type: str
    ) -> Optional[float]:
        """
        Calculate a 5% take profit price from the entry price.

        Args:
            entry_price: The entry price for the position
            position_type: The position type ('LONG' or 'SHORT')

        Returns:
            The calculated take profit price or None if calculation fails
        """
        try:
            if entry_price <= 0:
                logger.error(f"Invalid entry price: {entry_price}")
                return None

            # Calculate 5% take profit from entry price
            if position_type.upper() == 'LONG':
                take_profit_price = entry_price * (1 + 0.05)
                logger.info(f"LONG position: Calculated 5% take profit from entry. Entry: {entry_price}, TP: {take_profit_price}")
            elif position_type.upper() == 'SHORT':
                take_profit_price = entry_price * (1 - 0.05)
                logger.info(f"SHORT position: Calculated 5% take profit from entry. Entry: {entry_price}, TP: {take_profit_price}")
            else:
                logger.error(f"Unknown position type: {position_type}")
                return None

            return take_profit_price

        except Exception as e:
            logger.error(f"Error calculating 5% take profit: {e}")
            return None
