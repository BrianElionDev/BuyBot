import logging
import time
import asyncio
from typing import Dict, Set, Tuple, Optional, Any, Union, Literal
from config import settings as config
from src.services.price_service import PriceService
from src.exchange.yobit_exchange import YoBitExchange

logger = logging.getLogger(__name__)

# Import the new UniswapExchange class
try:
    from src.exchange.uniswap_exchange import UniswapExchange
    UNISWAP_AVAILABLE = True
except ImportError:
    UNISWAP_AVAILABLE = False
    logger.warning("UniswapExchange not available. DEX functionality will be disabled.")

class TradingEngine:
    def __init__(self, loop: Optional[asyncio.AbstractEventLoop] = None):
        """Initialize trading engine with both CEX and DEX support."""
        # Initialize event loop
        self.loop = loop or asyncio.get_event_loop()

        # Initialize price service for CoinGecko
        self.price_service = PriceService()

        # Track trade cooldowns
        self.trade_cooldowns: Dict[str, float] = {}

        # Initialize CEX (YoBit)
        self.yobit_exchange = YoBitExchange()
        logger.info("YoBitExchange initialized")

        # Initialize DEX (Uniswap) if available
        self.uniswap_exchange = None
        if UNISWAP_AVAILABLE:
            try:
                # Only reference UniswapExchange if import succeeded
                if config.INFURA_PROJECT_ID and config.WALLET_PRIVATE_KEY:
                    from src.exchange.uniswap_exchange import UniswapExchange
                    self.uniswap_exchange = UniswapExchange(loop=self.loop)
                    logger.info("UniswapExchange initialized")
                else:
                    logger.warning("Uniswap DEX functionality is not available: missing configuration")
            except Exception as e:
                logger.error(f"Failed to initialize UniswapExchange: {e}")
        else:
            logger.warning("UniswapExchange not available. DEX functionality will be disabled.")

    def _is_cooled_down(self, symbol: str) -> bool:
        """Check if trade cooldown period has passed for the given symbol."""
        last_trade = self.trade_cooldowns.get(symbol, 0)
        return time.time() - last_trade > config.TRADE_COOLDOWN

    async def process_signal(self, coin_symbol: str, signal_price: float,
                           exchange_type: str = "None", sell_coin: str = "None") -> bool:
        """
        Process trading signal and execute trade if conditions are met.

        Args:
            coin_symbol: Symbol of coin to buy (e.g., "DSYNC")
            signal_price: Price from the signal message
            exchange_type: "cex" (YoBit) or "dex" (Uniswap), defaults to config.PREFERRED_EXCHANGE_TYPE
            sell_coin: Symbol of coin to sell (e.g., "ETH", "USDC"), required for DEX trades

        Returns:
            True if trade was successfully processed, False otherwise
        """
        # Use default exchange type if not specified
        if not exchange_type:
            exchange_type = getattr(config, "PREFERRED_EXCHANGE_TYPE", "cex").lower()

        # Validate exchange type
        if exchange_type not in ["cex", "dex"]:
            logger.error(f"Invalid exchange_type: {exchange_type}. Must be 'cex' or 'dex'")
            return False

        # Route to appropriate method
        if exchange_type == "dex":
            if not self.uniswap_exchange:
                logger.error("DEX trading requested but Uniswap exchange is not available")
                return False
            if not sell_coin:
                logger.error("DEX trading requires sell_coin parameter")
                return False
            return await self._process_dex_signal(sell_coin, coin_symbol, signal_price)
        else:  # cex
            return await self._process_cex_signal(coin_symbol, signal_price)

    async def _process_cex_signal(self, coin_symbol: str, signal_price: float) -> bool:
        """Process a trading signal using the centralized exchange (YoBit)."""
        # Check cooldown
        if not self._is_cooled_down(f"cex_{coin_symbol}"):
            logger.info(f"Trade cooldown active for {coin_symbol} on CEX")
            return False

        logger.info(f"Processing CEX signal: {coin_symbol} @ ${signal_price}")

        # Get current market price
        current_price = await self.price_service.get_coin_price(coin_symbol)
        if not current_price:
            logger.error(f"Failed to get price for {coin_symbol}")
            return False

        # Check price difference threshold
        price_diff = abs(current_price - signal_price) / signal_price * 100
        if price_diff > config.PRICE_THRESHOLD:
            logger.warning(f"Price difference too high: {price_diff:.2f}% (threshold: {config.PRICE_THRESHOLD}%)")
            return False

        # Check account balance
        balances = await self.yobit_exchange.get_balance()
        if not balances:
            logger.error("Failed to get account balances from YoBit")
            return False

        usd_balance = balances.get('usd', 0)
        logger.info(f"Available USD balance on YoBit: ${usd_balance}")

        # Calculate trade amount
        trade_amount = min(
            usd_balance * (config.RISK_PERCENTAGE / 100),
            config.MAX_TRADE_AMOUNT
        )

        if trade_amount < config.MIN_TRADE_AMOUNT:
            logger.warning(f"Trade amount ${trade_amount} below minimum ${config.MIN_TRADE_AMOUNT}")
            return False

        # Calculate coin amount to buy
        coin_amount = trade_amount / current_price
        trading_pair = f"{coin_symbol.lower()}_usd"

        # Check if pair exists on YoBit
        pair_info = await self.yobit_exchange.get_pair_info(trading_pair)
        if not pair_info:
            logger.error(f"Trading pair {trading_pair} not available on YoBit")
            return False

        # Execute trade with slippage allowance
        buy_price = current_price * (1 + (config.SLIPPAGE_PERCENTAGE / 100))

        logger.info(f"Executing CEX trade: {coin_amount:.8f} {coin_symbol} @ ${buy_price}")

        order_result = await self.yobit_exchange.create_order(
            pair=trading_pair,
            order_type='buy',
            amount=coin_amount,
            price=buy_price
        )

        if order_result:
            self.trade_cooldowns[f"cex_{coin_symbol}"] = time.time()
            logger.info(f"CEX trade successful for {coin_symbol}")
            return True
        else:
            logger.error(f"CEX trade failed for {coin_symbol}")
            return False

    async def _process_dex_signal(self, sell_coin: str, buy_coin: str, signal_price: float) -> bool:
        """Process a trading signal using the decentralized exchange (Uniswap)."""
        if not self.uniswap_exchange:
            logger.error("Uniswap exchange is not available")
            return False

        # Key for cooldown tracking
        cooldown_key = f"dex_{sell_coin}_{buy_coin}"

        # Check cooldown
        if not self._is_cooled_down(cooldown_key):
            logger.info(f"DEX trade cooldown active for {sell_coin}/{buy_coin}")
            return False

        logger.info(f"Processing DEX signal: Sell {sell_coin} to buy {buy_coin} @ ${signal_price}")

        # Get addresses from the token map
        sell_token_address = config.TOKEN_ADDRESS_MAP.get(sell_coin.upper())
        buy_token_address = config.TOKEN_ADDRESS_MAP.get(buy_coin.upper())

        if not sell_token_address or not buy_token_address:
            logger.error(f"Missing token address mapping for {sell_coin} or {buy_coin}")
            return False

        # Get current market price from CoinGecko
        current_price = await self.price_service.get_coin_price(buy_coin)
        if not current_price:
            logger.error(f"Failed to get CoinGecko price for {buy_coin}")
            return False

        # Check price difference threshold
        price_diff = abs(current_price - signal_price) / signal_price * 100
        if price_diff > config.PRICE_THRESHOLD:
            logger.warning(f"Price difference too high: {price_diff:.2f}% (threshold: {config.PRICE_THRESHOLD}%)")
            return False

        # Determine trade amount based on sell_coin
        trade_amount_usd = config.MIN_TRADE_AMOUNT  # Starting point

        # Get available balance
        eth_price = None  # Ensure eth_price is always defined
        if sell_coin.upper() == "ETH":
            balance = await self.uniswap_exchange.get_eth_balance()
            # Get ETH price in USD
            eth_price = await self.price_service.get_coin_price("ethereum")
            if not eth_price:
                logger.error("Failed to get ETH price, using fixed USD amount")
                balance_usd = 0
            else:
                balance_usd = balance * eth_price
                # Calculate risk-adjusted amount
                trade_amount_usd = min(
                    balance_usd * (config.RISK_PERCENTAGE / 100),
                    config.MAX_TRADE_AMOUNT
                )
        else:
            # For other tokens like USDC
            balance = await self.uniswap_exchange.get_token_balance(sell_token_address)

            # For USDC, assume 1:1 with USD
            if sell_coin.upper() == "USDC":
                balance_usd = balance
                trade_amount_usd = min(
                    balance_usd * (config.RISK_PERCENTAGE / 100),
                    config.MAX_TRADE_AMOUNT
                )
            else:
                # For other tokens, would need price lookup
                token_price = await self.price_service.get_coin_price(sell_coin)
                if token_price:
                    balance_usd = balance * token_price
                    trade_amount_usd = min(
                        balance_usd * (config.RISK_PERCENTAGE / 100),
                        config.MAX_TRADE_AMOUNT
                    )

        # Ensure amount is within limits
        trade_amount_usd = max(trade_amount_usd, config.MIN_TRADE_AMOUNT)
        trade_amount_usd = min(trade_amount_usd, config.MAX_TRADE_AMOUNT)

        logger.info(f"DEX trade amount: ${trade_amount_usd:.2f}")

        # Calculate amount of sell_token to use (in its smallest unit)
        if sell_coin.upper() == "ETH":
            # Convert USD amount to ETH
            sell_amount = trade_amount_usd / eth_price if eth_price else 0
            sell_amount_atomic = int(self.uniswap_exchange.w3.to_wei(sell_amount, 'ether'))
        elif sell_coin.upper() == "USDC":
            # USDC has 6 decimals
            sell_amount = trade_amount_usd
            decimals = await self.uniswap_exchange.get_token_decimals(sell_token_address)
            sell_amount_atomic = int(sell_amount * (10 ** decimals))
        else:
            # Other tokens need price and decimals
            token_price = await self.price_service.get_coin_price(sell_coin)
            decimals = await self.uniswap_exchange.get_token_decimals(sell_token_address)
            sell_amount = trade_amount_usd / token_price if token_price else 0
            sell_amount_atomic = int(sell_amount * (10 ** decimals)) if sell_amount > 0 else 0

        if sell_amount_atomic <= 0:
            logger.error(f"Calculated sell amount is invalid: {sell_amount_atomic}")
            return False

        logger.info(f"Executing DEX swap: {sell_amount_atomic} {sell_coin} -> {buy_coin}")

        # Execute the swap
        swap_success = await self.uniswap_exchange.execute_swap(
            sell_token_address=sell_token_address,
            buy_token_address=buy_token_address,
            amount_in_atomic=sell_amount_atomic,
            slippage_percentage=config.DEX_SLIPPAGE_PERCENTAGE
        )

        if swap_success:
            self.trade_cooldowns[cooldown_key] = time.time()
            logger.info(f"DEX trade successful: {sell_coin}/{buy_coin}")
            return True
        else:
            logger.error(f"DEX trade failed: {sell_coin}/{buy_coin}")
            return False

    async def close(self):
        """Cleanup resources."""
        logger.info("Closing TradingEngine resources")

        # Close YoBit exchange
        if hasattr(self, 'yobit_exchange'):
            await self.yobit_exchange.close()

        # Close Uniswap exchange if initialized
        if hasattr(self, 'uniswap_exchange') and self.uniswap_exchange:
            await self.uniswap_exchange.close()