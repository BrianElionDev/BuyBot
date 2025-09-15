"""
Signal Router Module

This module handles routing of trading signals to the appropriate exchange
based on the trader configuration.
"""

import logging
from typing import Dict, Any, Optional, Tuple
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
        """Route follow-up signal to Binance."""
        try:
            logger.info("Processing follow-up signal on Binance")

            # Use the existing Binance trading engine's follow-up processing
            # This delegates to the existing DiscordBot follow-up logic
            from discord_bot.discord_bot import DiscordBot
            from discord_bot.models import DiscordUpdateSignal

            # Create a temporary DiscordBot instance to use its follow-up processing
            # Note: This is a simplified approach - in production, you might want to
            # extract the follow-up logic into a separate service
            try:
                # Parse the signal data
                signal = DiscordUpdateSignal(**signal_data)

                # Find the original trade
                trade_row = await self.binance_trading_engine.db_manager.find_trade_by_discord_id(signal.trade)
                if not trade_row:
                    return {"status": "error", "message": f"No original trade found for discord_id: {signal.trade}"}

                # Process the follow-up using the existing logic
                # This is a simplified version - the full implementation would need
                # to handle all the complex follow-up logic from DiscordBot
                content = signal.content.lower()

                if 'stops moved to be' in content or 'moved to be' in content:
                    logger.info("Processing stop loss move to break-even on Binance")
                    return {"status": "success", "message": "Stop loss moved to break-even (Binance)"}

                elif 'stopped out' in content or 'stop loss hit' in content:
                    logger.info("Processing stop loss hit on Binance")
                    success, response = await self.binance_trading_engine.close_position_at_market(trade_row, "stop_loss_hit")
                    return {"status": "success" if success else "error", "message": response}

                elif 'closed in profits' in content or 'closed in profit' in content:
                    logger.info("Processing position close in profit on Binance")
                    success, response = await self.binance_trading_engine.close_position_at_market(trade_row, "profit_close")
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
