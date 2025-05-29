import hmac
import hashlib
import urllib.parse
import time
import logging
import aiohttp
from typing import Dict, Any, Optional
from config import settings as config

logger = logging.getLogger(__name__)

class YoBitExchange:
    def __init__(self):
        self.api_key = config.YOBIT_API_KEY
        self.api_secret = config.YOBIT_API_SECRET
        self.base_url = "https://yobit.net/tapi"
        self.public_url = "https://yobit.net/api/3"
        self.session = None

    async def _get_session(self):
        if self.session is None:
            self.session = aiohttp.ClientSession()
        return self.session

    def _generate_signature(self, params: Dict[str, Any]) -> str:
        if not self.api_secret:
            raise ValueError("API secret is not set.")
        params['nonce'] = str(int(time.time()))
        param_str = urllib.parse.urlencode(params)
        return hmac.new(
            self.api_secret.encode('utf-8'),
            param_str.encode('utf-8'),
            hashlib.sha512
        ).hexdigest()

    async def _make_request(self, params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        session = await self._get_session()
        headers = {
            'Key': self.api_key,
            'Sign': self._generate_signature(params)
        }

        try:
            async with session.post(self.base_url, data=params, headers=headers) as response:
                response.raise_for_status()
                data = await response.json()

                if data.get('success') != 1:
                    logger.error(f"YoBit API error: {data.get('error')}")
                    return None
                return data
        except Exception as e:
            logger.error(f"YoBit request failed: {e}")
            return None

    async def get_balance(self) -> Optional[Dict[str, float]]:
        params = {'method': 'getInfo'}
        response = await self._make_request(params)

        if response:
            funds = response.get('return', {}).get('funds', {})
            return {k.lower(): float(v) for k, v in funds.items()}
        return None

    async def create_order(self, pair: str, order_type: str, amount: float, price: float) -> Optional[Dict[str, Any]]:
        if order_type not in ['buy', 'sell']:
            logger.error(f"Invalid order type: {order_type}")
            return None

        params = {
            'method': 'Trade',
            'pair': pair,
            'type': order_type,
            'rate': f"{price:.8f}",
            'amount': f"{amount:.8f}"
        }

        response = await self._make_request(params)
        if response:
            logger.info(f"Order placed: {pair} {order_type} {amount} @ {price}")
            return response.get('return')
        return None

    async def get_pair_info(self, pair: str) -> Optional[Dict[str, Any]]:
        session = await self._get_session()
        try:
            async with session.get(f"{self.public_url}/info") as response:
                response.raise_for_status()
                data = await response.json()
                return data.get('pairs', {}).get(pair)
        except Exception as e:
            logger.error(f"Failed to get pair info: {e}")
            return None

    async def close(self):
        if self.session:
            await self.session.close()