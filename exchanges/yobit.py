import hmac
import hashlib
import json
import urllib.parse
import time
import logging
import aiohttp
from typing import Dict, Any, Optional

from config.settings import settings
from exchanges.base_exchange import BaseExchange

logger = logging.getLogger(__name__)


class YoBitExchange(BaseExchange):
    """
    Handles the Yobit exchange operations
    Uses aiohttp for asynchronous HTTP requests
    """

    def __init__(self):
        self.api_key = settings.YOBBIT_API_KEY
        self.api_secret = settings.YOBIT_API_SECRET
        self.base_url = "https://yobit.net/tapi"
        self.public_url = "https://yobit.net/api/3" # For public info like pair info
        self.session = None # aiohttp ClientSession will be initialized on first use

    async def _get_session(self):
        """Initializes aiohttp ClientSession"""
        if self.session is None:
            self.session = aiohttp.ClientSession()
        return self.session

    async def close_session(self):
        """closes the aiohttp ClientSession"""
        if self.session:
            await self.session.close()
            self.session = None

    def _generate_signature(self, params: Dict[str, Any]) -> str:
        """
        Generates HMAC SHA512 signature for YoBit API requests.
        YoBit's TAPI requires parameters to be URL-encoded before signing.
        """
        # Ensure nonce is a string for URL encoding
        params['nonce'] = str(params['nonce'])
        param_str = urllib.parse.urlencode(params)
        return hmac.new(
            self.api_secret.encode('utf-8'), # Secret must be bytes
            param_str.encode('utf-8'),      # Data must be bytes
            hashlib.sha512
        ).hexdigest()

    async def _make_request(self, method: str, params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Makes an authenticated request to the Yobit API
        """
        session = await self._get_session()
        headers = {
            'Key': self.api_key,
            'Sign': self._generate_signature(params)
        }

        try:
            async with session.post(self.base_url, data=params, headers=headers) as response:
                response.raise_for_status()
                json_response = await response.json()
                if json_response.get('success') == 0:
                    logger.error(f"YoBit API Error: {json_response.get('error', 'uknown error')}")
                    return None
                return json_response
        except aiohttp.ClientError as e:
            logger.error(f"YoBit API network error for method '{method}': {e}")
            return None
        except Exception as e:
            logger.error(f"YoBit API unexpected error for method '{method}': {e}")
            return None

    async def get_balance(self) -> Optional[Dict[str, Any]]:
        """
        Asynchronously retrieves the account balances for all currencies.
        Returns a dictionary where keys are currency symbols (lowercase) and values are available amounts.
        Returns None on failure.
        """
        params = {
            'method': 'getInfo',
            'nonce': int(time.time()) # YoBit nonce is typically a Unix timestamp
        }
        response = await self._make_request('getInfo', params)
        if response and response.get('success') == 1:
            funds = response.get('return', {}).get('funds', {})
            # Convert all fund keys to lowercase for consistency
            return {k.lower(): float(v) for k, v in funds.items()}
        logger.error("Failed to retrieve YoBit balance.")
        return None

    async def create_order(self, pair: str, order_type: str, amount: float, price: float) -> Optional[Dict[str, Any]]:
        """
        Asynchronously creates a buy or sell order on the YoBit exchange.
        YoBit uses 'buy' and 'sell' for order_type.

        Args:
            pair (str): The trading pair (e.g., 'btc_usd').
            order_type (str): The type of order ('buy' or 'sell').
            amount (float): The amount of the base currency to buy/sell.
            price (float): The price at which to place the order.

        Returns:
            Optional[Dict[str, Any]]: A dictionary containing the order details if successful, None otherwise.
        """
        if order_type not in ['buy', 'sell']:
            logger.error(f"Invalid order_type '{order_type}'. Must be 'buy' or 'sell'.")
            return None

        params = {
            'method': 'Trade',
            'pair': pair,
            'type': order_type,
            'rate': f"{price:.8f}", # YoBit often requires specific precision for rate
            'amount': f"{amount:.8f}", # YoBit often requires specific precision for amount
            'nonce': int(time.time())
        }
        response = await self._make_request('Trade', params)
        if response and response.get('success') == 1:
            logger.info(f"YoBit order placed successfully: {response.get('return')}")
            return response.get('return')
        logger.error(f"Failed to place YoBit order for {pair} {order_type} {amount} @ {price}. Response: {response}")
        return None

    async def get_symbol_info(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Asynchronously retrieves information about a specific trading symbol/pair from YoBit's public API.
        This can include minimum trade amounts, precision, etc.
        YoBit's public API uses a different structure.
        """
        session = await self._get_session()
        pair = f"{symbol.lower()}_{settings.BASE_CURRENCY.lower()}"
        try:
            async with session.get(f"{self.public_url}/info") as response:
                response.raise_for_status()
                json_response = await response.json()
                if 'pairs' in json_response:
                    return json_response['pairs'].get(pair)
                logger.warning(f"YoBit public info API response missing 'pairs' key.")
                return None
        except aiohttp.ClientError as e:
            logger.error(f"YoBit public API network error for info: {e}")
            return None
        except Exception as e:
            logger.error(f"YoBit public API unexpected error for info: {e}")
            return None
