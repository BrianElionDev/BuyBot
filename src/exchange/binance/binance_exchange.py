"""
Binance Exchange Implementation

Main Binance exchange class implementing the ExchangeBase interface.
Following Clean Code principles with clear separation of concerns.
"""

import asyncio
import json
import logging
import time
import hmac
import hashlib
from typing import Dict, List, Optional, Tuple, Any
from binance.async_client import AsyncClient
from binance.exceptions import BinanceAPIException
from binance.enums import SIDE_BUY, SIDE_SELL, ORDER_TYPE_MARKET, ORDER_TYPE_LIMIT
from config import settings as cfg
import aiohttp

from ..core.exchange_base import ExchangeBase
from ..core.exchange_config import ExchangeConfig, format_value
from .binance_models import BinanceOrder, BinancePosition, BinanceBalance, BinanceTrade, BinanceIncome


logger = logging.getLogger(__name__)


class BinanceExchange(ExchangeBase):
    """
    Binance exchange implementation.

    Implements the ExchangeBase interface for Binance-specific operations.
    Follows Clean Code principles with clear method names and single responsibilities.
    """

    def __init__(self, api_key: str, api_secret: str, is_testnet: bool = False):
        """
        Initialize Binance exchange.

        Args:
            api_key: Binance API key
            api_secret: Binance API secret
            is_testnet: Whether to use testnet
        """
        self.api_key = api_key
        self.api_secret = api_secret
        self.is_testnet = is_testnet
        self.client: Optional[AsyncClient] = None
        self._spot_symbols: List[str] = []
        self._futures_symbols: List[str] = []

        logger.info(f"BinanceExchange initialized for testnet: {self.is_testnet}")

    async def initialize(self) -> bool:
        """Initialize the exchange connection."""
        try:
            await self._init_client()
            return True
        except Exception as e:
            logger.error(f"Failed to initialize Binance exchange: {e}")
            return False

    async def close(self) -> None:
        """Close the exchange connection and cleanup resources."""
        await self.close_client()

    async def _init_client(self):
        """Initialize the Binance client."""
        if self.client is None:
            self.client = await AsyncClient.create(
                self.api_key,
                self.api_secret,
                tld='com',
                testnet=self.is_testnet
            )

    async def close_client(self):
        """Close the Binance client connection."""
        if self.client:
            await self.client.close_connection()
            logger.info("Binance client connection closed.")

    # Account Operations
    async def get_account_balances(self) -> Dict[str, float]:
        """Get account balances for all assets."""
        await self._init_client()
        assert self.client is not None

        try:
            # Get futures account information
            account_info = await self.client.futures_account()
            balances = {}

            # Extract balance information from account
            for asset_info in account_info.get('assets', []):
                asset = asset_info.get('asset', '')
                wallet_balance = float(asset_info.get('walletBalance', 0))

                if wallet_balance > 0:
                    balances[asset] = wallet_balance

            logger.info(f"Retrieved Binance futures balances: {balances}")
            return balances

        except Exception as e:
            logger.error(f"Error getting futures account balances: {e}")
            return {}

    async def get_futures_account_info(self) -> Dict[str, Any]:
        """Get comprehensive futures account information including leverage settings."""
        await self._init_client()
        assert self.client is not None

        try:
            account_info = await self.client.futures_account()
            return account_info
        except Exception as e:
            logger.error(f"Error getting futures account info: {e}")
            return {}

    async def get_spot_balance(self) -> Dict[str, float]:
        """Get spot account balances."""
        await self._init_client()
        assert self.client is not None

        try:
            account_info = await self.client.get_account()
            balances = {}

            for balance in account_info['balances']:
                asset = balance['asset']
                free = float(balance['free'])
                locked = float(balance['locked'])
                total = free + locked

                if total > 0:
                    balances[asset] = total

            return balances
        except Exception as e:
            logger.error(f"Error getting spot balance: {e}")
            return {}

    # Order Operations
    async def set_futures_leverage(self, symbol: str, leverage: int) -> bool:
        """Set futures leverage for a specific symbol.

        Binance requires leverage to be set per symbol; do this before placing the order.
        """
        await self._init_client()
        assert self.client is not None

        try:
            # Clamp leverage to Binance limits 1..125
            lev = max(1, min(int(leverage), 125))
            result = await self.client.futures_change_leverage(symbol=symbol, leverage=lev)
            try:
                logger.info(f"Set leverage result for {symbol}: {json.dumps(result)}")
            except Exception:
                logger.info(f"Set leverage result for {symbol}: {result}")
            return True
        except BinanceAPIException as e:
            logger.error(f"Binance API error setting leverage for {symbol}: {e.message}")
            return False
        except Exception as e:
            logger.error(f"Error setting leverage for {symbol}: {e}")
            return False

    async def create_futures_order(self, pair: str, side: str, order_type: str,
                                 amount: float, price: Optional[float] = None,
                                 stop_price: Optional[float] = None,
                                 client_order_id: Optional[str] = None,
                                 reduce_only: bool = False,
                                 close_position: bool = False) -> Dict[str, Any]:
        """Create a futures order."""
        await self._init_client()
        assert self.client is not None

        logger.info(f"Creating futures order: {pair} {side} {order_type} {amount}")

        try:
            # Enhanced Precision Handling
            filters = await self.get_futures_symbol_filters(pair)
            if filters:
                lot_size_filter = filters.get('LOT_SIZE', {})
                price_filter = filters.get('PRICE_FILTER', {})
                min_notional_filter = filters.get('MIN_NOTIONAL', {})
                step_size = lot_size_filter.get('stepSize')
                tick_size = price_filter.get('tickSize')
                min_qty = float(lot_size_filter.get('minQty', 0))
                max_qty = float(lot_size_filter.get('maxQty', float('inf')))
                min_notional = float(min_notional_filter.get('notional', 0) or min_notional_filter.get('minNotional', 0))

                # Validate quantity bounds
                if amount < min_qty:
                    return {'error': f'Quantity {amount} below minimum {min_qty} for {pair}', 'code': -4005}
                if amount > max_qty:
                    return {'error': f'Quantity {amount} above maximum {max_qty} for {pair}', 'code': -4006}

                # Format quantity and price with proper precision
                if step_size:
                    amount = float(format_value(amount, step_size))
                if price and tick_size:
                    price = float(format_value(price, tick_size))
                if stop_price and tick_size:
                    stop_price = float(format_value(stop_price, tick_size))

                # Validate minimum notional using a reference price
                ref_price = None
                if order_type.upper() == 'MARKET':
                    # For MARKET orders: mark price fetch is mandatory
                    try:
                        ref_price = await self.get_futures_mark_price(pair)
                        if not ref_price or ref_price <= 0:
                            logger.error(f"Failed to fetch mark price for MARKET order validation on {pair}")
                            return {'error': f"Cannot validate notional value: mark price unavailable for {pair}. Please retry.", 'code': -4165}
                    except Exception as e:
                        logger.error(f"Exception while fetching mark price for MARKET order on {pair}: {e}")
                        return {'error': f"Cannot validate notional value: failed to fetch mark price for {pair}. Please retry.", 'code': -4165}
                elif price:
                    # For LIMIT orders: use provided price
                    ref_price = price

                # Validate notional if we have a valid price and minimum notional requirement
                if min_notional and min_notional > 0 and ref_price and ref_price > 0:
                    notional_value = float(amount) * float(ref_price)
                    if notional_value < min_notional:
                        return {'error': f"Order's notional must be no smaller than {min_notional}", 'code': -4164}
            # Prepare order parameters
            order_params = {
                'symbol': pair,
                'side': side,
                'type': order_type,
                'quantity': amount,
                'reduceOnly': reduce_only,
                'closePosition': close_position
            }

            # Add timeInForce for LIMIT orders (GTC by default; allow GTX post-only via config)
            if order_type.upper() == 'LIMIT':
                post_only = bool(getattr(cfg, 'BINANCE_POST_ONLY', False))
                order_params['timeInForce'] = 'GTX' if post_only else 'GTC'
            elif order_type.upper() in ('STOP_MARKET', 'TAKE_PROFIT_MARKET', 'STOP', 'TAKE_PROFIT'):
                # STOP_MARKET and TAKE_PROFIT_MARKET orders should use GTC, not GTX
                # GTX (post-only) causes EXPIRE_MAKER errors for trigger orders
                order_params['timeInForce'] = 'GTC'

            if price:
                # Robust maker-side pricing using N tick offset and optional post-only
                safe_price = price
                try:
                    if order_type.upper() == 'LIMIT' and not reduce_only:
                        depth = await self.client.futures_order_book(symbol=pair, limit=5)
                        bids = depth.get('bids') or [] if isinstance(depth, dict) else []
                        asks = depth.get('asks') or [] if isinstance(depth, dict) else []
                        best_bid = float(bids[0][0]) if bids else 0.0
                        best_ask = float(asks[0][0]) if asks else 0.0

                        # Fetch tick size; fall back to very small fraction if unavailable
                        filters = None
                        tick_size = 0.0
                        try:
                            filters = await self.get_futures_symbol_filters(pair)
                            if filters and filters.get('PRICE_FILTER', {}).get('tickSize'):
                                tick_size = float(filters['PRICE_FILTER']['tickSize'])
                        except Exception:
                            tick_size = 0.0

                        if tick_size <= 0:
                            baseline = best_bid or best_ask or price
                            tick_size = max(1e-8, baseline * 1e-8)

                        # Configurable maker offset (in ticks)
                        tick_offset = int(getattr(cfg, 'BINANCE_MAKER_TICK_OFFSET', 3))
                        offset = tick_size * max(1, tick_offset)

                        if side.upper() == 'BUY':
                            # Ensure strictly below best bid by offset when crossing or through the book
                            if (best_ask > 0 and price >= best_ask) or (best_bid > 0 and price > best_bid):
                                candidate = best_bid - offset if best_bid > 0 else price - offset
                                safe_price = candidate if candidate > 0 else price
                        elif side.upper() == 'SELL':
                            # Ensure strictly above best ask by offset when crossing or through the book
                            if (best_bid > 0 and price <= best_bid) or (best_ask > 0 and price < best_ask):
                                candidate = best_ask + offset if best_ask > 0 else price + offset
                                safe_price = candidate if candidate > 0 else price

                        # Respect tick formatting when known
                        if filters and filters.get('PRICE_FILTER', {}).get('tickSize'):
                            safe_price = float(format_value(safe_price, filters['PRICE_FILTER']['tickSize']))

                        try:
                            logger.info(
                                f"Maker-preflight {pair}: side={side} orig={price} safe={safe_price} "
                                f"bid={best_bid} ask={best_ask} tick={tick_size} ticks={tick_offset}"
                            )
                        except Exception:
                            pass
                except Exception:
                    safe_price = price

                order_params['price'] = safe_price
            if stop_price:
                order_params['stopPrice'] = stop_price
                # For trigger orders (STOP/TAKE_PROFIT variants), prefer MARK_PRICE working type
                try:
                    if str(order_type).upper() in ('STOP_MARKET', 'TAKE_PROFIT_MARKET', 'STOP', 'TAKE_PROFIT'):
                        order_params['workingType'] = 'MARK_PRICE'
                except Exception:
                    pass
            if client_order_id:
                order_params['newClientOrderId'] = client_order_id

            # Create the order
            result = await self.client.futures_create_order(**order_params)
            try:
                logger.info(f"Raw Binance order response: {json.dumps(result)}")
            except Exception:
                logger.info(f"Raw Binance order response (non-JSON-serializable): {result}")
            if 'orderId' not in result:
                raise ValueError(f"Missing orderId in response: {result}")
            logger.info(f"Futures order created successfully: {result.get('orderId')}")
            return result

        except BinanceAPIException as e:
            error_msg = f"Binance API error creating futures order: {e.message}"
            logger.error(error_msg)
            return {'error': error_msg, 'code': e.code}
        except Exception as e:
            error_msg = f"Error creating futures order: {e}"
            logger.error(error_msg)
            return {'error': error_msg, 'code': -1}

    async def create_algo_order(
        self,
        pair: str,
        side: str,
        order_type: str,
        quantity: float,
        stop_price: float,
        reduce_only: bool = False,
        client_order_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create an algo order (STOP_MARKET, TAKE_PROFIT_MARKET) using Binance Algo Order API.

        Binance requires STOP_MARKET and TAKE_PROFIT_MARKET orders to use the algo order endpoint
        instead of the regular order endpoint.

        Args:
            pair: Trading pair symbol
            side: Order side (BUY/SELL)
            order_type: Order type (STOP_MARKET, TAKE_PROFIT_MARKET)
            quantity: Order quantity
            stop_price: Stop price (trigger price)
            reduce_only: Whether order should only reduce position
            client_order_id: Custom order ID

        Returns:
            Dict containing order response or error information
        """
        await self._init_client()
        assert self.client is not None

        logger.info(f"Creating algo order: {pair} {side} {order_type} {quantity} @ {stop_price}")

        try:
            filters = await self.get_futures_symbol_filters(pair)
            if filters:
                lot_size_filter = filters.get('LOT_SIZE', {})
                price_filter = filters.get('PRICE_FILTER', {})
                step_size = lot_size_filter.get('stepSize')
                tick_size = price_filter.get('tickSize')
                min_qty = float(lot_size_filter.get('minQty', 0))
                max_qty = float(lot_size_filter.get('maxQty', float('inf')))

                if quantity < min_qty:
                    return {'error': f'Quantity {quantity} below minimum {min_qty} for {pair}', 'code': -4005}
                if quantity > max_qty:
                    return {'error': f'Quantity {quantity} above maximum {max_qty} for {pair}', 'code': -4006}

                if step_size:
                    quantity = float(format_value(quantity, step_size))
                if stop_price and tick_size:
                    stop_price = float(format_value(stop_price, tick_size))

            algo_params = {
                'symbol': pair,
                'side': side,
                'type': order_type,
                'quantity': quantity,
                'stopPrice': stop_price,
                'reduceOnly': reduce_only,
                'workingType': 'MARK_PRICE',
                'timeInForce': 'GTC'
            }

            if client_order_id:
                algo_params['newClientOrderId'] = client_order_id

            base_url = 'https://testnet.binancefuture.com' if self.is_testnet else 'https://fapi.binance.com'
            endpoint = '/fapi/v1/algoOrder'
            url = f"{base_url}{endpoint}"

            timestamp = int(time.time() * 1000)
            algo_params['timestamp'] = timestamp

            query_string = '&'.join([f"{k}={v}" for k, v in sorted(algo_params.items())])
            signature = hmac.new(
                self.api_secret.encode('utf-8'),
                query_string.encode('utf-8'),
                hashlib.sha256
            ).hexdigest()

            headers = {
                'X-MBX-APIKEY': self.api_key,
                'Content-Type': 'application/x-www-form-urlencoded'
            }

            payload = f"{query_string}&signature={signature}"

            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, data=payload, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                    if resp.status != 200:
                        error_text = await resp.text()
                        try:
                            error_data = await resp.json()
                            error_msg = error_data.get('msg', error_text)
                            error_code = error_data.get('code', -1)
                        except:
                            error_msg = error_text
                            error_code = -1
                        raise BinanceAPIException(response=None, status_code=resp.status, message=error_msg, code=error_code)

                    result = await resp.json()

            try:
                logger.info(f"Raw Binance algo order response: {json.dumps(result)}")
            except Exception:
                logger.info(f"Raw Binance algo order response (non-JSON-serializable): {result}")

            if 'algoId' in result:
                result['orderId'] = result['algoId']
                logger.info(f"Algo order created successfully: {result.get('algoId')}")
            elif 'orderId' in result:
                logger.info(f"Algo order created successfully: {result.get('orderId')}")
            else:
                raise ValueError(f"Missing algoId/orderId in response: {result}")

            return result

        except BinanceAPIException as e:
            if e.code == -4120:
                logger.warning(f"Binance returned -4120 (algo endpoint required), but we're already using algo parameters. Error: {e.message}")
            error_msg = f"Binance API error creating algo order: {e.message}"
            logger.error(error_msg)
            return {'error': error_msg, 'code': e.code}
        except Exception as e:
            error_msg = f"Error creating algo order: {e}"
            logger.error(error_msg)
            return {'error': error_msg, 'code': -1}

    async def cancel_futures_order(self, pair: str, order_id: str) -> Tuple[bool, Dict[str, Any]]:
        """Cancel a futures order."""
        await self._init_client()
        assert self.client is not None

        try:
            result = await self.client.futures_cancel_order(symbol=pair, orderId=order_id)
            try:
                logger.info(f"Raw Binance cancel response: {json.dumps(result)}")
            except Exception:
                logger.info(f"Raw Binance cancel response (non-JSON-serializable): {result}")
            if isinstance(result, dict) and 'code' in result and result.get('code') != 200:
                raise ValueError(f"Cancel failed: {result.get('msg', result)}")
            logger.info(f"Futures order cancelled successfully: {order_id}")
            return True, result
        except BinanceAPIException as e:
            error_msg = f"Binance API error cancelling futures order: {e.message}"
            logger.error(error_msg)
            return False, {'error': error_msg, 'code': e.code}
        except Exception as e:
            error_msg = f"Error cancelling futures order: {e}"
            logger.error(error_msg)
            return False, {'error': error_msg, 'code': -1}

    async def get_order_status(self, pair: str, order_id: str) -> Optional[Dict[str, Any]]:
        """Get order status."""
        await self._init_client()
        assert self.client is not None

        try:
            result = await self.client.futures_get_order(symbol=pair, orderId=order_id)
            return result
        except BinanceAPIException as e:
            logger.error(f"Binance API error getting order status: {e.message}")
            return None
        except Exception as e:
            logger.error(f"Error getting order status: {e}")
            return None

    # Position Operations
    async def get_futures_position_information(self) -> List[Dict[str, Any]]:
        """Get all futures positions with comprehensive information."""
        await self._init_client()
        assert self.client is not None

        try:
            # Get comprehensive account information which includes positions with leverage
            account_info = await self.client.futures_account()
            positions = account_info.get('positions', [])

            # Filter out positions with zero size and format the data
            active_positions = []
            for position in positions:
                position_amt = float(position.get('positionAmt', 0))
                if position_amt != 0:  # Only include active positions
                    # Ensure all required fields are present with proper types
                    formatted_position = {
                        'symbol': position.get('symbol', ''),
                        'positionAmt': position_amt,
                        'entryPrice': float(position.get('entryPrice', 0)),
                        'markPrice': float(position.get('markPrice', 0)),
                        'unRealizedProfit': float(position.get('unRealizedProfit', 0)),
                        'liquidationPrice': float(position.get('liquidationPrice', 0)),
                        'leverage': int(position.get('leverage', 1)),
                        'marginType': position.get('marginType', 'isolated'),
                        'isolatedMargin': float(position.get('isolatedMargin', 0)),
                        'isAutoAddMargin': position.get('isAutoAddMargin', False),
                        'positionSide': position.get('positionSide', 'BOTH'),
                        'notional': float(position.get('notional', 0)),
                        'isolatedWallet': float(position.get('isolatedWallet', 0)),
                        'updateTime': position.get('updateTime', 0)
                    }
                    active_positions.append(formatted_position)

            logger.info(f"Retrieved {len(active_positions)} active positions from Binance")
            return active_positions

        except Exception as e:
            logger.error(f"Error getting futures positions: {e}")
            return []

    async def close_position(self, pair: str, amount: float,
                           position_type: str) -> Tuple[bool, Dict[str, Any]]:
        """Close a futures position."""
        side = SIDE_SELL if position_type.upper() == 'LONG' else SIDE_BUY

        try:
            success, result = await self.create_futures_order(
                pair=pair,
                side=side,
                order_type=ORDER_TYPE_MARKET,
                amount=amount,
                reduce_only=True
            )
            return bool(success), result if isinstance(result, dict) else {'error': str(result)}
        except Exception as e:
            return False, {'error': str(e)}

    # Market Data
    async def get_current_prices(self, symbols: List[str]) -> Dict[str, float]:
        """Get current prices for symbols."""
        await self._init_client()
        assert self.client is not None

        try:
            tickers = await self.client.futures_ticker()
            prices = {}

            for ticker in tickers:
                symbol = ticker['symbol']
                if symbol in symbols:
                    prices[symbol] = float(ticker['lastPrice'])

            return prices
        except Exception as e:
            logger.error(f"Error getting current prices: {e}")
            return {}

    async def get_order_book(self, symbol: str, limit: int = 5) -> Optional[Dict[str, Any]]:
        """Get order book for a symbol."""
        await self._init_client()
        assert self.client is not None

        try:
            result = await self.client.futures_order_book(symbol=symbol, limit=limit)
            return result
        except Exception as e:
            logger.error(f"Error getting order book: {e}")
            return None

    # Symbol Information
    async def get_futures_symbol_filters(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get symbol filters for futures trading."""
        await self._init_client()
        assert self.client is not None

        try:
            exchange_info = await self.client.futures_exchange_info()

            for symbol_info in exchange_info['symbols']:
                if symbol_info['symbol'] == symbol:
                    filters = {}
                    for filter_info in symbol_info['filters']:
                        filters[filter_info['filterType']] = filter_info
                    return filters

            return None
        except Exception as e:
            logger.error(f"Error getting futures symbol filters: {e}")
            return None

    async def is_futures_symbol_supported(self, symbol: str) -> bool:
        """Check if symbol is supported for futures trading using dynamic validation."""
        try:
            # Import here to avoid circular imports
            from src.core.dynamic_symbol_validator import dynamic_validator

            # Use dynamic validation with caching
            is_supported = await dynamic_validator.is_symbol_supported(
                symbol=symbol,
                exchange='binance',
                exchange_client=self,
                trading_type='futures'
            )

            return is_supported

        except Exception as e:
            logger.error(f"Error in dynamic symbol validation for {symbol}: {e}")

            # Final fallback: check if symbol exists in exchange info
            try:
                filters = await self.get_futures_symbol_filters(symbol)
                return filters is not None
            except Exception as fallback_error:
                logger.error(f"All validation methods failed for {symbol}: {fallback_error}")
                return False

    # Trade History
    async def get_user_trades(self, symbol: str = "", limit: int = 1000,
                            from_id: int = 0, start_time: int = 0,
                            end_time: int = 0) -> List[Dict[str, Any]]:
        """Get user trade history."""
        await self._init_client()
        assert self.client is not None

        try:
            params: dict[str, int | str] = {'limit': limit}
            if symbol:
                params['symbol'] = symbol
            if from_id > 0:
                params['fromId'] = from_id
            if start_time > 0:
                params['startTime'] = start_time
            if end_time > 0:
                params['endTime'] = end_time

            result = await self.client.futures_account_trades(**params)
            return list(result)
        except Exception as e:
            logger.error(f"Error getting user trades: {e}")
            return []

    async def get_income_history(self, symbol: str = "", income_type: str = "",
                               start_time: int = 0, end_time: int = 0,
                               limit: int = 1000) -> List[Dict[str, Any]]:
        """Get income history (fees, funding, etc.)."""
        await self._init_client()
        assert self.client is not None

        try:
            params: dict[str, int | str] = {'limit': limit}
            if symbol:
                params['symbol'] = symbol
            if income_type:
                params['incomeType'] = income_type
            if start_time > 0:
                params['startTime'] = start_time
            if end_time > 0:
                params['endTime'] = end_time

            result = await self.client.futures_income_history(**params)
            return list(result)
        except Exception as e:
            logger.error(f"Error getting income history: {e}")
            return []

    # Additional methods for backward compatibility
    async def get_position_risk(self, symbol: str = "") -> List[Dict[str, Any]]:
        """Get position risk information (alias for get_futures_position_information)."""
        return await self.get_futures_position_information()

    async def get_positions(self, symbol: str = "") -> List[Dict[str, Any]]:
        """Get positions for a specific symbol or all positions."""
        positions = await self.get_futures_position_information()
        if symbol:
            return [pos for pos in positions if pos.get('symbol') == symbol]
        return positions

    async def get_futures_mark_price(self, symbol: str) -> Optional[float]:
        """Get futures mark price for a symbol."""
        await self._init_client()
        assert self.client is not None

        try:
            result = await self.client.futures_mark_price(symbol=symbol)
            return float(result.get('markPrice', 0))
        except Exception as e:
            logger.error(f"Error getting futures mark price: {e}")
            return None

    async def get_all_open_futures_orders(self) -> List[Dict[str, Any]]:
        """Get all open futures orders."""
        await self._init_client()
        assert self.client is not None

        try:
            result = await self.client.futures_get_open_orders()
            return list(result)
        except Exception as e:
            logger.error(f"Error getting open futures orders: {e}")
            return []
    async def get_exchange_info(self) -> Optional[Dict[str, Any]]:
        """Get exchange information including symbol details."""
        await self._init_client()
        assert self.client is not None

        try:
            result = await self.client.futures_exchange_info()
            return result
        except Exception as e:
            logger.error(f"Error getting exchange info: {e}")
            return None

    async def futures_exchange_info(self) -> Optional[Dict[str, Any]]:
        """Get futures exchange information (alias for get_exchange_info for compatibility)."""
        return await self.get_exchange_info()

    async def calculate_min_max_market_order_quantity(self, symbol: str) -> Tuple[float, float]:
        """Calculate minimum and maximum market order quantities for a symbol."""
        await self._init_client()
        assert self.client is not None

        try:
            # Get symbol filters
            filters = await self.get_futures_symbol_filters(symbol)
            if not filters:
                logger.error(f"Could not get filters for {symbol}")
                return 0.0, float('inf')

            # Extract lot size filter
            lot_size_filter = filters.get('LOT_SIZE', {})
            min_qty = float(lot_size_filter.get('minQty', 0))
            max_qty = float(lot_size_filter.get('maxQty', float('inf')))

            return min_qty, max_qty
        except Exception as e:
            logger.error(f"Error calculating min/max quantities for {symbol}: {e}")
            return 0.0, float('inf')

    def get_futures_trading_pair(self, coin_symbol: str) -> str:
        """Get the futures trading pair for a coin symbol."""
        # Convert coin symbol to uppercase and append USDT
        return f"{coin_symbol.upper()}USDT"

