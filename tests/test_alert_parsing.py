import pytest
from unittest.mock import Mock
from discord_bot.discord_bot import DiscordBot


class TestAlertParsing:
    """Test cases for alert content parsing"""

    def setup_method(self):
        """Set up test fixtures"""
        self.bot = DiscordBot()

    def test_stops_moved_to_be_parsing(self):
        """Test parsing of 'Stops moved to BE' alerts"""
        content = "ETH 🚀|  Stops moved to BE  | @Johnny"
        signal_data = {"coin_symbol": "ETH"}

        result = self.bot.parse_alert_content(content, signal_data)

        assert result["action_type"] == "stop_loss_update"
        assert result["stop_loss"] == "BE"
        assert result["binance_action"] == "UPDATE_STOP_ORDER"
        assert result["position_status"] == "OPEN"

    def test_limit_order_filled_parsing(self):
        """Test parsing of 'Limit order filled' alerts"""
        content = "ETH 🚀|  Limit order filled  | @Johnny"
        signal_data = {"coin_symbol": "ETH"}

        result = self.bot.parse_alert_content(content, signal_data)

        assert result["action_type"] == "limit_order_filled"
        assert result["binance_action"] == "NO_ACTION"
        assert result["position_status"] == "OPEN"
        assert "Limit order filled" in result["reason"]

    def test_closed_in_profits_parsing(self):
        """Test parsing of 'Closed in profits' alerts"""
        content = "ETH 🚀|  Closed in profits  | @Johnny"
        signal_data = {"coin_symbol": "ETH"}

        result = self.bot.parse_alert_content(content, signal_data)

        assert result["action_type"] == "stop_loss_hit"
        assert result["binance_action"] == "MARKET_SELL"
        assert result["position_status"] == "CLOSED"
        assert "Position closed" in result["reason"]

    def test_stopped_out_parsing(self):
        """Test parsing of 'Stopped out' alerts"""
        content = "SOL 🚀|  Stopped out  | @Johnny"
        signal_data = {"coin_symbol": "SOL"}

        result = self.bot.parse_alert_content(content, signal_data)

        assert result["action_type"] == "stop_loss_hit"
        assert result["binance_action"] == "MARKET_SELL"
        assert result["position_status"] == "CLOSED"
        assert "Position closed" in result["reason"]

    def test_move_stops_to_specific_price(self):
        """Test parsing of 'Move stops to X' alerts"""
        content = "LINK 🚀|  Move stops to 21.4  | @Johnny"
        signal_data = {"coin_symbol": "LINK"}

        result = self.bot.parse_alert_content(content, signal_data)

        assert result["action_type"] == "stop_loss_update"
        assert result["stop_loss"] == "21.4"
        assert result["binance_action"] == "UPDATE_STOP_ORDER"
        assert result["position_status"] == "OPEN"

    def test_coin_symbol_extraction(self):
        """Test coin symbol extraction from various formats"""
        test_cases = [
            ("ETH 🚀|  Stops moved to BE  | @Johnny", "ETH"),
            ("LINK 🚀|  Move stops to 21.4  | @Johnny", "LINK"),
            ("SOL 🚀|  Stopped out  | @Johnny", "SOL"),
            ("BTC 🚀|  Limit order filled  | @Johnny", "BTC"),
        ]

        for content, expected_symbol in test_cases:
            signal_data = {"coin_symbol": expected_symbol}
            result = self.bot.parse_alert_content(content, signal_data)
            assert result["coin_symbol"] == expected_symbol

    def test_unknown_update_handling(self):
        """Test handling of unknown update types"""
        content = "ETH 🚀|  Some unknown update  | @Johnny"
        signal_data = {"coin_symbol": "ETH"}

        result = self.bot.parse_alert_content(content, signal_data)

        assert result["action_type"] == "unknown_update"
        assert result["binance_action"] == "NO_ACTION"
        assert result["position_status"] == "UNKNOWN"
        assert "Unrecognized alert type" in result["reason"]

    def test_multiple_alert_patterns(self):
        """Test various alert patterns from your data"""
        test_cases = [
            # (content, expected_action_type, expected_binance_action)
            ("ETH 🚀|  Stops moved to BE  | @Johnny", "stop_loss_update", "UPDATE_STOP_ORDER"),
            ("LINK 🚀|  Move stops to 21.4  | @Johnny", "stop_loss_update", "UPDATE_STOP_ORDER"),
            ("SOL 🚀|  Stopped out  | @Johnny", "stop_loss_hit", "MARKET_SELL"),
            ("ETH 🚀|  Limit order filled  | @Johnny", "limit_order_filled", "NO_ACTION"),
            ("ETH 🚀|  Closed in profits  | @Johnny", "stop_loss_hit", "MARKET_SELL"),
            ("LINK 🚀|  Closed in profits  | @Johnny", "stop_loss_hit", "MARKET_SELL"),
        ]

        for content, expected_action, expected_binance_action in test_cases:
            signal_data = {"coin_symbol": "TEST"}
            result = self.bot.parse_alert_content(content, signal_data)

            assert result["action_type"] == expected_action, f"Failed for content: {content}"
            assert result["binance_action"] == expected_binance_action, f"Failed for content: {content}"
            assert result["coin_symbol"] in ["ETH", "LINK", "SOL"], f"Failed for content: {content}"

    def test_debug_regex_matching(self):
        """Debug test to see why regex isn't matching"""
        import re

        content = "ETH 🚀|  Stops moved to BE  | @Johnny"
        content_lower = content.lower()

        # Test the regex pattern
        stops_to_be_regex = r"\b(stop|sl)\b.*\bbe\b"
        match = re.search(stops_to_be_regex, content_lower)

        print(f"Content: '{content_lower}'")
        print(f"Regex pattern: '{stops_to_be_regex}'")
        print(f"Match result: {match}")

        if match:
            print(f"Matched groups: {match.groups()}")

        # Test with a simpler pattern
        simple_pattern = r"stops.*be"
        simple_match = re.search(simple_pattern, content_lower)
        print(f"Simple pattern '{simple_pattern}' match: {simple_match}")

        # Test with the exact pattern from your alerts
        exact_pattern = r"stops moved to be"
        exact_match = re.search(exact_pattern, content_lower)
        print(f"Exact pattern '{exact_pattern}' match: {exact_match}")

        # This should help us understand why the regex isn't working
        assert True  # Just for debugging


