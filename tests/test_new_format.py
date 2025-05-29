#!/usr/bin/env python3
"""
Test script to demonstrate the new message parsing functionality
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.bot.telegram_monitor import TelegramMonitor
import logging

# Set up logging to see the parsing output
logging.basicConfig(level=logging.INFO, format='%(levelname)s - %(message)s')

# Mock classes for testing
class MockConfig:
    pass

class MockTradingEngine:
    async def process_signal(self, symbol, price):
        print(f"🎯 Trading Engine received: {symbol} @ ${price}")

# Test message in the new format
test_message = """👋 Trade detected:
🟢 +531,835.742 Destra Network (DSync)
🔴 - 41.5 Ether (ETH)
💰 Price per token $0.136 USD
💎 Valued at $72,466.187 USD
🛡 Ethereum Blockchain
🤑 Now holds $177,487.57 USD of Destra Network
📄 0x0Papi"""

def test_parsing():
    print("=" * 60)
    print("TESTING NEW MESSAGE PARSING FUNCTIONALITY")
    print("=" * 60)

    print("\n📝 Original Message:")
    print(test_message)

    print("\n🔍 Testing Message Detection:")
    if test_message.startswith('👋 Trade detected'):
        print("✅ Message correctly identified as trade signal")
    else:
        print("❌ Message not identified as trade signal")

    print("\n🔧 Testing Parsing Logic:")

    # Create monitor instance
    config = MockConfig()
    trading_engine = MockTradingEngine()
    monitor = TelegramMonitor(trading_engine, config)

    # Test the parsing
    symbol, price = monitor._parse_signal(test_message)

    print(f"\n📊 Parsing Results:")
    print(f"Symbol: {symbol}")
    print(f"Price: ${price}")

    if symbol and price:
        print("\n✅ SUCCESS: Message parsed correctly!")
        print(f"🪙 Coin: {symbol}")
        print(f"💰 Price: ${price}")
    else:
        print("\n❌ FAILED: Could not parse message")

    print("\n" + "=" * 60)

if __name__ == "__main__":
    test_parsing()
