"""
Unified Status Management

This module provides a single source of truth for status mapping between
exchange order statuses and internal position statuses.
"""

from typing import Tuple, Optional
import logging

logger = logging.getLogger(__name__)

class StatusManager:
    """Unified status management for orders and positions."""

    # Exchange order statuses
    ORDER_STATUS = {
        'NEW': 'NEW',
        'PARTIALLY_FILLED': 'PARTIALLY_FILLED',
        'FILLED': 'FILLED',
        'CANCELED': 'CANCELED',
        'CANCELED': 'CANCELED',  # Handle both spellings
        'REJECTED': 'REJECTED',
        'EXPIRED': 'EXPIRED'
    }

    # Internal position statuses
    POSITION_STATUS = {
        'PENDING': 'PENDING',     # Order placed, waiting for fill
        'ACTIVE': 'ACTIVE',       # Position is open
        'CLOSED': 'CLOSED',       # Position is closed
        'FAILED': 'FAILED',       # Order failed
        'CANCELLED': 'CANCELLED'  # Order was cancelled
    }

    @staticmethod
    def map_exchange_to_internal(exchange_status: str, position_size: float = 0) -> Tuple[str, str]:
        """
        Map exchange order status to internal order_status and position status.

        Args:
            exchange_status: Exchange order status (NEW, FILLED, etc.)
            position_size: Current position size (0 means no position)

        Returns:
            Tuple of (order_status, position_status)
        """
        exchange_status = str(exchange_status).upper().strip()

        # Handle edge cases
        if not exchange_status or exchange_status == 'NONE':
            return ('NEW', 'PENDING')

        # Map exchange status to order status
        order_status = StatusManager.ORDER_STATUS.get(exchange_status, 'NEW')

        # Determine position status based on order status and position size
        if order_status == 'FILLED':
            if position_size > 0:
                position_status = 'ACTIVE'
            else:
                position_status = 'CLOSED'  # Exit order filled
        elif order_status == 'PARTIALLY_FILLED':
            if position_size > 0:
                position_status = 'ACTIVE'
            else:
                position_status = 'PENDING'  # Partial fill, still waiting
        elif order_status in ['CANCELED', 'CANCELLED', 'EXPIRED']:
            position_status = 'CANCELLED'
        elif order_status == 'REJECTED':
            position_status = 'FAILED'
        elif order_status == 'NEW':
            position_status = 'PENDING'
        else:
            position_status = 'PENDING'

        return (order_status, position_status)

    @staticmethod
    def validate_status_consistency(order_status: str, position_status: str) -> bool:
        """
        Validate that order_status and position_status are consistent.

        Args:
            order_status: Current order status
            position_status: Current position status

        Returns:
            True if consistent, False otherwise
        """
        order_status = str(order_status).upper().strip()
        position_status = str(position_status).upper().strip()

        # Define valid combinations
        valid_combinations = {
            'NEW': ['PENDING'],
            'PARTIALLY_FILLED': ['ACTIVE', 'PENDING'],
            'FILLED': ['ACTIVE', 'CLOSED'],
            'CANCELED': ['CANCELLED'],
            'CANCELLED': ['CANCELLED'],
            'REJECTED': ['FAILED'],
            'FAILED': ['FAILED'],  # Allow FAILED order_status with FAILED position_status
            'EXPIRED': ['CANCELLED']
        }

        valid_positions = valid_combinations.get(order_status, [])
        return position_status in valid_positions

    @staticmethod
    def fix_inconsistent_status(order_status: str, position_status: str) -> Tuple[str, str]:
        """
        Fix inconsistent status by determining the correct position status
        based on the order status.

        Args:
            order_status: Current order status
            position_status: Current position status

        Returns:
            Tuple of (corrected_order_status, corrected_position_status)
        """
        order_status = str(order_status).upper().strip()
        position_status = str(position_status).upper().strip()

        # If order is filled but position is pending, position should be active
        if order_status == 'FILLED' and position_status == 'PENDING':
            return (order_status, 'ACTIVE')

        # If order is canceled but position is active, position should be cancelled
        if order_status in ['CANCELED', 'CANCELLED'] and position_status == 'ACTIVE':
            return (order_status, 'CANCELLED')

        # If order is rejected but position is active, position should be failed
        if order_status == 'REJECTED' and position_status == 'ACTIVE':
            return (order_status, 'FAILED')

        # If order is new but position is closed, position should be pending
        if order_status == 'NEW' and position_status == 'CLOSED':
            return (order_status, 'PENDING')

        # Default: return as-is if no obvious fix
        return (order_status, position_status)
