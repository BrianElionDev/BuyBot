#!/usr/bin/env python3
"""
Test the enhanced parsing with the required formats
"""
import asyncio
import sys
import os

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from telethon import TelegramClient
import config.settings as config

async def test_enhanced_formats():
    """Test the enhanced message formats"""
    client = TelegramClient('enhanced_test_session', config.TELEGRAM_API_ID, config.TELEGRAM_API_HASH)

    try:
        await client.start(phone=config.TELEGRAM_PHONE)
        print(f"✅ Connected to Telegram")

        # Test Case 1: D/USDC transaction (should be ignored - not selling ETH/USDC)
        test_message_1 = """👋 Trade detected:
🟢 +2,336.576 USD Coin (USDC)
🔴 - 104,347.826 DAR Open Network (D)
💰 Price per token $1.022 USD
💎 Valued at $2,387.484 USD
🛡 Ethereum Blockchain
🤑 Now holds $9,940 USD of USD Coin
📄 Old Wallet"""

        # Test Case 2: USDC/BCB transaction (should work - selling USDC)
        test_message_2 = """👋  Trade Detected:

🟢  + 396,724.26 Blockchain Bets (BCB (https://etherscan.io/address/0x2d886570a0da04885bfd6eb48ed8b8ff01a0eb7e))

🔴  - 3,000 USD Coin (USDC (https://etherscan.io/address/0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48))

💵  Price per token $0.008 USD

💎  Valued at $3,003.9 USD

🔗  Ethereum Blockchain

🍰  Now holds $3,003.9 USD of Blockchain Bets"""

        # Test Case 3: ETH/DSYNC transaction (should work - selling ETH)
        test_message_3 = """👋 Trade detected:
🟢 +531,835.742 Destra Network (DSYNC)
🔴 - 1.5 Ethereum (ETH)
💰 Price per token $0.136 USD
💎 Valued at $72,329 USD
🛡 Ethereum Blockchain
🤑 Now holds $72,329 USD of Destra Network
📄 New Wallet"""

        test_cases = [
            ("Test 1 (D/USDC - should be ignored)", test_message_1),
            ("Test 2 (USDC/BCB - should work)", test_message_2),
            ("Test 3 (ETH/DSYNC - should work)", test_message_3),
        ]

        for i, (description, message) in enumerate(test_cases, 1):
            print(f"\n📤 Sending {description}")
            await client.send_message(config.TARGET_GROUP_ID, message)
            print(f"✅ Test case {i} sent")
            await asyncio.sleep(2)  # Wait between messages

        print(f"\n✅ All test cases sent to target group {config.TARGET_GROUP_ID}")
        print("📱 Check the logs and notification group for results...")

    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        await client.disconnect()

if __name__ == "__main__":
    asyncio.run(test_enhanced_formats())
