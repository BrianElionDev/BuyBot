import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from discord_bot.discord_bot import DiscordBot

class TestDiscordE2EFlow(unittest.TestCase):

    @patch('discord_bot.discord_bot.DiscordSignalParser')
    @patch('discord_bot.discord_bot.find_trade_by_discord_id')
    @patch('discord_bot.discord_bot.update_existing_trade')
    @patch('discord_bot.discord_bot.TradingEngine')
    @patch('discord_bot.discord_bot.send_telegram_notification')
    def test_full_signal_processing_flow(
        self,
        mock_send_notification: MagicMock,
        mock_trading_engine_class: MagicMock,
        mock_update_existing_trade: MagicMock,
        mock_find_trade_by_discord_id: MagicMock,
        mock_signal_parser_class: MagicMock
    ):
        """
        Tests the complete, end-to-end flow of processing a new trade signal,
        updating the existing database row with execution results.
        """
        # --- 1. Setup Mocks ---

        # Mock instance of the TradingEngine
        mock_trading_engine_instance = mock_trading_engine_class.return_value
        mock_trading_engine_instance.process_signal = AsyncMock(return_value=(True, "Trade executed"))

        # Mock price service for getting current market price
        mock_trading_engine_instance.price_service.get_coin_price = AsyncMock(return_value=42.30)

        # Mock instance of the DiscordSignalParser
        mock_parser_instance = mock_signal_parser_class.return_value

        # Mock the response for the initial symbol check
        mock_parser_instance.get_coin_symbol = AsyncMock(return_value="HYPE")

        # This is the expected output after the main AI parsing call
        parsed_signal_payload = {
            "coin_symbol": "HYPE",
            "position_type": "LONG",
            "entry_prices": [42.23],
            "stop_loss": 41.03,
            "take_profits": None,
            "order_type": "LIMIT",
            "risk_level": "risky"
        }
        mock_parser_instance.parse_new_trade_signal = AsyncMock(return_value=parsed_signal_payload)

        # Mock the response for the validation step
        mock_parser_instance.validate_signal = MagicMock(return_value=(True, None))

        # Mock database calls - no active trade found (this is initial signal)
        mock_find_trade_by_discord_id.return_value = None
        mock_update_existing_trade.return_value = True  # Mock successful update

        # --- 2. Define Inputs ---

        signal_data = {
            'timestamp': '2025-06-12T19:02:33.311Z',
            'content': '@Woods\nHype scalp risky 42.23 stop 41.03 (edited)',
            'structured': 'HYPE|Entry:|42.23|SL:|42.23',
            'signal_id': 'test_signal_123'  # Required for updating existing row
        }

        # --- 3. Execute the Test ---

        # Instantiate the bot. The loop is needed for async operations.
        loop = asyncio.get_event_loop()
        bot = DiscordBot(loop=loop)

        # Run the main processing function
        success, message = loop.run_until_complete(bot.process_signal(signal_data))

        # --- 4. Assert Outcomes ---

        # Assert the overall process was successful
        self.assertTrue(success)
        self.assertEqual(message, "New trade processed")

        # Verify the initial symbol check was called correctly
        mock_parser_instance.get_coin_symbol.assert_called_once_with(signal_data['content'])

        # Verify the main parsing function was called
        mock_parser_instance.parse_new_trade_signal.assert_called_once_with(signal_data['content'])

        # Verify the signal was validated
        mock_parser_instance.validate_signal.assert_called_once_with(parsed_signal_payload)

        # CRITICAL: Verify the Trading Engine was called with the correct parameters including CEX config
        expected_execution_params = {
            **parsed_signal_payload,
            "exchange_type": "cex",
            "sell_coin": "USDT"
        }
        mock_trading_engine_instance.process_signal.assert_called_once_with(**expected_execution_params)

        # Verify the existing trade row was updated with execution results
        self.assertTrue(mock_update_existing_trade.called)
        update_call_args = mock_update_existing_trade.call_args

        # Check that signal_id was used to identify the row
        self.assertEqual(update_call_args[1]['signal_id'], 'test_signal_123')

        # Check that the updates include the correct status and trade data
        updates = update_call_args[1]['updates']
        self.assertEqual(updates['status'], 'ACTIVE')
        self.assertEqual(updates['coin_symbol'], 'HYPE')
        self.assertEqual(updates['entry_price'], 42.30)  # Current market price
        self.assertIn('position_size', updates)
        self.assertIn('exchange_order_id', updates)

        # Verify that a success notification was sent
        mock_send_notification.assert_called_once()
        notification_message = mock_send_notification.call_args[0][0]
        self.assertIn("✅ New CEX Trade Opened", notification_message)
        self.assertIn("HYPE", notification_message)

    @patch('discord_bot.discord_bot.DiscordSignalParser')
    @patch('discord_bot.discord_bot.find_trade_by_discord_id')
    @patch('discord_bot.discord_bot.update_existing_trade')
    @patch('discord_bot.discord_bot.TradingEngine')
    @patch('discord_bot.discord_bot.send_telegram_notification')
    def test_trade_update_signal_flow(
        self,
        mock_send_notification: MagicMock,
        mock_trading_engine_class: MagicMock,
        mock_update_existing_trade: MagicMock,
        mock_find_trade_by_discord_id: MagicMock,
        mock_signal_parser_class: MagicMock
    ):
        """
        Tests the flow of processing a follow-up trade update signal.
        """
        # --- 1. Setup Mocks ---

        # Mock trading engine
        mock_trading_engine_instance = mock_trading_engine_class.return_value
        mock_trading_engine_instance.process_trade_update = AsyncMock(return_value=(
            True,
            {"fill_price": 45.50, "executed_qty": 100, "order_id": "12345", "close_reason": "take_profit"}
        ))

        # Mock parser
        mock_parser_instance = mock_signal_parser_class.return_value
        mock_parser_instance.parse_trade_update_signal = AsyncMock(return_value={
            "action_type": "CLOSE_POSITION"
        })

        # Mock finding the original trade
        original_trade = {
            "id": 42,
            "coin_symbol": "HYPE",
            "entry_price": 42.30,
            "position_size": 100,
            "status": "ACTIVE"
        }
        mock_find_trade_by_discord_id.return_value = original_trade
        mock_update_existing_trade.return_value = True

        # --- 2. Define Follow-up Signal ---

        follow_up_signal = {
            "discord_id": "1386336471073689725",
            "trader": "@Johnny",
            "trade": "original_signal_123",  # References original trade
            "timestamp": "2025-06-22T13:26:11.590Z",
            "content": " HYPE ⁠🚀｜trades⁠: Stopped out @Johnny"
        }

        # --- 3. Execute Test ---

        loop = asyncio.get_event_loop()
        bot = DiscordBot(loop=loop)
        success, message = loop.run_until_complete(bot.process_signal(follow_up_signal))

        # --- 4. Assert Outcomes ---

        self.assertTrue(success)
        self.assertEqual(message, "Trade update processed")

        # Verify it found the original trade
        mock_find_trade_by_discord_id.assert_called_once_with("original_signal_123")

        # Verify the update was parsed
        mock_parser_instance.parse_trade_update_signal.assert_called_once()

        # Verify the trading engine processed the update
        mock_trading_engine_instance.process_trade_update.assert_called_once()

        # Verify the trade row was updated with close information
        self.assertTrue(mock_update_existing_trade.called)
        update_call_args = mock_update_existing_trade.call_args

        # Check that trade_id was used to identify the row
        self.assertEqual(update_call_args[1]['trade_id'], 42)

        # Check the close updates
        updates = update_call_args[1]['updates']
        self.assertEqual(updates['status'], 'CLOSED')
        self.assertEqual(updates['exit_price'], 45.50)

        # P&L calculation: (45.50 - 42.30) * 100 = 320.00
        expected_pnl = (45.50 - 42.30) * 100
        self.assertEqual(updates['pnl_usd'], expected_pnl)

        # Verify notification
        mock_send_notification.assert_called_once()
        notification_message = mock_send_notification.call_args[0][0]
        self.assertIn("🔔 Position Closed", notification_message)
        self.assertIn("HYPE", notification_message)

if __name__ == '__main__':
    unittest.main()