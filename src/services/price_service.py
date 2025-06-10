import logging
import asyncio
from pycoingecko import CoinGeckoAPI
from typing import Optional, Dict
from config import settings as config

logger = logging.getLogger(__name__)

class PriceService:
    def __init__(self):
        self.cg = CoinGeckoAPI()
        self._coin_cache: Dict[str, str] = {}  # symbol -> coin_id cache
        self._last_call = 0

        # Preload common cryptocurrency mappings to avoid incorrect resolutions
        self._common_coins = {
            # Major cryptocurrencies
            "BTC": "bitcoin",
            "ETH": "ethereum",
            "SOL": "solana",
            "BNB": "binancecoin",
            "XRP": "ripple",
            "ADA": "cardano",
            "AVAX": "avalanche-2",
            "DOGE": "dogecoin",
            "DOT": "polkadot",
            "SHIB": "shiba-inu",
            "MATIC": "matic-network",
            "LINK": "chainlink",
            "UNI": "uniswap",
            "ATOM": "cosmos",
            "LTC": "litecoin",
            "XLM": "stellar",
            "ALGO": "algorand",
            "ARB": "arbitrum",
            "FIL": "filecoin",
            "ICP": "internet-computer",
            "TRX": "tron",
            "NEAR": "near",
            "OP": "optimism",
            "APT": "aptos",

            # DeFi & Exchange tokens
            "AAVE": "aave",
            "COMP": "compound-governance-token",
            "MKR": "maker",
            "SNX": "havven",
            "YFI": "yearn-finance",
            "CRV": "curve-dao-token",
            "SUSHI": "sushi",
            "1INCH": "1inch",
            "BAL": "balancer",
            "RUNE": "thorchain",

            # Wrapped tokens
            "WBTC": "wrapped-bitcoin",
            "WETH": "weth",

            # Other popular tokens
            "MANA": "decentraland",
            "SAND": "the-sandbox",
            "APE": "apecoin",
            "LDO": "lido-dao",

            # Stablecoins
            "USDT": "tether",
            "USDC": "usd-coin",
            "BUSD": "binance-usd",
            "DAI": "dai",
            "TUSD": "true-usd",
            "USDD": "usdd",
            "USDP": "paxos-standard",

            # Name variations & full names (to prevent incorrect matches)
            "SOLANA": "solana",
            "ETHEREUM": "ethereum",
            "BITCOIN": "bitcoin",
            "CARDANO": "cardano",
            "DOGECOIN": "dogecoin",
            "SHIBA": "shiba-inu",
            "SHIBAINU": "shiba-inu",
            "SHIBA INU": "shiba-inu",
        }

        # Load preloaded coins into cache
        self._coin_cache.update({k.upper(): v for k, v in self._common_coins.items()})

    async def _rate_limit(self):
        # CoinGecko free tier: 50 calls/minute
        elapsed = asyncio.get_event_loop().time() - self._last_call
        if elapsed < 1.2:  # ~50 calls per minute
            await asyncio.sleep(1.2 - elapsed)
        self._last_call = asyncio.get_event_loop().time()

    async def get_coin_id(self, symbol: str) -> Optional[str]:
        """
        Get coin ID from symbol with improved resolution logic
        Uses preloaded mappings for common coins and falls back to CoinGecko API
        """
        if not symbol:
            logger.error("Empty symbol received")
            return None

        symbol = symbol.upper().strip()

        # High priority check for Solana to ensure it always maps correctly
        if symbol in ["SOL", "SOLANA"]:
            logger.info(f"High-priority match for {symbol} -> solana")
            return "solana"

        # Handle special cases for SHIB token variations
        if symbol in ["SHIB", "SHIBA", "SHIBAINU", "SHIBA-INU"]:
            logger.info(f"Special handling for SHIB token: {symbol} -> shiba-inu")
            return "shiba-inu"

        # Check cache first (includes preloaded common coins)
        if symbol in self._coin_cache:
            logger.info(f"Cache hit: {symbol} -> {self._coin_cache[symbol]}")
            return self._coin_cache[symbol]

        # Common variations/aliases
        normalized_symbol = symbol
        # Remove common prefixes/suffixes
        if symbol.startswith("$"):
            normalized_symbol = symbol[1:]

        # Try alternative name normalizations
        alternatives = [symbol]
        if "." in symbol:  # Handle cases like SOL.X -> SOL
            alternatives.append(symbol.split('.')[0])
        if "-" in symbol:  # Handle cases like SHIBA-INU -> SHIBA
            alternatives.append(symbol.split('-')[0])

        # Check all alternatives
        for alt in alternatives:
            if alt in self._coin_cache:
                coin_id = self._coin_cache[alt]
                # Cache the original symbol too
                self._coin_cache[symbol] = coin_id
                logger.info(f"Alternative match: {symbol} via {alt} -> {coin_id}")
                return coin_id

        # Check normalized symbol in cache
        if normalized_symbol in self._coin_cache:
            coin_id = self._coin_cache[normalized_symbol]
            # Cache the original symbol too
            self._coin_cache[symbol] = coin_id
            logger.info(f"Normalized cache hit: {symbol} -> {coin_id}")
            return coin_id

        # If not in cache, use CoinGecko API
        await self._rate_limit()

        try:
            # Run in thread pool to avoid blocking
            coins_list = await asyncio.get_event_loop().run_in_executor(
                None, self.cg.get_coins_list
            )

            # First pass: Exact symbol match (best match)
            for coin in coins_list:
                if coin['symbol'].upper() == symbol:
                    # Verify this isn't a scam or fake coin
                    if self._is_likely_legitimate_coin(coin):
                        self._coin_cache[symbol] = coin['id']
                        logger.info(f"Exact match: {symbol} -> {coin['id']}")
                        return coin['id']

            # Second pass: Market cap ordered exact symbol match
            # Get market data for all coins with matching symbol
            matching_symbols = [coin for coin in coins_list if coin['symbol'].upper() == symbol]
            if matching_symbols:
                # Get market data for candidates
                try:
                    best_match = await self._get_highest_market_cap_coin(matching_symbols)
                    if best_match:
                        self._coin_cache[symbol] = best_match
                        logger.info(f"Market cap match: {symbol} -> {best_match}")
                        return best_match
                except Exception as e:
                    logger.warning(f"Failed to get market data: {e}")

            # No exact match found
            logger.warning(f"No exact match found for {symbol}")
            return None

        except Exception as e:
            logger.error(f"Failed to resolve coin ID for {symbol}: {e}")
            return None

    def _is_likely_legitimate_coin(self, coin_data: dict) -> bool:
        """Enhanced heuristic to identify legitimate coins vs scams with same symbol"""
        # Check if in our trusted list - exact ID match
        symbol = coin_data['symbol'].upper()
        if symbol in self._coin_cache:
            exact_match = self._coin_cache[symbol] == coin_data['id']
            if exact_match:
                return True
            # If it's in our cache but with different ID, it's a higher bar to pass

        # Major security check: if we have a common symbol and this isn't the expected ID, reject
        if symbol in ["BTC", "ETH", "SOL", "DOGE", "SHIB", "USDT", "USDC"] and self._coin_cache.get(symbol) != coin_data['id']:
            logger.warning(f"Rejecting potential scam impersonating {symbol}: {coin_data['id']}")
            return False

        # Coins with very long names are often scams
        if len(coin_data['name']) > 30:
            return False

        # Coins with overly complex IDs are often scams
        if len(coin_data['id']) > 30:
            return False

        # Check for suspicious strings in IDs that typically indicate scam tokens
        suspicious_fragments = ['fake', 'scam', 'elon', 'moon', 'baby', 'inu', 'doge', 'moon',
                               'pepe', 'safe', 'pump', 'wojak', 'cat', 'fork', 'wrapped']

        # Whitelist actual legitimate projects that might match these patterns
        whitelist = ['dogecoin', 'shiba-inu', 'baby-doge-coin', 'dogelon', 'wrapped-bitcoin',
                    'wrapped-ethereum', 'pepecoin', 'catcoin', 'safemoon']

        if coin_data['id'] in whitelist:
            return True

        for fragment in suspicious_fragments:
            if fragment in coin_data['id'].lower() and coin_data['id'] not in whitelist:
                # Higher bar for suspicious tokens - must have market cap data
                try:
                    has_market_cap = coin_data.get('market_cap_rank') is not None
                    if not has_market_cap:
                        logger.warning(f"Rejecting suspicious token without market cap: {coin_data['id']}")
                        return False
                except:
                    pass

        return True

    async def _get_highest_market_cap_coin(self, coin_candidates: list) -> Optional[str]:
        """Find the coin with highest market cap from candidates with same symbol"""
        if not coin_candidates:
            return None

        # If only one candidate, return it
        if len(coin_candidates) == 1:
            return coin_candidates[0]['id']

        # Get market cap data for each candidate
        await self._rate_limit()
        try:
            ids = [coin['id'] for coin in coin_candidates]
            ids_str = ','.join(ids)

            market_data = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self.cg.get_coins_markets(vs_currency='usd', ids=ids_str)
            )

            if not market_data:
                # If no market data, return first candidate
                return coin_candidates[0]['id']

            # Sort by market cap
            sorted_data = sorted(
                market_data,
                key=lambda x: x.get('market_cap', 0) if x.get('market_cap') else 0,
                reverse=True
            )

            # Return highest market cap coin
            if sorted_data:
                return sorted_data[0]['id']

        except Exception as e:
            logger.warning(f"Error getting market data: {e}")

        # Fallback to first candidate
        return coin_candidates[0]['id']

    async def get_price(self, coin_id: str) -> Optional[float]:
        await self._rate_limit()

        try:
            # Run in thread pool to avoid blocking
            price_data = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self.cg.get_price(ids=coin_id, vs_currencies='usd')
            )

            price = price_data.get(coin_id, {}).get('usd')
            if price:
                logger.info(f"Price for {coin_id}: ${price}")
                return float(price)

        except Exception as e:
            logger.error(f"Failed to get price for {coin_id}: {e}")

        return None

    async def get_coin_price(self, symbol: str) -> Optional[float]:
        """Get price by symbol (combines coin_id lookup and price fetch)"""
        coin_id = await self.get_coin_id(symbol)
        if not coin_id:
            return None
        return await self.get_price(coin_id)