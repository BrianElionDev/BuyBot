"""
KuCoin Exchange Implementation

Main KuCoin exchange class implementing the ExchangeBase interface.
Following Clean Code principles with clear separation of concerns.
"""

import asyncio
import json
import aiohttp
import logging
from typing import Dict, List, Optional, Tuple, Any, cast
from decimal import Decimal

from ..core.exchange_base import ExchangeBase
from ..core.exchange_config import ExchangeConfig
from .kucoin_models import (
    KucoinOrder, KucoinPosition, KucoinBalance,
    KucoinTrade, KucoinIncome, KucoinOrderStatus,
    KucoinOrderType, KucoinOrderSide
)
from .kucoin_client import KucoinClient
from .kucoin_symbol_mapper import symbol_mapper
from .kucoin_symbol_converter import symbol_converter

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
            try:
                await self.client.close()
                logger.info("KuCoin exchange connection closed")
            except Exception as e:
                logger.error(f"Error closing KuCoin exchange: {e}")
            finally:
                self.client = None

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

    def _futures_base_url(self) -> str:
        # KuCoin futures sandbox is currently offline, so always use production
        if self.is_testnet:
            logger.warning("KuCoin futures sandbox is currently offline; using production API")
        return "https://api-futures.kucoin.com"

    # Account Operations
    async def get_account_balances(self) -> Dict[str, float]:
        """
        Get account balances for all assets.

        Returns:
            Dict[str, float]: Asset symbol to balance mapping
        """
        try:
            await self._init_client()

            # Get both spot and futures balances
            spot_balances = await self.get_spot_balance()
            futures_balances = await self.get_futures_balance()

            # Combine balances (futures balances take precedence for overlapping currencies)
            combined_balances = {**spot_balances, **futures_balances}

            logger.info(f"Retrieved KuCoin account balances: {len(combined_balances)} assets")
            return combined_balances

        except Exception as e:
            logger.error(f"Failed to get KuCoin account balances: {e}")
            return {}

    async def get_futures_balance(self) -> Dict[str, float]:
        """
        Get futures account balances.

        Returns:
            Dict[str, float]: Asset symbol to balance mapping
        """
        try:
            await self._init_client()

            # Get futures account info
            account_info = await self.get_futures_account_info()
            if not account_info:
                logger.warning("No futures account info available")
                return {}

            # Extract balance information
            balances = {}
            currency = account_info.get('currency', 'USDT')
            total_balance = account_info.get('totalWalletBalance', 0.0)

            if total_balance > 0:
                balances[currency] = total_balance

            logger.info(f"Retrieved KuCoin futures balances: {balances}")
            return balances

        except Exception as e:
            logger.error(f"Failed to get KuCoin futures balances: {e}")
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

            if not self.client:
                logger.error("KuCoin client not initialized")
                return {}

            spot_service = self.client.get_spot_service()
            if not hasattr(spot_service, 'get_account_api'):
                logger.error("Spot service does not have get_account_api method")
                return {}
            account_api = cast(Any, spot_service).get_account_api()

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
                                 close_position: bool = False,
                                 leverage: Optional[float] = None) -> Dict[str, Any]:
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
            leverage: Leverage for the order (optional)

        Returns:
            Dict containing order response or error information
        """
        try:
            await self._init_client()

            logger.info(f"Creating KuCoin futures order: {pair} {side} {order_type} {amount} (asset quantity)")

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

            # Convert pair to KuCoin futures symbol format using proper converter
            kucoin_symbol = symbol_converter.convert_bot_to_kucoin_futures(pair)

            # Get contract multiplier for proper size calculation
            contract_multiplier = 1.0
            if filters and 'multiplier' in filters:
                try:
                    contract_multiplier = float(filters['multiplier'])
                except (TypeError, ValueError):
                    contract_multiplier = 1.0
                logger.info(f"Using contract multiplier: {contract_multiplier} for {kucoin_symbol}")

            # Calculate proper contract size (contracts = asset_qty / multiplier)
            lot_step = 1.0
            if filters and filters.get('LOT_SIZE', {}).get('stepSize') is not None:
                try:
                    lot_step = float(filters['LOT_SIZE']['stepSize'])
                except (TypeError, ValueError):
                    lot_step = 1.0
            raw_contracts = (amount / contract_multiplier) if contract_multiplier > 0 else amount
            # Round to nearest multiple of lot_step (contracts), enforce minimum 1 contract
            try:
                rounded_contracts = int(round(raw_contracts / lot_step) * lot_step)
            except Exception:
                rounded_contracts = int(raw_contracts)
            contract_size = max(1, rounded_contracts)
            logger.info(f"Contract size calculation: {amount} assets ÷ {contract_multiplier} multiplier ≈ {contract_size} contracts (lot_step={lot_step})")

            # Calculate actual asset quantity from contract size (for storage in origQty)
            # This ensures we store asset quantity, not contract count
            actual_asset_quantity = contract_size * contract_multiplier
            logger.info(f"Actual asset quantity for storage: {actual_asset_quantity} (from {contract_size} contracts × {contract_multiplier})")

            # Prepare order parameters
            order_params = {
                "clientOid": client_order_id or f"kucoin_{int(asyncio.get_event_loop().time() * 1000)}",
                "side": kucoin_side,
                "symbol": kucoin_symbol,  # Use converted symbol
                "type": kucoin_type,
                "size": contract_size  # KuCoin futures expects contract count, not asset quantity
            }

            if price and kucoin_type in ["limit", "stop_limit"]:
                order_params["price"] = str(price)

            if stop_price and kucoin_type in ["stop", "stop_limit"]:
                order_params["stopPrice"] = str(stop_price)

            if reduce_only:
                order_params["reduceOnly"] = True

            # Create order using KuCoin SDK - Use FUTURES service for futures orders
            if not self.client:
                logger.error("KuCoin client not initialized")
                return {"success": False, "error": "Client not initialized"}

            futures_service = self.client.get_futures_service()
            order_api = futures_service.get_order_api()

            from kucoin_universal_sdk.generate.futures.order.model_add_order_req import AddOrderReqBuilder

            # Get proper leverage for KuCoin
            if leverage is None:
                leverage = 1.0

            leverage_int = int(leverage) if leverage else 1
            if leverage_int < 1:
                leverage_int = 1  # Minimum leverage for KuCoin
            elif leverage_int > 100:
                leverage_int = 100  # Maximum leverage for KuCoin

            logger.info(f"Using leverage: {leverage_int}x for {order_params['symbol']}")

            # SDK expects enums; cast to Any to satisfy type checker while passing valid values
            order_request = (AddOrderReqBuilder()
                .set_client_oid(order_params["clientOid"])
                .set_side(cast(Any, order_params["side"]))
                .set_symbol(order_params["symbol"])
                .set_type(cast(Any, order_params["type"]))
                .set_size(order_params["size"])
                .set_leverage(leverage_int))

            if "price" in order_params:
                order_request.set_price(order_params["price"])
            if "stopPrice" in order_params:
                order_request.set_stop_price(order_params["stopPrice"])

            request = order_request.build()
            response = order_api.add_order(request)

            # Format response to match Binance format
            # IMPORTANT: origQty should store asset quantity, not contract count
            formatted_response = {
                "success": True,
                "orderId": getattr(response, 'orderId', order_params["clientOid"]),
                "clientOrderId": order_params["clientOid"],
                "symbol": pair,
                "side": side.upper(),
                "type": order_type.upper(),
                "origQty": str(actual_asset_quantity),  # Store asset quantity, not contract count
                "price": str(price) if price else None,
                "stopPrice": str(stop_price) if stop_price else None,
                "status": "NEW",
                "time": int(asyncio.get_event_loop().time() * 1000),
                "contract_multiplier": contract_multiplier,  # Store multiplier for reference
                "contract_size": contract_size  # Store contract size for reference
            }

            try:
                logger.info(f"Raw KuCoin order response: {json.dumps(getattr(response, '__dict__', {}))}")
            except Exception:
                logger.info(f"Raw KuCoin order response (non-JSON-serializable): {response}")

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

            if not self.client:
                logger.error("KuCoin client not initialized")
                return False, {"error": "Client not initialized"}

            futures_api = self.client.get_futures_service().get_order_api()

            from kucoin_universal_sdk.generate.futures.order.model_cancel_order_by_id_req import CancelOrderByIdReqBuilder

            # Build cancel order request
            cancel_request = CancelOrderByIdReqBuilder().set_order_id(order_id).build()
            response = futures_api.cancel_order_by_id(cancel_request)

            # Format response to match expected format
            formatted_response = {
                "success": True,
                "orderId": order_id,
                "symbol": pair,
                "status": "CANCELED",
                "raw_response": response
            }

            logger.info(f"KuCoin futures order canceled: {order_id}")
            return True, formatted_response

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

            if not self.client:
                logger.error("KuCoin client not initialized")
                return None

            futures_api = self.client.get_futures_service().get_order_api()

            from kucoin_universal_sdk.generate.futures.order.model_get_order_by_order_id_req import GetOrderByOrderIdReqBuilder

            # Build get order request
            get_order_request = GetOrderByOrderIdReqBuilder().set_order_id(order_id).build()
            response = futures_api.get_order_by_order_id(get_order_request)

            if not response:
                logger.warning(f"Order {order_id} not found")
                return None

            # Try to get data attribute safely
            order_data = None
            resp_any = cast(Any, response)
            if hasattr(resp_any, 'data'):
                order_data = resp_any.data
            elif hasattr(resp_any, 'order'):
                order_data = resp_any.order
            else:
                logger.warning(f"Order {order_id} response format not recognized")
                return None

            if not order_data:
                logger.warning(f"Order {order_id} not found")
                return None

            # Get contract multiplier for this symbol
            contract_multiplier = 1.0
            try:
                filters = await self.get_futures_symbol_filters(pair)
                if filters and 'multiplier' in filters:
                    try:
                        contract_multiplier = float(filters['multiplier'])
                    except (TypeError, ValueError):
                        contract_multiplier = 1.0
            except Exception as e:
                logger.warning(f"Could not get contract multiplier for {pair}: {e}")

            # Convert contract sizes to asset quantities
            size_contracts = float(getattr(order_data, 'size', '0'))
            filled_size_contracts = float(getattr(order_data, 'filledSize', '0'))

            # Calculate asset quantities
            size_assets = size_contracts * contract_multiplier
            filled_size_assets = filled_size_contracts * contract_multiplier

            # Format response to match expected format
            formatted_response = {
                "orderId": getattr(order_data, 'id', order_id),
                "clientOrderId": getattr(order_data, 'clientOid', ''),
                "symbol": getattr(order_data, 'symbol', pair),
                "status": getattr(order_data, 'status', 'UNKNOWN'),
                "side": getattr(order_data, 'side', 'UNKNOWN'),
                "type": getattr(order_data, 'type', 'UNKNOWN'),
                "size": str(size_contracts),  # Contract size (for API compatibility)
                "price": str(getattr(order_data, 'price', '0')),
                "filledSize": str(filled_size_contracts),  # Contract size (for API compatibility)
                "filledValue": str(getattr(order_data, 'filledValue', '0')),
                "time": getattr(order_data, 'createdAt', 0),
                "raw_response": order_data,
                # Add asset quantities for database storage
                "origQty": str(size_assets),  # Asset quantity (for database storage)
                "executedQty": str(filled_size_assets),  # Asset quantity (for database storage)
                "contract_multiplier": contract_multiplier  # Store multiplier for reference
            }

            logger.info(f"Retrieved KuCoin order status for {order_id}: {formatted_response['status']}")
            return formatted_response

        except Exception as e:
            logger.error(f"Failed to get KuCoin order status for {order_id}: {e}")
            return None

    # Position Operations
    async def get_futures_position_information(self) -> List[Dict[str, Any]]:
        """
        Get all futures positions using direct API calls.

        Returns:
            List of position information dictionaries
        """
        try:
            await self._init_client()

            # Use direct HTTP API call since SDK method is not available
            futures_base_url = self._futures_base_url()
            url = f"{futures_base_url}/api/v1/positions"

            # Prepare headers for authenticated request
            if not self.client or not hasattr(self.client, 'auth'):
                logger.error("KuCoin client or auth not initialized")
                return []

            headers = self.client.auth.get_futures_headers('GET', '/api/v1/positions')

            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    data = await resp.json()

                    if data.get('code') != '200000':
                        logger.error(f"KuCoin futures positions API error: {data}")
                        return []

                    positions_data = data.get('data', [])
                    if not positions_data:
                        logger.info("No futures positions found")
                        return []

                    positions = []
                    for position_data in positions_data:
                        # Only process open positions with non-zero quantity
                        current_qty = float(position_data.get('currentQty', 0))
                        if current_qty == 0 or not position_data.get('isOpen', False):
                            continue

                        # Determine side based on quantity
                        side = "LONG" if current_qty > 0 else "SHORT"

                        # Format position data to match expected format
                        formatted_position = {
                            "symbol": position_data.get('symbol', ''),
                            "side": side,
                            "size": abs(current_qty),  # Use absolute value for size
                            "entryPrice": float(position_data.get('avgEntryPrice', 0)),
                            "markPrice": float(position_data.get('markPrice', 0)),
                            "unrealizedPnl": float(position_data.get('unrealisedPnl', 0)),
                            "percentage": float(position_data.get('unrealisedPnlPcnt', 0)),
                            "marginMode": position_data.get('marginMode', 'UNKNOWN'),
                            "leverage": float(position_data.get('leverage', 1)),
                            "margin": float(position_data.get('posMargin', 0)),
                            "raw_response": position_data
                        }
                        positions.append(formatted_position)

                    logger.info(f"Retrieved {len(positions)} KuCoin futures positions")
                    return positions

        except Exception as e:
            logger.error(f"Failed to get KuCoin futures positions: {e}")
            return []

    async def close_position(self, pair: str, amount: float,
                           position_type: str) -> Tuple[bool, Dict[str, Any]]:
        """
        Close a futures position using direct API calls.

        Args:
            pair: Trading pair symbol
            amount: Amount to close
            position_type: Position type (LONG/SHORT)

        Returns:
            Tuple of (success, response_data)
        """
        try:
            await self._init_client()

            # If amount is 0 or None, fetch live position size and leverage
            current_leverage = 1.0
            if amount <= 0:
                positions = await self.get_futures_position_information()
                target_symbol = pair.replace('-', 'USDTM')  # Convert to futures format
                for pos in positions:
                    if pos.get('symbol') == target_symbol and pos.get('side', '').upper() == position_type.upper():
                        amount = float(pos.get('size', 0.0))
                        current_leverage = float(pos.get('leverage', 1.0))
                        logger.info(f"Found live position size for {pair}: {amount}, leverage: {current_leverage}")
                        break

                if amount <= 0:
                    logger.error(f"No open position found for {pair} {position_type}")
                    return False, {"error": f"No open position found for {pair} {position_type}"}

            # Determine side for closing
            side = "sell" if position_type.upper() == "LONG" else "buy"

            # Convert pair to KuCoin futures format
            # Remove the -USDT part and add USDTM
            if pair.endswith('-USDT'):
                kucoin_symbol = pair.replace('-USDT', 'USDTM')
            else:
                kucoin_symbol = pair.replace('-', 'USDTM')
            logger.info(f"Converting pair {pair} to KuCoin futures symbol: {kucoin_symbol}")

            # Get contract multiplier for proper conversion
            filters = await self.get_futures_symbol_filters(pair)
            contract_multiplier = 1.0
            if filters and 'multiplier' in filters:
                try:
                    contract_multiplier = float(filters['multiplier'])
                except (TypeError, ValueError):
                    contract_multiplier = 1.0
                logger.info(f"Using contract multiplier: {contract_multiplier} for {kucoin_symbol}")

            # Determine if amount is in asset quantity or contract size
            # If fetched from live position (line 581), it's contract size
            # If from database position_size, it's asset quantity
            # We'll assume it's asset quantity (from database) and convert to contracts
            asset_quantity = amount  # Store original for response
            raw_contracts = (amount / contract_multiplier) if contract_multiplier > 0 else amount
            lot_step = 1.0
            try:
                if filters and filters.get('LOT_SIZE', {}).get('stepSize') is not None:
                    lot_step = float(filters['LOT_SIZE']['stepSize'])
            except (TypeError, ValueError):
                lot_step = 1.0
            try:
                rounded_contracts = int(round(raw_contracts / lot_step) * lot_step)
            except Exception:
                rounded_contracts = int(raw_contracts)
            contract_size = max(1, rounded_contracts)
            logger.info(f"Close order: {asset_quantity} assets → {contract_size} contracts (multiplier: {contract_multiplier})")

            # Initialize client (was under an unnecessary try block)
            await self._init_client()

            if not self.client:
                logger.error("KuCoin client not initialized")
                return False, {"error": "Client not initialized"}

            futures_service = self.client.get_futures_service()
            order_api = futures_service.get_order_api()

            from kucoin_universal_sdk.generate.futures.order.model_add_order_req import AddOrderReqBuilder

            client_oid = f"close_{int(asyncio.get_event_loop().time() * 1000)}"

            try:
                    # Get current price using the ticker API
                    url = f"{self._futures_base_url()}/api/v1/ticker?symbol={kucoin_symbol}"
                    async with aiohttp.ClientSession() as session:
                        async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                            data = await resp.json()
                            if data.get('code') == '200000':
                                ticker_data = data.get('data', {})
                                current_price = float(ticker_data.get('price', 0))
                                logger.info(f"Current price for {kucoin_symbol}: {current_price}")
                            else:
                                raise RuntimeError(f"Ticker API error: {data}")
            except Exception as e:
                logger.warning(f"Could not get current price for {kucoin_symbol}: {e}")
                current_price = 1.0  # Fallback price

            try:
                close_leverage = int(current_leverage) if current_leverage else 1
            except Exception:
                close_leverage = 1

            if close_leverage < 1:
                close_leverage = 1
            elif close_leverage > 100:
                    close_leverage = 100

            order_request = AddOrderReqBuilder() \
                .set_client_oid(client_oid) \
                .set_side(cast(Any, side)) \
                .set_symbol(kucoin_symbol) \
                .set_type(cast(Any, "market")) \
                .set_size(contract_size) \
                .set_reduce_only(True) \
                .set_leverage(close_leverage)

            request = order_request.build()
            response = order_api.add_order(request)

            formatted_response = {
                    "success": True,
                    "orderId": getattr(response, 'orderId', client_oid),
                    "clientOrderId": client_oid,
                    "symbol": pair,
                    "side": side.upper(),
                "type": "MARKET",
                    "origQty": str(asset_quantity),  # Store asset quantity, not contract count
                    "status": "NEW",
                    "time": int(asyncio.get_event_loop().time() * 1000),
                    "contract_multiplier": contract_multiplier,
                    "contract_size": contract_size
                }

            try:
                logger.info(f"Raw KuCoin close response: {json.dumps(getattr(response, '__dict__', {}))}")
            except Exception:
                    logger.info(f"Raw KuCoin close response (non-JSON-serializable): {response}")

            logger.info(f"KuCoin futures order created: {formatted_response}")
            return True, formatted_response

        except Exception as e:
            logger.error(f"Error placing KuCoin close order: {e}")
            return False, {"error": str(e)}


    # Market Data
    async def get_current_prices(self, symbols: List[str]) -> Dict[str, float]:
        """
        Get current prices for symbols using KuCoin futures API.

        Args:
            symbols: List of symbol strings

        Returns:
            Dict mapping symbol to current price
        """
        try:
            await self._init_client()

            prices = {}

            # First, get all available futures symbols to understand the format
            available_symbols = set()
            try:
                url = f"{self._futures_base_url()}/api/v1/contracts/active"
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                        data = await resp.json()
                        items = data.get("data") or []
                        for it in items:
                            sym = it.get("symbol")
                            if sym:
                                available_symbols.add(sym)
                logger.info(f"Retrieved {len(available_symbols)} KuCoin futures symbols")
            except Exception as e:
                logger.warning(f"Failed to get all KuCoin futures symbols: {e}")
                available_symbols = set()

            # Update symbol converter with available symbols
            symbol_converter.available_symbols = list(available_symbols)

            for symbol in symbols:
                try:
                    # Use symbol converter to find the correct format
                    mapped_symbol = symbol_converter.find_matching_symbol(symbol, list(available_symbols), "futures")

                    price = None
                    working_symbol = None

                    if mapped_symbol:
                        try:
                            logger.info(f"Trying KuCoin futures ticker for: {mapped_symbol}")

                            # Try futures ticker first
                            ticker_data = await self.get_futures_ticker(mapped_symbol)
                            if ticker_data:
                                raw_price = ticker_data.get('price') or ticker_data.get('last') or ticker_data.get('bestAsk') or ticker_data.get('bestBid')
                                try:
                                    price = float(raw_price) if raw_price is not None else 0.0
                                except (ValueError, TypeError):
                                    price = 0.0

                                if price and price > 0:
                                    working_symbol = mapped_symbol
                                    logger.info(f"Found KuCoin futures price for {mapped_symbol}: ${price}")
                                else:
                                    logger.warning(f"Invalid price data for {mapped_symbol}: {raw_price}")
                            else:
                                logger.warning(f"No ticker data received for {mapped_symbol}")

                        except Exception as e:
                            logger.warning(f"KuCoin futures ticker failed for {mapped_symbol}: {e}")

                            # Try spot ticker as fallback
                            try:
                                spot_symbol = symbol_converter.convert_bot_to_kucoin_spot(symbol)
                                logger.info(f"Trying KuCoin spot ticker as fallback for: {spot_symbol}")

                                # Try spot API
                                spot_url = "https://api.kucoin.com/api/v1/market/orderbook/level1"
                                async with aiohttp.ClientSession() as session:
                                    async with session.get(spot_url, params={'symbol': spot_symbol}, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                                        spot_data = await resp.json()
                                        if spot_data.get('code') == '200000':
                                            spot_ticker = spot_data.get('data', {})
                                            raw_price = spot_ticker.get('price') or spot_ticker.get('bestAsk') or spot_ticker.get('bestBid')
                                            try:
                                                price = float(raw_price) if raw_price is not None else 0.0
                                                if price and price > 0:
                                                    working_symbol = spot_symbol
                                                    logger.info(f"Found KuCoin spot price for {spot_symbol}: ${price}")
                                            except (ValueError, TypeError):
                                                logger.warning(f"Invalid spot price data for {spot_symbol}: {raw_price}")
                            except Exception as spot_e:
                                logger.warning(f"KuCoin spot ticker also failed for {symbol}: {spot_e}")
                    else:
                        logger.warning(f"Could not map {symbol} to any available KuCoin futures symbol")

                    if price and price > 0:
                        prices[symbol] = price
                        logger.info(f"KuCoin price for {symbol} (using {working_symbol}): ${price}")
                    else:
                        logger.warning(f"No ticker price for {symbol} (mapped: {mapped_symbol}) on KuCoin futures")
                        prices[symbol] = 0.0

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

            if not self.client:
                logger.error("KuCoin client not initialized")
                return None

            spot_service = self.client.get_spot_service()
            market_api = spot_service.get_market_api()

            # First get all symbols to find the correct format
            symbols_request = GetAllSymbolsReqBuilder().build()
            symbols_response = market_api.get_all_symbols(symbols_request)
            symbols = []
            if hasattr(symbols_response, 'data') and symbols_response.data:
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

            # Get all available symbols first
            all_symbols = await self.get_futures_symbols()
            symbol_converter.available_symbols = all_symbols

            # Normalize symbol (same logic as is_futures_symbol_supported)
            base = (symbol or "").strip().upper().lstrip('@').replace(' ', '')

            # Normalize BTC to XBT for KuCoin
            if base.startswith('BTC'):
                base = base.replace('BTC', 'XBT', 1)
            if base.startswith('BTC-'):
                base = base.replace('BTC-', 'XBT-', 1)

            # Try direct lookup first
            if base in all_symbols:
                mapped_symbol = base
            else:
                # Generate candidates (KuCoin Futures uses USDTM for perpetuals)
                candidates = []
                if base.endswith('USDTM'):
                    candidates.append(base)
                elif base.endswith('USDT'):
                    # Convert USDT to USDTM for futures
                    candidates.extend([base + 'M', base])
                elif '-' in base:
                    no_dash = base.replace('-', '')
                    candidates.extend([no_dash + 'M', no_dash, base])
                else:
                    candidates.extend([f"{base}USDTM", f"{base}USDT", f"{base}-USDT"])

                # Find first matching candidate
                mapped_symbol = None
                for cand in candidates:
                    if cand in all_symbols:
                        mapped_symbol = cand
                        break

                # Fallback to symbol converter
                if not mapped_symbol:
                    mapped_symbol = symbol_converter.find_matching_symbol(symbol, all_symbols, "futures")

            if not mapped_symbol:
                logger.warning(f"Symbol {symbol} not found in KuCoin futures symbols")
                return None

            symbol_info = None
            working_symbol = mapped_symbol

            try:
                logger.info(f"Fetching KuCoin futures symbol details: {mapped_symbol}")
                url = f"{self._futures_base_url()}/api/v1/contracts/{mapped_symbol}"
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                        data = await resp.json()
                        symbol_info = (data or {}).get("data")
                        if not symbol_info:
                            logger.warning(f"Symbol {mapped_symbol} not found in KuCoin futures")
                        else:
                            logger.info(f"Found KuCoin futures symbol: {mapped_symbol}")

            except Exception as e:
                logger.error(f"Symbol {mapped_symbol} failed: {e}")
                return None

            if not symbol_info:
                logger.warning(f"Symbol {symbol} not found in KuCoin futures symbols")
                return None

            # Extract symbol information and create filters
            try:
                multiplier_val = float(symbol_info.get('multiplier', 1))
            except (TypeError, ValueError):
                multiplier_val = 1.0
            filters = {
                "symbol": symbol,
                "kucoin_symbol": working_symbol,
                "baseCurrency": symbol_info.get('baseCurrency', ''),
                "quoteCurrency": symbol_info.get('quoteCurrency', ''),
                "baseMinSize": symbol_info.get('lotSize', '1'),
                "baseMaxSize": symbol_info.get('maxOrderQty', '1000000'),
                "quoteMinSize": symbol_info.get('minPrice', '0.00001'),
                "quoteMaxSize": symbol_info.get('maxPrice', '1000000'),
                "baseIncrement": symbol_info.get('lotSize', '1'),
                "quoteIncrement": symbol_info.get('tickSize', '0.0001'),
                "priceIncrement": symbol_info.get('tickSize', '0.0001'),
                "enableTrading": symbol_info.get('status', '') == 'Open',
                "isMarginEnabled": getattr(symbol_info, 'isMarginEnabled', True),
                "contractType": symbol_info.get('type', 'FUTURES'),
                "contractSize": multiplier_val,
                "multiplier": multiplier_val,
                # KuCoin specific filters
                "LOT_SIZE": {
                    "minQty": symbol_info.get('lotSize', '1'),
                    "maxQty": symbol_info.get('maxOrderQty', '1000000'),
                    "stepSize": symbol_info.get('lotSize', '1')
                },
                "PRICE_FILTER": {
                    "minPrice": str(symbol_info.get('minPrice', '0.00001')),
                    "maxPrice": str(symbol_info.get('maxPrice', '1000000')),
                    "tickSize": str(symbol_info.get('tickSize', '0.0001'))
                },
                "MIN_NOTIONAL": {
                    "minNotional": str(symbol_info.get('minPrice', '0.00001'))
                }
            }

            logger.info(f"Retrieved KuCoin futures symbol filters for {symbol} (using {working_symbol})")
            return filters

        except Exception as e:
            logger.error(f"Failed to get KuCoin futures symbol filters for {symbol}: {e}")
            return None

    async def get_futures_symbols(self) -> List[str]:
        """
        Get all supported futures symbols.

        Returns:
            List of supported futures symbols
        """
        try:
            await self._init_client()

            url = f"{self._futures_base_url()}/api/v1/contracts/active"
            symbols: List[str] = []
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    data = await resp.json()
                    items = data.get("data") or []
                    for it in items:
                        if it.get('status') == 'Open':
                            sym = it.get('symbol')
                            if sym:
                                symbols.append(sym)

            logger.info(f"Retrieved {len(symbols)} KuCoin futures symbols")
            return symbols

        except Exception as e:
            logger.error(f"Failed to get KuCoin futures symbols: {e}")
            return []

    async def is_futures_symbol_supported(self, symbol: str) -> bool:
        """
        Check if symbol is supported for futures trading using dynamic validation.

        Args:
            symbol: Trading pair symbol

        Returns:
            True if supported, False otherwise
        """
        try:
            # Import here to avoid circular imports
            from src.core.dynamic_symbol_validator import dynamic_validator

            # Use dynamic validation with caching
            is_supported = await dynamic_validator.is_symbol_supported(
                symbol=symbol,
                exchange='kucoin',
                exchange_client=self,
                trading_type='futures'
            )

            return is_supported

        except Exception as e:
            logger.error(f"Failed to check KuCoin symbol support for {symbol}: {e}")
            return False

    def get_futures_trading_pair(self, coin_symbol: str) -> str:
        """
        Return a canonical pair used by our bot prior to KuCoin conversion.
        We use COINUSDTM format for KuCoin Futures perpetuals.
        """
        try:
            return f"{str(coin_symbol).upper()}USDTM"
        except Exception:
            return f"{coin_symbol}USDTM"

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

    async def get_futures_ticker(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Get futures ticker data for a symbol.

        Args:
            symbol: KuCoin futures symbol (e.g., 'BTCUSDTM')

        Returns:
            Ticker data dictionary or None if error
        """
        try:
            url = f"{self._futures_base_url()}/api/v1/ticker?symbol={symbol}"
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    data = await resp.json()
                    if data.get('code') == '200000':
                        return data.get('data', {})
                    else:
                        logger.error(f"KuCoin futures ticker API error for {symbol}: {data}")
                        return None
        except Exception as e:
            logger.error(f"Failed to get KuCoin futures ticker for {symbol}: {e}")
            return None

    async def get_mark_price(self, symbol: str) -> Optional[float]:
        """
        Get mark price for a symbol using futures API.

        Args:
            symbol: Trading pair symbol

        Returns:
            Mark price or None if not available
        """
        try:
            # Get mapped symbol for futures
            all_symbols = await self.get_futures_symbols()
            symbol_mapper.available_symbols = all_symbols
            mapped_symbol = symbol_mapper.map_to_futures_symbol(symbol, all_symbols)

            if not mapped_symbol:
                logger.warning(f"Could not map {symbol} to futures symbol for mark price")
                return None

            url = f"{self._futures_base_url()}/api/v1/mark-price/{mapped_symbol}/current"
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    data = await resp.json()
                    td = data.get("data") or {}
                    return float(td.get('value', 0.0))  # 'value' is mark price

        except Exception as e:
            logger.error(f"Failed to get KuCoin mark price for {symbol}: {e}")
            return None

    async def get_futures_account_info(self) -> Optional[Dict[str, Any]]:
        """
        Get futures account information using direct API calls.

        Returns:
            Account information or None if not available
        """
        try:
            await self._init_client()

            # Use direct HTTP API call since SDK method is not available
            futures_base_url = self._futures_base_url()
            url = f"{futures_base_url}/api/v1/account-overview"

            # Prepare headers for authenticated request
            if not self.client or not hasattr(self.client, 'auth'):
                logger.error("KuCoin client or auth not initialized")
                return None

            headers = self.client.auth.get_futures_headers('GET', '/api/v1/account-overview', {'currency': 'USDT'})

            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, params={'currency': 'USDT'}, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    data = await resp.json()

                    if data.get('code') != '200000':
                        logger.error(f"KuCoin futures account API error: {data}")
                        return None

                    account_data = data.get('data', {})
                    if not account_data:
                        logger.warning("No futures account data received")
                        return None

                    # Format response to match expected format
                    formatted_response = {
                        "totalWalletBalance": float(account_data.get('accountEquity', 0.0)),
                        "totalUnrealizedProfit": float(account_data.get('unrealisedPNL', 0.0)),
                        "totalMarginBalance": float(account_data.get('marginBalance', 0.0)),
                        "totalInitialMargin": float(account_data.get('positionMargin', 0.0)),
                        "totalMaintMargin": float(account_data.get('orderMargin', 0.0)),
                        "maxWithdrawAmount": float(account_data.get('maxWithdrawAmount', 0.0)),
                        "availableBalance": float(account_data.get('availableBalance', 0.0)),
                        "currency": account_data.get('currency', 'USDT'),
                        "raw_response": account_data
                    }

                    logger.info(f"Retrieved KuCoin futures account info: {formatted_response['totalWalletBalance']} {formatted_response['currency']}")
                    return formatted_response

        except Exception as e:
            logger.error(f"Failed to get KuCoin futures account info: {e}")
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

            if not self.client:
                logger.error("KuCoin client not initialized")
                return []

            futures_order_api = self.client.get_futures_service().get_order_api()

            from kucoin_universal_sdk.generate.futures.order.model_get_trade_history_req import GetTradeHistoryReqBuilder

            # Build get trade history request
            trade_request = GetTradeHistoryReqBuilder()

            if symbol:
                trade_request.set_symbol(symbol)
            if start_time:
                trade_request.set_start_at(start_time)
            if end_time:
                trade_request.set_end_at(end_time)

            request = trade_request.build()
            response = futures_order_api.get_trade_history(request)

            if not response:
                logger.info("No trade history found")
                return []

            # Try to get data attribute safely
            trade_data_list = []
            resp_any = cast(Any, response)
            if hasattr(resp_any, 'data') and resp_any.data:
                trade_data_list = resp_any.data
            elif hasattr(resp_any, 'items') and resp_any.items:
                trade_data_list = resp_any.items

            if not trade_data_list:
                logger.info("No trade history found")
                return []

            trades = []
            for trade_data in trade_data_list:
                # Try to extract orderId from various possible attributes
                order_id = None
                if hasattr(trade_data, 'orderId'):
                    order_id = getattr(trade_data, 'orderId', None)
                elif hasattr(trade_data, 'order_id'):
                    order_id = getattr(trade_data, 'order_id', None)
                elif hasattr(trade_data, 'orderOid'):
                    order_id = getattr(trade_data, 'orderOid', None)

                # Format trade data to match expected format
                formatted_trade = {
                    "id": getattr(trade_data, 'id', ''),
                    "symbol": getattr(trade_data, 'symbol', symbol),
                    "side": getattr(trade_data, 'side', 'UNKNOWN'),
                    "type": getattr(trade_data, 'type', 'UNKNOWN'),
                    "size": float(getattr(trade_data, 'size', 0)),
                    "price": float(getattr(trade_data, 'price', 0)),
                    "value": float(getattr(trade_data, 'value', 0)),
                    "fee": float(getattr(trade_data, 'fee', 0)),
                    "feeCurrency": getattr(trade_data, 'feeCurrency', 'USDT'),
                    "time": getattr(trade_data, 'createdAt', getattr(trade_data, 'time', 0)),
                    "orderId": order_id,
                    "raw_response": trade_data
                }
                trades.append(formatted_trade)

            logger.info(f"Retrieved {len(trades)} KuCoin user trades")
            return trades

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

            if not self.client:
                logger.error("KuCoin client not initialized")
                return []

            futures_funding_api = self.client.get_futures_service().get_funding_fees_api()

            from kucoin_universal_sdk.generate.futures.fundingfees.model_get_private_funding_history_req import GetPrivateFundingHistoryReqBuilder

            # Build get private funding history request
            funding_request = GetPrivateFundingHistoryReqBuilder()

            if symbol:
                funding_request.set_symbol(symbol)
            if start_time:
                funding_request.set_start_at(start_time)
            if end_time:
                funding_request.set_end_at(end_time)

            request = funding_request.build()
            response = futures_funding_api.get_private_funding_history(request)

            if not response:
                logger.info("No income history found")
                return []

            # Try to get data attribute safely
            income_data_list = []
            resp_any = cast(Any, response)
            if hasattr(resp_any, 'data') and resp_any.data:
                income_data_list = resp_any.data
            elif hasattr(resp_any, 'items') and resp_any.items:
                income_data_list = resp_any.items

            if not income_data_list:
                logger.info("No income history found")
                return []

            income_records = []
            for income_data in income_data_list:
                # Format income data to match expected format
                formatted_income = {
                    "id": getattr(income_data, 'id', ''),
                    "symbol": getattr(income_data, 'symbol', symbol),
                    "type": "FUNDING_FEE",
                    "amount": float(getattr(income_data, 'amount', 0)),
                    "currency": getattr(income_data, 'currency', 'USDT'),
                    "time": getattr(income_data, 'createdAt', 0),
                    "raw_response": income_data
                }
                income_records.append(formatted_income)

            logger.info(f"Retrieved {len(income_records)} KuCoin income records")
            return income_records

        except Exception as e:
            logger.error(f"Failed to get KuCoin income history: {e}")
            return []

    async def get_account_ledgers(self, currency: str = "", biz_type: str = "",
                                start_time: int = 0, end_time: int = 0,
                                limit: int = 1000) -> List[Dict[str, Any]]:
        """
        Get comprehensive account ledger from KuCoin.

        This is the primary method for getting all account activities including
        realized PnL, fees, deposits, withdrawals, and other transaction types.

        Args:
            currency: Currency filter (empty for all)
            biz_type: Business type filter (empty for all)
            start_time: Start time in milliseconds
            end_time: End time in milliseconds
            limit: Maximum number of records

        Returns:
            List of account ledger records
        """
        try:
            await self._init_client()

            if not self.client:
                logger.error("KuCoin client not initialized")
                return []

            # Build request parameters
            params = {}
            if currency:
                params['currency'] = currency
            if biz_type:
                params['bizType'] = biz_type
            if start_time:
                params['startAt'] = start_time
            if end_time:
                params['endAt'] = end_time

            # Use direct API call approach since SDK structure is unclear
            response = await self._make_direct_api_call(
                'GET', '/api/v1/accounts/ledgers', params
            )

            if not response:
                logger.info("No account ledgers found")
                return []

            # Handle response data
            ledger_data_list = []
            if isinstance(response, list):
                ledger_data_list = response
            elif isinstance(response, dict):
                ledger_data_list = response.get('data', [])
                if not ledger_data_list:
                    ledger_data_list = response.get('items', [])

            if not ledger_data_list:
                logger.info("No account ledgers found")
                return []

            ledger_records = []
            for ledger_data in ledger_data_list:
                # Format ledger data to match expected format
                if isinstance(ledger_data, dict):
                    formatted_ledger = {
                        "id": ledger_data.get('id', ''),
                        "currency": ledger_data.get('currency', ''),
                        "amount": float(ledger_data.get('amount', 0)),
                        "fee": float(ledger_data.get('fee', 0)),
                        "balance": float(ledger_data.get('balance', 0)),
                        "bizType": ledger_data.get('bizType', ''),
                        "direction": ledger_data.get('direction', ''),
                        "createdAt": ledger_data.get('createdAt', 0),
                        "context": ledger_data.get('context', ''),
                        "raw_response": ledger_data
                    }
                else:
                    # Handle object attributes if it's not a dict
                    formatted_ledger = {
                        "id": getattr(ledger_data, 'id', ''),
                        "currency": getattr(ledger_data, 'currency', ''),
                        "amount": float(getattr(ledger_data, 'amount', 0)),
                        "fee": float(getattr(ledger_data, 'fee', 0)),
                        "balance": float(getattr(ledger_data, 'balance', 0)),
                        "bizType": getattr(ledger_data, 'bizType', ''),
                        "direction": getattr(ledger_data, 'direction', ''),
                        "createdAt": getattr(ledger_data, 'createdAt', 0),
                        "context": getattr(ledger_data, 'context', ''),
                        "raw_response": ledger_data
                    }
                ledger_records.append(formatted_ledger)

            logger.info(f"Retrieved {len(ledger_records)} KuCoin account ledger records")
            return ledger_records

        except Exception as e:
            logger.error(f"Failed to get KuCoin account ledgers: {e}")
            return []

    async def get_futures_account_ledgers(self, currency: str = "", biz_type: str = "",
                                        start_time: int = 0, end_time: int = 0,
                                        limit: int = 1000) -> List[Dict[str, Any]]:
        """
        Get futures account ledger from KuCoin.

        This method specifically targets futures account activities.

        Args:
            currency: Currency filter (empty for all)
            biz_type: Business type filter (empty for all)
            start_time: Start time in milliseconds
            end_time: End time in milliseconds
            limit: Maximum number of records

        Returns:
            List of futures account ledger records
        """
        try:
            await self._init_client()

            if not self.client:
                logger.error("KuCoin client not initialized")
                return []

            # Build request parameters
            params = {}
            if currency:
                params['currency'] = currency
            if biz_type:
                params['bizType'] = biz_type
            if start_time:
                params['startAt'] = start_time
            if end_time:
                params['endAt'] = end_time

            # Use direct API call approach since SDK structure is unclear
            response = await self._make_direct_api_call(
                'GET', '/api/v1/futures/account/ledgers', params
            )

            if not response:
                logger.info("No futures account ledgers found")
                return []

            # Handle response data
            ledger_data_list = []
            if isinstance(response, list):
                ledger_data_list = response
            elif isinstance(response, dict):
                ledger_data_list = response.get('data', [])
                if not ledger_data_list:
                    ledger_data_list = response.get('items', [])

            if not ledger_data_list:
                logger.info("No futures account ledgers found")
                return []

            ledger_records = []
            for ledger_data in ledger_data_list:
                # Format ledger data to match expected format
                if isinstance(ledger_data, dict):
                    formatted_ledger = {
                        "id": ledger_data.get('id', ''),
                        "currency": ledger_data.get('currency', ''),
                        "amount": float(ledger_data.get('amount', 0)),
                        "fee": float(ledger_data.get('fee', 0)),
                        "balance": float(ledger_data.get('balance', 0)),
                        "bizType": ledger_data.get('bizType', ''),
                        "direction": ledger_data.get('direction', ''),
                        "createdAt": ledger_data.get('createdAt', 0),
                        "context": ledger_data.get('context', ''),
                        "raw_response": ledger_data
                    }
                else:
                    # Handle object attributes if it's not a dict
                    formatted_ledger = {
                        "id": getattr(ledger_data, 'id', ''),
                        "currency": getattr(ledger_data, 'currency', ''),
                        "amount": float(getattr(ledger_data, 'amount', 0)),
                        "fee": float(getattr(ledger_data, 'fee', 0)),
                        "balance": float(getattr(ledger_data, 'balance', 0)),
                        "bizType": getattr(ledger_data, 'bizType', ''),
                        "direction": getattr(ledger_data, 'direction', ''),
                        "createdAt": getattr(ledger_data, 'createdAt', 0),
                        "context": getattr(ledger_data, 'context', ''),
                        "raw_response": ledger_data
                    }
                ledger_records.append(formatted_ledger)

            logger.info(f"Retrieved {len(ledger_records)} KuCoin futures account ledger records")
            return ledger_records

        except Exception as e:
            logger.error(f"Failed to get KuCoin futures account ledgers: {e}")
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

    async def _make_direct_api_call(self, method: str, endpoint: str, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """
        Make a direct API call to KuCoin using the existing client.

        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint path
            params: Query parameters

        Returns:
            API response data
        """
        try:
            if not self.client:
                logger.error("KuCoin client not initialized")
                return []

            # Prepare parameters
            if params is None:
                params = {}

            # Build URL and auth headers
            futures_base_url = self._futures_base_url()
            url = f"{futures_base_url}{endpoint}"

            if not hasattr(self.client, 'auth') or not self.client.auth:
                logger.error("KuCoin client auth not initialized")
                return []

            try:
                headers = self.client.auth.get_futures_headers(method, endpoint, params)
            except Exception as e:
                logger.error(f"Failed to build KuCoin auth headers for {endpoint}: {e}")
                return []

            timeout = aiohttp.ClientTimeout(total=15)
            try:
                async with aiohttp.ClientSession() as session:
                    if method.upper() == 'GET':
                        async with session.get(url, headers=headers, params=params, timeout=timeout) as resp:
                            data = await resp.json()
                    elif method.upper() == 'POST':
                        async with session.post(url, headers=headers, json=params, timeout=timeout) as resp:
                            data = await resp.json()
                    else:
                        logger.error(f"Unsupported HTTP method: {method}")
                        return []

                if not isinstance(data, dict):
                    logger.error(f"Unexpected KuCoin response type for {endpoint}: {type(data)}")
                    return []

                # KuCoin responses typically wrap with code/data
                if data.get('code') == '200000':
                    payload = data.get('data')
                    # Some endpoints use list at root of data
                    if isinstance(payload, list):
                        return payload
                    if isinstance(payload, dict):
                        return payload  # caller will normalize dict vs list
                    # Some endpoints return paginated objects {items: [...]} or {data: [...]}
                    if 'items' in data:
                        items = data.get('items') or []
                        return items
                    return []
                else:
                    logger.error(f"KuCoin API error for {endpoint}: {data}")
                    return []

            except Exception as e:
                logger.error(f"Direct API call failed for {endpoint}: {e}")
                return []

        except Exception as e:
            logger.error(f"Direct API call failed: {e}")
            return []

    async def get_all_open_futures_orders(self) -> List[Dict[str, Any]]:
        """
        Get all open futures orders from KuCoin.

        Returns:
            List of open order dictionaries
        """
        try:
            if not self.client:
                logger.error("KuCoin client not initialized")
                return []

            futures_service = self.client.get_futures_service()
            order_api = futures_service.get_order_api()

            from kucoin_universal_sdk.generate.futures.order.model_get_order_list_req import GetOrderListReqBuilder

            # Get all open orders using enum for status
            # Some SDK versions may not expose StatusEnum; use cast with literal value
            request = GetOrderListReqBuilder().set_status(cast(Any, "active")).build()
            response = order_api.get_order_list(request)

            orders = []
            if not response:
                logger.info("No open orders found")
                return []

            # Try to get data attribute safely
            order_data_list = []
            resp_any = cast(Any, response)
            if hasattr(resp_any, 'data') and resp_any.data:
                if hasattr(resp_any.data, 'items') and resp_any.data.items:
                    order_data_list = resp_any.data.items
                elif hasattr(resp_any.data, 'data') and resp_any.data.data:
                    order_data_list = resp_any.data.data
            elif hasattr(resp_any, 'items') and resp_any.items:
                order_data_list = resp_any.items

            if not order_data_list:
                logger.info("No open orders found")
                return []

            for order in order_data_list:
                    orders.append({
                        'orderId': getattr(order, 'order_id', getattr(order, 'id', '')),
                        'symbol': getattr(order, 'symbol', ''),
                        'side': getattr(order, 'side', ''),
                        'type': getattr(order, 'type', ''),
                        'status': getattr(order, 'status', ''),
                        'price': float(getattr(order, 'price', 0)) if getattr(order, 'price', None) else None,
                        'origQty': float(getattr(order, 'size', 0)) if getattr(order, 'size', None) else None,
                        'executedQty': float(getattr(order, 'filled_size', 0)) if getattr(order, 'filled_size', None) else None,
                        'timeInForce': getattr(order, 'time_in_force', ''),
                        'time': getattr(order, 'created_at', 0),
                        'updateTime': getattr(order, 'updated_at', 0)
                    })

            logger.info(f"Retrieved {len(orders)} open orders from KuCoin")
            return orders

        except Exception as e:
            logger.error(f"Error getting open orders from KuCoin: {e}")
            return []
