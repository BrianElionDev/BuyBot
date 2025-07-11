import logging
import time
import asyncio
from typing import Dict, Set, Tuple, Optional, Any, Union, Literal, List
from config import settings as config
from config.settings import reload_env  # Import the reload function
from src.services.price_service import PriceService
from src.exchange.binance_exchange import BinanceExchange
from src.exchange.uniswap_exchange import UniswapExchange
from datetime import datetime
from config.settings import TRADE_AMOUNT, SLIPPAGE_PERCENTAGE, MIN_ETH_BALANCE, PRICE_THRESHOLD, TOKEN_ADDRESS_MAP
from binance.enums import (FUTURE_ORDER_TYPE_MARKET, FUTURE_ORDER_TYPE_STOP_MARKET,
                           ORDER_TYPE_MARKET,
                           SIDE_BUY, SIDE_SELL)

logger = logging.getLogger(__name__)

# Import the new UniswapExchange class
try:
    from src.exchange.uniswap_exchange import UniswapExchange
    UNISWAP_AVAILABLE = True
except ImportError:
    UNISWAP_AVAILABLE = False
    logger.warning("UniswapExchange not available. DEX functionality will be disabled.")

class TradingEngine:
    def __init__(self, api_key: str, api_secret: str, is_testnet: bool, loop: Optional[asyncio.AbstractEventLoop] = None):
        """Initialize trading engine with both CEX and DEX support."""
        # Initialize event loop
        self.loop = loop or asyncio.get_event_loop()

        # Initialize price service for CoinGecko
        self.price_service = PriceService()

        # Track trade cooldowns
        self.trade_cooldowns: Dict[str, float] = {}

        # Initialize CEX (Binance)
        self.binance_exchange = BinanceExchange(
            api_key=api_key, api_secret=api_secret, is_testnet=is_testnet
        )
        logger.info("BinanceExchange initialized")

        # Initialize DEX (Uniswap) if available
        self.uniswap_exchange = None
        if UNISWAP_AVAILABLE:
            try:
                self.uniswap_exchange = UniswapExchange(loop=self.loop)
                logger.info("UniswapExchange initialized")
            except Exception as e:
                logger.error(f"Failed to initialize UniswapExchange: {e}")

        # Common base currencies for transaction type detection
        self.base_currencies = {'usdt', 'busd', 'eth', 'btc', 'bnb', 'usdc'}

    async def reload_credentials(self) -> bool:
        """
        Reload environment variables and reinitialize the Binance exchange.
        Use this after switching between different credential sets.

        Returns:
            bool: True if credentials were successfully reloaded and tested, False otherwise
        """
        try:
            logger.info("🔄 Reloading Binance credentials...")

            # Reload environment variables
            reload_env()

            # Re-import the updated configuration
            from config import settings as updated_config

            # Close existing exchange connection
            if hasattr(self, 'binance_exchange'):
                await self.binance_exchange.close()

            # Initialize new exchange with updated credentials
            self.binance_exchange = BinanceExchange(
                api_key=updated_config.BINANCE_API_KEY,
                api_secret=updated_config.BINANCE_API_SECRET,
                is_testnet=updated_config.BINANCE_TESTNET
            )

            # Test the new credentials
            try:
                # Test with a simple balance check
                balances = await self.binance_exchange.get_spot_balance()
                logger.info("✅ Credentials reloaded successfully")
                logger.info(f"   Using API Key: {updated_config.BINANCE_API_KEY[:10]}...{updated_config.BINANCE_API_KEY[-5:] if updated_config.BINANCE_API_KEY else 'None'}")
                logger.info(f"   Testnet Mode: {updated_config.BINANCE_TESTNET}")
                return True

            except Exception as e:
                logger.error(f"❌ Failed to test new credentials: {e}")
                return False

        except Exception as e:
            logger.error(f"❌ Failed to reload credentials: {e}")
            return False

    def _is_cooled_down(self, symbol: str) -> bool:
        """Check if trade cooldown period has passed for the given symbol."""
        last_trade = self.trade_cooldowns.get(symbol, 0)
        return time.time() - last_trade > config.TRADE_COOLDOWN

    async def process_signal(self, coin_symbol: str, signal_price: float,
                           position_type: str = "SPOT",
                           exchange_type: str = "None", sell_coin: str = "None",
                           order_type: str = "MARKET", stop_loss: Optional[float] = None,
                           take_profits: Optional[List[float]] = None,
                           dca_range: Optional[List[float]] = None,
                           client_order_id: Optional[str] = None) -> Tuple[bool, Union[Dict, str]]:
        """
        Process trading signal and execute trade if conditions are met.

        Args:
            coin_symbol: Symbol of coin to buy (e.g., "DSYNC")
            signal_price: Price from the signal message
            position_type: 'LONG', 'SHORT', or 'SPOT'
            exchange_type: "cex" (Binance) or "dex" (Uniswap), defaults to config.PREFERRED_EXCHANGE_TYPE
            sell_coin: Symbol of coin to sell (e.g., "ETH", "USDC"), required for DEX trades
            order_type: Type of order ("MARKET", "LIMIT", "SPOT")
            stop_loss: Optional stop loss price
            take_profits: Optional list of take profit prices
            dca_range: Optional list of [high, low] prices for DCA
            client_order_id: Optional custom order ID to send to the exchange.

        Returns:
            A tuple of (bool, Union[Dict, str]) indicating success and a reason for failure
        """
        # Use default exchange type if not specified
        if not exchange_type:
            exchange_type = getattr(config, "PREFERRED_EXCHANGE_TYPE", "cex").lower()

        # Validate exchange type
        if exchange_type not in ["cex", "dex"]:
            reason = f"Invalid exchange_type: {exchange_type}. Must be 'cex' or 'dex'"
            logger.error(reason)
            return False, reason

        # Validate order type
        if order_type not in ["MARKET", "LIMIT", "SPOT"]:
            reason = f"Invalid order_type: {order_type}. Must be 'MARKET', 'LIMIT', or 'SPOT'"
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
            return await self._process_cex_signal(coin_symbol, signal_price, position_type, order_type, stop_loss, take_profits, dca_range, client_order_id)

    async def _process_cex_signal(self, coin_symbol: str, signal_price: float,
                                position_type: str, order_type: str = "MARKET",
                                stop_loss: Optional[float] = None,
                                take_profits: Optional[List[float]] = None,
                                dca_range: Optional[List[float]] = None,
                                client_order_id: Optional[str] = None) -> Tuple[bool, Union[Dict, str]]:
        """Process a trading signal using the centralized exchange (Binance)."""
        # Check cooldown
        if not self._is_cooled_down(f"cex_{coin_symbol}"):
            reason = f"Trade cooldown active for {coin_symbol} on CEX"
            logger.info(reason)
            return False, reason

        # Determine if it's a futures or spot trade
        is_futures = position_type.upper() in ['LONG', 'SHORT']

        # Pre-validate symbol using whitelist (for futures only)
        if is_futures:
            trading_pair = f"{coin_symbol.lower()}_usdt"
            formatted_pair = trading_pair.replace('_', '').upper()

            # Import and check whitelist
            try:
                from config.binance_futures_whitelist import is_symbol_supported
                if not is_symbol_supported(formatted_pair):
                    reason = f"Trading pair {formatted_pair} not available in futures whitelist"
                    logger.error(reason)
                    return False, reason
                logger.info(f"✅ Symbol {formatted_pair} validated against whitelist")
            except ImportError:
                logger.warning("Futures whitelist not available - skipping symbol validation")

        logger.info(f"Processing CEX signal: {coin_symbol} @ ${signal_price}")
        logger.info(f"Order Type: {order_type}")
        if stop_loss:
            logger.info(f"Stop Loss: ${stop_loss}")
        if take_profits:
            logger.info(f"Take Profits: {', '.join([f'${tp:.8f}' for tp in take_profits])}")
        if dca_range:
            logger.info(f"DCA Range: ${dca_range[0]:.8f} - ${dca_range[1]:.8f}")

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
        if is_futures:
            balances = await self.binance_exchange.get_futures_balance()
        else:
            balances = await self.binance_exchange.get_spot_balance()

        if not balances:
            market_type = "Futures" if is_futures else "Spot"
            reason = f"Failed to get account balances from Binance {market_type}"
            logger.error(reason)
            return False, reason

        usdt_balance = balances.get('usdt', 0)
        market_type = "Futures" if is_futures else "Spot"
        logger.info(f"Available USDT balance on Binance {market_type}: ${usdt_balance}")

        # --- MODIFIED TRADE AMOUNT CALCULATION ---
        # The user wants to trade with amounts no less than $500.
        ORDER_FLOOR_USD = 500.0

        # First, calculate the amount based on risk percentage
        risk_based_amount = usdt_balance * (config.RISK_PERCENTAGE / 100)

        # The desired amount is the greater of the risk-based amount or the $500 floor
        desired_amount = max(ORDER_FLOOR_USD, risk_based_amount)

        # The final trade amount is the lesser of the desired amount or the configured max trade amount
        trade_amount = min(desired_amount, config.MAX_TRADE_AMOUNT)

        # Check for sufficient balance for the calculated trade amount
        if trade_amount > usdt_balance:
            reason = (f"Insufficient balance for the desired trade amount. "
                      f"Required: ${trade_amount:.2f}, Available: ${usdt_balance:.2f}")
            logger.warning(reason)
            return False, reason

        # Final check against the exchange's minimum trade amount (e.g., $10).
        if trade_amount < config.MIN_TRADE_AMOUNT:
            reason = (f"Desired trade amount ${trade_amount:.2f} is below the exchange's minimum "
                      f"of ${config.MIN_TRADE_AMOUNT}")
            logger.warning(reason)
            return False, reason

        # Calculate coin amount to buy
        coin_amount = trade_amount / current_price
        trading_pair = f"{coin_symbol.lower()}_usdt"

        # Check if pair exists on Binance
        if is_futures:
            pair_info = await self.binance_exchange.get_futures_pair_info(trading_pair)
        else:
            pair_info = await self.binance_exchange.get_pair_info(trading_pair)

        if not pair_info:
            market_type = "Futures" if is_futures else "Spot"
            reason = f"Trading pair {trading_pair} not available on Binance {market_type}"
            logger.error(reason)
            return False, reason

        # Execute trade with slippage allowance
        buy_price = current_price * (1 + (config.SLIPPAGE_PERCENTAGE / 100))

        logger.info(f"Executing CEX trade: {coin_amount:.8f} {coin_symbol} @ ${buy_price}")

        # Determine side
        entry_side = SIDE_BUY if position_type.upper() == 'LONG' else SIDE_SELL

        if is_futures:
            # 1. Create the initial entry order
            order_result = await self.binance_exchange.create_futures_order(
                pair=trading_pair,
                side=entry_side,
                order_type_market=ORDER_TYPE_MARKET,
                amount=coin_amount,
                leverage=20, # Default leverage, can be made configurable
                client_order_id=client_order_id # Pass the ID here
            )

            # 2. If entry is successful and there is a stop loss, create the SL order
            if order_result and 'orderId' in order_result and stop_loss:

                # --- BEGIN SL VALIDATION & HANDLING ---
                sl_price_to_use = 0.0
                # Handle 'BE' for stop_loss, converting it to the entry price
                if isinstance(stop_loss, str) and stop_loss.upper() == 'BE':
                    sl_price_to_use = signal_price
                    logger.info(f"Stop loss is 'BE'. Using entry price for validation: ${sl_price_to_use}")
                else:
                    try:
                        sl_price_to_use = float(stop_loss)
                    except (ValueError, TypeError):
                        logger.error(f"Invalid stop loss value '{stop_loss}'. Cannot create SL order.")
                        sl_price_to_use = 0.0 # Will cause validation to fail

                if sl_price_to_use > 0:
                    is_long = position_type.upper() == 'LONG'
                    sl_is_valid = (is_long and sl_price_to_use < current_price) or \
                                  (not is_long and sl_price_to_use > current_price)

                    if not sl_is_valid:
                        price_comparison = "below" if is_long else "above"
                        logger.critical(
                            f"INVALID STOP-LOSS: For a {position_type} position, the stop price (${sl_price_to_use}) "
                            f"must be {price_comparison} the current market price (${current_price}). "
                            f"Skipping SL order creation. THE POSITION IS UNPROTECTED."
                        )
                    else:
                        sl_side = SIDE_SELL if is_long else SIDE_BUY
                        sl_order_result = await self.binance_exchange.create_futures_order(
                            pair=trading_pair,
                            side=sl_side,
                            order_type_market=FUTURE_ORDER_TYPE_STOP_MARKET,
                            stop_price=sl_price_to_use,
                            amount=coin_amount, # Close the full amount
                            leverage=20
                        )
                        if sl_order_result and 'orderId' in sl_order_result:
                            logger.info(f"Successfully created stop-loss order: {sl_order_result}")
                            order_result['stop_loss_order_details'] = sl_order_result
                        else:
                            logger.error(f"Failed to create stop-loss order: {sl_order_result}. Main trade remains open.")
                else:
                    logger.warning(f"Could not determine a valid numerical stop loss price from '{stop_loss}'. Skipping SL order creation.")

        else: # SPOT
            order_result = await self.binance_exchange.create_order(
                pair=trading_pair,
                side=entry_side,
                order_type_market=ORDER_TYPE_MARKET,
                amount=coin_amount,
                price=buy_price, # Note: price is ignored for market orders but kept for consistency
                client_order_id=client_order_id # Pass the ID here
            )
            # You could add Spot SL logic here if needed, following the futures pattern.
            # It would use ORDER_TYPE_STOP_LOSS_LIMIT.

        # Check for 'orderId' to confirm success
        if order_result and 'orderId' in order_result:
            self.trade_cooldowns[f"cex_{coin_symbol}"] = time.time()
            logger.info(f"CEX trade successful for {coin_symbol}: {order_result}")
            # Return the full order result so the caller can store it
            return True, order_result
        else:
            reason = f"CEX trade failed for {coin_symbol}. Response: {order_result}"
            logger.error(reason)
            return False, order_result

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
        sell_token_address = TOKEN_ADDRESS_MAP.get(sell_coin.upper())
        buy_token_address = TOKEN_ADDRESS_MAP.get(buy_coin.upper())

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
                usdc_address = TOKEN_ADDRESS_MAP.get("USDC")
                usdc_balance = 0.0
                if usdc_address:
                    usdc_balance = await self.uniswap_exchange.get_token_balance(usdc_address)

                balances['eth'] = eth_balance
                balances['usdc'] = usdc_balance
            except Exception as e:
                logger.error(f"Failed to get wallet balances: {e}")
        return balances

    async def get_all_wallet_balances(self) -> Dict[str, float]:
        """Get balances from all exchanges."""
        all_balances = {}

        # Get CEX balances
        try:
            binance_balances = await self.binance_exchange.get_spot_balance()
            if binance_balances:
                for coin, balance in binance_balances.items():
                    all_balances[f"binance_spot_{coin}"] = balance
        except Exception as e:
            logger.error(f"Failed to get Binance Spot balances: {e}")

        # Get DEX balances
        dex_balances = await self.get_wallet_balances()
        all_balances.update(dex_balances)

        return all_balances

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
                usdc_address = TOKEN_ADDRESS_MAP.get("USDC")
                if usdc_address:
                    usdc_balance = await self.uniswap_exchange.get_token_balance(usdc_address)
                    logger.info(f"[WALLET] USDC Balance: {usdc_balance:.6f}")

                weth_address = TOKEN_ADDRESS_MAP.get("WETH")
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

    def _determine_transaction_type(self, buy_coin: str, sell_coin: str) -> Optional[str]:
        """Determine if it's a buy or sell transaction."""
        if buy_coin in self.base_currencies and sell_coin not in self.base_currencies:
            return 'sell'
        if sell_coin in self.base_currencies and buy_coin not in self.base_currencies:
            return 'buy'
        return None

    def _create_response_message(self, **kwargs) -> str:
        # This is a placeholder for a more sophisticated message creation logic
        # For now, it just returns a simple string representation of the keyword arguments
        return ", ".join([f"{key.replace('_', ' ').title()}: {value}" for key, value in kwargs.items()])

    async def process_trade_update(self, update_data: Dict, active_trade: Dict) -> Tuple[bool, str]:
        """
        Handle trade updates like stop loss changes, take profits, position closes.

        Args:
            update_data: Parsed update signal with action_type and value
            active_trade: The original trade record from database

        Returns:
            Tuple of (success, message)
        """
        action_type = update_data.get("action_type")
        value = update_data.get("value")

        try:
            if action_type == "CLOSE_POSITION":
                return await self.close_position_at_market(active_trade)
            elif action_type == "UPDATE_SL":
                return await self.update_stop_loss(active_trade, value)
            elif action_type == "TAKE_PROFIT":
                return await self.close_position_at_market(active_trade, reason="take_profit")
            else:
                return False, f"Unknown update action: {action_type}"

        except Exception as e:
            logger.error(f"Error processing trade update: {e}", exc_info=True)
            return False, f"Trade update failed: {str(e)}"

    async def close_position_at_market(self, active_trade: Dict, reason: str = "manual_close", close_percentage: float = 100.0) -> Tuple[bool, Dict]:
        """
        Close an active position at current market price. Handles both CEX futures and spot.

        Args:
            active_trade: The trade record containing position info
            reason: Reason for closing (manual_close, take_profit, stop_loss)
            close_percentage: The percentage of the position to close (e.g., 50.0 for 50%)

        Returns:
            Tuple of (success, execution_details_or_error_dict)
        """
        try:
            # --- BEGIN ROBUST SIZE & SYMBOL LOOKUP ---
            parsed_signal = active_trade.get("parsed_signal") or {}
            coin_symbol = parsed_signal.get("coin_symbol")
            position_type = parsed_signal.get("position_type", "SPOT").upper() # Default to SPOT, ensure uppercase
            position_size = float(active_trade.get("position_size") or 0.0)

            if position_size <= 0:
                logger.warning(f"Position size for trade {active_trade.get('id')} is missing. Falling back to initial response.")
                initial_response = active_trade.get("binance_response")
                if isinstance(initial_response, dict):
                    position_size = float(initial_response.get('origQty') or 0.0)
                    if position_size > 0:
                        logger.info(f"Recovered position size ({position_size}) from initial Binance response.")

            if not coin_symbol or position_size <= 0:
            # --- END ROBUST SIZE & SYMBOL LOOKUP ---
                return False, {"error": f"Invalid trade data for closing position. Symbol: {coin_symbol}, Size: {position_size}"}

            # Calculate amount to close based on percentage
            amount_to_close = position_size * (close_percentage / 100.0)

            logger.info(f"Closing {close_percentage}% of position for {coin_symbol}: {amount_to_close} coins")

            # Create trading pair
            trading_pair = f"{coin_symbol.lower()}_usdt"
            close_order = None
            is_futures = position_type in ['LONG', 'SHORT']

            if is_futures:
                # Determine the correct side to close a futures position
                # To close a LONG, you SELL. To close a SHORT, you BUY.
                close_side = SIDE_SELL if position_type == 'LONG' else SIDE_BUY
                logger.info(f"Executing FUTURES close order for {position_type} position. Side: {close_side}")
                close_order = await self.binance_exchange.create_futures_order(
                    pair=trading_pair,
                    side=close_side,
                    order_type_market=FUTURE_ORDER_TYPE_MARKET,
                    amount=amount_to_close,
                    reduce_only=True # Set reduceOnly to true to ensure it only closes a position
                )
            else:
                # Fallback to SPOT order logic
                logger.info(f"Executing SPOT close order.")
                # For spot, we are always selling back to USDT.
                close_order = await self.binance_exchange.create_order(
                    pair=trading_pair,
                    side='sell',
                    order_type_market='MARKET',
                    amount=amount_to_close
                )


            if close_order and 'orderId' in close_order:
                # Extract execution details from Binance response
                fill_price = float(close_order.get('avgPrice', 0)) if is_futures else (float(close_order.get('fills', [{}])[0].get('price', 0)) if close_order.get('fills') else 0)
                executed_qty = float(close_order.get('executedQty', 0))
                order_id = close_order.get('orderId', '')

                execution_details = {
                    "fill_price": fill_price,
                    "executed_qty": executed_qty,
                    "order_id": str(order_id),
                    "close_reason": reason,
                    "binance_response": close_order # Include the full response
                }

                logger.info(f"Position closed successfully: {coin_symbol} @ ${fill_price}")
                return True, execution_details
            else:
                logger.error(f"Failed to close position for {coin_symbol}. Response: {close_order}")
                return False, close_order

        except Exception as e:
            logger.error(f"Error closing position: {e}", exc_info=True)
            return False, {"error": f"Position close failed: {str(e)}"}

    async def update_stop_loss(self, active_trade: Dict, new_sl_price: float) -> Tuple[bool, Dict]:
        """
        Update stop loss for an active position. This function will now:
        1. Cancel an existing stop loss order if one exists.
        2. Create a new stop loss order.
        """
        try:
            # --- BEGIN ROBUST SIZE & SYMBOL LOOKUP ---
            parsed_signal = active_trade.get("parsed_signal") or {}
            coin_symbol = parsed_signal.get("coin_symbol")
            position_type = parsed_signal.get("position_type", "SPOT")
            position_size = float(active_trade.get("position_size") or 0.0)
            old_sl_order_id = active_trade.get("stop_loss_order_id")

            if position_size <= 0:
                logger.warning(f"Position size for trade {active_trade.get('id')} is missing. Falling back to initial response.")
                initial_response = active_trade.get("binance_response")
                if isinstance(initial_response, dict):
                    position_size = float(initial_response.get('origQty') or 0.0)
                    if position_size > 0:
                        logger.info(f"Recovered position size ({position_size}) from initial Binance response.")

            if not coin_symbol or position_size <= 0:
            # --- END ROBUST SIZE & SYMBOL LOOKUP ---
                return False, {"error": f"Invalid trade data for updating stop loss. Symbol: {coin_symbol}, Size: {position_size}"}

            logger.info(f"Updating stop loss for {coin_symbol} to new price: ${new_sl_price}")
            trading_pair = f"{coin_symbol.lower()}_usdt"

            # 1. Cancel the existing stop loss order IF it exists
            if old_sl_order_id:
                logger.info(f"Attempting to cancel old stop loss order: {old_sl_order_id}")
                cancel_success = await self.binance_exchange.cancel_futures_order(trading_pair, old_sl_order_id)

                if not cancel_success:
                    err_msg = f"Failed to cancel existing stop loss order {old_sl_order_id} for {coin_symbol}. The position may still be protected by the old SL."
                    logger.error(err_msg)
                    # Returning True but with an error message in the response allows logging without halting logic.
                    return False, {"error": err_msg, "critical_alert": "OLD STOP LOSS MAY BE ACTIVE"}
                logger.info(f"Successfully cancelled old stop loss order {old_sl_order_id}.")
            else:
                logger.info("No existing stop-loss order ID found. Proceeding to create a new one.")


            # 2. Create a new stop loss order at the new price
            new_sl_side = SIDE_SELL if position_type.upper() == 'LONG' else SIDE_BUY
            logger.info(f"Creating new stop loss order for {coin_symbol} at price ${new_sl_price}")

            new_sl_order_result = await self.binance_exchange.create_futures_order(
                pair=trading_pair,
                side=new_sl_side,
                order_type_market=FUTURE_ORDER_TYPE_STOP_MARKET,
                stop_price=new_sl_price,
                amount=position_size,
                reduce_only=True
            )

            if new_sl_order_result and 'orderId' in new_sl_order_result:
                logger.info(f"Successfully created new stop loss order: {new_sl_order_result}")
                return True, new_sl_order_result
            else:
                err_msg = f"Cancelled old SL (if any) but FAILED to create new one for {coin_symbol}. Response: {new_sl_order_result}"
                logger.error(err_msg)
                # CRITICAL: At this point, the position is unprotected.
                # A robust implementation should attempt to close the position at market.
                return False, {"error": err_msg, "critical_alert": "POSITION UNPROTECTED"}

        except Exception as e:
            logger.error(f"Error updating stop loss: {e}", exc_info=True)
            return False, {"error": f"Stop loss update failed: {str(e)}"}