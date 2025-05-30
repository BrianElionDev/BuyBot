#!/usr/bin/env python3
"""
Quick test to understand the correct Telethon usage for version 1.40.0
"""
import asyncio
from telethon import TelegramClient
from config.settings import Config

async def test_telethon():
    config = Config()

    client = TelegramClient(
        'test_session',
        config.TELEGRAM_API_ID,
        config.TELEGRAM_API_HASH
    )

    print("Testing Telethon client methods...")

    # Test 1: Check if start is awaitable
    try:
        print("Testing client.start()...")
        result = client.start(phone=config.TELEGRAM_PHONE)
        print(f"client.start() returned: {type(result)}")

        if hasattr(result, '__await__'):
            print("client.start() is awaitable")
            await result
        else:
            print("client.start() is not awaitable")

    except Exception as e:
        print(f"Error with client.start(): {e}")

    # Test 2: Check if run_until_disconnected is awaitable
    try:
        print("\nTesting client.run_until_disconnected()...")
        result = client.run_until_disconnected()
        print(f"client.run_until_disconnected() returned: {type(result)}")

        if hasattr(result, '__await__'):
            print("client.run_until_disconnected() is awaitable")
        else:
            print("client.run_until_disconnected() is not awaitable")

    except Exception as e:
        print(f"Error with client.run_until_disconnected(): {e}")

    # Cleanup
    if client.is_connected():
        client.disconnect()

if __name__ == "__main__":
    asyncio.run(test_telethon())
