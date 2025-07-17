import asyncio
import logging
from decimal import Decimal, ROUND_DOWN
from typing import Dict, List, Optional, Tuple
from binance import AsyncClient
from binance.exceptions import BinanceAPIException
from binance.enums import SIDE_BUY, SIDE_SELL, ORDER_TYPE_MARKET, ORDER_TYPE_LIMIT, FUTURE_ORDER_TYPE_MARKET, FUTURE_ORDER_TYPE_STOP_MARKET

# Import symbol whitelist for validation
try:
    from config.binance_futures_whitelist import is_symbol_supported
    WHITELIST_AVAILABLE = True
except ImportError:
    WHITELIST_AVAILABLE = False
    logger = logging.getLogger(__name__)
    logger.warning("Futures whitelist not available - all symbols will be allowed")

# Default precision rules for common futures symbols
DEFAULT_PRECISION_RULES = {
    'BTCUSDT': {'quantity': 3, 'price': 2},
    'ETHUSDT': {'quantity': 3, 'price': 2},
    'ADAUSDT': {'quantity': 0, 'price': 5},
    'SOLUSDT': {'quantity': 2, 'price': 3},
    'DOGEUSDT': {'quantity': 0, 'price': 6},
    'XRPUSDT': {'quantity': 1, 'price': 5},
    'DOTUSDT': {'quantity': 2, 'price': 3},
    'LINKUSDT': {'quantity': 2, 'price': 3},
    'AVAXUSDT': {'quantity': 2, 'price': 3},
    'LTCUSDT': {'quantity': 3, 'price': 2},
    'BNBUSDT': {'quantity': 2, 'price': 2},
    'MATICUSDT': {'quantity': 0, 'price': 5},
    'ATOMUSDT': {'quantity': 2, 'price': 3},
    'UNIUSDT': {'quantity': 1, 'price': 4},
    'SUSHIUSDT': {'quantity': 1, 'price': 4},
}

logger = logging.getLogger(__name__)