class TestActionExecution:
    """Test cases for action execution"""

    def setup_method(self):
        """Set up test fixtures"""
        self.bot = DiscordBot()
        self.mock_trade_row = {
            "id": 123,
            "coin_symbol": "ETH",
            "status": "OPEN",
            "position_size": "0.1"
        }
        self.mock_signal = Mock()

    @pytest.mark.asyncio
    async def test_limit_order_filled_execution(self):
        """Test execution of limit_order_filled action"""
        action = {
            "action_type": "limit_order_filled",
            "action_description": "Limit order filled for ETH",
            "binance_action": "NO_ACTION",
            "position_status": "OPEN",
            "reason": "Limit order filled - position now open",
            "coin_symbol": "ETH"
        }

        success, result = await self.bot._execute_single_action(action, self.mock_trade_row, self.mock_signal)

        assert success is True
        assert "Limit order already filled" in result["message"]

    @pytest.mark.asyncio
    async def test_unknown_update_execution(self):
        """Test execution of unknown_update action"""
        action = {
            "action_type": "unknown_update",
            "action_description": "Update for ETH: Some unknown update",
            "binance_action": "NO_ACTION",
            "position_status": "UNKNOWN",
            "reason": "Unrecognized alert type",
            "coin_symbol": "ETH"
        }

        success, result = await self.bot._execute_single_action(action, self.mock_trade_row, self.mock_signal)

        assert success is True
        assert "Unknown update type - informational only" in result["message"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
