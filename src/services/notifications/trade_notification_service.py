"""
Trade Notification Service

This module provides reliable trade status notifications with maximum fault tolerance.
Designed to never become a failure point in the trading system.
"""

import logging
import asyncio
from datetime import datetime, timezone
from typing import Optional, Dict, Any, Union
from dataclasses import dataclass

from src.services.notifications.telegram_service import TelegramService

logger = logging.getLogger(__name__)

@dataclass
class TradeExecutionData:
    """Data for trade execution success notification."""
    symbol: str
    position_type: str
    entry_price: float
    quantity: float
    order_id: str
    timestamp: Optional[datetime] = None

@dataclass
class OrderFillData:
    """Data for order fill notification."""
    symbol: str
    position_type: str
    fill_price: float
    fill_quantity: float
    order_id: str
    timestamp: Optional[datetime] = None

@dataclass
class PnLUpdateData:
    """Data for PnL update notification."""
    symbol: str
    position_type: str
    entry_price: float
    current_price: float
    quantity: float
    unrealized_pnl: float
    timestamp: Optional[datetime] = None

@dataclass
class  StopLossData:
    """Data for stop-loss trigger notification."""
    symbol: str
    position_type: str
    entry_price: float
    stop_loss_price: float
    quantity: float
    realized_pnl: float
    timestamp: Optional[datetime] = None

@dataclass
class TakeProfitData:
    """Data for take-profit trigger notification."""
    symbol: str
    position_type: str
    entry_price: float
    take_profit_price: float
    quantity: float
    realized_pnl: float
    timestamp: Optional[datetime] = None

class TradeNotificationService:
    """
    Reliable trade notification service with maximum fault tolerance.

    This service is designed to never fail and never block trading operations.
    All methods are non-blocking and have comprehensive error handling.
    """

    def __init__(self):
        self.telegram_service = TelegramService()
        self._notification_queue = asyncio.Queue(maxsize=1000)
        self._is_running = False

    async def _safe_send_message(self, message: str, retry_count: int = 3) -> bool:
        """
        Safely send a message with retry logic.
        Never raises exceptions - always returns success/failure status.
        """
        for attempt in range(retry_count):
            try:
                success = await self.telegram_service.send_message(message)
                if success:
                    return True
                logger.warning(f"Telegram send attempt {attempt + 1} failed, retrying...")
            except Exception as e:
                logger.error(f"Telegram send attempt {attempt + 1} error: {e}")

            if attempt < retry_count - 1:
                await asyncio.sleep(0.5 * (attempt + 1))  # Exponential backoff

        logger.error("All Telegram send attempts failed")
        return False

    def _format_timestamp(self, timestamp: Optional[datetime] = None) -> str:
        """Format timestamp for display."""
        if timestamp is None:
            timestamp = datetime.now(timezone.utc)
        return timestamp.strftime("%Y-%m-%d %H:%M:%S UTC")

    def _format_price(self, price: float) -> str:
        """Format price with appropriate decimal places."""
        return f"${price:,.4f}"

    def _format_pnl(self, pnl: float) -> str:
        """Format PnL with color indicator."""
        if pnl >= 0:
            return f"🟢 ${pnl:,.2f}"
        else:
            return f"🔴 ${pnl:,.2f}"

    async def notify_trade_execution_success(self, data: TradeExecutionData) -> bool:
        """
        Send trade execution success notification.
        Returns True if sent successfully, False otherwise.
        """
        try:
            message = f"""✅ Trade Executed Successfully

📊 Trade Details:
• Symbol: {data.symbol}
• Type: {data.position_type}
• Entry Price: {self._format_price(data.entry_price)}
• Quantity: {data.quantity:,.6f}
• Order ID: {data.order_id}

⏰ Time: {self._format_timestamp(data.timestamp)}"""

            return await self._safe_send_message(message)

        except Exception as e:
            logger.error(f"Error creating trade execution success notification: {e}")
            return False

    async def notify_order_fill(self, data: OrderFillData) -> bool:
        """
        Send order fill notification.
        Returns True if sent successfully, False otherwise.
        """
        try:
            message = f"""🎯 Order Filled

📊 Fill Details:
• Symbol: {data.symbol}
• Type: {data.position_type}
• Fill Price: {self._format_price(data.fill_price)}
• Fill Quantity: {data.fill_quantity:,.6f}
• Order ID: {data.order_id}

⏰ Time: {self._format_timestamp(data.timestamp)}"""

            return await self._safe_send_message(message)

        except Exception as e:
            logger.error(f"Error creating order fill notification: {e}")
            return False

    async def notify_pnl_update(self, data: PnLUpdateData) -> bool:
        """
        Send PnL update notification.
        Returns True if sent successfully, False otherwise.
        """
        try:
            message = f"""📈 PnL Update

📊 Position Details:
• Symbol: {data.symbol}
• Type: {data.position_type}
• Entry Price: {self._format_price(data.entry_price)}
• Current Price: {self._format_price(data.current_price)}
• Quantity: {data.quantity:,.6f}

💰 PnL Status:
• Unrealized PnL: {self._format_pnl(data.unrealized_pnl)}

⏰ Time: {self._format_timestamp(data.timestamp)}"""

            return await self._safe_send_message(message)

        except Exception as e:
            logger.error(f"Error creating PnL update notification: {e}")
            return False

    async def notify_stop_loss_triggered(self, data: StopLossData) -> bool:
        """
        Send stop-loss trigger notification.
        Returns True if sent successfully, False otherwise.
        """
        try:
            message = f"""🛑 Stop-Loss Triggered

📊 Position Details:
• Symbol: {data.symbol}
• Type: {data.position_type}
• Entry Price: {self._format_price(data.entry_price)}
• Stop-Loss Price: {self._format_price(data.stop_loss_price)}
• Quantity: {data.quantity:,.6f}

💰 Final PnL:
• Realized PnL: {self._format_pnl(data.realized_pnl)}

⏰ Time: {self._format_timestamp(data.timestamp)}"""

            return await self._safe_send_message(message)

        except Exception as e:
            logger.error(f"Error creating stop-loss notification: {e}")
            return False

    async def notify_take_profit_triggered(self, data: TakeProfitData) -> bool:
        """
        Send take-profit trigger notification.
        Returns True if sent successfully, False otherwise.
        """
        try:
            message = f"""🎯 Take-Profit Triggered

📊 Position Details:
• Symbol: {data.symbol}
• Type: {data.position_type}
• Entry Price: {self._format_price(data.entry_price)}
• Take-Profit Price: {self._format_price(data.take_profit_price)}
• Quantity: {data.quantity:,.6f}

💰 Final PnL:
• Realized PnL: {self._format_pnl(data.realized_pnl)}

⏰ Time: {self._format_timestamp(data.timestamp)}"""

            return await self._safe_send_message(message)

        except Exception as e:
            logger.error(f"Error creating take-profit notification: {e}")
            return False

# Global instance for easy access
trade_notification_service = TradeNotificationService()
