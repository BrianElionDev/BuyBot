import logging
import asyncio
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone
from telegram import Bot
from telegram.error import TelegramError
from config import settings

logger = logging.getLogger(__name__)

class TelegramNotificationService:
    """
    Telegram notification service for sending trade updates and alerts.

    This service handles all Telegram notifications for the trading bot including:
    - Trade execution notifications
    - Order fill updates
    - PnL updates
    - Error notifications
    - Position updates
    """

    def __init__(self, bot_token: Optional[str] = None, chat_id: Optional[str] = None):
        """
        Initialize the Telegram notification service.

        Args:
            bot_token: Telegram bot token (from @BotFather)
            chat_id: Target chat/channel ID for notifications
        """
        self.bot_token = bot_token or settings.TELEGRAM_BOT_TOKEN
        self.chat_id = chat_id or settings.TELEGRAM_NOTIFICATION_CHAT_ID

        if not self.bot_token or self.bot_token == "YOUR_TELEGRAM_BOT_TOKEN":
            logger.warning("Telegram bot token not configured - notifications will be disabled")
            self.bot = None
        else:
            self.bot = Bot(token=self.bot_token)

        if not self.chat_id:
            logger.warning("Telegram chat ID not configured - notifications will be disabled")

    async def send_message(self, message: str, parse_mode: str = "HTML") -> bool:
        """
        Send a message to the configured Telegram chat.

        Args:
            message: The message to send
            parse_mode: Message parse mode (HTML, Markdown, etc.)

        Returns:
            True if message sent successfully, False otherwise
        """
        if not self.bot or not self.chat_id:
            logger.debug(f"Telegram notification (disabled): {message[:100]}...")
            return False

        try:
            await self.bot.send_message(
                chat_id=self.chat_id,
                text=message,
                parse_mode=parse_mode
            )
            logger.info(f"✅ Telegram notification sent successfully")
            return True
        except TelegramError as e:
            logger.error(f"❌ Failed to send Telegram notification: {e}")
            return False
        except Exception as e:
            logger.error(f"❌ Unexpected error sending Telegram notification: {e}")
            return False

    async def send_trade_execution_notification(
        self,
        coin_symbol: str,
        position_type: str,
        entry_price: float,
        quantity: float,
        order_id: str,
        status: str,
        error_message: Optional[str] = None
    ) -> bool:
        """
        Send notification when a trade is executed.

        Args:
            coin_symbol: Trading symbol (e.g., 'BTC')
            position_type: Position type ('LONG' or 'SHORT')
            entry_price: Entry price
            quantity: Position size
            order_id: Binance order ID
            status: Order status ('SUCCESS', 'FAILED', etc.)
            error_message: Error message if trade failed

        Returns:
            True if notification sent successfully
        """
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

        if status.upper() == "SUCCESS":
            emoji = "✅"
            title = "Trade Executed Successfully"
            message = f"""
{emoji} <b>{title}</b>

📊 <b>Trade Details:</b>
• Symbol: <code>{coin_symbol}USDT</code>
• Type: <b>{position_type}</b>
• Entry Price: <code>${entry_price:,.4f}</code>
• Quantity: <code>{quantity:.6f}</code>
• Order ID: <code>{order_id}</code>

⏰ <b>Time:</b> {timestamp}
            """
        else:
            emoji = "❌"
            title = "Trade Execution Failed"
            message = f"""
{emoji} <b>{title}</b>

📊 <b>Trade Details:</b>
• Symbol: <code>{coin_symbol}USDT</code>
• Type: <b>{position_type}</b>
• Entry Price: <code>${entry_price:,.4f}</code>
• Quantity: <code>{quantity:.6f}</code>

❌ <b>Error:</b> {error_message or "Unknown error"}

⏰ <b>Time:</b> {timestamp}
            """

        return await self.send_message(message.strip())

    async def send_order_fill_notification(
        self,
        coin_symbol: str,
        position_type: str,
        fill_price: float,
        fill_quantity: float,
        order_id: str,
        commission: Optional[float] = None
    ) -> bool:
        """
        Send notification when an order gets filled.

        Args:
            coin_symbol: Trading symbol
            position_type: Position type
            fill_price: Actual fill price
            fill_quantity: Actual fill quantity
            order_id: Binance order ID
            commission: Trading commission paid

        Returns:
            True if notification sent successfully
        """
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

        message = f"""
🎯 <b>Order Filled</b>

📊 <b>Fill Details:</b>
• Symbol: <code>{coin_symbol}USDT</code>
• Type: <b>{position_type}</b>
• Fill Price: <code>${fill_price:,.4f}</code>
• Fill Quantity: <code>{fill_quantity:.6f}</code>
• Order ID: <code>{order_id}</code>
"""

        if commission:
            message += f"• Commission: <code>${commission:.4f}</code>\n"

        message += f"""
⏰ <b>Time:</b> {timestamp}
        """

        return await self.send_message(message.strip())

    async def send_pnl_update_notification(
        self,
        coin_symbol: str,
        position_type: str,
        entry_price: float,
        current_price: float,
        quantity: float,
        unrealized_pnl: float,
        realized_pnl: Optional[float] = None
    ) -> bool:
        """
        Send PnL update notification.

        Args:
            coin_symbol: Trading symbol
            position_type: Position type
            entry_price: Entry price
            current_price: Current market price
            quantity: Position size
            unrealized_pnl: Unrealized profit/loss
            realized_pnl: Realized profit/loss (if position closed)

        Returns:
            True if notification sent successfully
        """
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

        # Calculate percentage change
        if position_type.upper() == "LONG":
            pct_change = ((current_price - entry_price) / entry_price) * 100
        else:  # SHORT
            pct_change = ((entry_price - current_price) / entry_price) * 100

        # Determine emoji based on PnL
        if unrealized_pnl > 0:
            emoji = "📈"
        elif unrealized_pnl < 0:
            emoji = "📉"
        else:
            emoji = "➡️"

        message = f"""
{emoji} <b>PnL Update</b>

📊 <b>Position Details:</b>
• Symbol: <code>{coin_symbol}USDT</code>
• Type: <b>{position_type}</b>
• Entry Price: <code>${entry_price:,.4f}</code>
• Current Price: <code>${current_price:,.4f}</code>
• Quantity: <code>{quantity:.6f}</code>
• Change: <code>{pct_change:+.2f}%</code>

💰 <b>Profit/Loss:</b>
• Unrealized PnL: <code>${unrealized_pnl:,.2f}</code>
"""

        if realized_pnl is not None:
            message += f"• Realized PnL: <code>${realized_pnl:,.2f}</code>\n"

        message += f"""
⏰ <b>Time:</b> {timestamp}
        """

        return await self.send_message(message.strip())

    async def send_position_closed_notification(
        self,
        coin_symbol: str,
        position_type: str,
        entry_price: float,
        exit_price: float,
        quantity: float,
        realized_pnl: float,
        total_fees: Optional[float] = None
    ) -> bool:
        """
        Send notification when a position is closed.

        Args:
            coin_symbol: Trading symbol
            position_type: Position type
            entry_price: Entry price
            exit_price: Exit price
            quantity: Position size
            realized_pnl: Realized profit/loss
            total_fees: Total fees paid

        Returns:
            True if notification sent successfully
        """
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

        # Calculate percentage return
        if position_type.upper() == "LONG":
            pct_return = ((exit_price - entry_price) / entry_price) * 100
        else:  # SHORT
            pct_return = ((entry_price - exit_price) / entry_price) * 100

        # Determine emoji based on PnL
        if realized_pnl > 0:
            emoji = "🎉"
            result = "PROFIT"
        elif realized_pnl < 0:
            emoji = "💸"
            result = "LOSS"
        else:
            emoji = "➡️"
            result = "BREAKEVEN"

        message = f"""
{emoji} <b>Position Closed - {result}</b>

📊 <b>Trade Summary:</b>
• Symbol: <code>{coin_symbol}USDT</code>
• Type: <b>{position_type}</b>
• Entry Price: <code>${entry_price:,.4f}</code>
• Exit Price: <code>${exit_price:,.4f}</code>
• Quantity: <code>{quantity:.6f}</code>
• Return: <code>{pct_return:+.2f}%</code>

💰 <b>Final PnL:</b>
• Realized PnL: <code>${realized_pnl:,.2f}</code>
"""

        if total_fees:
            message += f"• Total Fees: <code>${total_fees:.4f}</code>\n"

        message += f"""
⏰ <b>Time:</b> {timestamp}
        """

        return await self.send_message(message.strip())

    async def send_stop_loss_triggered_notification(
        self,
        coin_symbol: str,
        position_type: str,
        entry_price: float,
        sl_price: float,
        quantity: float,
        realized_pnl: float
    ) -> bool:
        """
        Send notification when stop-loss is triggered.

        Args:
            coin_symbol: Trading symbol
            position_type: Position type
            entry_price: Entry price
            sl_price: Stop-loss price
            quantity: Position size
            realized_pnl: Realized profit/loss

        Returns:
            True if notification sent successfully
        """
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

        message = f"""
🛑 <b>Stop-Loss Triggered</b>

📊 <b>Position Details:</b>
• Symbol: <code>{coin_symbol}USDT</code>
• Type: <b>{position_type}</b>
• Entry Price: <code>${entry_price:,.4f}</code>
• Stop-Loss Price: <code>${sl_price:,.4f}</code>
• Quantity: <code>{quantity:.6f}</code>

💰 <b>Final PnL:</b>
• Realized PnL: <code>${realized_pnl:,.2f}</code>

⏰ <b>Time:</b> {timestamp}
        """

        return await self.send_message(message.strip())

    async def send_error_notification(
        self,
        error_type: str,
        error_message: str,
        context: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Send error notification.

        Args:
            error_type: Type of error (e.g., 'Trade Execution', 'API Error')
            error_message: Error message
            context: Additional context information

        Returns:
            True if notification sent successfully
        """
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

        message = f"""
⚠️ <b>Error Alert</b>

🚨 <b>Error Type:</b> {error_type}
❌ <b>Error Message:</b> {error_message}
"""

        if context:
            message += "\n📋 <b>Context:</b>\n"
            for key, value in context.items():
                message += f"• {key}: <code>{value}</code>\n"

        message += f"""
⏰ <b>Time:</b> {timestamp}
        """

        return await self.send_message(message.strip())

    async def send_system_status_notification(
        self,
        status: str,
        message: str,
        details: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Send system status notification.

        Args:
            status: System status ('ONLINE', 'OFFLINE', 'MAINTENANCE')
            message: Status message
            details: Additional details

        Returns:
            True if notification sent successfully
        """
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

        if status.upper() == "ONLINE":
            emoji = "🟢"
        elif status.upper() == "OFFLINE":
            emoji = "🔴"
        elif status.upper() == "MAINTENANCE":
            emoji = "🟡"
        else:
            emoji = "⚪"

        message_text = f"""
{emoji} <b>System Status: {status.upper()}</b>

📝 <b>Message:</b> {message}
"""

        if details:
            message_text += "\n📋 <b>Details:</b>\n"
            for key, value in details.items():
                message_text += f"• {key}: <code>{value}</code>\n"

        message_text += f"""
⏰ <b>Time:</b> {timestamp}
        """

        return await self.send_message(message_text.strip())

