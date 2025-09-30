"""
Position Close Service

This service handles closing positions based on active futures changes.
"""

import logging
import asyncio
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime, timezone

from src.database import TradeRepository, AlertRepository, Trade, Alert
from src.database.core.connection_manager import connection_manager
from src.config.trader_config import get_exchange_for_trader, ExchangeType

logger = logging.getLogger(__name__)

class PositionCloseService:
    """Service for closing positions based on active futures changes."""

    def __init__(self, db_manager):
        """Initialize the position close service."""
        self.db_manager = db_manager
        self.trade_repo = TradeRepository(db_manager)
        self.alert_repo = AlertRepository(db_manager)

    async def initialize(self) -> bool:
        """Initialize the service."""
        try:
            await self.db_manager.initialize()
            logger.info("PositionCloseService initialized successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize PositionCloseService: {e}")
            return False

    async def close_position_by_trade(self, trade: Trade, reason: str = "active_futures_closed") -> Tuple[bool, Dict[str, Any]]:
        """Close a position for a specific trade."""
        try:
            exchange_type = get_exchange_for_trader(trade.trader)

            if exchange_type == ExchangeType.BINANCE:
                return await self._close_binance_position(trade, reason)
            elif exchange_type == ExchangeType.KUCOIN:
                return await self._close_kucoin_position(trade, reason)
            else:
                logger.error(f"Unsupported exchange type: {exchange_type}")
                return False, {"error": f"Unsupported exchange type: {exchange_type}"}

        except Exception as e:
            logger.error(f"Error closing position for trade {trade.discord_id}: {e}")
            return False, {"error": str(e)}

    async def _close_binance_position(self, trade: Trade, reason: str) -> Tuple[bool, Dict[str, Any]]:
        """Close a Binance position."""
        try:
            from src.bot.trading_engine import TradingEngine
            from src.exchange.binance.binance_exchange import BinanceExchange

            exchange = BinanceExchange()
            trading_engine = TradingEngine(exchange)

            trade_dict = {
                "discord_id": trade.discord_id,
                "coin_symbol": trade.coin_symbol,
                "trader": trade.trader,
                "status": trade.status,
                "position_size": trade.position_size,
                "entry_price": trade.entry_price,
                "exchange_order_id": trade.exchange_order_id,
                "binance_response": trade.binance_response
            }

            success, response = await trading_engine.close_position_at_market(
                trade_dict,
                reason=reason,
                close_percentage=100.0
            )

            if success:
                await self._update_trade_after_close(trade, response, reason)
                logger.info(f"Successfully closed Binance position for trade {trade.discord_id}")
                return True, response
            else:
                logger.error(f"Failed to close Binance position for trade {trade.discord_id}: {response}")
                return False, response

        except Exception as e:
            logger.error(f"Error closing Binance position for trade {trade.discord_id}: {e}")
            return False, {"error": str(e)}

    async def _close_kucoin_position(self, trade: Trade, reason: str) -> Tuple[bool, Dict[str, Any]]:
        """Close a KuCoin position."""
        try:
            from src.bot.kucoin_trading_engine import KucoinTradingEngine
            from src.exchange.kucoin.kucoin_exchange import KucoinExchange

            exchange = KucoinExchange()
            trading_engine = KucoinTradingEngine(exchange)

            trade_dict = {
                "discord_id": trade.discord_id,
                "coin_symbol": trade.coin_symbol,
                "trader": trade.trader,
                "status": trade.status,
                "position_size": trade.position_size,
                "entry_price": trade.entry_price,
                "exchange_order_id": trade.exchange_order_id,
                "kucoin_response": trade.kucoin_response
            }

            success, response = await trading_engine.close_position_at_market(
                trade_dict,
                reason=reason,
                close_percentage=100.0
            )

            if success:
                await self._update_trade_after_close(trade, response, reason)
                logger.info(f"Successfully closed KuCoin position for trade {trade.discord_id}")
                return True, response
            else:
                logger.error(f"Failed to close KuCoin position for trade {trade.discord_id}: {response}")
                return False, response

        except Exception as e:
            logger.error(f"Error closing KuCoin position for trade {trade.discord_id}: {e}")
            return False, {"error": str(e)}

    async def _update_trade_after_close(self, trade: Trade, response: Dict[str, Any], reason: str) -> None:
        """Update trade record after successful position closure."""
        try:
            update_data = {
                "status": "CLOSED",
                "closed_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat()
            }

            if isinstance(response, dict):
                if "price" in response:
                    update_data["exit_price"] = float(response["price"])
                if "orderId" in response:
                    update_data["exchange_order_id"] = str(response["orderId"])
                if "origQty" in response:
                    update_data["position_size"] = float(response["origQty"])

            await self.trade_repo.update_trade(trade.id, update_data)
            logger.info(f"Updated trade {trade.discord_id} after position closure")

        except Exception as e:
            logger.error(f"Error updating trade {trade.discord_id} after closure: {e}")

    async def process_related_alerts(self, trade: Trade) -> List[Dict[str, Any]]:
        """Process related alerts for a trade to trigger closure."""
        try:
            alerts = await self.alert_repo.get_alerts_by_trade_id(trade.discord_id)

            if not alerts:
                logger.info(f"No related alerts found for trade {trade.discord_id}")
                return []

            processed_alerts = []

            for alert in alerts:
                if alert.status == "PENDING":
                    try:
                        alert_data = {
                            "timestamp": alert.timestamp,
                            "content": alert.content,
                            "discord_id": alert.discord_id,
                            "trader": alert.trader,
                            "trade": alert.trade
                        }

                        from discord_bot.discord_bot import DiscordBot
                        bot = DiscordBot()

                        result = await bot.process_update_signal(alert_data)

                        processed_alerts.append({
                            "alert_id": alert.id,
                            "result": result,
                            "status": "processed"
                        })

                        if result.get("status") == "success":
                            await self.alert_repo.update_alert(alert.id, {
                                "status": "PROCESSED",
                                "updated_at": datetime.now(timezone.utc).isoformat()
                            })

                    except Exception as e:
                        logger.error(f"Error processing alert {alert.id}: {e}")
                        processed_alerts.append({
                            "alert_id": alert.id,
                            "result": {"status": "error", "message": str(e)},
                            "status": "failed"
                        })

            return processed_alerts

        except Exception as e:
            logger.error(f"Error processing related alerts for trade {trade.discord_id}: {e}")
            return []

    async def emergency_close_all_positions(self, trader: str) -> Dict[str, Any]:
        """Emergency close all positions for a specific trader."""
        try:
            open_trades = await self.trade_repo.get_trades_by_filter({
                "trader": trader,
                "status": "OPEN"
            })

            if not open_trades:
                return {
                    "status": "success",
                    "message": f"No open positions found for trader {trader}",
                    "closed_count": 0
                }

            results = {
                "total_trades": len(open_trades),
                "successful_closes": 0,
                "failed_closes": 0,
                "errors": []
            }

            for trade in open_trades:
                try:
                    success, response = await self.close_position_by_trade(
                        trade,
                        reason="emergency_close"
                    )

                    if success:
                        results["successful_closes"] += 1
                        logger.info(f"Emergency closed position for trade {trade.discord_id}")
                    else:
                        results["failed_closes"] += 1
                        results["errors"].append(f"Failed to close trade {trade.discord_id}: {response}")
                        logger.error(f"Failed to emergency close trade {trade.discord_id}: {response}")

                except Exception as e:
                    results["failed_closes"] += 1
                    results["errors"].append(f"Error closing trade {trade.discord_id}: {str(e)}")
                    logger.error(f"Error in emergency close for trade {trade.discord_id}: {e}")

            return {
                "status": "completed",
                "results": results,
                "message": f"Emergency close completed for trader {trader}"
            }

        except Exception as e:
            logger.error(f"Error in emergency close for trader {trader}: {e}")
            return {
                "status": "error",
                "message": f"Emergency close failed: {str(e)}"
            }

    async def get_position_status(self, trade: Trade) -> Dict[str, Any]:
        """Get current position status for a trade."""
        try:
            exchange_type = get_exchange_for_trader(trade.trader)

            if exchange_type == ExchangeType.BINANCE:
                return await self._get_binance_position_status(trade)
            elif exchange_type == ExchangeType.KUCOIN:
                return await self._get_kucoin_position_status(trade)
            else:
                return {"error": f"Unsupported exchange type: {exchange_type}"}

        except Exception as e:
            logger.error(f"Error getting position status for trade {trade.discord_id}: {e}")
            return {"error": str(e)}

    async def _get_binance_position_status(self, trade: Trade) -> Dict[str, Any]:
        """Get Binance position status."""
        try:
            from src.exchange.binance.binance_exchange import BinanceExchange

            exchange = BinanceExchange()
            positions = await exchange.get_futures_position_information()

            target_symbol = f"{trade.coin_symbol}USDT"

            for position in positions:
                if position.get("symbol") == target_symbol:
                    return {
                        "symbol": position.get("symbol"),
                        "position_amt": position.get("positionAmt"),
                        "entry_price": position.get("entryPrice"),
                        "mark_price": position.get("markPrice"),
                        "unrealized_pnl": position.get("unRealizedProfit"),
                        "position_side": position.get("positionSide"),
                        "is_open": float(position.get("positionAmt", 0)) != 0
                    }

            return {"is_open": False, "message": "Position not found"}

        except Exception as e:
            logger.error(f"Error getting Binance position status: {e}")
            return {"error": str(e)}

    async def _get_kucoin_position_status(self, trade: Trade) -> Dict[str, Any]:
        """Get KuCoin position status."""
        try:
            from src.exchange.kucoin.kucoin_exchange import KucoinExchange

            exchange = KucoinExchange()
            positions = await exchange.get_futures_position_information()

            target_symbol = f"{trade.coin_symbol}USDTM"

            for position in positions:
                if position.get("symbol") == target_symbol:
                    return {
                        "symbol": position.get("symbol"),
                        "size": position.get("size"),
                        "side": position.get("side"),
                        "entry_price": position.get("avgEntryPrice"),
                        "mark_price": position.get("markPrice"),
                        "unrealized_pnl": position.get("unrealisedPnl"),
                        "is_open": float(position.get("size", 0)) != 0
                    }

            return {"is_open": False, "message": "Position not found"}

        except Exception as e:
            logger.error(f"Error getting KuCoin position status: {e}")
            return {"error": str(e)}
