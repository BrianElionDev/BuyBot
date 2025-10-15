"""
Signal Router Module

This module handles routing of trading signals to the appropriate exchange
based on the trader configuration from the database.
"""

import logging
import json
from datetime import datetime, timezone
from typing import Dict, Any, Optional, Tuple, List
from src.services.trader_config_service import (
    ExchangeType, trader_config_service,
    get_exchange_for_trader, is_trader_supported
)

logger = logging.getLogger(__name__)


class SignalRouter:
    """
    Routes trading signals to the appropriate exchange based on trader configuration.
    """

    def __init__(self, binance_trading_engine, kucoin_trading_engine=None):
        """
        Initialize the signal router.

        Args:
            binance_trading_engine: The Binance trading engine instance
            kucoin_trading_engine: The KuCoin trading engine instance (optional)
        """
        self.binance_trading_engine = binance_trading_engine
        self.kucoin_trading_engine = kucoin_trading_engine

        #Initialize runtime config
        from src.config.runtime_config import init_runtime_config, runtime_config
        from config.settings import SUPABASE_URL, SUPABASE_KEY
        if SUPABASE_URL and SUPABASE_KEY:
            init_runtime_config(SUPABASE_URL, SUPABASE_KEY)
            self.runtime_config = runtime_config
        else:
            logger.warning("Supabase URL or Key not set. Cannot connect to the database.")
            self.runtime_config = None

        self.runtime_config = runtime_config

    async def is_trader_supported(self, trader: str) -> bool:
        """
        Check if a trader is supported.

        Args:
            trader: The trader identifier

        Returns:
            bool: True if trader is supported, False otherwise
        """
        return await is_trader_supported(trader)

    async def get_exchange_for_trader(self, trader: str) -> ExchangeType:
        """
        Get the exchange type for a given trader.

        Args:
            trader: The trader identifier

        Returns:
            ExchangeType: The exchange that should handle this trader's signals
        """
        return await get_exchange_for_trader(trader)

        logger.info("SignalRouter initialized")

    async def route_initial_signal(
        self,
        coin_symbol: str,
        signal_price: float,
        position_type: str,
        trader: str,
        order_type: str = "MARKET",
        stop_loss: Optional[float] = None,
        take_profits: Optional[list] = None,
        dca_range: Optional[list] = None,
        client_order_id: Optional[str] = None,
        price_threshold_override: Optional[float] = None,
        quantity_multiplier: Optional[int] = None,
        entry_prices: Optional[list] = None,
        discord_id: Optional[str] = None
    ) -> Tuple[bool, Any]:
        """
        Route an initial trading signal to the appropriate exchange.

        Args:
            coin_symbol: The cryptocurrency symbol
            signal_price: The signal price
            position_type: LONG or SHORT
            trader: The trader identifier
            order_type: The order type (MARKET, LIMIT, etc.)
            stop_loss: Stop loss price
            take_profits: List of take profit prices
            dca_range: DCA range prices
            client_order_id: Client order ID
            price_threshold_override: Price threshold override
            quantity_multiplier: Quantity multiplier
            entry_prices: List of entry prices

        Returns:
            Tuple[bool, Any]: Success status and response data
        """
        try:
            # Determine which exchange to use
            exchange_type = await get_exchange_for_trader(trader)

            logger.info(f"Routing signal from trader {trader} to {exchange_type.value} exchange")

            # Inject runtime config and trader context into engines
            if exchange_type == ExchangeType.BINANCE and self.binance_trading_engine:
                setattr(self.binance_trading_engine, 'runtime_config', self.runtime_config)
                setattr(self.binance_trading_engine, 'trader_id', trader)
            elif exchange_type == ExchangeType.KUCOIN and self.kucoin_trading_engine:
                setattr(self.kucoin_trading_engine, 'runtime_config', self.runtime_config)
                setattr(self.kucoin_trading_engine, 'trader_id', trader)

            # Route to appropriate exchange
            if exchange_type == ExchangeType.BINANCE:
                return await self._route_to_binance(
                    coin_symbol, signal_price, position_type, order_type,
                    stop_loss, take_profits, dca_range, client_order_id,
                    price_threshold_override, quantity_multiplier, entry_prices, discord_id
                )
            elif exchange_type == ExchangeType.KUCOIN:
                return await self._route_to_kucoin(
                    coin_symbol, signal_price, position_type, order_type,
                    stop_loss, take_profits, dca_range, client_order_id,
                    price_threshold_override, quantity_multiplier, entry_prices, discord_id
                )
            else:
                logger.error(f"Unsupported exchange type: {exchange_type}")
                return False, f"Unsupported exchange type: {exchange_type}"

        except Exception as e:
            logger.error(f"Error routing initial signal: {e}")
            return False, f"Error routing signal: {str(e)}"

    async def route_followup_signal(
        self,
        signal_data: Dict[str, Any],
        trader: str
    ) -> Dict[str, Any]:
        """
        Route a follow-up signal to the appropriate exchange.

        Args:
            signal_data: The follow-up signal data
            trader: The trader identifier

        Returns:
            Dict[str, Any]: Response data
        """
        try:
            # Determine which exchange to use
            exchange_type = await get_exchange_for_trader(trader)

            logger.info(f"Routing follow-up signal from trader {trader} to {exchange_type.value} exchange")

            # Route to appropriate exchange
            if exchange_type == ExchangeType.BINANCE:
                return await self._route_followup_to_binance(signal_data)
            elif exchange_type == ExchangeType.KUCOIN:
                return await self._route_followup_to_kucoin(signal_data)
            else:
                logger.error(f"Unsupported exchange type: {exchange_type}")
                return {"status": "error", "message": f"Unsupported exchange type: {exchange_type}"}

        except Exception as e:
            logger.error(f"Error routing follow-up signal: {e}")
            return {"status": "error", "message": f"Error routing follow-up signal: {str(e)}"}

    async def route_alert_signal(
        self,
        alert_data: Dict[str, Any],
        trader: str
    ) -> Dict[str, Any]:
        """
        Route an alert signal with enhanced timestamp-based order matching.

        Args:
            alert_data: The alert data containing parsed alert information
            trader: The trader identifier

        Returns:
            Dict[str, Any]: Response data with detailed order processing results
        """
        try:
            # Determine which exchange to use
            exchange_type = await get_exchange_for_trader(trader)

            logger.info(f"Routing alert signal from trader {trader} to {exchange_type.value} exchange")

            # Extract coin symbol and timestamp from alert data
            coin_symbol = alert_data.get('coin_symbol')
            alert_timestamp = alert_data.get('timestamp')

            if not coin_symbol or not alert_timestamp:
                return {"status": "error", "message": "Missing coin_symbol or timestamp in alert data"}

            # Find related orders using timestamp matching
            related_orders = await self._find_related_orders(
                coin_symbol=coin_symbol,
                alert_timestamp=alert_timestamp,
                trade_group_id=alert_data.get('trade_group_id')
            )

            if not related_orders:
                logger.warning(f"No related orders found for {coin_symbol} at {alert_timestamp}")
                return {"status": "error", "message": f"No related orders found for {coin_symbol}"}

            # Route to appropriate exchange for processing
            if exchange_type == ExchangeType.BINANCE:
                return await self._process_alert_for_multiple_orders(alert_data, related_orders)
            elif exchange_type == ExchangeType.KUCOIN:
                if not self.kucoin_trading_engine:
                    return {"status": "error", "message": "KuCoin trading engine not available"}

                # For KuCoin, process each order individually for now
                results = []
                for trade in related_orders:
                    result = await self.kucoin_trading_engine.process_followup_signal(alert_data, trade)
                    results.append({
                        'trade_id': trade.get('discord_id'),
                        'result': result
                    })
                return {
                    'status': 'success',
                    'message': f"Processed {len(results)} KuCoin orders",
                    'results': results
                }
            else:
                logger.error(f"Unsupported exchange type: {exchange_type}")
                return {"status": "error", "message": f"Unsupported exchange type: {exchange_type}"}

        except Exception as e:
            logger.error(f"Error routing alert signal: {e}")
            return {"status": "error", "message": f"Error routing alert signal: {str(e)}"}

    async def _route_to_binance(
        self,
        coin_symbol: str,
        signal_price: float,
        position_type: str,
        order_type: str,
        stop_loss: Optional[float],
        take_profits: Optional[list],
        dca_range: Optional[list],
        client_order_id: Optional[str],
        price_threshold_override: Optional[float],
        quantity_multiplier: Optional[int],
        entry_prices: Optional[list],
        discord_id: Optional[str] = None
    ) -> Tuple[bool, Any]:
        """Route signal to Binance trading engine."""
        try:
            logger.info(f"Executing signal on Binance: {coin_symbol} {position_type}")

            success, response = await self.binance_trading_engine.process_signal(
                coin_symbol=coin_symbol,
                signal_price=signal_price,
                position_type=position_type,
                order_type=order_type,
                stop_loss=stop_loss,
                take_profits=take_profits,
                dca_range=dca_range,
                client_order_id=client_order_id,
                price_threshold_override=price_threshold_override,
                quantity_multiplier=quantity_multiplier,
                entry_prices=entry_prices,
                discord_id=discord_id
            )

            if success:
                logger.info(f"✅ Signal executed successfully on Binance: {coin_symbol}")
            else:
                logger.error(f"❌ Signal execution failed on Binance: {response}")

            return success, response

        except Exception as e:
            logger.error(f"Error executing signal on Binance: {e}")
            return False, f"Binance execution error: {str(e)}"

    async def _route_to_kucoin(
        self,
        coin_symbol: str,
        signal_price: float,
        position_type: str,
        order_type: str,
        stop_loss: Optional[float],
        take_profits: Optional[list],
        dca_range: Optional[list],
        client_order_id: Optional[str],
        price_threshold_override: Optional[float],
        quantity_multiplier: Optional[int],
        entry_prices: Optional[list],
        discord_id: Optional[str] = None
    ) -> Tuple[bool, Any]:
        """Route signal to KuCoin trading engine."""
        if not self.kucoin_trading_engine:
            logger.error("KuCoin trading engine not available")
            return False, "KuCoin trading engine not available"

        try:
            logger.info(f"Executing signal on KuCoin: {coin_symbol} {position_type}")

            success, response = await self.kucoin_trading_engine.process_signal(
                coin_symbol=coin_symbol,
                signal_price=signal_price,
                position_type=position_type,
                order_type=order_type,
                stop_loss=stop_loss,
                take_profits=take_profits,
                dca_range=dca_range,
                client_order_id=client_order_id,
                price_threshold_override=price_threshold_override,
                quantity_multiplier=quantity_multiplier,
                entry_prices=entry_prices,
                discord_id=discord_id
            )

            if success:
                logger.info(f"✅ Signal executed successfully on KuCoin: {coin_symbol}")
            else:
                logger.error(f"❌ Signal execution failed on KuCoin: {response}")

            return success, response

        except Exception as e:
            logger.error(f"Error executing signal on KuCoin: {e}")
            return False, f"KuCoin execution error: {str(e)}"

    async def _route_followup_to_binance(self, signal_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Route follow-up signal to Binance trading engine.

        Args:
            signal_data: The follow-up signal data

        Returns:
            Dict[str, Any]: Response data
        """
        try:
            if not self.binance_trading_engine:
                return {"status": "error", "message": "Binance trading engine not available"}

            # Extract signal information
            content = signal_data.get('content', '')
            discord_id = signal_data.get('discord_id', '')
            trader = signal_data.get('trader', '')
            trade_reference = (signal_data.get('trade', '') or '').strip()

            logger.info(f"Routing follow-up signal to Binance: {content}")

            trade_row = await self._find_trade_by_discord_id(trade_reference)
            if not trade_row:
                return {"status": "error", "message": f"No trade found for trade reference: {trade_reference}"}

            # Process the follow-up signal
            result = await self.binance_trading_engine.process_followup_signal(signal_data, trade_row)

            return {
                "status": "success" if result.get("success", False) else "error",
                "message": result.get("message", "Follow-up signal processed"),
                "exchange_response": result,
                "exchange": "binance"
            }

        except Exception as e:
            logger.error(f"Error routing follow-up signal to Binance: {e}")
            return {
                "status": "error",
                "message": f"Error processing Binance follow-up signal: {str(e)}",
                "exchange": "binance"
            }

    async def _route_followup_to_kucoin(self, signal_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Route follow-up signal to KuCoin trading engine.

        Args:
            signal_data: The follow-up signal data

        Returns:
            Dict[str, Any]: Response data
        """
        try:
            if not self.kucoin_trading_engine:
                return {"status": "error", "message": "KuCoin trading engine not available"}

            # Extract signal information
            content = signal_data.get('content', '')
            discord_id = signal_data.get('discord_id', '')
            trader = signal_data.get('trader', '')
            trade_reference = (signal_data.get('trade', '') or '').strip()

            logger.info(f"Routing follow-up signal to KuCoin: {content}")

            trade_row = await self._find_trade_by_discord_id(trade_reference)
            if not trade_row:
                return {"status": "error", "message": f"No trade found for trade reference: {trade_reference}"}

            # Process the follow-up signal
            result = await self.kucoin_trading_engine.process_followup_signal(signal_data, trade_row)

            return {
                "status": "success" if result.get("success", False) else "error",
                "message": result.get("message", "Follow-up signal processed"),
                "exchange_response": result,
                "exchange": "kucoin"
            }

        except Exception as e:
            logger.error(f"Error routing follow-up signal to KuCoin: {e}")
            return {
                "status": "error",
                "message": f"Error processing KuCoin follow-up signal: {str(e)}",
                "exchange": "kucoin"
            }

    # Removed duplicate method definitions of get_exchange_for_trader and is_trader_supported

    def _convert_binance_timestamp(self, update_time_ms: int) -> datetime:
        """
        Convert Binance updateTime (milliseconds) to datetime.

        Args:
            update_time_ms: Binance updateTime in milliseconds

        Returns:
            datetime: Converted datetime object
        """
        return datetime.fromtimestamp(update_time_ms / 1000, tz=timezone.utc)

    def _parse_discord_timestamp(self, timestamp_input) -> datetime:
        """
        Parse Discord timestamp string or datetime to datetime.

        Args:
            timestamp_input: Discord timestamp string (ISO format) or datetime object

        Returns:
            datetime: Parsed datetime object
        """
        try:
            # If already a datetime object, return it
            if isinstance(timestamp_input, datetime):
                return timestamp_input

            # If it's a string, parse it
            if isinstance(timestamp_input, str):
                timestamp_str = timestamp_input
                # Remove 'Z' and parse as UTC
                if timestamp_str.endswith('Z'):
                    timestamp_str = timestamp_str[:-1] + '+00:00'
                return datetime.fromisoformat(timestamp_str)

            # If it's something else, convert to string first
            timestamp_str = str(timestamp_input)
            if timestamp_str.endswith('Z'):
                timestamp_str = timestamp_str[:-1] + '+00:00'
            return datetime.fromisoformat(timestamp_str)

        except Exception as e:
            logger.error(f"Error parsing Discord timestamp {timestamp_input}: {e}")
            return datetime.now(timezone.utc)

    def _is_timestamp_within_range(self, alert_time: datetime, trade_time: datetime,
                                 binance_time: Optional[datetime] = None,
                                 tolerance_minutes: int = 5) -> bool:
        """
        Check if timestamps are within acceptable range for order matching.

        Args:
            alert_time: Alert timestamp
            trade_time: Trade timestamp from Discord
            binance_time: Binance updateTime (optional)
            tolerance_minutes: Time tolerance in minutes

        Returns:
            bool: True if timestamps are within range
        """
        tolerance = tolerance_minutes * 60  # Convert to seconds

        # Check Discord timestamp proximity
        discord_diff = abs((alert_time - trade_time).total_seconds())
        if discord_diff <= tolerance:
            return True

        # If Binance timestamp is available, check it too
        if binance_time:
            binance_diff = abs((alert_time - binance_time).total_seconds())
            if binance_diff <= tolerance:
                return True

        return False

    async def _find_related_orders(self, coin_symbol: str, alert_timestamp: str,
                                 trade_group_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Find all orders related to a position based on timestamp and grouping.

        Args:
            coin_symbol: The cryptocurrency symbol
            alert_timestamp: Alert timestamp string
            trade_group_id: Optional trade group ID for grouping

        Returns:
            List[Dict]: List of related trade orders
        """
        try:
            alert_time = self._parse_discord_timestamp(alert_timestamp)

            # Query trades by coin symbol
            if hasattr(self.binance_trading_engine, 'db_manager'):
                trades = await self.binance_trading_engine.db_manager.get_trades_by_coin_symbol(coin_symbol)
            else:
                logger.error("Database manager not available")
                return []

            related_orders = []

            for trade in trades:
                if not trade.get('is_active', True):
                    continue

                trade_time = self._parse_discord_timestamp(trade.get('timestamp', ''))

                # Parse Binance response for updateTime
                binance_time = None
                raw = trade.get('exchange_response') or trade.get('binance_response', '')
                if raw:
                    try:
                        response_data = json.loads(raw) if isinstance(raw, str) else raw
                        if 'updateTime' in response_data:
                            binance_time = self._convert_binance_timestamp(response_data['updateTime'])
                    except (json.JSONDecodeError, KeyError, TypeError):
                        pass

                # Check if timestamps match
                if self._is_timestamp_within_range(alert_time, trade_time, binance_time):
                    # If trade_group_id is provided, also check grouping
                    if trade_group_id and trade.get('trade_group_id') != trade_group_id:
                        continue

                    related_orders.append(trade)
                    logger.info(f"Found related order: {trade.get('discord_id')} - {trade.get('exchange_order_id')}")

            return related_orders

        except Exception as e:
            logger.error(f"Error finding related orders: {e}")
            return []

    async def _extract_order_ids_from_trade(self, trade: Dict[str, Any]) -> List[str]:
        """
        Extract all order IDs from a trade's Binance response.

        Args:
            trade: Trade dictionary

        Returns:
            List[str]: List of order IDs
        """
        order_ids = []

        try:
            # Main order ID
            if trade.get('exchange_order_id'):
                order_ids.append(trade['exchange_order_id'])

            # Stop loss order ID
            if trade.get('stop_loss_order_id'):
                order_ids.append(trade['stop_loss_order_id'])

            # Parse binance_response for additional orders
            binance_response = trade.get('binance_response', '')
            if binance_response:
                try:
                    response_data = json.loads(binance_response)

                    # Main order ID from response
                    if 'order_id' in response_data:
                        order_ids.append(str(response_data['order_id']))

                    # TP/SL orders
                    tp_sl_orders = response_data.get('tp_sl_orders', [])
                    for order in tp_sl_orders:
                        if 'orderId' in order:
                            order_ids.append(str(order['orderId']))

                except (json.JSONDecodeError, KeyError, TypeError) as e:
                    logger.warning(f"Error parsing binance_response: {e}")

            # Remove duplicates
            return list(set(order_ids))

        except Exception as e:
            logger.error(f"Error extracting order IDs: {e}")
            return []

    async def _process_alert_for_multiple_orders(self, alert_data: Dict[str, Any],
                                               related_orders: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Process an alert that affects multiple orders in a position.

        Args:
            alert_data: Alert data dictionary
            related_orders: List of related trade orders

        Returns:
            Dict: Processing result
        """
        try:
            action_type = alert_data.get('action_determined', {}).get('action_type', '')
            coin_symbol = alert_data.get('coin_symbol', '')

            logger.info(f"Processing alert for {len(related_orders)} orders: {action_type}")

            results = []

            for trade in related_orders:
                # Extract all order IDs for this trade
                order_ids = await self._extract_order_ids_from_trade(trade)

                if not order_ids:
                    logger.warning(f"No order IDs found for trade {trade.get('discord_id')}")
                    continue

                logger.info(f"Processing {action_type} for trade {trade.get('discord_id')} with orders: {order_ids}")

                # Process based on action type
                if action_type == 'stop_loss_hit':
                    # Close position for this trade
                    success, response = await self.binance_trading_engine.close_position_at_market(
                        trade, "stop_loss_hit"
                    )
                    results.append({
                        'trade_id': trade.get('discord_id'),
                        'order_ids': order_ids,
                        'success': success,
                        'response': response
                    })

                elif action_type == 'profit_close':
                    # Close position in profit
                    success, response = await self.binance_trading_engine.close_position_at_market(
                        trade, "profit_close"
                    )
                    results.append({
                        'trade_id': trade.get('discord_id'),
                        'order_ids': order_ids,
                        'success': success,
                        'response': response
                    })

                elif action_type == 'break_even':
                    # Move stop loss to break even
                    # This would need to be implemented in the trading engine
                    logger.info(f"Break even action for trade {trade.get('discord_id')} - not yet implemented")
                    results.append({
                        'trade_id': trade.get('discord_id'),
                        'order_ids': order_ids,
                        'success': False,
                        'response': "Break even action not yet implemented"
                    })

                else:
                    logger.warning(f"Unknown action type: {action_type}")
                    results.append({
                        'trade_id': trade.get('discord_id'),
                        'order_ids': order_ids,
                        'success': False,
                        'response': f"Unknown action type: {action_type}"
                    })

            # Determine overall success
            successful_results = [r for r in results if r['success']]
            overall_success = len(successful_results) > 0

            return {
                'status': 'success' if overall_success else 'error',
                'message': f"Processed {len(successful_results)}/{len(results)} orders successfully",
                'results': results,
                'total_orders_affected': len(results)
            }

        except Exception as e:
            logger.error(f"Error processing alert for multiple orders: {e}")
            return {
                'status': 'error',
                'message': f"Error processing alert: {str(e)}",
                'results': [],
                'total_orders_affected': 0
            }

    async def _find_trade_by_discord_id(self, discord_id: str) -> Optional[Dict[str, Any]]:
        """
        Find trade by discord_id.

        Args:
            discord_id: The discord ID to search for

        Returns:
            Dict[str, Any]: Trade data or None if not found
        """
        try:
            ref = (discord_id or "").strip()
            if not ref:
                return None

            # We need database access via a Supabase client; use runtime_config.supabase directly
            trade = None
            try:
                if self.runtime_config and getattr(self.runtime_config, 'supabase', None):
                    resp = self.runtime_config.supabase.table("trades").select("*").eq("discord_id", ref).limit(1).execute()
                    data = getattr(resp, 'data', None)
                    if data:
                        trade = data[0]
            except Exception:
                trade = None
            if trade:
                return trade

            # Fallback 1: match by signal_id
            try:
                if self.runtime_config and getattr(self.runtime_config, 'supabase', None):
                    resp = self.runtime_config.supabase.table("trades").select("*").eq("signal_id", ref).limit(1).execute()
                    data = getattr(resp, 'data', None)
                    if data:
                        return data[0]
            except Exception:
                pass

            # Fallback 2: numeric id
            try:
                numeric_id = int(ref)
                if self.runtime_config and getattr(self.runtime_config, 'supabase', None):
                    resp = self.runtime_config.supabase.table("trades").select("*").eq("id", numeric_id).limit(1).execute()
                    data = getattr(resp, 'data', None)
                    if data:
                        return data[0]
            except Exception:
                pass

            logger.info(f"No trade found by reference after fallbacks: {ref}")
            return None
        except Exception as e:
            logger.error(f"Error finding trade by discord_id {discord_id}: {e}")
            return None
