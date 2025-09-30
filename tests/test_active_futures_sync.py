"""
Test Active Futures Synchronization

This module tests the active futures synchronization functionality.
"""

import logging
import pytest
from unittest.mock import Mock, AsyncMock, patch
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.database import (
    DatabaseManager,
    ActiveFutures, Trade
)
from src.services.active_futures_sync_service import ActiveFuturesSyncService, TradeMatch
from src.services.position_close_service import PositionCloseService

logger = logging.getLogger(__name__)

class TestActiveFuturesSyncService:
    """Test cases for ActiveFuturesSyncService."""

    @pytest.fixture
    def mock_db_manager(self):
        """Create a mock database manager."""
        db_manager = Mock(spec=DatabaseManager)
        db_manager.initialize = AsyncMock(return_value=True)
        db_manager.client = Mock()
        return db_manager

    @pytest.fixture
    def sync_service(self, mock_db_manager):
        """Create a sync service instance."""
        return ActiveFuturesSyncService(mock_db_manager)

    def test_extract_coin_symbol_from_content(self, sync_service):
        """Test coin symbol extraction from content."""
        test_cases = [
            ("BTC Entry: 110547-110328 SL: 108310", "BTC"),
            ("ETH Entry: 4437-4421 SL: 4348", "ETH"),
            ("SOL Entry: 177-172.9 SL: 169", "SOL"),
            ("PUMP Entry: 0.0041-0.0039 SL: 0.00384", "PUMP"),
            ("1000SATS Entry: 0.0000356-0.0000372 SL: 30m", "1000SATS"),
            ("NAORIS Entry: 0.10773 SL: 0.101 PnL: +1.44%", "NAORIS"),
            ("VELVET Entry: 0.12121 SL: 0.1126 PnL: +4.10%", "VELVET"),
            ("Invalid content without coin", None),
            ("", None),
        ]

        for content, expected in test_cases:
            result = sync_service.extract_coin_symbol_from_content(content)
            assert result == expected, f"Failed for content: {content}"

    def test_calculate_content_similarity(self, sync_service):
        """Test content similarity calculation."""
        test_cases = [
            ("BTC Entry: 110547-110328 SL: 108310", "BTC Entry: 110547-110328 SL: 108310", 1.0),
            ("BTC Entry: 110547-110328 SL: 108310", "BTC Entry: 110500-110300 SL: 108000", 0.3),
            ("ETH Entry: 4437-4421 SL: 4348", "BTC Entry: 110547-110328 SL: 108310", 0.2),
            ("", "BTC Entry: 110547-110328 SL: 108310", 0.0),
            ("BTC Entry: 110547-110328 SL: 108310", "", 0.0),
        ]

        for content1, content2, expected_min in test_cases:
            result = sync_service.calculate_content_similarity(content1, content2)
            if expected_min == 1.0:
                assert result == expected_min
            elif expected_min == 0.0:
                assert result == expected_min
            else:
                assert result >= expected_min - 0.1

    def test_is_timestamp_proximate(self, sync_service):
        """Test timestamp proximity check."""
        base_time = "2025-01-15T10:00:00Z"

        test_cases = [
            ("2025-01-15T10:00:00Z", "2025-01-15T10:00:00Z", True),
            ("2025-01-15T10:00:00Z", "2025-01-15T11:00:00Z", True),
            ("2025-01-15T10:00:00Z", "2025-01-15T12:00:00Z", True),
            ("2025-01-15T10:00:00Z", "2025-01-15T15:00:00Z", True),
            ("2025-01-15T10:00:00Z", "2025-01-15T20:00:00Z", True),
            ("2025-01-15T10:00:00Z", "2025-01-16T10:00:00Z", True),
            ("2025-01-15T10:00:00Z", "invalid_timestamp", False),
        ]

        for timestamp1, timestamp2, expected in test_cases:
            result = sync_service.is_timestamp_proximate(timestamp1, timestamp2, max_hours=24)
            assert result == expected, f"Failed for timestamps: {timestamp1}, {timestamp2}"

    @pytest.mark.asyncio
    async def test_find_trade_matches(self, sync_service):
        """Test finding trade matches for active futures."""
        active_futures = ActiveFutures(
            id=1,
            trader="@Johnny",
            content="BTC Entry: 110547-110328 SL: 108310",
            status="CLOSED",
            created_at="2025-01-15T10:00:00Z"
        )

        mock_trades = [
            Trade(
                id=1,
                discord_id="trade1",
                trader="@Johnny",
                coin_symbol="BTC",
                content="BTC Entry: 110547-110328 SL: 108310",
                status="OPEN",
                timestamp="2025-01-15T10:05:00Z"
            ),
            Trade(
                id=2,
                discord_id="trade2",
                trader="@Johnny",
                coin_symbol="ETH",
                content="ETH Entry: 4437-4421 SL: 4348",
                status="OPEN",
                timestamp="2025-01-15T10:00:00Z"
            )
        ]

        with patch.object(sync_service.trade_repo, 'get_trades_by_filter', return_value=mock_trades):
            matches = await sync_service.find_trade_matches(active_futures)

            assert len(matches) == 1
            assert matches[0].trade.discord_id == "trade1"
            assert matches[0].confidence >= 0.5

    @pytest.mark.asyncio
    async def test_get_closed_futures_to_process(self, sync_service):
        """Test getting closed futures to process."""
        from datetime import datetime, timezone, timedelta

        # Set last_sync_time to ensure we get recent closed futures
        sync_service.last_sync_time = datetime.now(timezone.utc) - timedelta(hours=2)

        mock_closed_futures = [
            ActiveFutures(
                id=1,
                trader="@Johnny",
                content="BTC Entry: 110547-110328 SL: 108310",
                status="CLOSED",
                stopped_at=datetime.now(timezone.utc).isoformat()
            ),
            ActiveFutures(
                id=2,
                trader="@Tareeq",
                content="ETH Entry: 4437-4421 SL: 4348",
                status="CLOSED",
                stopped_at=datetime.now(timezone.utc).isoformat()
            )
        ]

        with patch.object(sync_service.active_futures_repo, 'get_futures_by_traders_and_status', return_value=mock_closed_futures):
            closed_futures = await sync_service.get_closed_futures_to_process()

            assert len(closed_futures) == 2
            assert all(af.status == "CLOSED" for af in closed_futures)
            assert all(af.trader in ["@Johnny", "@Tareeq"] for af in closed_futures)

