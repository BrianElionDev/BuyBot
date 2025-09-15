"""
Signal Router Module

This module handles routing of trading signals to the appropriate exchange
based on the trader configuration.
"""

import logging
import json
from datetime import datetime, timezone
from typing import Dict, Any, Optional, Tuple, List
from src.config.trader_config import ExchangeType, get_exchange_for_trader

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
        entry_prices: Optional[list] = None
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
            exchange_type = get_exchange_for_trader(trader)

            logger.info(f"Routing signal from trader {trader} to {exchange_type.value} exchange")

            # Route to appropriate exchange
            if exchange_type == ExchangeType.BINANCE:
                return await self._route_to_binance(
                    coin_symbol, signal_price, position_type, order_type,
                    stop_loss, take_profits, dca_range, client_order_id,
                    price_threshold_override, quantity_multiplier, entry_prices
                )
            elif exchange_type == ExchangeType.KUCOIN:
                return await self._route_to_kucoin(
                    coin_symbol, signal_price, position_type, order_type,
                    stop_loss, take_profits, dca_range, client_order_id,
                    price_threshold_override, quantity_multiplier, entry_prices
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
            exchange_type = get_exchange_for_trader(trader)

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
            exchange_type = get_exchange_for_trader(trader)

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
        entry_prices: Optional[list]
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
                entry_prices=entry_prices
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
        entry_prices: Optional[list]
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
                entry_prices=entry_prices
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
        """Route follow-up signal to Binance with enhanced order matching."""
        try:
            logger.info("Processing follow-up signal on Binance with timestamp-based order matching")

            from discord_bot.models import DiscordUpdateSignal

            try:
                # Parse the signal data
                signal = DiscordUpdateSignal(**signal_data)

                # Extract alert data for enhanced processing
                alert_data = signal_data.get('parsed_alert', {})
                if isinstance(alert_data, str):
                    try:
                        alert_data = json.loads(alert_data)
                    except json.JSONDecodeError:
                        alert_data = {}

                # Get coin symbol from alert data or signal
                coin_symbol = alert_data.get('coin_symbol') or signal_data.get('coin_symbol')
                if not coin_symbol:
                    logger.error("No coin symbol found in signal data")
                    return {"status": "error", "message": "No coin symbol found in signal data"}

                # Find related orders using timestamp matching
                related_orders = await self._find_related_orders(
                    coin_symbol=coin_symbol,
                    alert_timestamp=signal.timestamp,
                    trade_group_id=signal_data.get('trade_group_id')
                )

                if not related_orders:
                    # Fallback to original single trade lookup
                    logger.info("No related orders found, falling back to single trade lookup")
                    trade_row = await self.binance_trading_engine.db_manager.find_trade_by_discord_id(signal.trade)
                    if not trade_row:
                        return {"status": "error", "message": f"No original trade found for discord_id: {signal.trade}"}
                    related_orders = [trade_row]

                # Process the follow-up using enhanced logic
                content = signal.content.lower()

                if 'stops moved to be' in content or 'moved to be' in content:
                    logger.info("Processing stop loss move to break-even on Binance")
                    # Use enhanced processing for multiple orders
                    if len(related_orders) > 1:
                        alert_data['action_determined'] = {'action_type': 'break_even'}
                        return await self._process_alert_for_multiple_orders(alert_data, related_orders)
                    else:
                        return {"status": "success", "message": "Stop loss moved to break-even (Binance)"}

                elif 'stopped out' in content or 'stop loss hit' in content:
                    logger.info("Processing stop loss hit on Binance")
                    # Use enhanced processing for multiple orders
                    if len(related_orders) > 1:
                        alert_data['action_determined'] = {'action_type': 'stop_loss_hit'}
                        return await self._process_alert_for_multiple_orders(alert_data, related_orders)
                    else:
                        success, response = await self.binance_trading_engine.close_position_at_market(related_orders[0], "stop_loss_hit")
                        return {"status": "success" if success else "error", "message": response}

                elif 'closed in profits' in content or 'closed in profit' in content:
                    logger.info("Processing position close in profit on Binance")
                    # Use enhanced processing for multiple orders
                    if len(related_orders) > 1:
                        alert_data['action_determined'] = {'action_type': 'profit_close'}
                        return await self._process_alert_for_multiple_orders(alert_data, related_orders)
                    else:
                        success, response = await self.binance_trading_engine.close_position_at_market(related_orders[0], "profit_close")
                        return {"status": "success" if success else "error", "message": response}

                elif 'limit order filled' in content:
                    logger.info("Processing limit order filled on Binance")
                    return {"status": "success", "message": "Limit order filled (Binance)"}

                else:
                    logger.warning(f"Unknown follow-up signal on Binance: {signal.content}")
                    return {"status": "error", "message": f"Unknown follow-up signal: {signal.content}"}

            except Exception as e:
                logger.error(f"Error in Binance follow-up processing: {e}")
                return {"status": "error", "message": f"Binance follow-up processing error: {str(e)}"}

        except Exception as e:
            logger.error(f"Error processing follow-up signal on Binance: {e}")
            return {"status": "error", "message": f"Binance follow-up error: {str(e)}"}

    async def _route_followup_to_kucoin(self, signal_data: Dict[str, Any]) -> Dict[str, Any]:
        """Route follow-up signal to KuCoin."""
        if not self.kucoin_trading_engine:
            logger.error("KuCoin trading engine not available")
            return {"status": "error", "message": "KuCoin trading engine not available"}

        try:
            logger.info("Processing follow-up signal on KuCoin")

            # Use the KuCoin trading engine's follow-up processing
            from discord_bot.models import DiscordUpdateSignal

            try:
                # Parse the signal data
                signal = DiscordUpdateSignal(**signal_data)

                # Find the original trade
                trade_row = await self.kucoin_trading_engine.db_manager.find_trade_by_discord_id(signal.trade)
                if not trade_row:
                    return {"status": "error", "message": f"No original trade found for discord_id: {signal.trade}"}

                # Process the follow-up using KuCoin trading engine
                result = await self.kucoin_trading_engine.process_followup_signal(signal_data, trade_row)
                return result

            except Exception as e:
                logger.error(f"Error in KuCoin follow-up processing: {e}")
                return {"status": "error", "message": f"KuCoin follow-up processing error: {str(e)}"}

        except Exception as e:
            logger.error(f"Error processing follow-up signal on KuCoin: {e}")
            return {"status": "error", "message": f"KuCoin follow-up error: {str(e)}"}

    def get_exchange_for_trader(self, trader: str) -> ExchangeType:
        """
        Get the exchange type for a given trader.

        Args:
            trader: The trader identifier

        Returns:
            ExchangeType: The exchange that should handle this trader's signals
        """
        return get_exchange_for_trader(trader)

    def is_trader_supported(self, trader: str) -> bool:
        """
        Check if a trader is supported.

        Args:
            trader: The trader identifier

        Returns:
            bool: True if trader is supported, False otherwise
        """
        from src.config.trader_config import is_trader_supported
        return is_trader_supported(trader)

    def _convert_binance_timestamp(self, update_time_ms: int) -> datetime:
        """
        Convert Binance updateTime (milliseconds) to datetime.

        Args:
            update_time_ms: Binance updateTime in milliseconds

        Returns:
            datetime: Converted datetime object
        """
        return datetime.fromtimestamp(update_time_ms / 1000, tz=timezone.utc)

    def _parse_discord_timestamp(self, timestamp_str: str) -> datetime:
        """
        Parse Discord timestamp string to datetime.

        Args:
            timestamp_str: Discord timestamp string (ISO format)

        Returns:
            datetime: Parsed datetime object
        """
        try:
            # Remove 'Z' and parse as UTC
            if timestamp_str.endswith('Z'):
                timestamp_str = timestamp_str[:-1] + '+00:00'
            return datetime.fromisoformat(timestamp_str)
        except Exception as e:
            logger.error(f"Error parsing Discord timestamp {timestamp_str}: {e}")
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
                binance_response = trade.get('binance_response', '')
                if binance_response:
                    try:
                        response_data = json.loads(binance_response)
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
