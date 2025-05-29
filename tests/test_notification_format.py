#!/usr/bin/env python3
"""
Test the notification format with mock data
"""
import asyncio
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_notification_format():
    """Test notification formatting with mock price data"""

    # Mock price data
    mock_prices = {
        'ETH': 2728.80,
        'DSYNC': 0.136,
        'BTC': 65432.10,
        'USDC': 1.00
    }

    def format_cost_message(coin_symbol, amount, price):
        if price:
            cost_value = price * amount
            return f"${cost_value:.6f} (${price:.6f} per {coin_symbol})"
        else:
            return f"Price unavailable for {coin_symbol}"

    # Test different scenarios
    test_cases = [
        {'coin': 'DSYNC', 'amount': 10, 'price': mock_prices['DSYNC']},
        {'coin': 'ETH', 'amount': 1, 'price': mock_prices['ETH']},
        {'coin': 'BTC', 'amount': 0.5, 'price': mock_prices['BTC']},
        {'coin': 'UNKNOWN', 'amount': 100, 'price': None},
    ]

    logger.info("🧪 Testing notification formats:")
    logger.info("=" * 60)

    for case in test_cases:
        coin = case['coin']
        amount = case['amount']
        price = case['price']

        cost_message = format_cost_message(coin, amount, price)

        message = (
            f"Transaction Type: Buy\n"
            f"Sell: ETH\n"
            f"Buy: USDC\n"
            f"Amount: {amount}\n"
            f"Cost: {cost_message}"
        )

        logger.info(f"📧 Notification for {coin}:")
        logger.info(message)
        logger.info("-" * 40)

if __name__ == "__main__":
    asyncio.run(test_notification_format())
