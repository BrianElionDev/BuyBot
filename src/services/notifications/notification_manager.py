import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from .telegram_service import TelegramService
from .message_formatter import MessageFormatter
from .notification_models import (
    TradeNotification, OrderFillNotification, PnLNotification,
    StopLossNotification, TakeProfitNotification, ErrorNotification,
    SystemStatusNotification, NotificationConfig
)

from .message_formatter import format_entry_signal_payload, format_update_signal_payload
logger = logging.getLogger(__name__)


class NotificationManager:
    """Orchestrates the notification process across different channels"""

    def __init__(self, telegram_config: Optional[NotificationConfig] = None):
        """Initialize the notification manager"""
        self.telegram_service = TelegramService(telegram_config)
        self.message_formatter = MessageFormatter()
        self.enabled = self.telegram_service.is_enabled()

        if not self.enabled:
            logger.warning("Notification service is disabled - no notifications will be sent")

    async def send_trade_execution_notification(
        self,
        coin_symbol: str,
        position_type: str,
        entry_price: float,
        quantity: float,
        order_id: str,
        status: str,
        exchange: str,
        error_message: Optional[str] = None
    ) -> bool:
        """Send trade execution notification"""
        if not self.enabled:
            return False

        try:
            notification = TradeNotification(
                coin_symbol=coin_symbol,
                position_type=position_type,
                entry_price=entry_price,
                quantity=quantity,
                order_id=order_id,
                status=status,
                exchange=exchange,
                error_message=error_message,
                timestamp=datetime.now(timezone.utc)
            )

            message = self.message_formatter.format_trade_execution_notification(notification)
            return await self.telegram_service.send_message(message)
        except Exception as e:
            logger.error(f"Failed to send trade execution notification: {e}")
            return False

    async def send_order_fill_notification(
        self,
        coin_symbol: str,
        position_type: str,
        fill_price: float,
        fill_quantity: float,
        order_id: str,
        exchange: str,
        commission: Optional[float] = None
    ) -> bool:
        """Send order fill notification"""
        if not self.enabled:
            return False

        try:
            notification = OrderFillNotification(
                coin_symbol=coin_symbol,
                position_type=position_type,
                fill_price=fill_price,
                fill_quantity=fill_quantity,
                order_id=order_id,
                exchange=exchange,
                commission=commission,
                timestamp=datetime.now(timezone.utc)
            )

            message = self.message_formatter.format_order_fill_notification(notification)
            return await self.telegram_service.send_message(message)
        except Exception as e:
            logger.error(f"Failed to send order fill notification: {e}")
            return False

    async def send_pnl_update_notification(
        self,
        coin_symbol: str,
        position_type: str,
        entry_price: float,
        current_price: float,
        quantity: float,
        unrealized_pnl: float,
        exchange: str,
        realized_pnl: Optional[float] = None
    ) -> bool:
        """Send PnL update notification"""
        if not self.enabled:
            return False

        try:
            notification = PnLNotification(
                coin_symbol=coin_symbol,
                position_type=position_type,
                entry_price=entry_price,
                current_price=current_price,
                quantity=quantity,
                unrealized_pnl=unrealized_pnl,
                exchange=exchange,
                realized_pnl=realized_pnl,
                timestamp=datetime.now(timezone.utc)
            )

            message = self.message_formatter.format_pnl_update_notification(notification)
            return await self.telegram_service.send_message(message)
        except Exception as e:
            logger.error(f"Failed to send PnL update notification: {e}")
            return False

    async def send_stop_loss_notification(
        self,
        coin_symbol: str,
        position_type: str,
        entry_price: float,
        sl_price: float,
        quantity: float,
        realized_pnl: float,
        exchange: str
    ) -> bool:
        """Send stop-loss notification"""
        if not self.enabled:
            return False

        try:
            notification = StopLossNotification(
                coin_symbol=coin_symbol,
                position_type=position_type,
                entry_price=entry_price,
                sl_price=sl_price,
                quantity=quantity,
                realized_pnl=realized_pnl,
                exchange=exchange,
                timestamp=datetime.now(timezone.utc)
            )

            message = self.message_formatter.format_stop_loss_notification(notification)
            return await self.telegram_service.send_message(message)
        except Exception as e:
            logger.error(f"Failed to send stop-loss notification: {e}")
            return False

    async def send_take_profit_notification(
        self,
        coin_symbol: str,
        position_type: str,
        entry_price: float,
        tp_price: float,
        quantity: float,
        realized_pnl: float,
        exchange: str
    ) -> bool:
        """Send take-profit notification"""
        if not self.enabled:
            return False

        try:
            notification = TakeProfitNotification(
                coin_symbol=coin_symbol,
                position_type=position_type,
                entry_price=entry_price,
                tp_price=tp_price,
                quantity=quantity,
                realized_pnl=realized_pnl,
                exchange=exchange,
                timestamp=datetime.now(timezone.utc)
            )

            message = self.message_formatter.format_take_profit_notification(notification)
            return await self.telegram_service.send_message(message)
        except Exception as e:
            logger.error(f"Failed to send take-profit notification: {e}")
            return False

    async def send_error_notification(
        self,
        error_type: str,
        error_message: str,
        context: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Send error notification"""
        if not self.enabled:
            return False

        try:
            notification = ErrorNotification(
                error_type=error_type,
                error_message=error_message,
                context=context,
                timestamp=datetime.now(timezone.utc)
            )

            message = self.message_formatter.format_error_notification(notification)
            return await self.telegram_service.send_message(message)
        except Exception as e:
            logger.error(f"Failed to send error notification: {e}")
            return False

    async def send_system_status_notification(
        self,
        status: str,
        message: str,
        details: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Send system status notification"""
        if not self.enabled:
            return False

        try:
            notification = SystemStatusNotification(
                status=status,
                message=message,
                details=details,
                timestamp=datetime.now(timezone.utc)
            )

            message = self.message_formatter.format_system_status_notification(notification)
            return await self.telegram_service.send_message(message)
        except Exception as e:
            logger.error(f"Failed to send system status notification: {e}")
            return False

    def is_enabled(self) -> bool:
        """Check if notifications are enabled"""
        return self.enabled

    def get_telegram_config(self) -> NotificationConfig:
        """Get the current Telegram configuration"""
        return self.telegram_service.get_config()

    def update_telegram_config(self, config: NotificationConfig) -> None:
        """Update the Telegram configuration"""
        self.telegram_service.update_config(config)
        self.enabled = self.telegram_service.is_enabled()

    @staticmethod
    async def notify_entry_signal(payload: Dict[str, Any]) -> None:
        """Notify entry signal"""
        try:
            from src.services.telegram.trader_filter import should_notify_trader
            trader = payload.get('trader', '') if payload else ''
            if not should_notify_trader(trader):
                logger.debug(f"Skipping entry signal notification for trader '{trader}' (not in Supabase config)")
                return

            text = format_entry_signal_payload(payload or {})
            svc = TelegramService()
            await svc.send_message(text, parse_mode="HTML")
        except Exception as e:
            logger.error(f"Failed to send the notification: {e}")

    @staticmethod
    async def notify_update_signal(payload: Dict[str, Any]) -> None:
        """Notify update signal"""
        try:
            from src.services.telegram.trader_filter import should_notify_trader
            trader = payload.get('trader', '') if payload else ''
            if not should_notify_trader(trader):
                logger.debug(f"Skipping update signal notification for trader '{trader}' (not in Supabase config)")
                return

            text = format_update_signal_payload(payload or {})
            svc = TelegramService()
            await svc.send_message(text, parse_mode="HTML")
        except Exception as e:
            logger.error(f"Failed to send the notification: {e}")