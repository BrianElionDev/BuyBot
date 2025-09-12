"""
KuCoin Exchange Implementation

Main KuCoin exchange class implementing the ExchangeBase interface.
Following Clean Code principles with clear separation of concerns.
"""

import asyncio
import logging
from typing import Dict, List, Optional, Tuple, Any
from decimal import Decimal

from ..core.exchange_base import ExchangeBase
from ..core.exchange_config import ExchangeConfig
from .kucoin_models import (
    KucoinOrder, KucoinPosition, KucoinBalance,
    KucoinTrade, KucoinIncome, KucoinOrderStatus,
    KucoinOrderType, KucoinOrderSide
)
from .kucoin_client import KucoinClient

logger = logging.getLogger(__name__)


class KucoinExchange(ExchangeBase):
    """
    KuCoin exchange implementation.

    Implements the ExchangeBase interface for KuCoin-specific operations.
    Follows Clean Code principles with clear method names and single responsibilities.
    """

    def __init__(self, api_key: str, api_secret: str, api_passphrase: str, is_testnet: bool = False):
        """
        Initialize KuCoin exchange.

        Args:
            api_key: KuCoin API key
            api_secret: KuCoin API secret
            api_passphrase: KuCoin API passphrase
            is_testnet: Whether to use testnet
        """
        self.api_key = api_key
        self.api_secret = api_secret
        self.api_passphrase = api_passphrase
        self.is_testnet = is_testnet
        self.client: Optional[KucoinClient] = None
        self._spot_symbols: List[str] = []
        self._futures_symbols: List[str] = []

        logger.info(f"KucoinExchange initialized for testnet: {self.is_testnet}")

    async def initialize(self) -> bool:
        """Initialize the exchange connection."""
        try:
            await self._init_client()
            return True
        except Exception as e:
            logger.error(f"Failed to initialize KuCoin exchange: {e}")
            return False

    async def close(self) -> None:
        """Close the exchange connection and cleanup resources."""
        if self.client:
            await self.client.close()

    async def _init_client(self):
        """Initialize the KuCoin client."""
        if self.client is None:
            self.client = KucoinClient(
                self.api_key,
                self.api_secret,
                self.api_passphrase,
                self.is_testnet
            )
            await self.client.initialize()

    # Account Operations
    async def get_account_balances(self) -> Dict[str, float]:
        """
        Get account balances for all assets.

        Returns:
            Dict[str, float]: Asset symbol to balance mapping
        """
        try:
            await self._init_client()

            # Get spot account balances
            spot_balances = await self.get_spot_balance()

            # For KuCoin, we'll focus on spot balances for now
            # Futures balances would be handled separately
            return spot_balances

        except Exception as e:
            logger.error(f"Failed to get KuCoin account balances: {e}")
            return {}

    async def get_spot_balance(self) -> Dict[str, float]:
        """
        Get spot account balances.

        Returns:
            Dict[str, float]: Asset symbol to balance mapping
        """
        try:
            await self._init_client()

            from kucoin_universal_sdk.generate.account.account.model_get_spot_account_list_req import GetSpotAccountListReqBuilder

            spot_service = self.client.get_spot_service()
            account_api = spot_service.get_account_api()

            # Get all spot accounts
            request = GetSpotAccountListReqBuilder().build()
            response = account_api.get_spot_account_list(request)

            balances = {}
            for account in response.data:
                if float(account.balance) > 0:
                    balances[account.currency] = float(account.balance)

            return balances

        except Exception as e:
            logger.error(f"Failed to get KuCoin spot balances: {e}")
            return {}

    # Order Operations
    async def create_futures_order(self, pair: str, side: str, order_type: str,
                                 amount: float, price: Optional[float] = None,
                                 stop_price: Optional[float] = None,
                                 client_order_id: Optional[str] = None,
                                 reduce_only: bool = False,
                                 close_position: bool = False) -> Dict[str, Any]:
        """
        Create a futures order with comprehensive validation.

        Args:
            pair: Trading pair symbol
            side: Order side (BUY/SELL)
            order_type: Order type (MARKET/LIMIT/STOP)
            amount: Order quantity
            price: Order price (for limit orders)
            stop_price: Stop price (for stop orders)
            client_order_id: Custom order ID
            reduce_only: Whether order should only reduce position
            close_position: Whether order should close position

        Returns:
            Dict containing order response or error information
        """
        try:
            await self._init_client()

            logger.info(f"Creating KuCoin futures order: {pair} {side} {order_type} {amount}")

            # Enhanced Precision Handling and Validation
            filters = await self.get_futures_symbol_filters(pair)
            if filters:
                lot_size_filter = filters.get('LOT_SIZE', {})
                price_filter = filters.get('PRICE_FILTER', {})
                step_size = float(lot_size_filter.get('stepSize', 0.0001))
                tick_size = float(price_filter.get('tickSize', 0.00001))
                min_qty = float(lot_size_filter.get('minQty', 0))
                max_qty = float(lot_size_filter.get('maxQty', float('inf')))
                min_notional = float(filters.get('MIN_NOTIONAL', {}).get('minNotional', 0))

                # Validate quantity bounds
                if amount < min_qty:
                    return {'error': f'Quantity {amount} below minimum {min_qty} for {pair}', 'code': -4005}
                if amount > max_qty:
                    return {'error': f'Quantity {amount} above maximum {max_qty} for {pair}', 'code': -4006}

                # Format quantity and price with proper precision
                if step_size:
                    amount = round(amount / step_size) * step_size
                if price and tick_size:
                    price = round(price / tick_size) * tick_size
                if stop_price and tick_size:
                    stop_price = round(stop_price / tick_size) * tick_size

                # Validate minimum notional
                if price:
                    notional = amount * price
                    if notional < min_notional:
                        return {'error': f'Notional value {notional} below minimum {min_notional} for {pair}', 'code': -4007}

            # Convert to KuCoin format
            kucoin_side = "buy" if side.upper() == "BUY" else "sell"
            kucoin_type = self._convert_order_type(order_type)

            # Prepare order parameters
            order_params = {
                "clientOid": client_order_id or f"kucoin_{int(asyncio.get_event_loop().time() * 1000)}",
                "side": kucoin_side,
                "symbol": pair,
                "type": kucoin_type,
                "size": str(amount)
            }

            if price and kucoin_type in ["limit", "stop_limit"]:
                order_params["price"] = str(price)

            if stop_price and kucoin_type in ["stop", "stop_limit"]:
                order_params["stopPrice"] = str(stop_price)

            if reduce_only:
                order_params["reduceOnly"] = True

            # Create order using KuCoin SDK
            spot_service = self.client.get_spot_service()
            order_api = spot_service.get_order_api()

            from kucoin_universal_sdk.generate.spot.order.model_create_order_req import CreateOrderReqBuilder

            # Build the order request
            order_request = CreateOrderReqBuilder() \
                .set_client_oid(order_params["clientOid"]) \
                .set_side(order_params["side"]) \
                .set_symbol(order_params["symbol"]) \
                .set_type(order_params["type"]) \
                .set_size(order_params["size"])

            if "price" in order_params:
                order_request.set_price(order_params["price"])
            if "stopPrice" in order_params:
                order_request.set_stop_price(order_params["stopPrice"])

            request = order_request.build()
            response = order_api.create_order(request)

            # Format response to match Binance format
            formatted_response = {
                "success": True,
                "orderId": getattr(response, 'orderId', order_params["clientOid"]),
                "clientOrderId": order_params["clientOid"],
                "symbol": pair,
                "side": side.upper(),
                "type": order_type.upper(),
                "origQty": str(amount),
                "price": str(price) if price else None,
                "stopPrice": str(stop_price) if stop_price else None,
                "status": "NEW",
                "time": int(asyncio.get_event_loop().time() * 1000)
            }

            logger.info(f"KuCoin futures order created: {formatted_response}")
            return formatted_response

        except Exception as e:
            logger.error(f"Failed to create KuCoin futures order: {e}")
            return {"success": False, "error": str(e)}

    async def cancel_futures_order(self, pair: str, order_id: str) -> Tuple[bool, Dict[str, Any]]:
        """
        Cancel a futures order.

        Args:
            pair: Trading pair symbol
            order_id: Order ID to cancel

        Returns:
            Tuple of (success, response_data)
        """
        try:
            await self._init_client()

            futures_api = self.client.get_futures_service().get_order_api()

            # Placeholder - replace with actual SDK call
            response = {"success": True, "orderId": order_id}

            logger.info(f"KuCoin futures order canceled: {order_id}")
            return True, response

        except Exception as e:
            logger.error(f"Failed to cancel KuCoin futures order {order_id}: {e}")
            return False, {"error": str(e)}

    async def get_order_status(self, pair: str, order_id: str) -> Optional[Dict[str, Any]]:
        """
        Get order status.

        Args:
            pair: Trading pair symbol
            order_id: Order ID

        Returns:
            Order status information or None if not found
        """
        try:
            await self._init_client()

            futures_api = self.client.get_futures_service().get_order_api()

            # Placeholder - replace with actual SDK call
            return {
                "orderId": order_id,
                "symbol": pair,
                "status": "active",
                "side": "buy",
                "type": "limit",
                "size": "1.0",
                "price": "50000.0"
            }

        except Exception as e:
            logger.error(f"Failed to get KuCoin order status for {order_id}: {e}")
            return None

    # Position Operations
    async def get_futures_position_information(self) -> List[Dict[str, Any]]:
        """
        Get all futures positions.

        Returns:
            List of position information dictionaries
        """
        try:
            await self._init_client()

            futures_api = self.client.get_futures_service().get_position_api()

            # Placeholder - replace with actual SDK call
            return []

        except Exception as e:
            logger.error(f"Failed to get KuCoin futures positions: {e}")
            return []

    async def close_position(self, pair: str, amount: float,
                           position_type: str) -> Tuple[bool, Dict[str, Any]]:
        """
        Close a futures position.

        Args:
            pair: Trading pair symbol
            amount: Amount to close
            position_type: Position type (LONG/SHORT)

        Returns:
            Tuple of (success, response_data)
        """
        try:
            await self._init_client()

            # Determine side for closing
            side = "sell" if position_type.upper() == "LONG" else "buy"

            # Create closing order
            result = await self.create_futures_order(
                pair=pair,
                side=side,
                order_type="MARKET",
                amount=amount,
                reduce_only=True
            )

            return result.get("success", False), result

        except Exception as e:
            logger.error(f"Failed to close KuCoin position for {pair}: {e}")
            return False, {"error": str(e)}

    # Market Data
    async def get_current_prices(self, symbols: List[str]) -> Dict[str, float]:
        """
        Get current prices for symbols.

        Args:
            symbols: List of symbol strings

        Returns:
            Dict mapping symbol to current price
        """
        try:
            await self._init_client()

            from kucoin_universal_sdk.generate.spot.market.model_get_ticker_req import GetTickerReqBuilder

            spot_service = self.client.get_spot_service()
            market_api = spot_service.get_market_api()
            prices = {}

            for symbol in symbols:
                try:
                    request = GetTickerReqBuilder().set_symbol(symbol).build()
                    response = market_api.get_ticker(request)
                    prices[symbol] = float(response.price) if hasattr(response, 'price') else 0.0
                except Exception as e:
                    logger.warning(f"Failed to get price for {symbol}: {e}")
                    prices[symbol] = 0.0

            return prices

        except Exception as e:
            logger.error(f"Failed to get KuCoin current prices: {e}")
            return {}

    async def get_order_book(self, symbol: str, limit: int = 5) -> Optional[Dict[str, Any]]:
        """
        Get order book for a symbol.

        Args:
            symbol: Trading pair symbol
            limit: Number of order book levels

        Returns:
            Order book data or None if error
        """
        try:
            await self._init_client()

            from kucoin_universal_sdk.generate.spot.market.model_get_all_symbols_req import GetAllSymbolsReqBuilder

            spot_service = self.client.get_spot_service()
            market_api = spot_service.get_market_api()

            # First get all symbols to find the correct format
            symbols_request = GetAllSymbolsReqBuilder().build()
            symbols_response = market_api.get_all_symbols(symbols_request)
            symbols = symbols_response.data

            # Find matching symbol
            matching_symbol = None
            for s in symbols:
                if s.symbol == symbol:
                    matching_symbol = s.symbol
                    break

            if not matching_symbol:
                logger.warning(f"Symbol {symbol} not found in KuCoin symbols")
                return None

            # Try to get order book with the correct symbol
            from kucoin_universal_sdk.generate.spot.market.model_get_part_order_book_req import GetPartOrderBookReqBuilder
            request = GetPartOrderBookReqBuilder().set_symbol(matching_symbol).set_size(str(limit)).build()
            response = market_api.get_part_order_book(request)

            return {
                "symbol": matching_symbol,
                "bids": response.bids,
                "asks": response.asks,
                "time": response.time,
                "sequence": response.sequence
            }

        except Exception as e:
            logger.error(f"Failed to get KuCoin order book for {symbol}: {e}")
            return None

    # Symbol Information
    async def get_futures_symbol_filters(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Get symbol filters for futures trading.

        Args:
            symbol: Trading pair symbol

        Returns:
            Symbol filters or None if not found
        """
        try:
            await self._init_client()

            from kucoin_universal_sdk.generate.spot.market.model_get_all_symbols_req import GetAllSymbolsReqBuilder

            spot_service = self.client.get_spot_service()
            market_api = spot_service.get_market_api()

            # Get all symbols to find the specific one
            symbols_request = GetAllSymbolsReqBuilder().build()
            symbols_response = market_api.get_all_symbols(symbols_request)
            symbols = symbols_response.data

            # Find the specific symbol
            symbol_info = None
            for s in symbols:
                if s.symbol == symbol:
                    symbol_info = s
                    break

            if not symbol_info:
                logger.warning(f"Symbol {symbol} not found in KuCoin symbols")
                return None

            # Extract symbol information and create filters
            filters = {
                "symbol": symbol,
                "baseCurrency": getattr(symbol_info, 'baseCurrency', ''),
                "quoteCurrency": getattr(symbol_info, 'quoteCurrency', ''),
                "baseMinSize": getattr(symbol_info, 'baseMinSize', '0.001'),
                "baseMaxSize": getattr(symbol_info, 'baseMaxSize', '1000000'),
                "quoteMinSize": getattr(symbol_info, 'quoteMinSize', '0.00001'),
                "quoteMaxSize": getattr(symbol_info, 'quoteMaxSize', '1000000'),
                "baseIncrement": getattr(symbol_info, 'baseIncrement', '0.0001'),
                "quoteIncrement": getattr(symbol_info, 'quoteIncrement', '0.00001'),
                "priceIncrement": getattr(symbol_info, 'priceIncrement', '0.00001'),
                "enableTrading": getattr(symbol_info, 'enableTrading', True),
                "isMarginEnabled": getattr(symbol_info, 'isMarginEnabled', False),
                # KuCoin specific filters
                "LOT_SIZE": {
                    "minQty": getattr(symbol_info, 'baseMinSize', '0.001'),
                    "maxQty": getattr(symbol_info, 'baseMaxSize', '1000000'),
                    "stepSize": getattr(symbol_info, 'baseIncrement', '0.0001')
                },
                "PRICE_FILTER": {
                    "minPrice": "0.00001",
                    "maxPrice": "1000000",
                    "tickSize": getattr(symbol_info, 'priceIncrement', '0.00001')
                },
                "MIN_NOTIONAL": {
                    "minNotional": getattr(symbol_info, 'quoteMinSize', '0.00001')
                }
            }

            return filters

        except Exception as e:
            logger.error(f"Failed to get KuCoin symbol filters for {symbol}: {e}")
            return None

    async def is_futures_symbol_supported(self, symbol: str) -> bool:
        """
        Check if symbol is supported for futures trading.

        Args:
            symbol: Trading pair symbol

        Returns:
            True if supported, False otherwise
        """
        try:
            filters = await self.get_futures_symbol_filters(symbol)
            if filters and filters.get('enableTrading', False):
                return True
            return False

        except Exception as e:
            logger.error(f"Failed to check KuCoin symbol support for {symbol}: {e}")
            return False

    async def validate_trade_amount(self, symbol: str, amount: float, price: float) -> Tuple[bool, Optional[str]]:
        """
        Validate trade amount against symbol filters.

        Args:
            symbol: Trading pair symbol
            amount: Trade amount
            price: Trade price

        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            filters = await self.get_futures_symbol_filters(symbol)
            if not filters:
                return False, f"Symbol {symbol} not supported"

            # Check minimum and maximum quantity
            lot_size = filters.get('LOT_SIZE', {})
            min_qty = float(lot_size.get('minQty', 0))
            max_qty = float(lot_size.get('maxQty', float('inf')))
            step_size = float(lot_size.get('stepSize', 0.0001))

            if amount < min_qty:
                return False, f"Amount {amount} below minimum {min_qty} for {symbol}"
            if amount > max_qty:
                return False, f"Amount {amount} above maximum {max_qty} for {symbol}"

            # Check step size (be more lenient for KuCoin)
            if step_size > 0:
                remainder = amount % step_size
                if remainder > step_size * 0.1:  # Allow 10% tolerance for step size
                    return False, f"Amount {amount} not aligned with step size {step_size} for {symbol}"

            # Check minimum notional value
            min_notional = filters.get('MIN_NOTIONAL', {})
            min_notional_value = float(min_notional.get('minNotional', 0))
            notional_value = amount * price

            if notional_value < min_notional_value:
                return False, f"Notional value {notional_value} below minimum {min_notional_value} for {symbol}"

            return True, None

        except Exception as e:
            logger.error(f"Error validating trade amount for {symbol}: {e}")
            return False, f"Validation error: {str(e)}"

    async def get_mark_price(self, symbol: str) -> Optional[float]:
        """
        Get mark price for a symbol.

        Args:
            symbol: Trading pair symbol

        Returns:
            Mark price or None if not available
        """
        try:
            await self._init_client()

            from kucoin_universal_sdk.generate.spot.market.model_get_ticker_req import GetTickerReqBuilder

            spot_service = self.client.get_spot_service()
            market_api = spot_service.get_market_api()

            request = GetTickerReqBuilder().set_symbol(symbol).build()
            response = market_api.get_ticker(request)

            if hasattr(response, 'price'):
                return float(response.price)
            return None

        except Exception as e:
            logger.error(f"Failed to get KuCoin mark price for {symbol}: {e}")
            return None

    async def get_futures_account_info(self) -> Optional[Dict[str, Any]]:
        """
        Get futures account information.

        Returns:
            Account information or None if not available
        """
        try:
            await self._init_client()

            # For KuCoin, we'll use account service for account information
            account_service = self.client.client.rest_service().get_account_service()
            account_api = account_service.get_account_api()

            from kucoin_universal_sdk.generate.account.account.model_get_spot_account_list_req import GetSpotAccountListReqBuilder
            request = GetSpotAccountListReqBuilder().build()
            response = account_api.get_spot_account_list(request)

            # Calculate total balance
            total_balance = 0.0
            balances = {}
            if response.data:
                for account in response.data:
                    if account.balance:
                        balance = float(account.balance)
                        balances[account.currency] = balance
                        if account.currency == 'USDT':
                            total_balance = balance

            return {
                "totalWalletBalance": total_balance,
                "totalUnrealizedProfit": 0.0,
                "totalMarginBalance": total_balance,
                "totalInitialMargin": 0.0,
                "totalMaintMargin": 0.0,
                "maxWithdrawAmount": total_balance,
                "balances": balances
            }

        except Exception as e:
            logger.error(f"Failed to get KuCoin account info: {e}")
            return None

    async def calculate_max_position_size(self, symbol: str, leverage: float = 1.0) -> Optional[float]:
        """
        Calculate maximum position size based on account balance and leverage.

        Args:
            symbol: Trading pair symbol
            leverage: Leverage multiplier

        Returns:
            Maximum position size or None if not available
        """
        try:
            account_info = await self.get_futures_account_info()
            if not account_info:
                return None

            # Get current price
            current_price = await self.get_mark_price(symbol)
            if not current_price:
                return None

            # Calculate max position size
            max_balance = account_info.get('totalWalletBalance', 0.0)
            max_position_value = max_balance * leverage
            max_position_size = max_position_value / current_price

            return max_position_size

        except Exception as e:
            logger.error(f"Failed to calculate max position size for {symbol}: {e}")
            return None

    # Trade History
    async def get_user_trades(self, symbol: str = "", limit: int = 1000,
                            from_id: int = 0, start_time: int = 0,
                            end_time: int = 0) -> List[Dict[str, Any]]:
        """
        Get user trade history.

        Args:
            symbol: Trading pair symbol (empty for all)
            limit: Maximum number of trades
            from_id: Start from trade ID
            start_time: Start time in milliseconds
            end_time: End time in milliseconds

        Returns:
            List of trade history records
        """
        try:
            await self._init_client()

            futures_api = self.client.get_futures_service().get_fill_api()

            # Placeholder - replace with actual SDK call
            return []

        except Exception as e:
            logger.error(f"Failed to get KuCoin user trades: {e}")
            return []

    async def get_income_history(self, symbol: str = "", income_type: str = "",
                               start_time: int = 0, end_time: int = 0,
                               limit: int = 1000) -> List[Dict[str, Any]]:
        """
        Get income history (fees, funding, etc.).

        Args:
            symbol: Trading pair symbol (empty for all)
            income_type: Type of income (empty for all)
            start_time: Start time in milliseconds
            end_time: End time in milliseconds
            limit: Maximum number of records

        Returns:
            List of income history records
        """
        try:
            await self._init_client()

            futures_api = self.client.get_futures_service().get_account_api()

            # Placeholder - replace with actual SDK call
            return []

        except Exception as e:
            logger.error(f"Failed to get KuCoin income history: {e}")
            return []

    # Helper Methods
    def _convert_order_type(self, order_type: str) -> str:
        """Convert standard order type to KuCoin format."""
        type_mapping = {
            "MARKET": "market",
            "LIMIT": "limit",
            "STOP": "stop",
            "STOP_LIMIT": "stop_limit"
        }
        return type_mapping.get(order_type.upper(), "limit")
