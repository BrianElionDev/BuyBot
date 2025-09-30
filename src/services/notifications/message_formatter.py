from datetime import datetime, timezone
from typing import Optional, Dict, Any
from .notification_models import (
    TradeNotification, OrderFillNotification, PnLNotification,
    StopLossNotification, TakeProfitNotification, ErrorNotification,
    SystemStatusNotification
)


class MessageFormatter:
    """Handles formatting of notification messages"""

    @staticmethod
    def format_trade_execution_notification(notification: TradeNotification) -> str:
        """Format trade execution notification message"""
        timestamp = notification.timestamp or datetime.now(timezone.utc)
        formatted_time = timestamp.strftime("%Y-%m-%d %H:%M:%S UTC")

        if notification.status.upper() == "SUCCESS":
            emoji = "✅"
            title = "Trade Executed Successfully"
            message = f"""
{emoji} <b>{title}</b>

📊 <b>Trade Details:</b>
• Symbol: <code>{notification.coin_symbol}USDT</code>
• Type: <b>{notification.position_type}</b>
• Entry Price: <code>${notification.entry_price:,.4f}</code>
• Quantity: <code>{notification.quantity:.6f}</code>
• Order ID: <code>{notification.order_id}</code>

⏰ <b>Time:</b> {formatted_time}
            """
        else:
            emoji = "❌"
            title = "Trade Execution Failed"
            message = f"""
{emoji} <b>{title}</b>

📊 <b>Trade Details:</b>
• Symbol: <code>{notification.coin_symbol}USDT</code>
• Type: <b>{notification.position_type}</b>
• Entry Price: <code>${notification.entry_price:,.4f}</code>
• Quantity: <code>{notification.quantity:.6f}</code>

❌ <b>Error:</b> {notification.error_message or "Unknown error"}

⏰ <b>Time:</b> {formatted_time}
            """

        return message.strip()

    @staticmethod
    def format_order_fill_notification(notification: OrderFillNotification) -> str:
        """Format order fill notification message"""
        timestamp = notification.timestamp or datetime.now(timezone.utc)
        formatted_time = timestamp.strftime("%Y-%m-%d %H:%M:%S UTC")

        message = f"""
🎯 <b>Order Filled</b>

📊 <b>Fill Details:</b>
• Symbol: <code>{notification.coin_symbol}USDT</code>
• Type: <b>{notification.position_type}</b>
• Fill Price: <code>${notification.fill_price:,.4f}</code>
• Fill Quantity: <code>{notification.fill_quantity:.6f}</code>
• Order ID: <code>{notification.order_id}</code>
"""

        if notification.commission:
            message += f"• Commission: <code>${notification.commission:.4f}</code>\n"

        message += f"""
⏰ <b>Time:</b> {formatted_time}
        """

        return message.strip()

    @staticmethod
    def format_pnl_update_notification(notification: PnLNotification) -> str:
        """Format PnL update notification message"""
        timestamp = notification.timestamp or datetime.now(timezone.utc)
        formatted_time = timestamp.strftime("%Y-%m-%d %H:%M:%S UTC")

        pnl_emoji = "📈" if notification.unrealized_pnl >= 0 else "📉"
        pnl_color = "🟢" if notification.unrealized_pnl >= 0 else "🔴"

        message = f"""
{pnl_emoji} <b>PnL Update</b>

📊 <b>Position Details:</b>
• Symbol: <code>{notification.coin_symbol}USDT</code>
• Type: <b>{notification.position_type}</b>
• Entry Price: <code>${notification.entry_price:,.4f}</code>
• Current Price: <code>${notification.current_price:,.4f}</code>
• Quantity: <code>{notification.quantity:.6f}</code>

💰 <b>PnL Status:</b>
• Unrealized PnL: {pnl_color} <code>${notification.unrealized_pnl:,.2f}</code>
"""

        if notification.realized_pnl is not None:
            realized_emoji = "🟢" if notification.realized_pnl >= 0 else "🔴"
            message += f"• Realized PnL: {realized_emoji} <code>${notification.realized_pnl:,.2f}</code>\n"

        message += f"""
⏰ <b>Time:</b> {formatted_time}
        """

        return message.strip()

    @staticmethod
    def format_stop_loss_notification(notification: StopLossNotification) -> str:
        """Format stop-loss notification message"""
        timestamp = notification.timestamp or datetime.now(timezone.utc)
        formatted_time = timestamp.strftime("%Y-%m-%d %H:%M:%S UTC")

        pnl_emoji = "🟢" if notification.realized_pnl >= 0 else "🔴"

        message = f"""
🛑 <b>Stop-Loss Triggered</b>

📊 <b>Position Details:</b>
• Symbol: <code>{notification.coin_symbol}USDT</code>
• Type: <b>{notification.position_type}</b>
• Entry Price: <code>${notification.entry_price:,.4f}</code>
• Stop-Loss Price: <code>${notification.sl_price:,.4f}</code>
• Quantity: <code>{notification.quantity:.6f}</code>

💰 <b>Final PnL:</b>
• Realized PnL: {pnl_emoji} <code>${notification.realized_pnl:,.2f}</code>

⏰ <b>Time:</b> {formatted_time}
        """

        return message.strip()

    @staticmethod
    def format_take_profit_notification(notification: TakeProfitNotification) -> str:
        """Format take-profit notification message"""
        timestamp = notification.timestamp or datetime.now(timezone.utc)
        formatted_time = timestamp.strftime("%Y-%m-%d %H:%M:%S UTC")

        pnl_emoji = "🟢" if notification.realized_pnl >= 0 else "🔴"

        message = f"""
🎯 <b>Take-Profit Triggered</b>

📊 <b>Position Details:</b>
• Symbol: <code>{notification.coin_symbol}USDT</code>
• Type: <b>{notification.position_type}</b>
• Entry Price: <code>${notification.entry_price:,.4f}</code>
• Take-Profit Price: <code>${notification.tp_price:,.4f}</code>
• Quantity: <code>{notification.quantity:.6f}</code>

💰 <b>Final PnL:</b>
• Realized PnL: {pnl_emoji} <code>${notification.realized_pnl:,.2f}</code>

⏰ <b>Time:</b> {formatted_time}
        """

        return message.strip()

    @staticmethod
    def format_error_notification(notification: ErrorNotification) -> str:
        """Format error notification message"""
        timestamp = notification.timestamp or datetime.now(timezone.utc)
        formatted_time = timestamp.strftime("%Y-%m-%d %H:%M:%S UTC")

        message = f"""
⚠️ <b>Error Alert</b>

🚨 <b>Error Type:</b> {notification.error_type}
❌ <b>Error Message:</b> {notification.error_message}
"""

        if notification.context:
            message += "\n📋 <b>Context:</b>\n"
            for key, value in notification.context.items():
                message += f"• {key}: <code>{value}</code>\n"

        message += f"""
⏰ <b>Time:</b> {formatted_time}
        """

        return message.strip()

    @staticmethod
    def format_system_status_notification(notification: SystemStatusNotification) -> str:
        """Format system status notification message"""
        timestamp = notification.timestamp or datetime.now(timezone.utc)
        formatted_time = timestamp.strftime("%Y-%m-%d %H:%M:%S UTC")

        if notification.status.upper() == "ONLINE":
            emoji = "🟢"
        elif notification.status.upper() == "OFFLINE":
            emoji = "🔴"
        elif notification.status.upper() == "MAINTENANCE":
            emoji = "🟡"
        else:
            emoji = "⚪"

        message = f"""
{emoji} <b>System Status: {notification.status.upper()}</b>
    discord_id = payload.get("discord_id") or "-"

📝 <b>Message:</b> {notification.message}
"""

        if notification.details:
            message += "\n📋 <b>Details:</b>\n"
            for key, value in notification.details.items():
                message += f"• {key}: <code>{value}</code>\n"

        message += f"""
⏰ <b>Time:</b> {formatted_time}
        """

        return message.strip()

def format_entry_signal_payload(payload: dict) -> str:
    """Format entry signal payload"""
    trader = payload.get("trader") or "-"
    discord_id = payload.get("discord_id") or "-"
    timestamp = payload.get("timestamp") or "-"
    content = payload.get("content") or "-"
    structured = payload.get("structured") or "-"
    return (
        f"📥 <b>New Entry Signal</b>\n"
        f"Trader: {trader}\n"
        f"Discord ID: {discord_id}\n"
        f"Timestamp: {timestamp}\n"
        f"Content:\n{content}\n"
    )

def format_update_signal_payload(payload: dict) -> str:
    """Format update signal payload"""
    trader = payload.get("trader") or "-"
    trade = payload.get("trade") or "-"
    timestamp = payload.get("timestamp") or "-"
    content = payload.get("content") or "-"
    return (
    "🔔 <b>Trade Update</b>\n"
        f"Trader: {trader}\n"
        f"Trade: {trade}\n"
        f"Timestamp: {timestamp}\n"
        f"Content:\n{content}"
        )
