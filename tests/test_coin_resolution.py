#!/usr/bin/env python3
"""
Test for coin resolution issues, specifically focusing on:
1. SHIB parsing in signal messages
2. Solana resolution to correct CoinGecko ID
"""
import asyncio
import sys
import os
import logging
import re

# Add the project root to the Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.services.price_service import PriceService
from src.bot.telegram_monitor import TelegramMonitor

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

class MockTradingEngine:
    """Mock trading engine for testing"""
    async def process_signal(self, *args, **kwargs):
        return True

class MockConfig:
    """Mock configuration for testing"""
    TELEGRAM_API_ID = 123
    TELEGRAM_API_HASH = "test_hash"
    TELEGRAM_PHONE = "+1234567890"
    TARGET_GROUP_ID = -123456
    NOTIFICATION_GROUP_ID = -123456
    SLIPPAGE_PERCENTAGE = 10.0
    PREFERRED_EXCHANGE_TYPE = "cex"

async def test_price_service_resolution():
    """Test coin resolution in PriceService"""
    logger.info("=" * 80)
    logger.info("TESTING PRICE SERVICE RESOLUTION")
    logger.info("=" * 80)

    price_service = PriceService()

    # Test high-priority coins that had issues
    coins_to_test = {
        "SOL": "solana",
        "SOLANA": "solana",
        "BTC": "bitcoin",
        "ETH": "ethereum",
        "SHIB": "shiba-inu"
    }

    for symbol, expected_id in coins_to_test.items():
        coin_id = await price_service.get_coin_id(symbol)
        if coin_id == expected_id:
            logger.info(f"✅ {symbol} correctly resolved to {coin_id}")
        else:
            logger.error(f"❌ {symbol} resolved to {coin_id}, expected {expected_id}")

    # Test with price lookups to ensure full flow works
    for symbol in coins_to_test.keys():
        price = await price_service.get_coin_price(symbol)
        if price:
            logger.info(f"✅ Got price for {symbol}: ${price}")
        else:
            logger.error(f"❌ Failed to get price for {symbol}")

    logger.info("Price service resolution test complete")

async def test_signal_parsing():
    """Test parsing of SHIB and other signals"""
    logger.info("=" * 80)
    logger.info("TESTING SIGNAL PARSING")
    logger.info("=" * 80)

    # Create mock TelegramMonitor instance
    config = MockConfig()
    trading_engine = MockTradingEngine()
    monitor = TelegramMonitor(trading_engine, config)

    # Test signal for SHIB
    shib_signal = """
👋 Trade detected!

🟢 +14,857.13 USDC (USDC)
🔴 -1,069,850,000 SHIBA INU (SHIB)

📊 DEX: UNISWAP V3
💰 Price per token $0.000014 USD
💵 Txn gas price: 25 GWEI
🧮 Txn gas used: 144899.0
⛓️ TX: https://etherscan.io/tx/0xabcd...
    """

    # Test signal for SOLANA
    sol_signal = """
👋 Trade detected!

🟢 +425.0 SOLANA (SOL)
🔴 -5000 USDC (USDC)

📊 DEX: RAYDIUM
💰 Price per token $11.75 USD
💵 Txn gas price: 18 GWEI
🧮 Txn gas used: 95000.0
⛓️ TX: https://solscan.io/tx/0xabcd...
    """

    # Test signals
    signals = [
        ("SHIB Signal", shib_signal),
        ("SOL Signal", sol_signal),
    ]

    for name, signal in signals:
        logger.info(f"Testing {name}")
        sell_coin, buy_coin, price, is_valid = monitor._parse_enhanced_signal(signal)

        logger.info(f"Parsed result: sell_coin={sell_coin}, buy_coin={buy_coin}, price={price}, valid={is_valid}")

        # Verify the parse was successful
        if buy_coin and sell_coin and price:
            logger.info(f"✅ Successfully parsed {name}")
        else:
            logger.error(f"❌ Failed to parse {name}")

    logger.info("Signal parsing test complete")

async def run_tests():
    """Run all tests"""
    await test_price_service_resolution()
    print("\n")
    await test_signal_parsing()

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(run_tests())
