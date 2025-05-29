import logging
import time
from typing import Dict, Set
from config import settings as config
from src.services.price_service import PriceService
from src.exchange.yobit_exchange import YoBitExchange

logger = logging.getLogger(__name__)

class TradingEngine:
    def __init__(self):
        self.exchange = YoBitExchange()
        self.price_service = PriceService()
        self.trade_cooldowns: Dict[str, float] = {}

    def _is_cooled_down(self, symbol: str) -> bool:
        last_trade = self.trade_cooldowns.get(symbol, 0)
        return time.time() - last_trade > config.TRADE_COOLDOWN

    async def process_signal(self, coin_symbol: str, signal_price: float) -> bool:
        """Process trading signal and execute trade if conditions are met"""

        # Check cooldown
        if not self._is_cooled_down(coin_symbol):
            logger.info(f"Trade cooldown active for {coin_symbol}")
            return False

        logger.info(f"Processing signal: {coin_symbol} @ ${signal_price}")

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
        balances = await self.exchange.get_balance()
        if not balances:
            logger.error("Failed to get account balances")
            return False

        usd_balance = balances.get('usd', 0)
        logger.info(f"Available USD balance: ${usd_balance}")

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
        pair_info = await self.exchange.get_pair_info(trading_pair)
        if not pair_info:
            logger.error(f"Trading pair {trading_pair} not available on YoBit")
            return False

        # Execute trade with 1% slippage
        buy_price = current_price * 1.01

        logger.info(f"Executing trade: {coin_amount:.8f} {coin_symbol} @ ${buy_price}")

        order_result = await self.exchange.create_order(
            pair=trading_pair,
            order_type='buy',
            amount=coin_amount,
            price=buy_price
        )

        if order_result:
            self.trade_cooldowns[coin_symbol] = time.time()
            logger.info(f"Trade successful for {coin_symbol}")
            return True
        else:
            logger.error(f"Trade failed for {coin_symbol}")
            return False

    async def close(self):
        """Cleanup resources"""
        await self.exchange.close()