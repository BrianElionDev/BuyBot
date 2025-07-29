#!/usr/bin/env python3
"""
Test script to validate quantity calculation fixes for problematic symbols.
"""

import asyncio
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.exchange.binance_exchange import BinanceExchange
from src.services.price_service import PriceService
from config.settings import BINANCE_API_KEY, BINANCE_API_SECRET, BINANCE_TESTNET, TRADE_AMOUNT
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_quantity_calculation():
    """Test quantity calculation for problematic symbols."""

    # Check if API keys are available
    if not BINANCE_API_KEY or not BINANCE_API_SECRET:
        print("❌ Binance API keys not configured")
        return

    # Initialize services
    price_service = PriceService()
    binance_exchange = BinanceExchange(
        api_key=BINANCE_API_KEY,
        api_secret=BINANCE_API_SECRET,
        is_testnet=BINANCE_TESTNET
    )

    # Test symbols from the failed trades
    test_symbols = [
        ('SUI', 2.9),      # SUIUSDT - min_qty: 0.1, max_qty: 10,000,000
        ('PENGU', 0.04079), # PENGUUSDT - min_qty: 1.0, max_qty: 20,000,000
        ('HYPE', 39.9),     # HYPEUSDT - min_qty: 0.01, max_qty: 30,000
        ('XRP', 2.51),      # XRPUSDT - min_qty: 0.1, max_qty: 1,000,000
    ]

    print("🔍 Testing Quantity Calculation Fixes")
    print("=" * 50)

    for coin_symbol, signal_price in test_symbols:
        print(f"\n📊 Testing {coin_symbol}USDT @ ${signal_price}")
        print("-" * 30)

        try:
            # Get current price
            current_price = await price_service.get_coin_price(coin_symbol)
            if not current_price:
                print(f"❌ Failed to get price for {coin_symbol}")
                continue

            print(f"Current price: ${current_price:.8f}")

            # Calculate trade amount (old method)
            old_trade_amount = TRADE_AMOUNT / current_price
            print(f"Old calculation: {old_trade_amount:.8f} {coin_symbol}")

            # Get symbol filters
            trading_pair = f"{coin_symbol}USDT"
            filters = await binance_exchange.get_futures_symbol_filters(trading_pair)

            if not filters:
                print(f"❌ No filters found for {trading_pair}")
                continue

            lot_size_filter = filters.get('LOT_SIZE', {})
            min_qty = float(lot_size_filter.get('minQty', 0))
            max_qty = float(lot_size_filter.get('maxQty', float('inf')))
            step_size = lot_size_filter.get('stepSize')

            print(f"Min Qty: {min_qty}")
            print(f"Max Qty: {max_qty}")
            print(f"Step Size: {step_size}")

            # Test new calculation with precision formatting
            from decimal import Decimal
            trade_amount = TRADE_AMOUNT / current_price

            if step_size:
                step_dec = Decimal(str(step_size))
                amount_dec = Decimal(str(trade_amount))
                formatted_amount = (amount_dec // step_dec) * step_dec
                trade_amount = float(formatted_amount)
                print(f"New calculation (formatted): {trade_amount:.8f} {coin_symbol}")
            else:
                print(f"New calculation: {trade_amount:.8f} {coin_symbol}")

            # Validate quantity
            if trade_amount < min_qty:
                print(f"❌ Quantity {trade_amount} below minimum {min_qty}")
            elif trade_amount > max_qty:
                print(f"❌ Quantity {trade_amount} above maximum {max_qty}")
            else:
                print(f"✅ Quantity {trade_amount} is valid")

            # Check notional value
            notional_value = trade_amount * current_price
            min_notional = float(filters.get('MIN_NOTIONAL', {}).get('notional', 0)) if 'MIN_NOTIONAL' in filters else 0
            print(f"Notional value: ${notional_value:.2f} (min: ${min_notional:.2f})")

            if notional_value < min_notional:
                print(f"❌ Notional value below minimum")
            else:
                print(f"✅ Notional value is valid")

        except Exception as e:
            print(f"❌ Error testing {coin_symbol}: {e}")

    await binance_exchange.close()

if __name__ == "__main__":
    asyncio.run(test_quantity_calculation())