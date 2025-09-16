"""
Position auditing utilities for the trading bot.

This module contains functions for auditing positions including
position verification, risk assessment, and compliance checking.
"""

import logging
from typing import Dict, Any, Optional, List, Tuple

logger = logging.getLogger(__name__)


class PositionAuditor:
    """
    Core class for auditing positions and risk management.
    """

    def __init__(self, exchange):
        """
        Initialize the position auditor.

        Args:
            exchange: The exchange instance (Binance, KuCoin, etc.)
        """
        self.exchange = exchange

    async def audit_all_positions(self) -> Dict[str, Any]:
        """
        Comprehensive audit of all positions for risk management compliance.

        Returns:
            Dictionary with comprehensive audit results
        """
        try:
            logger.info("Starting comprehensive position audit...")

            # Get all positions
            positions = await self.exchange.get_position_risk()

            audit_results = {
                'total_positions': 0,
                'open_positions': 0,
                'closed_positions': 0,
                'positions_with_sl': 0,
                'positions_without_sl': 0,
                'positions_with_tp': 0,
                'positions_without_tp': 0,
                'high_risk_positions': [],
                'errors': []
            }

            for position in positions:
                symbol = position.get('symbol')
                position_amt = float(position.get('positionAmt', 0))
                unrealized_pnl = float(position.get('unRealizedProfit', 0))
                entry_price = float(position.get('entryPrice', 0))
                mark_price = float(position.get('markPrice', 0))

                audit_results['total_positions'] += 1

                # Skip positions with zero size
                if position_amt == 0:
                    audit_results['closed_positions'] += 1
                    continue

                audit_results['open_positions'] += 1

                # Determine position type
                position_type = 'LONG' if position_amt > 0 else 'SHORT'

                # Check for stop loss
                has_sl = await self._check_position_has_stop_loss(symbol)
                if has_sl:
                    audit_results['positions_with_sl'] += 1
                else:
                    audit_results['positions_without_sl'] += 1

                # Check for take profit
                has_tp = await self._check_position_has_take_profit(symbol)
                if has_tp:
                    audit_results['positions_with_tp'] += 1
                else:
                    audit_results['positions_without_tp'] += 1

                # Risk assessment
                risk_level = await self._assess_position_risk(
                    symbol, position_type, position_amt, unrealized_pnl, entry_price, mark_price
                )

                if risk_level == 'HIGH':
                    audit_results['high_risk_positions'].append({
                        'symbol': symbol,
                        'position_type': position_type,
                        'position_size': position_amt,
                        'unrealized_pnl': unrealized_pnl,
                        'entry_price': entry_price,
                        'mark_price': mark_price,
                        'has_sl': has_sl,
                        'has_tp': has_tp
                    })

            logger.info(f"Comprehensive position audit completed: {audit_results}")
            return audit_results

        except Exception as e:
            logger.error(f"Error during comprehensive position audit: {e}")
            return {'error': str(e)}

    async def _check_position_has_stop_loss(self, trading_pair: str) -> bool:
        """
        Check if a position has active stop loss orders.

        Args:
            trading_pair: The trading pair (e.g., 'BTCUSDT')

        Returns:
            True if position has stop loss orders, False otherwise
        """
        try:
            open_orders = await self.exchange.get_all_open_futures_orders()

            if not open_orders:
                return False

            # Check for stop loss orders
            for order in open_orders:
                if (order.get('symbol') == trading_pair and
                    order.get('type') == 'STOP_MARKET'):
                    return True

            return False

        except Exception as e:
            logger.error(f"Error checking stop loss orders for {trading_pair}: {e}")
            return False

    async def _check_position_has_take_profit(self, trading_pair: str) -> bool:
        """
        Check if a position has active take profit orders.

        Args:
            trading_pair: The trading pair (e.g., 'BTCUSDT')

        Returns:
            True if position has take profit orders, False otherwise
        """
        try:
            open_orders = await self.exchange.get_all_open_futures_orders()

            if not open_orders:
                return False

            # Check for take profit orders
            for order in open_orders:
                if (order.get('symbol') == trading_pair and
                    order.get('type') == 'TAKE_PROFIT_MARKET'):
                    return True

            return False

        except Exception as e:
            logger.error(f"Error checking take profit orders for {trading_pair}: {e}")
            return False

    async def _assess_position_risk(
        self,
        symbol: str,
        position_type: str,
        position_amt: float,
        unrealized_pnl: float,
        entry_price: float,
        mark_price: float
    ) -> str:
        """
        Assess the risk level of a position.

        Args:
            symbol: The trading symbol
            position_type: The position type ('LONG' or 'SHORT')
            position_amt: The position amount
            unrealized_pnl: The unrealized PnL
            entry_price: The entry price
            mark_price: The current mark price

        Returns:
            Risk level ('LOW', 'MEDIUM', 'HIGH')
        """
        try:
            # Calculate percentage loss
            if entry_price > 0:
                if position_type == 'LONG':
                    percentage_change = ((mark_price - entry_price) / entry_price) * 100
                else:  # SHORT
                    percentage_change = ((entry_price - mark_price) / entry_price) * 100
            else:
                percentage_change = 0

            # Risk assessment criteria
            if percentage_change <= -10:  # 10% or more loss
                return 'HIGH'
            elif percentage_change <= -5:  # 5-10% loss
                return 'MEDIUM'
            elif unrealized_pnl < -100:  # Large absolute loss
                return 'HIGH'
            else:
                return 'LOW'

        except Exception as e:
            logger.error(f"Error assessing position risk for {symbol}: {e}")
            return 'MEDIUM'  # Default to medium risk on error

    async def get_position_summary(self) -> Dict[str, Any]:
        """
        Get a summary of all positions.

        Returns:
            Dictionary with position summary
        """
        try:
            positions = await self.exchange.get_position_risk()

            summary = {
                'total_positions': len(positions),
                'open_positions': 0,
                'total_unrealized_pnl': 0.0,
                'profitable_positions': 0,
                'losing_positions': 0,
                'position_types': {'LONG': 0, 'SHORT': 0}
            }

            for position in positions:
                position_amt = float(position.get('positionAmt', 0))
                unrealized_pnl = float(position.get('unRealizedProfit', 0))

                if position_amt != 0:
                    summary['open_positions'] += 1
                    summary['total_unrealized_pnl'] += unrealized_pnl

                    if unrealized_pnl > 0:
                        summary['profitable_positions'] += 1
                    elif unrealized_pnl < 0:
                        summary['losing_positions'] += 1

                    # Count position types
                    if position_amt > 0:
                        summary['position_types']['LONG'] += 1
                    else:
                        summary['position_types']['SHORT'] += 1

            return summary

        except Exception as e:
            logger.error(f"Error getting position summary: {e}")
            return {'error': str(e)}

    async def validate_position_compliance(self, symbol: str) -> Tuple[bool, List[str]]:
        """
        Validate if a position complies with risk management rules.

        Args:
            symbol: The trading symbol to validate

        Returns:
            Tuple of (is_compliant, list_of_violations)
        """
        try:
            violations = []

            # Check if position has stop loss
            has_sl = await self._check_position_has_stop_loss(symbol)
            if not has_sl:
                violations.append("Missing stop loss order")

            # Check if position has take profit
            has_tp = await self._check_position_has_take_profit(symbol)
            if not has_tp:
                violations.append("Missing take profit order")

            # Check position size limits (if implemented)
            # This could be expanded based on specific requirements

            is_compliant = len(violations) == 0
            return is_compliant, violations

        except Exception as e:
            logger.error(f"Error validating position compliance for {symbol}: {e}")
            return False, [f"Error during validation: {str(e)}"]
