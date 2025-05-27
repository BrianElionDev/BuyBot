# crypto-signal-bot/trading/trading_engine.py

import logging
from typing import TYPE_CHECKING

from config.settings import settings
from trading.coin_gecko import CoinGeckoAPI

# Type checking for dependency injection to avoid circular imports
if TYPE_CHECKING:
    from exchanges.base_exchange import BaseExchange

logger = logging.getLogger(__name__)

class TradingEngine:
    """
    The core trading logic processor.
    It receives signals, fetches real-time market data, checks balances,
    calculates trade amounts, and executes one-time purchase orders.
    """

    def __init__(self, exchange: 'BaseExchange'):
        """
        Initializes the TradingEngine with an exchange instance.

        Args:
            exchange (BaseExchange): An instance of an exchange class (e.g., YoBitExchange).
        """
        self.exchange = exchange
        self.coin_gecko = CoinGeckoAPI()
        self.min_trade_amount = settings.MINIMUM_TRADE_AMOUNT
        self.risk_percentage = settings.RISK_PERCENTAGE
        self.slippage_percentage = settings.SLIPPAGE_PERCENTAGE
        self.base_currency = settings.BASE_CURRENCY.lower()

    async def process_signal(self, coin_symbol: str, signal_price: float) -> bool:
        """
        Processes a trading signal received from Telegram.
        Performs a one-time purchase if conditions are met.

        Args:
            coin_symbol (str): The symbol of the cryptocurrency (e.g., 'BTC').
            signal_price (float): The price mentioned in the signal message.

        Returns:
            bool: True if the trade was successfully initiated, False otherwise.
        """
        logger.info(f"Processing signal for {coin_symbol} at signal price {signal_price} {self.base_currency.upper()}")

        # 1. Get CoinGecko ID for accurate price lookup
        coin_id = await self.coin_gecko.get_coin_id(coin_symbol)
        if not coin_id:
            logger.error(f"Could not resolve CoinGecko ID for symbol: {coin_symbol}. Skipping trade.")
            return False

        # 2. Get current market price from CoinGecko
        current_market_price = await self.coin_gecko.get_price(coin_id)
        if not current_market_price:
            logger.error(f"Could not fetch current market price for {coin_symbol}. Skipping trade.")
            return False

        logger.info(f"Current market price for {coin_symbol} ({coin_id}): {current_market_price} {self.base_currency.upper()}")

        # 3. Check if current market price is within acceptable range of signal price (optional, but good for validation)
        # For a one-time purchase, we might just use the current market price, but comparing to signal is good.
        # Example: if signal_price is significantly different from current_market_price, it might be a stale signal.
        # For simplicity, we'll proceed with current_market_price for the order.

        # 4. Check account balance on the exchange
        balances = await self.exchange.get_balance()
        if not balances:
            logger.error("Failed to retrieve account balances from exchange. Skipping trade.")
            return False

        available_base_balance = balances.get(self.base_currency, 0.0)
        logger.info(f"Available {self.base_currency.upper()} balance: {available_base_balance}")

        if available_base_balance < self.min_trade_amount:
            logger.warning(f"Insufficient {self.base_currency.upper()} balance ({available_base_balance}) for minimum trade amount ({self.min_trade_amount}). Skipping trade.")
            return False

        # 5. Calculate trade size based on risk percentage
        # Amount to spend in base currency
        amount_to_spend = min(
            available_base_balance * (self.risk_percentage / 100.0), # Risk percentage of total balance
            available_base_balance # Ensure we don't try to spend more than available
        )

        if amount_to_spend < self.min_trade_amount:
            logger.warning(f"Calculated trade amount ({amount_to_spend:.4f} {self.base_currency.upper()}) is less than minimum trade amount ({self.min_trade_amount}). Skipping trade.")
            return False

        logger.info(f"Calculated amount to spend: {amount_to_spend:.4f} {self.base_currency.upper()}")

        # 6. Determine order price with slippage
        # For a 'buy' order, we might want to place a limit order slightly above current market price
        # to ensure quick fill, or a market order. For simplicity, we'll use a limit order with slippage.
        # This means we are willing to pay up to (current_market_price * (1 + slippage_percentage/100))
        order_price = current_market_price * (1 + self.slippage_percentage / 100.0)
        # Calculate the amount of crypto coin to buy
        amount_of_coin_to_buy = amount_to_spend / order_price

        # 7. Get symbol info from exchange to check precision and min amounts
        # This is crucial for real-world trading to avoid API errors due to invalid amounts/prices.
        # YoBit's get_symbol_info is for public info, not specific to user's trading limits.
        # For a robust solution, you'd need to parse YoBit's /info endpoint for pair details.
        # For now, we'll assume default precision and rely on YoBit's API to handle rounding.
        # A more advanced implementation would fetch this info and adjust `amount_of_coin_to_buy` and `order_price`
        # to match exchange's required precision and minimums.
        pair_info = await self.exchange.get_symbol_info(coin_symbol)
        if pair_info:
            # Example: YoBit's info endpoint might give 'min_amount', 'min_price', 'decimal_places'
            # You would use these to round `amount_of_coin_to_buy` and `order_price`
            # For now, we'll log it and proceed.
            logger.debug(f"Exchange pair info for {coin_symbol}_{self.base_currency}: {pair_info}")
            # Example of applying precision (YoBit often uses 8 decimal places for amounts/rates)
            # amount_of_coin_to_buy = round(amount_of_coin_to_buy, 8)
            # order_price = round(order_price, 8)
        else:
            logger.warning(f"Could not retrieve exchange pair info for {coin_symbol}_{self.base_currency}. Proceeding with calculated values.")


        # 8. Execute the trade (one-time purchase)
        trading_pair = f"{coin_symbol.lower()}_{self.base_currency.lower()}"
        logger.info(f"Attempting to place BUY order for {amount_of_coin_to_buy:.8f} {coin_symbol.upper()} at {order_price:.8f} {self.base_currency.upper()} on {trading_pair}")

        order_result = await self.exchange.create_order(
            pair=trading_pair,
            order_type='buy',
            amount=amount_of_coin_to_buy,
            price=order_price
        )

        if order_result:
            logger.info(f"Trade execution successful for {coin_symbol}. Order ID: {order_result.get('order_id', 'N/A')}")
            return True
        else:
            logger.error(f"Trade execution failed for {coin_symbol}.")
            return False

    async def close_all_sessions(self):
        """Closes all aiohttp client sessions used by the trading engine and its components."""
        await self.coin_gecko.close_session()
        await self.exchange.close_session()
        logger.info("Closed all aiohttp client sessions.")