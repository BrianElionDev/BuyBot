#!/usr/bin/env python3
"""
Final verification test for enhanced notification format and dynamic coin pair parsing
Tests:
1. ETH/USDC validation (only allow trades selling ETH or USDC)
2. Enhanced notification format with CoinGecko prices
3. Dynamic coin pair parsing from green/red emoji lines
"""
import asyncio
import sys
import os

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from telethon import TelegramClient
import config.settings as config

async def test_final_verification():
    """Final verification of the enhanced functionality"""
    client = TelegramClient('final_test_session', config.TELEGRAM_API_ID, config.TELEGRAM_API_HASH)

    try:
        await client.start(phone=config.TELEGRAM_PHONE)
        print(f"✅ Connected to Telegram")
        print(f"🎯 Sending test cases to group {config.TARGET_GROUP_ID}")
        print(f"📱 Notifications will go to group {config.NOTIFICATION_GROUP_ID}")
        print("=" * 80)

        # Test cases with expected results
        test_cases = [
            {
                "name": "❌ D/USDC (Should be IGNORED - selling D, not ETH/USDC)",
                "message": """👋 Trade detected:
🟢 +2,336.576 USD Coin (USDC)
🔴 - 104,347.826 DAR Open Network (D)
💰 Price per token $1.022 USD
💎 Valued at $2,387.484 USD
🛡 Ethereum Blockchain
🤑 Now holds $9,940 USD of USD Coin
📄 Old Wallet""",
                "expected": "IGNORED (selling D)"
            },
            {
                "name": "✅ USDC/BCB (Should WORK - selling USDC)",
                "message": """👋  Trade Detected:

🟢  + 396,724.26 Blockchain Bets (BCB (https://etherscan.io/address/0x2d886570a0da04885bfd6eb48ed8b8ff01a0eb7e))

🔴  - 3,000 USD Coin (USDC (https://etherscan.io/address/0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48))

💵  Price per token $0.008 USD

💎  Valued at $3,003.9 USD

🔗  Ethereum Blockchain

🍰  Now holds $3,003.9 USD of Blockchain Bets""",
                "expected": "VALID (selling USDC)"
            },
            {
                "name": "✅ ETH/DSYNC (Should WORK - selling ETH)",
                "message": """👋 Trade detected:
🟢 +531,835.742 Destra Network (DSYNC)
🔴 - 1.5 Ethereum (ETH)
💰 Price per token $0.136 USD
💎 Valued at $72,329 USD
🛡 Ethereum Blockchain
🤑 Now holds $72,329 USD of Destra Network
📄 New Wallet""",
                "expected": "VALID (selling ETH)"
            }
        ]

        for i, test_case in enumerate(test_cases, 1):
            print(f"\n📤 Test {i}: {test_case['name']}")
            print(f"Expected: {test_case['expected']}")

            await client.send_message(config.TARGET_GROUP_ID, test_case['message'])
            print(f"✅ Sent successfully")
            await asyncio.sleep(3)  # Wait between messages

        print(f"\n" + "=" * 80)
        print("✅ All test cases sent!")
        print("\n📊 EXPECTED RESULTS:")
        print("1. Test 1 (D/USDC): Should be IGNORED - logged but no notification sent")
        print("2. Test 2 (USDC/BCB): Should send notification with BCB price from CoinGecko")
        print("3. Test 3 (ETH/DSYNC): Should send notification with DSYNC price from CoinGecko")

        print(f"\n📱 Check notification group {config.NOTIFICATION_GROUP_ID} for results")
        print("📋 Check logs for detailed parsing information")
        print("\n🔍 Notification format should be:")
        print("🚨 Trade Signal Detected!")
        print("")
        print("Transaction Type: Buy")
        print("{sell_coin}/{buy_coin}")
        print("Price: ${coingecko_price}")
        print("Amount: 10.0")

    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        await client.disconnect()

if __name__ == "__main__":
    asyncio.run(test_final_verification())
