import logging
import time
import asyncio
from typing import Dict, Set, Tuple, Optional, Any, Union, Literal
from config import settings as config
from src.services.price_service import PriceService
from src.exchange.binance_exchange import BinanceExchange

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

        # Initialize CEX (Binance)
        self.binance_exchange = BinanceExchange()
        logger.info("BinanceExchange initialized")

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
                           exchange_type: str = "None", sell_coin: str = "None") -> Tuple[bool, Optional[str]]:
        """
        Process trading signal and execute trade if conditions are met.

        Args:
            coin_symbol: Symbol of coin to buy (e.g., "DSYNC")
            signal_price: Price from the signal message
            exchange_type: "cex" (Binance) or "dex" (Uniswap), defaults to config.PREFERRED_EXCHANGE_TYPE
            sell_coin: Symbol of coin to sell (e.g., "ETH", "USDC"), required for DEX trades

        Returns:
            A tuple of (bool, Optional[str]) indicating success and a reason for failure
        """
        # Use default exchange type if not specified
        if not exchange_type:
            exchange_type = getattr(config, "PREFERRED_EXCHANGE_TYPE", "cex").lower()

        # Validate exchange type
        if exchange_type not in ["cex", "dex"]:
            reason = f"Invalid exchange_type: {exchange_type}. Must be 'cex' or 'dex'"
            logger.error(reason)
            return False, reason

        # Route to appropriate method
        if exchange_type == "dex":
            if not self.uniswap_exchange:
                reason = "DEX trading requested but Uniswap exchange is not available"
                logger.error(reason)
                return False, reason
            if not sell_coin:
                reason = "DEX trading requires sell_coin parameter"
                logger.error(reason)
                return False, reason
            return await self._process_dex_signal(sell_coin, coin_symbol, signal_price)
        else:  # cex
            return await self._process_cex_signal(coin_symbol, signal_price)

    async def _process_cex_signal(self, coin_symbol: str, signal_price: float) -> Tuple[bool, Optional[str]]:
        """Process a trading signal using the centralized exchange (Binance)."""
        # Check cooldown
        if not self._is_cooled_down(f"cex_{coin_symbol}"):
            reason = f"Trade cooldown active for {coin_symbol} on CEX"
            logger.info(reason)
            return False, reason

        logger.info(f"Processing CEX signal: {coin_symbol} @ ${signal_price}")

        # Get current market price
        current_price = await self.price_service.get_coin_price(coin_symbol)
        if not current_price:
            reason = f"Failed to get price for {coin_symbol}"
            logger.error(reason)
            return False, reason

        # Check price difference threshold
        price_diff = abs(current_price - signal_price) / signal_price * 100
        if price_diff > config.PRICE_THRESHOLD:
            reason = f"Price difference too high: {price_diff:.2f}% (threshold: {config.PRICE_THRESHOLD}%)"
            logger.warning(reason)
            return False, reason

        # Check account balance
        balances = await self.binance_exchange.get_balance()
        if not balances:
            reason = "Failed to get account balances from Binance"
            logger.error(reason)
            return False, reason

        usdt_balance = balances.get('usdt', 0)
        logger.info(f"Available USDT balance on Binance: ${usdt_balance}")

        # Calculate trade amount
        trade_amount = min(
            usdt_balance * (config.RISK_PERCENTAGE / 100),
            config.MAX_TRADE_AMOUNT
        )

        if trade_amount < config.MIN_TRADE_AMOUNT:
            reason = f"Trade amount ${trade_amount:.2f} below minimum ${config.MIN_TRADE_AMOUNT}"
            logger.warning(reason)
            return False, reason

        # Calculate coin amount to buy
        coin_amount = trade_amount / current_price
        trading_pair = f"{coin_symbol.lower()}_usdt"

        # Check if pair exists on Binance
        pair_info = await self.binance_exchange.get_pair_info(trading_pair)
        if not pair_info:
            reason = f"Trading pair {trading_pair} not available on Binance"
            logger.error(reason)
            return False, reason

        # Execute trade with slippage allowance
        buy_price = current_price * (1 + (config.SLIPPAGE_PERCENTAGE / 100))

        logger.info(f"Executing CEX trade: {coin_amount:.8f} {coin_symbol} @ ${buy_price}")

        order_result = await self.binance_exchange.create_order(
            pair=trading_pair,
            order_type='buy',
            amount=coin_amount,
            price=buy_price
        )

        if order_result:
            self.trade_cooldowns[f"cex_{coin_symbol}"] = time.time()
            logger.info(f"CEX trade successful for {coin_symbol}")
            return True, None
        else:
            reason = f"CEX trade failed for {coin_symbol}"
            logger.error(reason)
            return False, reason

    async def _process_dex_signal(self, sell_coin: str, buy_coin: str, signal_price: float) -> Tuple[bool, Optional[str]]:
        """Process a trading signal using the decentralized exchange (Uniswap)."""
        if not self.uniswap_exchange:
            reason = "Uniswap exchange is not available"
            logger.error(reason)
            return False, reason

        # Key for cooldown tracking
        cooldown_key = f"dex_{sell_coin}_{buy_coin}"

        # Check cooldown
        if not self._is_cooled_down(cooldown_key):
            reason = f"DEX trade cooldown active for {sell_coin}/{buy_coin}"
            logger.info(reason)
            return False, reason

        logger.info(f"Processing DEX signal: Sell {sell_coin} to buy {buy_coin} @ ${signal_price}")

        # Get addresses from the token map
        sell_token_address = config.TOKEN_ADDRESS_MAP.get(sell_coin.upper())
        buy_token_address = config.TOKEN_ADDRESS_MAP.get(buy_coin.upper())

        if not sell_token_address or not buy_token_address:
            reason = f"Missing token address mapping for {sell_coin} or {buy_coin}"
            logger.error(reason)
            return False, reason

        # Get current market price from CoinGecko
        current_price = await self.price_service.get_coin_price(buy_coin)
        if not current_price:
            reason = f"Failed to get CoinGecko price for {buy_coin}"
            logger.error(reason)
            return False, reason

        # Check price difference threshold
        price_diff = abs(current_price - signal_price) / signal_price * 100
        if price_diff > config.PRICE_THRESHOLD:
            reason = f"Price difference too high: {price_diff:.2f}% (threshold: {config.PRICE_THRESHOLD}%)"
            logger.warning(reason)
            return False, reason

        # Determine trade amount based on sell_coin
        trade_amount_usd = config.MIN_TRADE_AMOUNT  # Starting point

        # Get available balance
        eth_price = None
        if sell_coin.upper() == "ETH":
            balance = await self.uniswap_exchange.get_eth_balance()
            # Get ETH price in USD
            eth_price = await self.price_service.get_coin_price("ethereum")
            if not eth_price:
                reason = "Failed to get ETH price, using fixed USD amount"
                logger.error(reason)
                return False, reason

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
                else:
                    reason = f"Could not determine price for {sell_coin}"
                    logger.error(reason)
                    return False, reason

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
            if not token_price or not decimals:
                reason = f"Could not get price or decimals for {sell_coin}"
                logger.error(reason)
                return False, reason
            sell_amount = trade_amount_usd / token_price if token_price else 0
            sell_amount_atomic = int(sell_amount * (10 ** decimals)) if sell_amount > 0 else 0

        if sell_amount_atomic <= 0:
            reason = f"Calculated sell amount is invalid: {sell_amount_atomic}"
            logger.error(reason)
            return False, reason

        logger.info(f"Executing DEX swap: {sell_amount_atomic} {sell_coin} -> {buy_coin}")

        # Execute the swap
        swap_success, swap_reason = await self.uniswap_exchange.execute_swap(
            sell_token_address=sell_token_address,
            buy_token_address=buy_token_address,
            amount_in_atomic=sell_amount_atomic,
            slippage_percentage=config.DEX_SLIPPAGE_PERCENTAGE
        )

        if swap_success:
            self.trade_cooldowns[cooldown_key] = time.time()
            logger.info(f"DEX trade successful: {sell_coin}/{buy_coin}")
            return True, None
        else:
            logger.error(f"DEX trade failed: {swap_reason}")
            return False, swap_reason

    def get_price_threshold(self) -> float:
        """Returns the configured price threshold."""
        return config.PRICE_THRESHOLD

    async def get_wallet_balances(self) -> Dict[str, float]:
        """
        Get current wallet balances for ETH and USDC.

        Returns:
            A dictionary with 'eth' and 'usdc' balances.
        """
        balances = {'eth': 0.0, 'usdc': 0.0}
        if self.uniswap_exchange:
            try:
                eth_balance = await self.uniswap_exchange.get_eth_balance()
                usdc_address = config.TOKEN_ADDRESS_MAP.get("USDC")
                usdc_balance = 0.0
                if usdc_address:
                    usdc_balance = await self.uniswap_exchange.get_token_balance(usdc_address)

                balances['eth'] = eth_balance
                balances['usdc'] = usdc_balance
            except Exception as e:
                logger.error(f"Failed to get wallet balances: {e}")
        return balances

    async def get_all_wallet_balances(self) -> Dict[str, float]:
        """
        Get current wallet balances for all known tokens with a non-zero balance.

        Returns:
            A dictionary with token symbols and their balances.
        """
        balances = {}
        if self.uniswap_exchange:
            try:
                # Get ETH balance first
                eth_balance = await self.uniswap_exchange.get_eth_balance()
                if eth_balance > 0:
                    balances['eth'] = eth_balance

                # Get balances for all tokens in the map
                for symbol, address in config.TOKEN_ADDRESS_MAP.items():
                    # Skip WETH as we already have ETH
                    if symbol.upper() == 'WETH':
                        continue

                    try:
                        token_balance = await self.uniswap_exchange.get_token_balance(address)
                        # Only include tokens with a balance greater than 0
                        if token_balance > 0:
                            balances[symbol.lower()] = token_balance
                    except Exception as e:
                        logger.error(f"Failed to get balance for {symbol}: {e}")

            except Exception as e:
                logger.error(f"Failed to get all wallet balances: {e}")
        return balances

    async def check_wallet_connection(self) -> bool:
        """
        Verify wallet connection and log initial balances.
        """
        if self.uniswap_exchange:
            try:
                logger.info("[WALLET] Checking wallet connection and balance...")

                # Check ETH balance
                eth_balance = await self.uniswap_exchange.get_eth_balance()
                logger.info(f"[WALLET] ETH Balance: {eth_balance:.6f} ETH")

                if eth_balance < config.MIN_ETH_BALANCE:
                    logger.warning(f"[WALLET] ⚠️ ETH balance is low ({eth_balance:.6f} ETH). May cause transaction failures.")
                else:
                    logger.info(f"[WALLET] ⚡ Limited ETH balance ({eth_balance:.6f} ETH) - sufficient for a few transactions")

                # Check wallet address
                wallet_address = self.uniswap_exchange.wallet_address
                logger.info(f"[WALLET] Wallet Address: {wallet_address}")

                # Check connection status (block number)
                block_number = await self.uniswap_exchange._run_in_executor(self.uniswap_exchange.w3.eth.get_block_number)
                logger.info(f"[WALLET] Connected to Ethereum - Latest block: {block_number}")

                # Check USDC and WETH balances
                usdc_address = config.TOKEN_ADDRESS_MAP.get("USDC")
                if usdc_address:
                    usdc_balance = await self.uniswap_exchange.get_token_balance(usdc_address)
                    logger.info(f"[WALLET] USDC Balance: {usdc_balance:.6f}")

                weth_address = config.TOKEN_ADDRESS_MAP.get("WETH")
                if weth_address:
                    weth_balance = await self.uniswap_exchange.get_token_balance(weth_address)
                    logger.info(f"[WALLET] WETH Balance: {weth_balance:.6f}")

                logger.info("[WALLET] ✅ Wallet connection verified successfully")
                return True
            except Exception as e:
                logger.error(f"[WALLET] ❌ Wallet connection check failed: {e}")
                return False
        return False

    async def close(self):
        """Close connections for all exchanges."""
        logger.info("Closing TradingEngine resources")

        # Close Binance exchange
        if hasattr(self, 'binance_exchange'):
            await self.binance_exchange.close()

        # Close Uniswap exchange if initialized
        if hasattr(self, 'uniswap_exchange') and self.uniswap_exchange:
            await self.uniswap_exchange.close()