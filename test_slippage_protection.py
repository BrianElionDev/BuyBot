#!/usr/bin/env python3
"""
Test slippage protection functionality
Tests different scenarios:
1. Signal price $1.00, Market price $1.15 - Should PASS (15% < 20%)
2. Signal price $1.00, Market price $1.25 - Should FAIL (25% > 20%)
3. Signal price $0.10, Market price $0.13 - Should FAIL (30% > 20%)
4. Signal price $0.136, Market price $0.154 - Should PASS (13.2% < 20%)
"""
import asyncio
import sys
import os

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from telethon import TelegramClient
import config.settings as config

async def test_slippage_protection():
    """Test slippage protection with various scenarios"""
    client = TelegramClient('slippage_test_session', config.TELEGRAM_API_ID, config.TELEGRAM_API_HASH)

    try:
        await client.start(phone=config.TELEGRAM_PHONE)
        print(f"✅ Connected to Telegram")
        print(f"🎯 Testing slippage protection with {config.SLIPPAGE_PERCENTAGE}% threshold")
        print(f"📤 Sending test cases to group {config.TARGET_GROUP_ID}")
        print("=" * 80)

        # Test cases with different price scenarios
        test_cases = [
            {
                "name": "✅ Test 1: Should PASS (15% difference < 20% threshold)",
                "signal_price": 1.00,
                "expected_market_price": "~$1.15",
                "message": """👋 Trade detected:
🟢 +10,000 Test Token A (TTA)
🔴 - 100 USD Coin (USDC)
💰 Price per token $1.00 USD
💎 Valued at $10,000 USD
🛡 Ethereum Blockchain
🤑 Now holds $10,000 USD of Test Token A
📄 Test Wallet""",
                "expected": "SHOULD PASS - 15% difference"
            },
            {
                "name": "❌ Test 2: Should FAIL (25% difference > 20% threshold)",
                "signal_price": 1.00,
                "expected_market_price": "~$1.25",
                "message": """👋 Trade detected:
🟢 +8,000 Test Token B (TTB)
🔴 - 100 USD Coin (USDC)
💰 Price per token $1.00 USD
💎 Valued at $8,000 USD
🛡 Ethereum Blockchain
🤑 Now holds $8,000 USD of Test Token B
📄 Test Wallet""",
                "expected": "SHOULD FAIL - 25% difference"
            },
            {
                "name": "❌ Test 3: Should FAIL (30% difference > 20% threshold)",
                "signal_price": 0.10,
                "expected_market_price": "~$0.13",
                "message": """👋 Trade detected:
🟢 +100,000 Test Token C (TTC)
🔴 - 50 Ethereum (ETH)
💰 Price per token $0.10 USD
💎 Valued at $10,000 USD
🛡 Ethereum Blockchain
🤑 Now holds $10,000 USD of Test Token C
📄 Test Wallet""",
                "expected": "SHOULD FAIL - 30% difference"
            },
            {
                "name": "✅ Test 4: Real scenario - Should PASS (DSYNC 13.2% difference < 20%)",
                "signal_price": 0.136,
                "expected_market_price": "~$0.154",
                "message": """👋 Trade detected:
🟢 +73,529 Destra Network (DSYNC)
🔴 - 2.0 Ethereum (ETH)
💰 Price per token $0.136 USD
💎 Valued at $10,000 USD
🛡 Ethereum Blockchain
🤑 Now holds $10,000 USD of Destra Network
📄 Test Wallet""",
                "expected": "SHOULD PASS - ~13% difference"
            }
        ]

        for i, test_case in enumerate(test_cases, 1):
            print(f"\n📤 {test_case['name']}")
            print(f"Signal Price: ${test_case['signal_price']:.6f}")
            print(f"Expected Market: {test_case['expected_market_price']}")
            print(f"Expected Result: {test_case['expected']}")

            await client.send_message(config.TARGET_GROUP_ID, test_case['message'])
            print(f"✅ Test case {i} sent")
            await asyncio.sleep(5)  # Wait longer between messages to see results

        print(f"\n" + "=" * 80)
        print("✅ All slippage protection test cases sent!")
        print(f"\n📊 EXPECTED RESULTS:")
        print("1. Test 1 (TTA): ✅ PASS - Notification should be sent (15% < 20%)")
        print("2. Test 2 (TTB): ❌ FAIL - Notification blocked (25% > 20%)")
        print("3. Test 3 (TTC): ❌ FAIL - Notification blocked (30% > 20%)")
        print("4. Test 4 (DSYNC): ✅ PASS - Notification should be sent (~13% < 20%)")

        print(f"\n📱 Check notification group {config.NOTIFICATION_GROUP_ID}")
        print("📋 Check logs for detailed slippage calculations")
        print(f"\n🛡️ Slippage threshold set to: {config.SLIPPAGE_PERCENTAGE}%")

    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        await client.disconnect()

if __name__ == "__main__":
    asyncio.run(test_slippage_protection())