def format_value(value: float, step_size: str) -> str:
    """
    Formats a value to be a valid multiple of a given step size.
    Uses Decimal for precision.
    """
    value_dec = Decimal(str(value))
    step_dec = Decimal(str(step_size))

    # Perform quantization
    quantized_value = (value_dec // step_dec) * step_dec

    # Format the output string to match the precision of the step_size
    return f"{quantized_value:.{step_dec.normalize().as_tuple().exponent * -1}f}"

class BinanceExchange:
    def __init__(self, api_key: str, api_secret: str, is_testnet: bool = False):
        self.api_key = api_key
        self.api_secret = api_secret
        self.is_testnet = is_testnet
        self.client: Optional[AsyncClient] = None
        self._spot_symbols: List[str] = []
        self._futures_symbols: List[str] = []
        logger.info(f"BinanceExchange initialized for testnet: {self.is_testnet}")

    async def _init_client(self):
        if self.client is None:
            self.client = await AsyncClient.create(self.api_key, self.api_secret, tld='com', testnet=self.is_testnet)

    async def close_client(self):
        if self.client:
            await self.client.close_connection()
            logger.info("Binance client connection closed.")

    async def get_account_balances(self) -> Dict[str, float]:
        # REMOVE: USDM balance logic (futures_account)
        # If you want to keep coin-m, implement coin-m balance fetch here, or just pass for now
        return {}

    async def create_futures_order(self, pair: str, side: str, order_type_market: str, amount: float,
                                 price: Optional[float] = None, stop_price: Optional[float] = None,
                                 client_order_id: Optional[str] = None, reduce_only: bool = False) -> Dict:
        await self._init_client()
        assert self.client is not None

        # --- Begin Precision Handling ---
        try:
            # Get the precision filters for the symbol
            filters = await self.get_futures_symbol_filters(pair)
            if filters:
                step_size = filters.get('LOT_SIZE', {}).get('stepSize')
                tick_size = filters.get('PRICE_FILTER', {}).get('tickSize')

                # Format amount according to stepSize
                if step_size:
                    formatted_amount = format_value(amount, step_size)
                    logger.info(f"Original amount: {amount}, Formatted amount: {formatted_amount} (Step: {step_size})")
                    amount = float(formatted_amount) # Convert back for Binance library, though it will be sent as string

                # Format price according to tickSize
                if price is not None and tick_size:
                    formatted_price = format_value(price, tick_size)
                    logger.info(f"Original price: {price}, Formatted price: {formatted_price} (Tick: {tick_size})")
                    price = float(formatted_price)

            else:
                logger.warning(f"Could not retrieve precision filters for {pair}. Using original values.")
        except Exception as e:
            logger.error(f"An error occurred during futures precision handling for {pair}: {e}", exc_info=True)
        # --- End Precision Handling ---

        params = {
            'symbol': pair,
            'side': side,
            'type': order_type_market,
            'quantity': f"{amount}"
        }
        if order_type_market == 'LIMIT' and price is not None:
            params['price'] = f"{price}"
            params['timeInForce'] = 'GTC'
        if stop_price:
            params['stopPrice'] = f"{stop_price}"
            params['closePosition'] = 'true'
        if reduce_only:
            params['reduceOnly'] = 'true'
        if client_order_id:
            params['newClientOrderId'] = client_order_id

        try:
            response = await self.client.futures_create_order(**params)
            return response
        except BinanceAPIException as e:
            logger.error(f"Binance API Error on order creation: {e}")
            return {'error': str(e), 'code': e.code}
        except Exception as e:
            logger.error(f"Unexpected error on order creation: {e}")
            return {'error': str(e)}

    async def close_position(self, pair: str, amount: float, position_type: str) -> Tuple[bool, Dict]:
        """Closes a position by creating a market order in the opposite direction."""
        side = SIDE_SELL if position_type.upper() == 'LONG' else SIDE_BUY
        try:
            # For simplicity, we assume closing is always a MARKET order.
            # We explicitly set reduce_only to False to handle cases where the
            # position doesn't exist on the exchange (state mismatch).
            response = await self.create_futures_order(
                pair=pair,
                side=side,
                order_type_market=FUTURE_ORDER_TYPE_MARKET,
                amount=amount,
                reduce_only=False
            )
            return True, response
        except Exception as e:
            logger.error(f"Failed to close position for {pair}: {e}")
            return False, {"error": str(e)}

    async def update_stop_loss(self, pair: str, stop_price: float, amount: float, position_type: str) -> Tuple[bool, Dict]:
        """Updates the stop loss by canceling old SL orders and creating a new one."""
        await self._init_client()
        assert self.client is not None
        side = SIDE_SELL if position_type.upper() == 'LONG' else SIDE_BUY
        try:
            # 1. Cancel existing stop loss orders for the symbol
            await self.client.futures_cancel_all_open_orders(symbol=pair)

            # 2. Create a new STOP_MARKET order. This must be reduceOnly.
            response = await self.client.futures_create_order(
                symbol=pair,
                side=side,
                type=FUTURE_ORDER_TYPE_STOP_MARKET,
                quantity=amount,
                stopPrice=stop_price,
                reduceOnly=True
            )
            return True, response
        except Exception as e:
            logger.error(f"Failed to update stop loss for {pair}: {e}", exc_info=True)
            return False, {"error": str(e)}

    def get_futures_trading_pair(self, coin_symbol: str) -> str:
        """Returns the standardized futures trading pair for a given coin symbol."""
        return f"{coin_symbol.upper()}USDT"

    async def cancel_futures_order(self, pair: str, order_id: str) -> Tuple[bool, Dict]:
        """Cancels a specific futures order by its ID."""
        await self._init_client()
        assert self.client is not None
        try:
            response = await self.client.futures_cancel_order(symbol=pair, orderId=order_id)
            logger.info(f"Successfully cancelled order {order_id} for {pair}.")
            return True, response
        except BinanceAPIException as e:
            # It's common for an order to be already filled or cancelled, which can raise an error.
            # We log these as warnings because it's often not a critical failure.
            logger.warning(f"Could not cancel order {order_id} for {pair} (it may already be filled/cancelled): {e}")
            return False, {"error": str(e)}

    async def get_all_spot_symbols(self) -> List[str]:
        """Fetches all valid SPOT symbols from Binance."""
        await self._init_client()
        assert self.client is not None
        if not self._spot_symbols:
            try:
                exchange_info = await self.client.get_exchange_info()
                self._spot_symbols = [s['symbol'] for s in exchange_info['symbols']]
            except Exception as e:
                logger.error(f"Failed to fetch spot symbols: {e}")
                return []
        return self._spot_symbols

    async def get_all_futures_symbols(self) -> List[str]:
        """Fetches all valid FUTURES symbols from Binance."""
        await self._init_client()
        assert self.client is not None
        if not self._futures_symbols:
            try:
                exchange_info = await self.client.futures_exchange_info()
                self._futures_symbols = [s['symbol'] for s in exchange_info['symbols'] if s['status'] == 'TRADING']
            except Exception as e:
                logger.error(f"Failed to fetch futures symbols: {e}")
                return []
        return self._futures_symbols

    async def get_spot_balance(self) -> Dict[str, float]:
        """
        Retrieves spot account balances for all assets with a balance > 0.
        """
        await self._init_client()
        assert self.client is not None
        try:
            account_info = await self.client.get_account()
            balances = {
                asset['asset']: float(asset['free'])
                for asset in account_info['balances']
                if float(asset['free']) > 0
            }
            return balances
        except BinanceAPIException as e:
            logger.error(f"Failed to get spot balance from Binance: {e}")
            return {}

    async def create_order(self, pair: str, side: str, order_type_market: str, amount: float,
                         price: Optional[float] = None, client_order_id: Optional[str] = None) -> Dict:
        await self._init_client()
        assert self.client is not None

        # --- Begin Spot Precision Handling ---
        try:
            filters = await self.get_spot_symbol_filters(pair)
            if filters:
                step_size = filters.get('LOT_SIZE', {}).get('stepSize')
                tick_size = filters.get('PRICE_FILTER', {}).get('tickSize')

                # Format amount
                if step_size:
                    formatted_amount = format_value(amount, step_size)
                    logger.info(f"Spot original amount: {amount}, Formatted amount: {formatted_amount} (Step: {step_size})")
                    amount = float(formatted_amount)

                # Format price
                if price is not None and tick_size:
                    formatted_price = format_value(price, tick_size)
                    logger.info(f"Spot original price: {price}, Formatted price: {formatted_price} (Tick: {tick_size})")
                    price = float(formatted_price)
            else:
                logger.warning(f"Could not retrieve spot precision filters for {pair}. Using original values.")
        except Exception as e:
            logger.error(f"An error occurred during spot precision handling for {pair}: {e}", exc_info=True)
        # --- End Spot Precision Handling ---

        params = {
            'symbol': pair,
            'side': side,
            'type': order_type_market,
        }
        if order_type_market == ORDER_TYPE_MARKET:
            params['quantity'] = f"{amount}"
        elif order_type_market == ORDER_TYPE_LIMIT and price:
            params['quantity'] = f"{amount}"
            params['price'] = f"{price}"
            params['timeInForce'] = 'GTC'

        if client_order_id:
            params['newClientOrderId'] = client_order_id

        try:
            response = await self.client.create_order(**params)
            return response
        except BinanceAPIException as e:
            logger.error(f"Failed to create order on Binance Spot: {e}")
            return {}
        except Exception as e:
            logger.error(f"An unexpected error occurred: {e}")
            return {}

    async def get_order_status(self, pair: str, order_id: str) -> Optional[Dict]:
        """
        Get the status of an order.

        Args:
            pair: Trading pair (e.g., 'BTCUSDT')
            order_id: Order ID

        Returns:
            Order status dictionary or None if failed
        """
        await self._init_client()
        assert self.client is not None
        try:
            formatted_pair = pair.replace('_', '').upper()
            order = await self.client.get_order(
                symbol=formatted_pair,
                orderId=order_id
            )
            return order
        except BinanceAPIException as e:
            logger.error(f"Failed to get order status: {e}")
            return None

    async def cancel_order(self, pair: str, order_id: str) -> bool:
        """
        Cancel an existing order.

        Args:
            pair: Trading pair (e.g., 'BTCUSDT')
            order_id: Order ID

        Returns:
            True if successful, False otherwise
        """
        await self._init_client()
        assert self.client is not None
        try:
            formatted_pair = pair.replace('_', '').upper()
            result = await self.client.cancel_order(
                symbol=formatted_pair,
                orderId=order_id
            )
            logger.info(f"Order cancelled successfully: {result}")
            return True
        except BinanceAPIException as e:
            logger.error(f"Failed to cancel order: {e}")
            return False

    async def get_all_open_futures_orders(self) -> List:
        """
        Retrieves all open futures orders.
        """
        await self._init_client()
        assert self.client is not None
        try:
            orders = await self.client.futures_get_open_orders()
            return orders if isinstance(orders, list) else [orders]
        except BinanceAPIException as e:
            logger.error(f"Failed to get open futures orders: {e}")
            return []
        except Exception as e:
            logger.error(f"An unexpected error occurred while fetching open futures orders: {e}")
            return []

    async def get_futures_position_information(self) -> List:
        """
        Retrieves information about futures positions.
        """
        await self._init_client()
        assert self.client is not None
        try:
            positions = await self.client.futures_position_information()
            return positions if isinstance(positions, list) else [positions]
        except BinanceAPIException as e:
            logger.error(f"Failed to get futures position information: {e}")
            return []
        except Exception as e:
            logger.error(f"An unexpected error occurred while fetching position information: {e}")
            return []

    async def get_spot_symbol_filters(self, symbol: str) -> Optional[Dict]:
        """
        Retrieves all filters for a given spot symbol.
        """
        await self._init_client()
        assert self.client is not None
        try:
            exchange_info = await self.client.get_exchange_info()
            for s in exchange_info['symbols']:
                if s['symbol'] == symbol:
                    # Return a dictionary of filters keyed by filterType
                    return {f['filterType']: f for f in s['filters']}
            return None
        except Exception as e:
            logger.error(f"Could not retrieve spot filters for {symbol}: {e}")
            return None

    async def get_futures_symbol_filters(self, symbol: str) -> Optional[Dict]:
        """
        Retrieves all filters for a given futures symbol.
        """
        await self._init_client()
        assert self.client is not None
        try:
            exchange_info = await self.client.futures_exchange_info()
            for s in exchange_info['symbols']:
                if s['symbol'] == symbol:
                    # Return a dictionary of filters keyed by filterType
                    return {f['filterType']: f for f in s['filters']}
            return None
        except Exception as e:
            logger.error(f"Could not retrieve precision filters for {symbol}: {e}")
            return None

    async def is_futures_symbol_supported(self, symbol: str) -> bool:
        """
        Check if a symbol is supported for futures trading.
        """
        await self._init_client()
        assert self.client is not None
        try:
            exchange_info = await self.client.futures_exchange_info()
            for s in exchange_info['symbols']:
                if s['symbol'] == symbol and s['status'] == 'TRADING':
                    return True
            return False
        except Exception as e:
            logger.error(f"Error checking futures symbol support for {symbol}: {e}")
            return False

    async def close(self):
        """Close the exchange connection."""
        await self.close_client()