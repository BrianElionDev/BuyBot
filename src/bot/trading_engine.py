import asyncio
import logging
import time
from typing import Any, Dict, List, Optional, Tuple, Union

from discord_bot.database import DatabaseManager
from src.exchange.binance_exchange import BinanceExchange
from src.services.price_service import PriceService

from config import settings as config
import json

logger = logging.getLogger(__name__)

# Constants from binance-python
SIDE_BUY = 'BUY'
SIDE_SELL = 'SELL'
ORDER_TYPE_MARKET = 'MARKET'
ORDER_TYPE_LIMIT = 'LIMIT'
FUTURE_ORDER_TYPE_MARKET = 'MARKET'
FUTURE_ORDER_TYPE_STOP_MARKET = 'STOP_MARKET'

class TradingEngine:
    """
    The core logic for processing signals and executing trades.
    """
    def __init__(self, price_service: PriceService, binance_exchange: BinanceExchange, db_manager: DatabaseManager):
        self.price_service = price_service
        self.binance_exchange = binance_exchange
        self.db_manager = db_manager
        self.trade_cooldowns = {}
        logger.info("TradingEngine initialized.")

    async def process_signal(
        self,
        coin_symbol: str,
        signal_price: float,
        position_type: str,
        order_type: str = "MARKET",
        stop_loss: Optional[Union[float, str]] = None,
        take_profits: Optional[List[float]] = None,
        dca_range: Optional[List[float]] = None,
        client_order_id: Optional[str] = None,
        price_threshold_override: Optional[float] = None,
        quantity_multiplier: Optional[int] = None
    ) -> Tuple[bool, Union[Dict, str]]:
        """
        Processes a CEX (Binance) signal.
        This is the main entry point for executing trades based on alerts.
        """
        logger.info(f"--- Processing CEX Signal for {coin_symbol} ---")

        # Check cooldown
        cooldown_key = f"cex_{coin_symbol}"
        if time.time() - self.trade_cooldowns.get(cooldown_key, 0) < config.TRADE_COOLDOWN:
            reason = f"Trade cooldown active for {coin_symbol}"
            logger.info(reason)
            return False, reason

        # --- Pair Validation and Auto-Switching ---
        is_futures = position_type.upper() in ['LONG', 'SHORT']
        trading_pair = self.binance_exchange.get_futures_trading_pair(coin_symbol)

        if is_futures:
            is_supported = await self.binance_exchange.is_futures_symbol_supported(trading_pair)
            if not is_supported:
                logger.warning(f"Futures symbol {trading_pair} not supported. Checking SPOT market.")
                spot_pair = f"{coin_symbol.upper()}USDT"
                is_spot_supported = await self.binance_exchange.is_futures_symbol_supported(spot_pair) # Placeholder, needs spot check
                if is_spot_supported:
                    logger.info(f"Symbol found on SPOT market. Switching trade to SPOT buy.")
                    position_type = 'SPOT'
                    is_futures = False
                    trading_pair = spot_pair
                else:
                    reason = f"Symbol {coin_symbol} not supported on Futures or Spot."
                    logger.error(reason)
                    return False, reason
        # --- End Validation ---

        logger.info(f"Processing trade for {trading_pair} ({'Futures' if is_futures else 'Spot'})")
        logger.info(f"Position Type: {position_type}")
        logger.info(f"Signal Price: ${signal_price:.8f}")
        logger.info(f"Order Type: {order_type}")
        if stop_loss:
            logger.info(f"Stop Loss: ${stop_loss}")
        if take_profits:
            logger.info(f"Take Profits: {', '.join([f'${tp:.8f}' for tp in take_profits])}")

        # Get current market price
        current_price = await self.price_service.get_coin_price(coin_symbol)
        if not current_price:
            reason = f"Failed to get price for {coin_symbol}"
            logger.error(reason)
            return False, reason

        # Check price difference threshold
        threshold = price_threshold_override if price_threshold_override is not None else config.PRICE_THRESHOLD

        # Use dynamic thresholds based on coin type
        memecoin_symbols = ['PEPE', 'BONK', 'DOGE', 'SHIB', 'FLOKI', 'PENGU', 'H', 'TOSHI', 'TURBO', 'MOG', 'FARTCOIN', 'PUMP', 'PUMPFUN']
        low_liquidity_symbols = ['ICNT', 'SPX', 'SYRUP', 'VIC', 'SPEC', 'HAEDAL', 'ZORA', 'CUDI', 'BERA', 'ALU', 'INIT', 'XLM', 'ADA', 'REZ', 'SEI', 'VIRTUAL', 'ES', 'HBAR', 'ONDO', 'LAUNCHCOIN', 'PNUT', 'MAV', 'PLUME']

        if coin_symbol.upper() in memecoin_symbols:
            threshold = max(threshold, config.MEMECOIN_PRICE_THRESHOLD)
            logger.info(f"Using memecoin threshold: {threshold}% for {coin_symbol}")
        elif coin_symbol.upper() in low_liquidity_symbols:
            threshold = max(threshold, config.LOW_LIQUIDITY_PRICE_THRESHOLD)
            logger.info(f"Using low-liquidity threshold: {threshold}% for {coin_symbol}")

        price_diff = abs(current_price - signal_price) / signal_price * 100
        if price_diff > threshold:
            # For high price differences, try using market order instead of rejecting
            if order_type == 'LIMIT':
                logger.warning(f"Price difference high ({price_diff:.2f}%) for {coin_symbol}. Switching to MARKET order.")
                order_type = 'MARKET'
                # Continue with market order instead of rejecting
            else:
                reason = f"Price difference too high: {price_diff:.2f}% (threshold: {threshold}%)"
                logger.warning(reason)
                return False, reason

        # --- Calculate Trade Amount ---
        trade_amount = 0.0
        try:
            # REMOVE: USDT/USDM balance logic
            trade_amount = config.TRADE_AMOUNT / current_price
            logger.info(f"Using fixed trade amount: {trade_amount} {coin_symbol} (${config.TRADE_AMOUNT:.2f})")

            # Apply quantity multiplier if specified (for memecoins)
            if quantity_multiplier and quantity_multiplier > 1:
                trade_amount *= quantity_multiplier
                logger.info(f"Applied quantity multiplier {quantity_multiplier}: {trade_amount} {coin_symbol}")

        except Exception as e:
            reason = f"Failed to calculate trade amount: {e}"
            logger.error(reason, exc_info=True)
            return False, reason

        if trade_amount <= 0:
            return False, "Calculated trade amount is zero or negative."
        # --- End Calculate Trade Amount ---

        order_result = {}
        if is_futures:
            entry_side = SIDE_BUY if position_type.upper() == 'LONG' else SIDE_SELL
            order_result = await self.binance_exchange.create_futures_order(
                pair=trading_pair,
                side=entry_side,
                order_type_market=order_type,
                amount=trade_amount,
                price=signal_price if order_type == 'LIMIT' else None,
                client_order_id=client_order_id
            )

            if order_result and 'orderId' in order_result and stop_loss:
                try:
                    sl_price = float(stop_loss)
                    sl_order_result = await self.binance_exchange.create_futures_order(
                        pair=trading_pair,
                        side=SIDE_SELL if position_type.upper() == 'LONG' else SIDE_BUY,
                        order_type_market=FUTURE_ORDER_TYPE_STOP_MARKET,
                        stop_price=sl_price,
                        amount=order_result.get('origQty', trade_amount),
                        reduce_only=True
                    )
                    if sl_order_result and 'orderId' in sl_order_result:
                        logger.info(f"Successfully created stop-loss order: {sl_order_result}")
                        order_result['stop_loss_order_details'] = sl_order_result
                    else:
                        logger.error(f"Failed to create stop-loss order: {sl_order_result}. Main trade remains open.")
                except (ValueError, TypeError):
                    logger.warning(f"Could not determine a valid numerical stop loss price from '{stop_loss}'. Skipping SL order creation.")
        else: # Spot
            order_result = await self.binance_exchange.create_order(
                pair=trading_pair,
                side=SIDE_BUY,
                order_type_market=ORDER_TYPE_MARKET,
                amount=trade_amount
            )

        if order_result and 'orderId' in order_result:
            self.trade_cooldowns[cooldown_key] = time.time()
            logger.info(f"CEX trade successful for {coin_symbol}: {order_result}")
            return True, order_result
        else:
            reason = f"CEX trade failed for {coin_symbol}. Response: {order_result}"
            logger.error(reason)
            return False, order_result

    async def cancel_order(self, active_trade: Dict) -> Tuple[bool, Dict]:
        """
        Cancels an open order associated with a trade.
        """
        try:
            coin_symbol = (active_trade.get("parsed_signal") or {}).get("coin_symbol")
            order_id = active_trade.get("exchange_order_id")

            if not coin_symbol or not order_id:
                return False, {"error": f"Missing coin_symbol or order_id for trade {active_trade.get('id')}"}

            logger.info(f"Attempting to cancel order {order_id} for {coin_symbol}")

            trading_pair = self.binance_exchange.get_futures_trading_pair(coin_symbol)
            success, response = await self.binance_exchange.cancel_futures_order(trading_pair, order_id)

            if success:
                logger.info(f"Successfully cancelled order {order_id} for {coin_symbol}")
                return True, response
            else:
                logger.error(f"Failed to cancel order {order_id} for {coin_symbol}. Reason: {response}")
                return False, response

        except Exception as e:
            logger.error(f"Error cancelling order: {e}", exc_info=True)
            return False, {"error": f"Order cancellation failed: {str(e)}"}

    async def is_position_open(self, coin_symbol: str, position_side: str = 'BOTH') -> bool:
        """Check if a position is open for the given symbol and side on Binance Futures."""
        if not coin_symbol:
            logger.error("coin_symbol is required for is_position_open")
            return False
        try:
            trading_pair = self.binance_exchange.get_futures_trading_pair(coin_symbol)
            pos_info = await self.binance_exchange.client.futures_position_information(symbol=trading_pair)  # type: ignore
            for pos in pos_info:
                if pos['positionSide'] == position_side and float(pos['positionAmt']) != 0:
                    logger.info(f"Position is open for {coin_symbol} side {position_side}: {pos['positionAmt']}")
                    return True
            logger.info(f"No open position for {coin_symbol} side {position_side}")
            return False
        except Exception as e:
            logger.error(f"Error checking position status for {coin_symbol}: {e}")
            return False

    async def process_trade_update(self, trade_id: int, action: str, details: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
        """
        Process updates for an existing trade, like taking profit, moving stop loss, or partial close.
        """
        active_trade = await self.db_manager.get_trade_by_id(trade_id)
        if not active_trade:
            logger.error(f"Could not find an active trade for ID {trade_id} to process update.")
            return False, {"error": "Active trade not found"}

        # Parse position size and order info
        position_size = float(active_trade.get('position_size') or 0.0)
        binance_response = active_trade.get('binance_response')
        if isinstance(binance_response, str):
            import json
            try:
                binance_response = json.loads(binance_response)
            except Exception:
                binance_response = {}
        exchange_order_id = (active_trade.get('exchange_order_id') or (binance_response.get('orderId') if binance_response else None))
        stop_loss_order_id = (active_trade.get('stop_loss_order_id') or ((binance_response.get('stop_loss_order_details') or {}).get('orderId') if binance_response else None))
        coin_symbol = ((active_trade.get('parsed_signal') or {}).get('coin_symbol') or active_trade.get('coin_symbol'))
        position_type = ((active_trade.get('parsed_signal') or {}).get('position_type') or active_trade.get('signal_type'))
        entry_price = active_trade.get('entry_price')
        if not coin_symbol or not position_type:
            logger.error(f"Missing coin_symbol or position_type for trade {trade_id}")
            return False, {"error": f"Missing coin_symbol or position_type for trade {trade_id}"}
        trading_pair = self.binance_exchange.get_futures_trading_pair(coin_symbol)

        # Check if position is open before acting
        is_open = await self.is_position_open(coin_symbol)
        if not is_open:
            logger.warning(f"Position for {coin_symbol} is already closed. No action taken.")
            return False, {"error": f"Position for {coin_symbol} is already closed."}

        # Partial close logic
        close_pct = details.get('close_percentage', 100.0)
        if close_pct < 100.0:
            amount_to_close = position_size * (close_pct / 100.0)
            logger.info(f"Partial close: closing {close_pct}% of position ({amount_to_close} {coin_symbol})")
        else:
            amount_to_close = position_size
            logger.info(f"Full close: closing 100% of position ({amount_to_close} {coin_symbol})")

        # Multiple TP logic
        if action.startswith('take_profit_'):
            tp_idx = int(action.split('_')[-1])
            tp_price = details.get('tp_price')
            if not tp_price:
                logger.error(f"No TP price provided for TP{tp_idx}")
                return False, {"error": f"No TP price provided for TP{tp_idx}"}
            logger.info(f"Placing TP{tp_idx} for {coin_symbol} at {tp_price} for {amount_to_close}")
            # Place a LIMIT order at tp_price for amount_to_close, reduceOnly
            tp_side = 'SELL' if position_type and position_type.upper() == 'LONG' else 'BUY'
            tp_order = await self.binance_exchange.create_futures_order(
                pair=trading_pair,
                side=tp_side,
                order_type_market='LIMIT',
                amount=amount_to_close,
                price=tp_price,
                reduce_only=True
            )
            if tp_order and 'orderId' in tp_order:
                logger.info(f"TP{tp_idx} order placed: {tp_order['orderId']}")
                return True, tp_order
            else:
                logger.error(f"Failed to place TP{tp_idx} order: {tp_order}")
                return False, {"error": f"Failed to place TP{tp_idx} order", "response": tp_order}

        # Standard close (market)
        if action in ['take_profit', 'stop_loss_hit', 'position_closed']:
            logger.info(f"Closing position for {coin_symbol} at market. Reason: {action}")
            close_side = 'SELL' if position_type and position_type.upper() == 'LONG' else 'BUY'
            close_order = await self.binance_exchange.create_futures_order(
                pair=trading_pair,
                side=close_side,
                order_type_market='MARKET',
                amount=amount_to_close,
                reduce_only=True
            )
            if close_order and 'orderId' in close_order:
                logger.info(f"Position closed: {close_order['orderId']}")
                return True, close_order
            else:
                logger.error(f"Failed to close position: {close_order}")
                return False, {"error": "Failed to close position", "response": close_order}

        # Stop loss update
        if action == 'stop_loss_update':
            new_stop_price = details.get('stop_price')
            if new_stop_price == 'BE':
                new_stop_price = entry_price
            if not isinstance(new_stop_price, (float, int)) or new_stop_price is None or new_stop_price <= 0:
                logger.error(f"Invalid new stop price for update: {new_stop_price}")
                return False, {"error": f"Invalid new stop price for update: {new_stop_price}"}
            logger.info(f"Updating stop loss for {coin_symbol} to {new_stop_price}")
            # Cancel old SL order if exists
            if stop_loss_order_id:
                await self.binance_exchange.cancel_futures_order(trading_pair, stop_loss_order_id)
            new_sl_side = 'SELL' if position_type and position_type.upper() == 'LONG' else 'BUY'
            new_sl_order = await self.binance_exchange.create_futures_order(
                pair=trading_pair,
                side=new_sl_side,
                order_type_market='STOP_MARKET',
                stop_price=new_stop_price,
                amount=position_size,
                reduce_only=True
            )
            if new_sl_order and 'orderId' in new_sl_order:
                logger.info(f"Stop loss updated: {new_sl_order['orderId']}")
                return True, new_sl_order
            else:
                logger.error(f"Failed to update stop loss: {new_sl_order}")
                return False, {"error": "Failed to update stop loss", "response": new_sl_order}

        logger.error(f"Unknown action: {action}")
        return False, {"error": f"Unknown action: {action}"}

    async def close_position_at_market(self, active_trade: Dict, reason: str = "manual_close", close_percentage: float = 100.0) -> Tuple[bool, Dict]:
        """
        Closes a percentage of an open futures position at the current market price.
        """
        try:
            parsed_signal = active_trade.get("parsed_signal") or {}
            coin_symbol = parsed_signal.get("coin_symbol")
            position_type = parsed_signal.get("position_type", "SPOT").upper()
            position_size = float(active_trade.get("position_size") or 0.0)

            if position_size <= 0:
                initial_response = active_trade.get("binance_response")
                if isinstance(initial_response, dict):
                    position_size = float(initial_response.get('origQty') or 0.0)

            if not coin_symbol or position_size <= 0:
                return False, {"error": f"Invalid trade data for closing position. Symbol: {coin_symbol}, Size: {position_size}"}

            amount_to_close = position_size * (close_percentage / 100.0)
            trading_pair = self.binance_exchange.get_futures_trading_pair(coin_symbol)
            is_futures = position_type in ['LONG', 'SHORT']

            if is_futures:
                close_side = SIDE_SELL if position_type == 'LONG' else SIDE_BUY
                close_order = await self.binance_exchange.create_futures_order(
                    pair=trading_pair,
                    side=close_side,
                    order_type_market=FUTURE_ORDER_TYPE_MARKET,
                    amount=amount_to_close,
                    reduce_only=False
                )
            else:
                close_order = await self.binance_exchange.create_order(
                    pair=trading_pair,
                    side='sell',
                    order_type_market='MARKET',
                    amount=amount_to_close
                )

            if close_order and 'orderId' in close_order:
                logger.info(f"Successfully placed close order for {coin_symbol}: {close_order}")
                return True, close_order
            else:
                return False, {"error": f"Failed to place close order. Response: {close_order}"}
        except Exception as e:
            logger.error(f"Error closing position: {e}", exc_info=True)
            return False, {"error": str(e)}

    async def update_stop_loss(self, active_trade: Dict, new_sl_price: float) -> Tuple[bool, Dict]:
        """
        Update stop loss for an active position.
        """
        try:
            parsed_signal = active_trade.get("parsed_signal") or {}
            coin_symbol = parsed_signal.get("coin_symbol")
            position_type = parsed_signal.get("position_type", "SPOT")
            position_size = float(active_trade.get("position_size") or 0.0)
            old_sl_order_id = active_trade.get("stop_loss_order_id")

            if position_size <= 0:
                initial_response = active_trade.get("binance_response")
                if isinstance(initial_response, dict):
                    position_size = float(initial_response.get('origQty') or 0.0)

            if not coin_symbol or position_size <= 0:
                return False, {"error": f"Invalid trade data for updating stop loss. Symbol: {coin_symbol}, Size: {position_size}"}

            trading_pair = self.binance_exchange.get_futures_trading_pair(coin_symbol)

            if old_sl_order_id:
                await self.binance_exchange.cancel_futures_order(trading_pair, old_sl_order_id)

            new_sl_side = SIDE_SELL if position_type.upper() == 'LONG' else SIDE_BUY
            new_sl_order_result = await self.binance_exchange.create_futures_order(
                pair=trading_pair,
                side=new_sl_side,
                order_type_market=FUTURE_ORDER_TYPE_STOP_MARKET,
                stop_price=new_sl_price,
                amount=position_size,
                reduce_only=True
            )

            if new_sl_order_result and 'orderId' in new_sl_order_result:
                return True, new_sl_order_result
            else:
                return False, {"error": f"Failed to create new SL order. Response: {new_sl_order_result}"}
        except Exception as e:
            logger.error(f"Error updating stop loss: {e}", exc_info=True)
            return False, {"error": f"Stop loss update failed: {str(e)}"}

    async def close(self):
        """Close all exchange connections."""
        await self.binance_exchange.close_client()
        logger.info("TradingEngine connections closed.")