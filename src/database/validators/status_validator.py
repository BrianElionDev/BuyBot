"""
Status Validation

This module provides validation functions to ensure status consistency
when updating trades in the database.
"""

import logging
from typing import Dict, Any, Optional, Tuple
from src.core.status_manager import StatusManager

logger = logging.getLogger(__name__)

class StatusValidator:
    """Validates trade status updates for consistency."""

    @staticmethod
    def validate_trade_update(update_data: Dict[str, Any], current_trade: Optional[Dict[str, Any]] = None) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Validate a trade update to ensure status consistency.

        Args:
            update_data: The update data being applied
            current_trade: Current trade data (if available)

        Returns:
            Tuple of (is_valid, error_message, corrected_data)
        """
        corrected_data = update_data.copy()

        # Check if status fields are being updated
        if 'order_status' in update_data or 'status' in update_data:
            order_status = update_data.get('order_status')
            position_status = update_data.get('status')

            # If we have current trade data, use it for missing fields
            if current_trade:
                if order_status is None:
                    order_status = current_trade.get('order_status')
                if position_status is None:
                    position_status = current_trade.get('status')

            # If both status fields are present, validate consistency
            if order_status and position_status:
                if not StatusManager.validate_status_consistency(order_status, position_status):
                    # Try to fix the inconsistency
                    fixed_order, fixed_position = StatusManager.fix_inconsistent_status(order_status, position_status)

                    if StatusManager.validate_status_consistency(fixed_order, fixed_position):
                        corrected_data['order_status'] = fixed_order
                        corrected_data['status'] = fixed_position
                        logger.warning(f"Fixed inconsistent status: {order_status}/{position_status} -> {fixed_order}/{fixed_position}")
                    else:
                        return False, f"Inconsistent status combination: order_status='{order_status}', status='{position_status}'", corrected_data

            # If only order_status is being updated, determine correct position_status
            elif order_status and not position_status:
                if current_trade:
                    position_size = current_trade.get('position_size', 0) or 0
                    _, correct_position = StatusManager.map_exchange_to_internal(order_status, position_size)
                    corrected_data['status'] = correct_position
                    logger.info(f"Auto-corrected position status to '{correct_position}' for order_status '{order_status}'")

            # If only position_status is being updated, validate against current order_status
            elif position_status and not order_status:
                if current_trade:
                    current_order_status = current_trade.get('order_status')
                    if current_order_status and not StatusManager.validate_status_consistency(current_order_status, position_status):
                        return False, f"Position status '{position_status}' inconsistent with order status '{current_order_status}'", corrected_data

        return True, "", corrected_data

    @staticmethod
    def validate_trade_creation(trade_data: Dict[str, Any]) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Validate trade creation data for status consistency.

        Args:
            trade_data: The trade data being created

        Returns:
            Tuple of (is_valid, error_message, corrected_data)
        """
        corrected_data = trade_data.copy()

        # Ensure default status values
        if 'status' not in corrected_data:
            corrected_data['status'] = 'PENDING'

        if 'order_status' not in corrected_data:
            corrected_data['order_status'] = 'NEW'

        # Validate consistency
        order_status = corrected_data.get('order_status')
        position_status = corrected_data.get('status')

        if order_status and position_status:
            if not StatusManager.validate_status_consistency(order_status, position_status):
                # Fix inconsistency
                fixed_order, fixed_position = StatusManager.fix_inconsistent_status(order_status, position_status)
                corrected_data['order_status'] = fixed_order
                corrected_data['status'] = fixed_position
                logger.warning(f"Fixed inconsistent status in trade creation: {order_status}/{position_status} -> {fixed_order}/{fixed_position}")

        return True, "", corrected_data
