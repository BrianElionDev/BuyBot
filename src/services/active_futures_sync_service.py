"""
Active Futures Synchronization Service

This service monitors the active_futures table and synchronizes with local trades.
"""

import logging
import re
import asyncio
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass

from src.database import (
    DatabaseManager, ActiveFuturesRepository, TradeRepository,
    AlertRepository, ActiveFutures, Trade, Alert
)
from src.database.core.connection_manager import connection_manager
from src.core.response_models import ServiceResponse, ErrorCode

logger = logging.getLogger(__name__)

@dataclass
class TradeMatch:
    """Represents a match between active futures and local trade."""
    active_futures: ActiveFutures
    trade: Trade
    confidence: float
    match_reason: str

class ActiveFuturesSyncService:
    """Service for synchronizing active futures with local trades."""

    def __init__(self, db_manager: DatabaseManager):
        """Initialize the sync service."""
        self.db_manager = db_manager
        self.active_futures_repo = ActiveFuturesRepository(db_manager)
        self.trade_repo = TradeRepository(db_manager)
        self.alert_repo = AlertRepository(db_manager)
        # Load target traders from configuration
        from config import settings
        self.target_traders = getattr(settings, 'TARGET_TRADERS', ["@Johnny", "@Tareeq"])
        self.last_sync_time = None
        # Add thread safety for concurrent access
        self._sync_lock = asyncio.Lock()

    async def initialize(self) -> bool:
        """Initialize the service."""
        try:
            await self.db_manager.initialize()
            logger.info("ActiveFuturesSyncService initialized successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize ActiveFuturesSyncService: {e}")
            return False

    def extract_coin_symbol_from_content(self, content: str) -> Optional[str]:
        """Extract coin symbol from active futures content."""
        if not content:
            return None

        patterns = [
            r'\b(BTC|ETH|SOL|ADA|DOT|LINK|UNI|AAVE|MATIC|AVAX|NEAR|FTM|ALGO|ATOM|XRP|DOGE|SHIB|PEPE|BONK|WIF|FLOKI|TOSHI|TURBO|HYPE|FARTCOIN|VELVET|NAORIS|PUMP|SUI|1000SATS|DAM|SOMI|PENGU|ENA|ZEC|TAO|USELESS)\b',
            r'\b([A-Z]{2,10})\s+Entry:',
            r'\b([A-Z]{2,10})\s+Entry\s*:',
            r'Entry:\s*([A-Z]{2,10})',
            r'([A-Z]{2,10})\s+Entry\s*:\s*\d',
        ]

        for pattern in patterns:
            match = re.search(pattern, content.upper())
            if match:
                symbol = match.group(1)
                if len(symbol) >= 2 and symbol.isalnum():
                    return symbol

        return None

    def calculate_content_similarity(self, content1: str, content2: str) -> float:
        """Calculate similarity between two content strings."""
        if not content1 and not content2:
            return 1.0
        if not content1 or not content2:
            return 0.0

        content1_upper = content1.upper()
        content2_upper = content2.upper()

        if content1_upper == content2_upper:
            return 1.0

        words1 = set(content1_upper.split())
        words2 = set(content2_upper.split())

        if not words1 or not words2:
            return 0.0

        intersection = words1.intersection(words2)
        union = words1.union(words2)

        return len(intersection) / len(union) if union else 0.0

    def is_timestamp_proximate(self, timestamp1: str, timestamp2: str, max_hours: int = 24) -> bool:
        """Check if two timestamps are within acceptable proximity."""
        try:
            dt1 = datetime.fromisoformat(timestamp1.replace('Z', '+00:00'))
            dt2 = datetime.fromisoformat(timestamp2.replace('Z', '+00:00'))

            time_diff = abs((dt1 - dt2).total_seconds())
            max_diff_seconds = max_hours * 3600

            return time_diff <= max_diff_seconds
        except Exception:
            return False

    async def find_trade_matches(self, active_futures: ActiveFutures) -> List[TradeMatch]:
        """Find matching trades for an active futures entry."""
        matches = []

        try:
            coin_symbol = self.extract_coin_symbol_from_content(active_futures.content)

            if not coin_symbol:
                logger.warning(f"No coin symbol extracted from content: {active_futures.content}")
                return matches

            # First try to find trades with exact coin symbol match
            trades = await self.trade_repo.get_trades_by_filter({
                "trader": active_futures.trader,
                "coin_symbol": coin_symbol,
                "status": "OPEN"
            })

            # If no exact matches, try broader search
            if not trades:
                trades = await self.trade_repo.get_trades_by_filter({
                    "trader": active_futures.trader,
                    "status": "OPEN"
                })

            for trade in trades:
                confidence = 0.0
                match_reasons = []

                # Trader match (required)
                if trade.trader == active_futures.trader:
                    confidence += 0.4
                    match_reasons.append("trader_match")
                else:
                    continue  # Skip if trader doesn't match

                # Coin symbol match (high weight)
                if trade.coin_symbol == coin_symbol:
                    confidence += 0.4
                    match_reasons.append("coin_symbol_match")
                elif trade.coin_symbol:
                    # Check if coin symbol is similar (case insensitive)
                    if trade.coin_symbol.upper() == coin_symbol.upper():
                        confidence += 0.4
                        match_reasons.append("coin_symbol_match")
                    else:
                        confidence -= 0.2  # Penalty for different coin

                # Content similarity
                content_similarity = self.calculate_content_similarity(
                    active_futures.content, trade.content
                )
                if content_similarity > 0.2:
                    confidence += content_similarity * 0.2
                    match_reasons.append(f"content_similarity_{content_similarity:.2f}")

                # Timestamp proximity
                if self.is_timestamp_proximate(active_futures.created_at, trade.timestamp):
                    confidence += 0.1
                    match_reasons.append("timestamp_proximate")

                # Only include matches with reasonable confidence
                if confidence >= 0.6:
                    matches.append(TradeMatch(
                        active_futures=active_futures,
                        trade=trade,
                        confidence=confidence,
                        match_reason=", ".join(match_reasons)
                    ))

            matches.sort(key=lambda x: x.confidence, reverse=True)

        except Exception as e:
            logger.error(f"Error finding trade matches for active futures {active_futures.id}: {e}")

        return matches

    async def get_closed_futures_to_process(self) -> List[ActiveFutures]:
        """Get recently closed futures that need processing."""
        # Use lock to prevent race conditions with concurrent access
        async with self._sync_lock:
            try:
                if self.last_sync_time:
                    cutoff_time = self.last_sync_time
                else:
                    cutoff_time = datetime.now(timezone.utc) - timedelta(hours=24)

                closed_futures = await self.active_futures_repo.get_futures_by_traders_and_status(
                    self.target_traders, "CLOSED"
                )

                recent_closed = []
                for af in closed_futures:
                    if af.stopped_at:
                        try:
                            stopped_time = datetime.fromisoformat(af.stopped_at.replace('Z', '+00:00'))
                            if stopped_time >= cutoff_time:
                                recent_closed.append(af)
                        except Exception as e:
                            logger.warning(f"Error parsing stopped_at time for futures {af.id}: {e}")
                            continue

                logger.info(f"Found {len(recent_closed)} recently closed futures to process")
                return recent_closed

            except Exception as e:
                logger.error(f"Error getting closed futures to process: {e}")
                return []

    async def process_closed_futures(self, closed_futures: List[ActiveFutures]) -> Dict[str, Any]:
        """Process closed futures and close corresponding positions."""
        results = {
            "processed": 0,
            "successful_closes": 0,
            "failed_closes": 0,
            "no_matches": 0,
            "errors": []
        }

        # Process each futures entry with proper error isolation
        for active_futures in closed_futures:
            # Use lock to ensure atomic processing of each futures entry
            async with self._sync_lock:
                try:
                    results["processed"] += 1

                    matches = await self.find_trade_matches(active_futures)

                    if not matches:
                        results["no_matches"] += 1
                        logger.warning(f"No matching trades found for closed futures {active_futures.id}")
                        continue

                    best_match = matches[0]
                    logger.info(f"Found best match for futures {active_futures.id}: trade {best_match.trade.discord_id} (confidence: {best_match.confidence:.2f})")

                    # Process position closure with error handling
                    success = await self.close_trade_position(best_match.trade, active_futures)

                    if success:
                        results["successful_closes"] += 1
                        logger.info(f"Successfully closed position for trade {best_match.trade.discord_id}")
                    else:
                        results["failed_closes"] += 1
                        logger.error(f"Failed to close position for trade {best_match.trade.discord_id}")

                except Exception as e:
                    results["failed_closes"] += 1
                    results["errors"].append(f"Error processing futures {active_futures.id}: {str(e)}")
                    logger.error(f"Error processing closed futures {active_futures.id}: {e}")

        return results

    async def close_trade_position(self, trade: Trade, active_futures: ActiveFutures) -> bool:
        """Close a trade position based on active futures closure."""
        try:
            from src.core.position_manager import PositionManager
            from src.exchange.binance.binance_exchange import BinanceExchange
            from src.exchange.kucoin.kucoin_exchange import KucoinExchange
            from src.config.trader_config import get_exchange_for_trader

            exchange_type = get_exchange_for_trader(trade.trader)

            if exchange_type.value == "binance":
                exchange = BinanceExchange()
            elif exchange_type.value == "kucoin":
                exchange = KucoinExchange()
            else:
                logger.error(f"Unsupported exchange type: {exchange_type}")
                return False

            position_manager = PositionManager(exchange)

            trade_dict = {
                "discord_id": trade.discord_id,
                "coin_symbol": trade.coin_symbol,
                "trader": trade.trader,
                "status": trade.status,
                "position_size": trade.position_size,
                "entry_price": trade.entry_price,
                "exchange_order_id": trade.exchange_order_id
            }

            success, response = await position_manager.close_position_at_market(
                trade_dict,
                reason="active_futures_closed",
                close_percentage=100.0
            )

            if success:
                await self.trade_repo.update_trade(trade.id, {
                    "status": "CLOSED",
                    "closed_at": datetime.now(timezone.utc).isoformat(),
                    "exit_price": response.get("price") if isinstance(response, dict) else None
                })

                logger.info(f"Successfully closed trade {trade.discord_id} due to active futures closure")
                return True
            else:
                logger.error(f"Failed to close trade {trade.discord_id}: {response}")
                return False

        except Exception as e:
            logger.error(f"Error closing trade position {trade.discord_id}: {e}")
            return False

    async def sync_active_futures(self) -> ServiceResponse:
        """Main synchronization method."""
        try:
            logger.info("Starting active futures synchronization")

            closed_futures = await self.get_closed_futures_to_process()

            if not closed_futures:
                logger.info("No closed futures to process")
                return ServiceResponse.success_response(
                    data={"processed": 0, "message": "No closed futures to process"}
                )

            results = await self.process_closed_futures(closed_futures)

            self.last_sync_time = datetime.now(timezone.utc)

            logger.info(f"Active futures sync completed: {results}")
            return ServiceResponse.success_response(
                data=results,
                metadata={"processed_count": results['processed']}
            )

        except Exception as e:
            logger.error(f"Error in active futures synchronization: {e}")
            return ServiceResponse.error_response(
                error=f"Sync failed: {str(e)}",
                error_code=ErrorCode.DATABASE_ERROR,
                metadata={"operation": "sync_active_futures"}
            )

    async def get_sync_status(self) -> Dict[str, Any]:
        """Get current synchronization status."""
        try:
            active_futures_count = len(await self.active_futures_repo.get_futures_by_traders_and_status(
                self.target_traders, "ACTIVE"
            ))

            closed_futures_count = len(await self.active_futures_repo.get_futures_by_traders_and_status(
                self.target_traders, "CLOSED"
            ))

            return {
                "last_sync_time": self.last_sync_time.isoformat() if self.last_sync_time else None,
                "active_futures_count": active_futures_count,
                "closed_futures_count": closed_futures_count,
                "target_traders": self.target_traders
            }

        except Exception as e:
            logger.error(f"Error getting sync status: {e}")
            return {"error": str(e)}
