import logging
from typing import Dict, Optional
from binance.client import Client
from binance.exceptions import BinanceAPIException
from config import settings as config
from binance.enums import *

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

class BinanceExchange:
    def __init__(self, api_key: str, api_secret: str, is_testnet: bool = False):
        """Initialize Binance exchange client."""
        self.api_key = api_key
        self.api_secret = api_secret
        # Explicitly set tld to 'com' to ensure connection to the global Binance platform
        self.client = Client(self.api_key, self.api_secret, testnet=is_testnet, tld='com')
        self._futures_exchange_info_cache = None
        logger.info(f"BinanceExchange initialized for testnet: {is_testnet}")

    async def get_spot_balance(self) -> Dict[str, float]:
        """
        Get account balances for all assets.

        Returns:
            Dictionary with asset symbols as keys and free balances as values.
        """
        try:
            account = self.client.get_account()
            balances = {}

            for asset in account['balances']:
                free = float(asset['free'])
                if free > 0:  # Only include non-zero balances
                    balances[asset['asset'].lower()] = free

            return balances
        except BinanceAPIException as e:
            logger.error(f"Failed to get Binance balances: {e}")
            return {}

    async def get_futures_balance(self) -> Dict[str, float]:
        """
        Get futures account balances. It tries USDⓈ-M futures first,
        and falls back to COIN-M futures if a specific permissions error occurs.
        """
        try:
            # First, try to get USDⓈ-M futures balance (most common)
            logger.info("Attempting to fetch USDⓈ-M futures balance...")
            balances_list = self.client.futures_account_balance()
            logger.info("Successfully fetched USDⓈ-M futures balance.")

            balances = {}
            for asset in balances_list:
                bal = float(asset['availableBalance'])
                if bal > 0:
                    balances[asset['asset'].lower()] = bal
            return balances

        except BinanceAPIException as e:
            # Check for the specific authentication error
            if e.code == -2015:
                logger.warning("Failed to get USDⓈ-M futures balance with APIError -2015. Attempting to fetch COIN-M futures balance as a fallback...")
                try:
                    # Fallback to COIN-M futures balance
                    balances_list = self.client.futures_coin_account_balance()
                    logger.info("Successfully fetched COIN-M futures balance.")

                    balances = {}
                    for asset in balances_list:
                        bal = float(asset['availableBalance'])
                        if bal > 0:
                            balances[asset['asset'].lower()] = bal
                    return balances
                except BinanceAPIException as e2:
                    logger.error(f"Fallback to COIN-M futures also failed: {e2}")
                    return {}
            else:
                # Handle other potential API errors
                logger.error(f"Failed to get Binance futures balances: {e}")
                return {}
        except Exception as e:
            logger.error(f"An unexpected error occurred while fetching futures balances: {e}")
            return {}

    async def get_pair_info(self, symbol: str) -> Optional[Dict]:
        """
        Get trading pair information for SPOT trading.

        Args:
            symbol: Trading pair symbol (e.g., 'BTCUSDT')

        Returns:
            Dictionary with pair information or None if not found
        """
        try:
            # Convert symbol format if needed (e.g., btc_usd -> BTCUSDT)
            formatted_symbol = symbol.replace('_', '').upper()

            # Get exchange info for the symbol
            exchange_info = self.client.get_exchange_info()
            for s in exchange_info['symbols']:
                if s['symbol'] == formatted_symbol:
                    return {
                        'symbol': s['symbol'],
                        'baseAsset': s['baseAsset'],
                        'quoteAsset': s['quoteAsset'],
                        'status': s['status'],
                        'filters': s['filters']
                    }
            return None
        except BinanceAPIException as e:
            logger.error(f"Failed to get spot pair info for {symbol}: {e}")
            return None

    async def get_futures_pair_info(self, symbol: str) -> Optional[Dict]:
        """
        Get trading pair information for FUTURES trading.

        Args:
            symbol: Trading pair symbol (e.g., 'BTCUSDT')

        Returns:
            Dictionary with pair information or None if not found
        """
        try:
            # Convert symbol format if needed (e.g., btc_usd -> BTCUSDT)
            formatted_symbol = symbol.replace('_', '').upper()

            # Get futures exchange info for the symbol
            exchange_info = self.client.futures_exchange_info()
            for s in exchange_info['symbols']:
                if s['symbol'] == formatted_symbol:
                    return {
                        'symbol': s['symbol'],
                        'baseAsset': s['baseAsset'],
                        'quoteAsset': s['quoteAsset'],
                        'status': s['status'],
                        'filters': s['filters']
                    }
            return None
        except BinanceAPIException as e:
            logger.error(f"Failed to get futures pair info for {symbol}: {e}")
            return None

    async def is_futures_symbol_supported(self, symbol: str) -> bool:
        """
        Check if a symbol is supported for futures trading.

        Args:
            symbol: Trading pair symbol (e.g., 'BTCUSDT' or 'btc_usdt')

        Returns:
            True if symbol is supported for futures trading, False otherwise
        """
        pair_info = await self.get_futures_pair_info(symbol)
        return pair_info is not None and pair_info.get('status') == 'TRADING'

    def _get_futures_quantity_precision(self, symbol: str) -> int:
        """
        Get quantity precision for a futures symbol by fetching exchange info.
        """
        try:
            # Fetch and cache exchange info on first call
            if self._futures_exchange_info_cache is None:
                logger.info("Fetching futures exchange info for precision rules...")
                self._futures_exchange_info_cache = self.client.futures_exchange_info()

            formatted_symbol = symbol.replace('_', '').upper()

            for s in self._futures_exchange_info_cache['symbols']:
                if s['symbol'] == formatted_symbol:
                    return s['quantityPrecision']

            logger.warning(f"Could not find dynamic futures quantity precision for {symbol}. Using default of 2.")
            return 2
        except Exception as e:
            logger.error(f"Error fetching futures quantity precision for {symbol}: {e}. Using default of 2.")
            return 2

    def _get_futures_price_precision(self, symbol: str) -> int:
        """
        Get price precision for a futures symbol by fetching exchange info.
        """
        try:
            # Fetch and cache exchange info on first call
            if self._futures_exchange_info_cache is None:
                logger.info("Fetching futures exchange info for precision rules...")
                self._futures_exchange_info_cache = self.client.futures_exchange_info()

            formatted_symbol = symbol.replace('_', '').upper()

            for s in self._futures_exchange_info_cache['symbols']:
                if s['symbol'] == formatted_symbol:
                    return s['pricePrecision']

            logger.warning(f"Could not find dynamic futures price precision for {symbol}. Using default of 2.")
            return 2
        except Exception as e:
            logger.error(f"Error fetching futures price precision for {symbol}: {e}. Using default of 2.")
            return 2

    def _round_futures_quantity(self, symbol: str, quantity: float) -> float:
        """
        Round quantity to correct precision for futures trading.

        Args:
            symbol: Trading pair symbol
            quantity: Quantity to round

        Returns:
            Properly rounded quantity
        """
        precision = self._get_futures_quantity_precision(symbol)
        return round(quantity, precision)

    def _round_futures_price(self, symbol: str, price: float) -> float:
        """
        Round price to correct precision for futures trading.

        Args:
            symbol: Trading pair symbol
            price: Price to round

        Returns:
            Properly rounded price
        """
        precision = self._get_futures_price_precision(symbol)
        return round(price, precision)

    def _validate_futures_symbol(self, symbol: str) -> bool:
        """
        Validate if a symbol is available for futures trading using whitelist.

        Args:
            symbol: Trading pair symbol (e.g., 'BTCUSDT' or 'btc_usdt')

        Returns:
            True if symbol is in whitelist, False otherwise
        """
        if not WHITELIST_AVAILABLE:
            return True  # Allow all symbols if whitelist is not available

        formatted_symbol = symbol.replace('_', '').upper()
        return is_symbol_supported(formatted_symbol)

    async def create_order(
        self,
        pair: str,
        side: str,
        order_type_market: str,
        amount: float,
        price: Optional[float] = None,
        stop_price: Optional[float] = None
    ) -> Dict:
        """
        Create a new order on Binance Spot.

        Args:
            pair: Trading pair symbol (e.g., 'btc_usdt')
            side: SIDE_BUY or SIDE_SELL
            order_type_market: e.g., ORDER_TYPE_MARKET, ORDER_TYPE_LIMIT
            amount: Amount of the asset to trade
            price: Price for the order (required for limit orders)
            stop_price: Price for stop orders

        Returns:
            Dictionary with order details, or error information.
        """
        try:
            formatted_pair = pair.replace('_', '').upper()

            # Get symbol info for precision
            symbol_info = await self.get_pair_info(pair)
            if not symbol_info:
                err_msg = f"Could not get symbol info for {pair}"
                logger.error(err_msg)
                return {'code': -1, 'message': err_msg}

            # Find quantity precision from filters
            quantity_precision = 8  # Default precision
            for f in symbol_info['filters']:
                if f['filterType'] == 'LOT_SIZE':
                    step_size_str = f['stepSize'].rstrip('0')
                    if '.' in step_size_str:
                        quantity_precision = len(step_size_str.split('.')[1])
                    else:
                        quantity_precision = 0 # Whole numbers
                    break

            # Round amount to correct precision
            rounded_amount = round(amount, quantity_precision)

            params = {
                "symbol": formatted_pair,
                "side": side,
                "type": order_type_market,
                "quantity": rounded_amount,
            }

            if order_type_market == ORDER_TYPE_LIMIT:
                if not price:
                    raise ValueError("Price is required for LIMIT orders")
                params["price"] = price
                params["timeInForce"] = TIME_IN_FORCE_GTC

            if stop_price:
                 params["stopPrice"] = stop_price

            order = self.client.create_order(**params)
            logger.info(f"Successfully created spot order: {order}")
            return order
        except BinanceAPIException as e:
            logger.error(f"Failed to create spot order for {pair}: {e}")
            return {'code': e.code, 'message': e.message}
        except Exception as e:
            logger.error(f"An unexpected error occurred during spot order creation: {e}")
            return {'code': -1, 'message': str(e)}

    async def get_order_status(self, pair: str, order_id: str) -> Optional[Dict]:
        """
        Get the status of an order.

        Args:
            pair: Trading pair (e.g., 'BTCUSDT')
            order_id: Order ID

        Returns:
            Order status dictionary or None if failed
        """
        try:
            formatted_pair = pair.replace('_', '').upper()
            order = self.client.get_order(
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
        try:
            formatted_pair = pair.replace('_', '').upper()
            result = self.client.cancel_order(
                symbol=formatted_pair,
                orderId=order_id
            )
            logger.info(f"Order cancelled successfully: {result}")
            return True
        except BinanceAPIException as e:
            logger.error(f"Failed to cancel order: {e}")
            return False

    async def create_futures_order(
        self,
        pair: str,
        side: str,
        order_type_market: str,
        amount: float,
        price: Optional[float] = None,
        stop_price: Optional[float] = None,
        leverage: int = 1
    ) -> Dict:
        """
        Create a new order on Binance Futures.

        Args:
            pair: Trading pair symbol (e.g., 'btc_usdt')
            side: SIDE_BUY or SIDE_SELL
            order_type_market: e.g., ORDER_TYPE_MARKET, STOP_MARKET
            amount: Amount of the asset to trade
            price: Price for the order (required for limit orders)
            stop_price: Price for stop orders
            leverage: Desired leverage

        Returns:
            Dictionary with order details, or error information.
        """
        try:
            formatted_pair = pair.replace('_', '').upper()

            # Pre-validate symbol (optional but recommended)
            if not self._validate_futures_symbol(formatted_pair):
                # If validation fails, we can still try to place the order
                # Binance will reject it if truly invalid
                logger.warning(f"Symbol {formatted_pair} not in whitelist, proceeding with order attempt...")

            # Set leverage
            try:
                self.client.futures_change_leverage(symbol=formatted_pair, leverage=leverage)
            except BinanceAPIException as e:
                # Leverage change can fail if position already exists; log as warning
                logger.warning(f"Could not set leverage for {formatted_pair} to {leverage}: {e}")

            # Round quantity and price based on precision rules
            quantity = self._round_futures_quantity(formatted_pair, amount)
            # For market orders, price is not needed, but if a limit order were used:
            # order_price = self._round_futures_price(formatted_pair, price) if price else None

            params = {
                "symbol": formatted_pair,
                "side": side,
                "type": order_type_market,
                "quantity": quantity,
            }

            if stop_price:
                params["stopPrice"] = stop_price
                # For STOP_MARKET orders, you shouldn't send a price
                # For STOP (limit) orders, you would send a price
                # We are focusing on STOP_MARKET for simplicity
                params["closePosition"] = True # To ensure it closes the position

            # Create order
            order = self.client.futures_create_order(**params)

            logger.info(f"Successfully created futures order: {order}")
            return order
        except BinanceAPIException as e:
            logger.error(f"Failed to create futures order for {pair}: {e}")
            return {'code': e.code, 'message': e.message}
        except Exception as e:
            logger.error(f"An unexpected error occurred during futures order creation: {e}")
            return {'code': -1, 'message': str(e)}

    async def cancel_futures_order(self, pair: str, order_id: str) -> bool:
        """
        Cancel an existing futures order.

        Args:
            pair: Trading pair (e.g., 'BTCUSDT' or 'btc_usdt')
            order_id: Order ID

        Returns:
            True if successful, False otherwise
        """
        try:
            formatted_pair = pair.replace('_', '').upper()
            result = self.client.futures_cancel_order(
                symbol=formatted_pair,
                orderId=order_id
            )
            logger.info(f"Futures order cancelled successfully: {result}")
            return True
        except BinanceAPIException as e:
            logger.error(f"Failed to cancel futures order: {e}")
            return False

    async def close(self):
        """Close the exchange connection."""
        # Binance client doesn't require explicit closing
        pass