class TestPositionCloseService:
    """Test cases for PositionCloseService."""

    @pytest.fixture
    def mock_db_manager(self):
        """Create a mock database manager."""
        db_manager = Mock(spec=DatabaseManager)
        db_manager.initialize = AsyncMock(return_value=True)
        db_manager.client = Mock()
        return db_manager

    @pytest.fixture
    def position_close_service(self, mock_db_manager):
        """Create a position close service instance."""
        return PositionCloseService(mock_db_manager)

    @pytest.mark.asyncio
    async def test_close_position_by_trade_binance(self, position_close_service):
        """Test closing a Binance position."""
        trade = Trade(
            id=1,
            discord_id="trade1",
            trader="@Johnny",
            coin_symbol="BTC",
            status="OPEN",
            position_size=0.1,
            entry_price=50000.0
        )

        with patch('src.services.position_close_service.get_exchange_for_trader') as mock_get_exchange:
            from src.config.trader_config import ExchangeType
            mock_get_exchange.return_value = ExchangeType.BINANCE

            with patch.object(position_close_service, '_close_binance_position', return_value=(True, {"orderId": "12345", "price": "51000"})):
                success, response = await position_close_service.close_position_by_trade(trade)

                assert success is True
                assert "orderId" in response

    @pytest.mark.asyncio
    async def test_close_position_by_trade_kucoin(self, position_close_service):
        """Test closing a KuCoin position."""
        trade = Trade(
            id=1,
            discord_id="trade1",
            trader="@Tareeq",
            coin_symbol="ETH",
            status="OPEN",
            position_size=1.0,
            entry_price=3000.0
        )

        with patch('src.services.position_close_service.get_exchange_for_trader') as mock_get_exchange:
            from src.config.trader_config import ExchangeType
            mock_get_exchange.return_value = ExchangeType.KUCOIN

            with patch.object(position_close_service, '_close_kucoin_position', return_value=(True, {"orderId": "67890", "price": "3100"})):
                success, response = await position_close_service.close_position_by_trade(trade)

                assert success is True
                assert "orderId" in response

    @pytest.mark.asyncio
    async def test_emergency_close_all_positions(self, position_close_service):
        """Test emergency close all positions for a trader."""
        mock_trades = [
            Trade(
                id=1,
                discord_id="trade1",
                trader="@Johnny",
                coin_symbol="BTC",
                status="OPEN"
            ),
            Trade(
                id=2,
                discord_id="trade2",
                trader="@Johnny",
                coin_symbol="ETH",
                status="OPEN"
            )
        ]

        with patch.object(position_close_service.trade_repo, 'get_trades_by_filter', return_value=mock_trades):
            with patch.object(position_close_service, 'close_position_by_trade', return_value=(True, {})):
                result = await position_close_service.emergency_close_all_positions("@Johnny")

                assert result["status"] == "completed"
                assert result["results"]["total_trades"] == 2
                assert result["results"]["successful_closes"] == 2

class TestIntegration:
    """Integration tests for the complete active futures sync flow."""

    @pytest.mark.asyncio
    async def test_complete_sync_flow(self):
        """Test the complete synchronization flow."""
        mock_db_manager = Mock(spec=DatabaseManager)
        mock_db_manager.initialize = AsyncMock(return_value=True)
        mock_db_manager.client = Mock()

        sync_service = ActiveFuturesSyncService(mock_db_manager)

        mock_closed_futures = [
            ActiveFutures(
                id=1,
                trader="@Johnny",
                content="BTC Entry: 110547-110328 SL: 108310",
                status="CLOSED",
                stopped_at="2025-01-15T10:00:00Z"
            )
        ]

        mock_trades = [
            Trade(
                id=1,
                discord_id="trade1",
                trader="@Johnny",
                coin_symbol="BTC",
                content="BTC Entry: 110547-110328 SL: 108310",
                status="OPEN",
                timestamp="2025-01-15T10:05:00Z"
            )
        ]

        # Set last_sync_time to ensure we get recent closed futures
        from datetime import datetime, timezone, timedelta
        sync_service.last_sync_time = datetime.now(timezone.utc) - timedelta(hours=2)

        with patch.object(sync_service, 'get_closed_futures_to_process', return_value=mock_closed_futures):
            with patch.object(sync_service, 'find_trade_matches', return_value=[
                TradeMatch(
                    active_futures=mock_closed_futures[0],
                    trade=mock_trades[0],
                    confidence=0.9,
                    match_reason="trader_match, coin_symbol_match, content_similarity_0.95"
                )
            ]):
                with patch.object(sync_service, 'close_trade_position', return_value=True):
                    result = await sync_service.sync_active_futures()

                    assert result["status"] == "success"
                    assert "results" in result
                    assert result["results"]["processed"] == 1
                    assert result["results"]["successful_closes"] == 1

if __name__ == "__main__":
    # Run the tests
    pytest.main([__file__, "-v"])
