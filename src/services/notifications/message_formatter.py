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
• Exchange: <b>{notification.exchange}</b>

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
• Exchange: <b>{notification.exchange}</b>

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
• Exchange: <b>{notification.exchange}</b>
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
• Exchange: <b>{notification.exchange}</b>

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
• Exchange: <b>{notification.exchange}</b>

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
• Exchange: <b>{notification.exchange}</b>

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

        # Derive readable cancel/expire reason if provided in context
        reason_text = ""
        ctx = notification.context or {}
        expire_reason = str(ctx.get("expire_reason") or "").upper()
        if expire_reason == "EXPIRE_MAKER":
            reason_text = " (post-only would take liquidity)"

        # Check if this is a TP/SL order cancellation
        is_tp_sl = ctx.get("is_tp_sl_order", False)
        order_type = ctx.get("order_type", "")
        reduce_only = ctx.get("reduce_only", False)

        tp_sl_indicator = ""
        if is_tp_sl or reduce_only or ("TAKE_PROFIT" in str(order_type).upper() or "STOP" in str(order_type).upper()):
            tp_sl_indicator = " 🎯 [TP/SL Order]"

        message = f"""
⚠️ <b>Error Alert</b>{tp_sl_indicator}

🚨 <b>Error Type:</b> {notification.error_type}
❌ <b>Error Message:</b> {notification.error_message}
"""

        # Print exchange prominently if available
        exchange = ctx.get("exchange")
        if exchange:
            message += f"\n🏦 <b>Exchange:</b> {exchange}\n"

        if notification.context:
            message += "\n📋 <b>Context:</b>\n"
            for key, value in notification.context.items():
                # For expire_reason, append a human hint
                if key == "expire_reason" and reason_text:
                    message += f"• {key}: <code>{value}</code>{reason_text}\n"
                else:
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
    trade = payload.get("trade") or payload.get("discord_id") or "-"
    timestamp = payload.get("timestamp") or "-"
    content = payload.get("content") or "-"

    status_raw = (payload.get("status") or "").strip().lower()
    status_emoji = "✅" if status_raw == "success" else ("❌" if status_raw == "failed" else "🔔")
    status_line = f"\n<b>Status:</b> <code>{status_raw.upper()}</code>" if status_raw in ("success", "failed") else ""

    exchange = payload.get("exchange")
    exchange_line = f"\n<b>Exchange:</b> <code>{exchange}</code>" if exchange else ""

    action_type = payload.get("action_type")
    action_line = f"\n<b>Action:</b> <code>{action_type}</code>" if action_type else ""

    message = payload.get("message")
    message_line = f"\n<b>Message:</b> {message}" if message else ""

    error = payload.get("error")
    error_line = f"\n<b>Error:</b> {error}" if error else ""

    exch_resp = payload.get("exchange_response") or payload.get("binance_response") or payload.get("kucoin_response")
    if isinstance(exch_resp, (dict, list)):
        exch_resp_str = str(exch_resp)
    else:
        exch_resp_str = exch_resp or ""
    # keep messages reasonably short for Telegram; HTML parse_mode is used by caller
    if exch_resp_str and len(exch_resp_str) > 2000:
        exch_resp_str = exch_resp_str[:2000] + "...(truncated)"
    exch_resp_line = f"\n<b>Exchange Response:</b>\n<code>{exch_resp_str}</code>" if exch_resp_str else ""

    return (
        f"{status_emoji} <b>Trade Update</b>\n"
        f"Trader: {trader}\n"
        f"Trade: {trade}\n"
        f"Timestamp: {timestamp}\n"
        f"Content:\n{content}"
        f"{status_line}"
        f"{exchange_line}"
        f"{action_line}"
        f"{message_line}"
        f"{error_line}"
        f"{exch_resp_line}"
    ).strip()
