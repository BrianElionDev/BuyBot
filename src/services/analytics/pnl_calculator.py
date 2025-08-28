import logging
from typing import Optional, Dict
from datetime import datetime
from .analytics_models import PnLData, AnalyticsConfig

logger = logging.getLogger(__name__)


class PnLCalculator:
    """Handles profit and loss calculations for trading positions"""

    def __init__(self, config: Optional[AnalyticsConfig] = None):
        """Initialize the PnL calculator"""
        self.config = config or AnalyticsConfig()

    def calculate_unrealized_pnl(
        self,
        symbol: str,
        position_type: str,
        entry_price: float,
        current_price: float,
        quantity: float,
        fees_paid: float = 0.0
    ) -> PnLData:
        """
        Calculate unrealized PnL for an open position

        Args:
            symbol: Trading symbol
            position_type: 'LONG' or 'SHORT'
            entry_price: Entry price of the position
            current_price: Current market price
            quantity: Position size
            fees_paid: Fees already paid

        Returns:
            PnLData with calculated values
        """
        if entry_price <= 0 or current_price <= 0 or quantity <= 0:
            raise ValueError("Entry price, current price, and quantity must be positive")

        # Calculate total cost and value
        total_cost = entry_price * quantity + fees_paid

        if position_type.upper() == "LONG":
            total_value = current_price * quantity
            unrealized_pnl = total_value - total_cost
        elif position_type.upper() == "SHORT":
            total_value = (2 * entry_price - current_price) * quantity
            unrealized_pnl = total_cost - (current_price * quantity)
        else:
            raise ValueError("Position type must be 'LONG' or 'SHORT'")

        return PnLData(
            symbol=symbol,
            position_type=position_type,
            entry_price=entry_price,
            current_price=current_price,
            quantity=quantity,
            unrealized_pnl=unrealized_pnl,
            fees_paid=fees_paid,
            total_cost=total_cost,
            total_value=total_value,
            entry_time=datetime.now()
        )

    def calculate_realized_pnl(
        self,
        symbol: str,
        position_type: str,
        entry_price: float,
        exit_price: float,
        quantity: float,
        entry_fees: float = 0.0,
        exit_fees: float = 0.0,
        entry_time: Optional[datetime] = None,
        exit_time: Optional[datetime] = None
    ) -> PnLData:
        """
        Calculate realized PnL for a closed position

        Args:
            symbol: Trading symbol
            position_type: 'LONG' or 'SHORT'
            entry_price: Entry price of the position
            exit_price: Exit price of the position
            quantity: Position size
            entry_fees: Fees paid on entry
            exit_fees: Fees paid on exit
            entry_time: When position was opened
            exit_time: When position was closed

        Returns:
            PnLData with calculated values
        """
        if entry_price <= 0 or exit_price <= 0 or quantity <= 0:
            raise ValueError("Entry price, exit price, and quantity must be positive")

        total_fees = entry_fees + exit_fees
        total_cost = entry_price * quantity + total_fees

        if position_type.upper() == "LONG":
            total_value = exit_price * quantity
            realized_pnl = total_value - total_cost
        elif position_type.upper() == "SHORT":
            total_value = (2 * entry_price - exit_price) * quantity
            realized_pnl = total_cost - (exit_price * quantity)
        else:
            raise ValueError("Position type must be 'LONG' or 'SHORT'")

        return PnLData(
            symbol=symbol,
            position_type=position_type,
            entry_price=entry_price,
            current_price=exit_price,
            quantity=quantity,
            unrealized_pnl=0.0,  # Position is closed
            realized_pnl=realized_pnl,
            entry_time=entry_time or datetime.now(),
            exit_time=exit_time or datetime.now(),
            fees_paid=total_fees,
            total_cost=total_cost,
            total_value=total_value
        )

    def calculate_pnl_percentage(self, pnl: float, total_cost: float) -> float:
        """
        Calculate PnL as a percentage of total cost

        Args:
            pnl: Profit or loss amount
            total_cost: Total cost of the position

        Returns:
            PnL percentage
        """
        if total_cost <= 0:
            return 0.0

        return (pnl / total_cost) * 100

    def calculate_breakeven_price(
        self,
        entry_price: float,
        position_type: str,
        fees_paid: float = 0.0,
        quantity: float = 1.0
    ) -> float:
        """
        Calculate breakeven price for a position

        Args:
            entry_price: Entry price of the position
            position_type: 'LONG' or 'SHORT'
            fees_paid: Total fees paid
            quantity: Position size

        Returns:
            Breakeven price
        """
        if quantity <= 0:
            raise ValueError("Quantity must be positive")

        total_fees_per_unit = fees_paid / quantity

        if position_type.upper() == "LONG":
            return entry_price + total_fees_per_unit
        elif position_type.upper() == "SHORT":
            return entry_price - total_fees_per_unit
        else:
            raise ValueError("Position type must be 'LONG' or 'SHORT'")

    def calculate_risk_reward_ratio(
        self,
        target_profit: float,
        stop_loss: float,
        entry_price: float,
        position_type: str
    ) -> float:
        """
        Calculate risk-reward ratio for a position

        Args:
            target_profit: Target profit price
            stop_loss: Stop loss price
            entry_price: Entry price
            position_type: 'LONG' or 'SHORT'

        Returns:
            Risk-reward ratio
        """
        if position_type.upper() == "LONG":
            reward = abs(target_profit - entry_price)
            risk = abs(entry_price - stop_loss)
        elif position_type.upper() == "SHORT":
            reward = abs(entry_price - target_profit)
            risk = abs(stop_loss - entry_price)
        else:
            raise ValueError("Position type must be 'LONG' or 'SHORT'")

        if risk <= 0:
            return 0.0

        return reward / risk

    def calculate_position_size_for_risk(
        self,
        account_balance: float,
        risk_percentage: float,
        entry_price: float,
        stop_loss: float,
        position_type: str
    ) -> float:
        """
        Calculate position size based on risk management

        Args:
            account_balance: Total account balance
            risk_percentage: Maximum risk as percentage of balance
            entry_price: Entry price
            stop_loss: Stop loss price
            position_type: 'LONG' or 'SHORT'

        Returns:
            Recommended position size
        """
        if risk_percentage <= 0 or risk_percentage > 100:
            raise ValueError("Risk percentage must be between 0 and 100")

        if position_type.upper() == "LONG":
            risk_per_unit = entry_price - stop_loss
        elif position_type.upper() == "SHORT":
            risk_per_unit = stop_loss - entry_price
        else:
            raise ValueError("Position type must be 'LONG' or 'SHORT'")

        if risk_per_unit <= 0:
            raise ValueError("Stop loss must be valid for position type")

        max_risk_amount = account_balance * (risk_percentage / 100)
        position_size = max_risk_amount / risk_per_unit

        return position_size

    def calculate_fees_impact(
        self,
        entry_price: float,
        exit_price: float,
        quantity: float,
        fee_rate: float,
        position_type: str
    ) -> Dict[str, float]:
        """
        Calculate the impact of fees on PnL

        Args:
            entry_price: Entry price
            exit_price: Exit price
            quantity: Position size
            fee_rate: Fee rate as decimal (e.g., 0.001 for 0.1%)
            position_type: 'LONG' or 'SHORT'

        Returns:
            Dictionary with fee calculations
        """
        entry_fees = entry_price * quantity * fee_rate
        exit_fees = exit_price * quantity * fee_rate
        total_fees = entry_fees + exit_fees

        # Calculate PnL without fees
        if position_type.upper() == "LONG":
            gross_pnl = (exit_price - entry_price) * quantity
        elif position_type.upper() == "SHORT":
            gross_pnl = (entry_price - exit_price) * quantity
        else:
            raise ValueError("Position type must be 'LONG' or 'SHORT'")

        net_pnl = gross_pnl - total_fees
        fees_impact_percentage = (total_fees / abs(gross_pnl)) * 100 if gross_pnl != 0 else 0

        return {
            'entry_fees': entry_fees,
            'exit_fees': exit_fees,
            'total_fees': total_fees,
            'gross_pnl': gross_pnl,
            'net_pnl': net_pnl,
            'fees_impact_percentage': fees_impact_percentage
        }
