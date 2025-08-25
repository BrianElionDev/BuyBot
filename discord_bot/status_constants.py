"""
Status constants and mapping functions for order and position status.
This module provides clear separation between order lifecycle and position lifecycle.
"""

# Order Status Constants
ORDER_STATUS = {
    'NEW': 'UNFILLED',          # Order created but not yet executed
    'PARTIALLY_FILLED': 'PARTIALLY_FILLED',  # Order partially executed
    'FILLED': 'FILLED',         # Order fully executed
    'CANCELED': 'CANCELED',     # Order was canceled
    'EXPIRED': 'EXPIRED',       # Order expired
    'REJECTED': 'REJECTED'      # Order was rejected
}

# Position Status Constants
POSITION_STATUS = {
    'NONE': 'NONE',           # No position exists
    'OPEN': 'OPEN',           # Position is active
    'PARTIALLY_CLOSED': 'PARTIALLY_CLOSED',  # Position partially closed
    'CLOSED': 'CLOSED'       # Position fully closed
}

# Overall Trade Status
TRADE_STATUS = {
    'PENDING': 'PENDING',     # Order pending, no position
    'ACTIVE': 'ACTIVE',       # Order filled, position open
    'CLOSED': 'CLOSED',      # Position closed
    'FAILED': 'FAILED'       # Order failed
}

def map_binance_order_status(binance_status: str) -> str:
    """Map Binance order status to our order_status column."""
    return ORDER_STATUS.get(binance_status.upper(), 'PENDING')

def determine_position_status_from_order(order_status: str, position_size: float = 0, is_exit_order: bool = False) -> str:
    """
    Determine position status based on order status and position size.

    Args:
        order_status: The order status (FILLED, PARTIALLY_FILLED, etc.)
        position_size: Current position size (0 means no position)
        is_exit_order: Whether this is an exit order (reduceOnly=True or closePosition=True)

    Returns:
        Position status string
    """
    if order_status == 'FILLED':
        if is_exit_order:
            return POSITION_STATUS['CLOSED']  # Exit order filled = position closed
        elif position_size > 0:
            return POSITION_STATUS['OPEN']    # Entry order filled = position open
        else:
            return POSITION_STATUS['NONE']    # No position
    elif order_status == 'PARTIALLY_FILLED':
        if is_exit_order:
            return POSITION_STATUS['PARTIALLY_CLOSED']  # Exit order partially filled
        elif position_size > 0:
            return POSITION_STATUS['OPEN']    # Entry order partially filled = position open
        else:
            return POSITION_STATUS['NONE']
    elif order_status == 'UNFILLED':
        return POSITION_STATUS['NONE']  # Order unfilled = no position yet
    elif order_status in ['CANCELED', 'EXPIRED', 'REJECTED']:
        return POSITION_STATUS['NONE']
    else:
        return POSITION_STATUS['NONE']

def determine_overall_trade_status(order_status: str, position_status: str) -> str:
    """
    Determine overall trade status for backward compatibility.

    Args:
        order_status: Order status
        position_status: Position status

    Returns:
        Overall trade status
    """
    if order_status in ['CANCELED', 'EXPIRED', 'REJECTED']:
        return TRADE_STATUS['FAILED']
    elif position_status == POSITION_STATUS['OPEN']:
        return TRADE_STATUS['ACTIVE']
    elif position_status == POSITION_STATUS['CLOSED']:
        return TRADE_STATUS['CLOSED']
    elif order_status == 'PENDING':
        return TRADE_STATUS['PENDING']
    else:
        return TRADE_STATUS['PENDING']