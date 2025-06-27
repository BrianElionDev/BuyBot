import logging
from typing import Dict, Optional
from binance.client import Client
from binance.exceptions import BinanceAPIException
from config import settings as config
from binance.enums import *

logger = logging.getLogger(__name__)

class BinanceExchange:
    def __init__(self, api_key: str, api_secret: str, is_testnet: bool = False):
        """Initialize Binance exchange client."""
        self.api_key = api_key
        self.api_secret = api_secret
        # Explicitly set tld to 'com' to ensure connection to the global Binance platform
        self.client = Client(self.api_key, self.api_secret, testnet=is_testnet, tld='com')
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
        Get trading pair information.

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
            logger.error(f"Failed to get pair info for {symbol}: {e}")
            return None

    async def create_order(
        self,
        pair: str,
        order_type: str,
        amount: float,
        price: Optional[float] = None
    ) -> Optional[Dict]:
        """
        Create a new order.

        Args:
            pair: Trading pair (e.g., 'BTCUSDT')
            order_type: 'buy' or 'sell'
            amount: Order amount
            price: Price for limit orders (optional)

        Returns:
            Order information dictionary or None if failed
        """
        try:
            # Convert pair format (e.g., btc_usd -> BTCUSDT)
            formatted_pair = pair.replace('_', '').upper()

            # Convert order type to Binance format
            side = Client.SIDE_BUY if order_type.lower() == 'buy' else Client.SIDE_SELL

            # Get symbol info for precision
            symbol_info = await self.get_pair_info(pair)
            if not symbol_info:
                logger.error(f"Could not get symbol info for {pair}")
                return None

            # Find quantity precision from filters
            quantity_precision = 8  # Default precision
            for f in symbol_info['filters']:
                if f['filterType'] == 'LOT_SIZE':
                    step_size = float(f['stepSize'])
                    quantity_precision = len(str(step_size).rstrip('0').split('.')[-1])
                    break

            # Round amount to correct precision
            amount = round(amount, quantity_precision)

            if price:
                # Place limit order
                order = self.client.create_order(
                    symbol=formatted_pair,
                    side=side,
                    type=Client.ORDER_TYPE_LIMIT,
                    timeInForce=Client.TIME_IN_FORCE_GTC,
                    quantity=amount,
                    price=price
                )
            else:
                # Place market order
                order = self.client.create_order(
                    symbol=formatted_pair,
                    side=side,
                    type=Client.ORDER_TYPE_MARKET,
                    quantity=amount
                )

            logger.info(f"Order placed successfully: {order}")
            return order

        except BinanceAPIException as e:
            logger.error(f"Failed to create order: {e}")
            return None

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
        order_type: str,
        amount: float,
        price: Optional[float] = None,
        leverage: int = 1
    ) -> Optional[Dict]:
        """
        Create a new futures order.
        Args:
            pair: Trading pair (e.g., 'BTCUSDT')
            order_type: 'buy' or 'sell'
            amount: Order amount
            price: Price for limit orders (optional)
            leverage: The leverage to use for the order
        Returns:
            Order information dictionary or None if failed
        """
        try:
            # Set leverage
            self.client.futures_change_leverage(symbol=pair, leverage=leverage)

            # Convert pair format (e.g., btc_usd -> BTCUSDT)
            formatted_pair = pair.replace('_', '').upper()

            # Convert order type to Binance format
            side = Client.SIDE_BUY if order_type.lower() == 'buy' else Client.SIDE_SELL

            if price:
                # Place limit order
                order = self.client.futures_create_order(
                    symbol=formatted_pair,
                    side=side,
                    type=Client.ORDER_TYPE_LIMIT,
                    timeInForce=Client.TIME_IN_FORCE_GTC,
                    quantity=amount,
                    price=price
                )
            else:
                # Place market order
                order = self.client.futures_create_order(
                    symbol=formatted_pair,
                    side=side,
                    type=Client.ORDER_TYPE_MARKET,
                    quantity=amount
                )

            logger.info(f"Futures order placed successfully: {order}")
            return order

        except BinanceAPIException as e:
            logger.error(f"Failed to create futures order: {e}")
            return None

    async def close(self):
        """Close the exchange connection."""
        # Binance client doesn't require explicit closing
        pass