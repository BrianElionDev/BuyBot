"""
Transaction management utilities for ensuring atomic operations.
"""

import logging
from typing import Any, Callable, List, Optional, Dict
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timezone

from src.core.response_models import ServiceResponse, ErrorCode

logger = logging.getLogger(__name__)


@dataclass
class TransactionStep:
    """Represents a single step in a transaction."""
    name: str
    operation: Callable
    rollback: Optional[Callable] = None
    data: Optional[Dict[str, Any]] = None


class TransactionManager:
    """Manages multi-step transactions with rollback capabilities."""

    def __init__(self):
        self.steps: List[TransactionStep] = []
        self.completed_steps: List[TransactionStep] = []
        self.transaction_id: Optional[str] = None

    def add_step(
        self,
        name: str,
        operation: Callable,
        rollback: Optional[Callable] = None,
        data: Optional[Dict[str, Any]] = None
    ) -> 'TransactionManager':
        """Add a step to the transaction."""
        step = TransactionStep(name=name, operation=operation, rollback=rollback, data=data)
        self.steps.append(step)
        return self

    async def execute(self) -> ServiceResponse:
        """Execute all transaction steps with rollback on failure."""
        self.transaction_id = f"txn_{datetime.now(timezone.utc).timestamp()}"
        logger.info(f"Starting transaction {self.transaction_id} with {len(self.steps)} steps")

        try:
            for step in self.steps:
                logger.debug(f"Executing step: {step.name}")

                # Execute the operation
                result = await step.operation()

                # Check if operation was successful
                if isinstance(result, ServiceResponse) and not result.success:
                    logger.error(f"Step {step.name} failed: {result.error}")
                    await self._rollback()
                    return ServiceResponse.error_response(
                        error=f"Transaction failed at step '{step.name}': {result.error}",
                        error_code=result.error_code or ErrorCode.UNKNOWN_ERROR,
                        metadata={"transaction_id": self.transaction_id, "failed_step": step.name}
                    )

                # Mark step as completed
                self.completed_steps.append(step)
                logger.debug(f"Step {step.name} completed successfully")

            logger.info(f"Transaction {self.transaction_id} completed successfully")
            return ServiceResponse.success_response(
                data={"transaction_id": self.transaction_id, "steps_completed": len(self.completed_steps)},
                metadata={"transaction_id": self.transaction_id}
            )

        except Exception as e:
            logger.error(f"Transaction {self.transaction_id} failed with exception: {e}")
            await self._rollback()
            return ServiceResponse.error_response(
                error=f"Transaction failed with exception: {str(e)}",
                error_code=ErrorCode.UNKNOWN_ERROR,
                metadata={"transaction_id": self.transaction_id}
            )

    async def _rollback(self) -> None:
        """Rollback completed steps in reverse order."""
        if not self.completed_steps:
            logger.info(f"No steps to rollback for transaction {self.transaction_id}")
            return

        logger.info(f"Rolling back transaction {self.transaction_id}")

        # Rollback in reverse order
        for step in reversed(self.completed_steps):
            if step.rollback:
                try:
                    logger.debug(f"Rolling back step: {step.name}")
                    await step.rollback()
                    logger.debug(f"Step {step.name} rolled back successfully")
                except Exception as e:
                    logger.error(f"Failed to rollback step {step.name}: {e}")
                    # Continue with other rollbacks even if one fails
            else:
                logger.warning(f"No rollback function defined for step: {step.name}")

        logger.info(f"Transaction {self.transaction_id} rollback completed")


@asynccontextmanager
async def transaction_context():
    """Context manager for transaction operations."""
    manager = TransactionManager()
    try:
        yield manager
        result = await manager.execute()
        if not result.success:
            raise Exception(f"Transaction failed: {result.error}")
    except Exception as e:
        logger.error(f"Transaction context failed: {e}")
        raise


class DatabaseTransactionManager:
    """Specialized transaction manager for database operations."""

    def __init__(self, db_manager):
        self.db_manager = db_manager
        self.transaction_manager = TransactionManager()

    async def execute_trade_closure_transaction(
        self,
        trade: Any,
        active_futures: Any,
        position_manager: Any
    ) -> ServiceResponse:
        """Execute a complete trade closure transaction."""

        # Step 1: Cancel existing TP/SL orders
        self.transaction_manager.add_step(
            name="cancel_tp_sl_orders",
            operation=lambda: self._cancel_tp_sl_orders(trade),
            rollback=lambda: self._restore_tp_sl_orders(trade)
        )

        # Step 2: Close position at market
        self.transaction_manager.add_step(
            name="close_position",
            operation=lambda: position_manager.close_position_at_market(
                trade, "active_futures_closed", 100.0
            ),
            rollback=lambda: self._restore_position(trade)
        )

        # Step 3: Update trade status in database
        self.transaction_manager.add_step(
            name="update_trade_status",
            operation=lambda: self._update_trade_status(trade),
            rollback=lambda: self._restore_trade_status(trade)
        )

        return await self.transaction_manager.execute()

    async def _cancel_tp_sl_orders(self, trade: Any) -> ServiceResponse:
        """Cancel TP/SL orders for a trade."""
        try:
            # Implementation would depend on the specific order cancellation logic
            # This is a placeholder for the actual implementation
            logger.info(f"Cancelling TP/SL orders for trade {trade.discord_id}")
            return ServiceResponse.success_response()
        except Exception as e:
            return ServiceResponse.error_response(
                error=f"Failed to cancel TP/SL orders: {str(e)}",
                error_code=ErrorCode.ORDER_FAILED
            )

    async def _restore_tp_sl_orders(self, trade: Any) -> None:
        """Restore TP/SL orders (rollback operation)."""
        logger.info(f"Restoring TP/SL orders for trade {trade.discord_id}")
        # Implementation would restore the original TP/SL orders
        pass

    async def _update_trade_status(self, trade: Any) -> ServiceResponse:
        """Update trade status in database."""
        try:
            # Implementation would update the trade status
            logger.info(f"Updating trade status for {trade.discord_id}")
            return ServiceResponse.success_response()
        except Exception as e:
            return ServiceResponse.error_response(
                error=f"Failed to update trade status: {str(e)}",
                error_code=ErrorCode.DATABASE_ERROR
            )

    async def _restore_trade_status(self, trade: Any) -> None:
        """Restore original trade status (rollback operation)."""
        logger.info(f"Restoring trade status for {trade.discord_id}")
        # Implementation would restore the original trade status
        pass

    async def _restore_position(self, trade: Any) -> None:
        """Restore position (rollback operation)."""
        logger.info(f"Restoring position for trade {trade.discord_id}")
        # Implementation would restore the original position
        pass
