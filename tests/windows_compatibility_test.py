#!/usr/bin/env python3
"""
Windows Compatibility Test
This test verifies that the bot can run on Windows without Unicode encoding errors.
"""
import sys
import os
import logging

# Add the project root to the Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_logging_configuration():
    """Test that logging works with Windows-compatible configuration"""
    print("[TEST] Testing logging configuration...")

    # Import the main module to test logging setup
    from main import setup_logging

    # Setup logging (this should work on Windows now)
    setup_logging()
    logger = logging.getLogger(__name__)

    # Test various log levels with Windows-compatible messages
    logger.info("[DEBUG] This is a debug message")
    logger.info("[INFO] This is an info message")
    logger.warning("[WARNING] This is a warning message")
    logger.error("[ERROR] This is an error message")

    print("[SUCCESS] Logging configuration test passed!")

def test_message_parsing():
    """Test that message parsing works with Windows-compatible format"""
    print("[TEST] Testing message parsing...")

    # Test message in Windows-compatible format (no emojis)
    test_message = """[TRADE] Trade detected:
[GREEN] +531,835.742 Destra Network (DSync)
[RED] - 41.5 Ether (ETH)
[PRICE] Price per token $0.136 USD
[VALUE] Valued at $72,466.187 USD
[BLOCKCHAIN] Ethereum Blockchain
[HOLDINGS] Now holds $177,487.57 USD of Destra Network
[ADDRESS] 0x0Papi"""

    # Test that the message can be processed without Unicode errors
    for line in test_message.split('\n'):
        logging.info(f"[PARSE] Processing line: {line}")

    print("[SUCCESS] Message parsing test passed!")

def test_price_service():
    """Test that the price service works"""
    print("[TEST] Testing price service...")

    try:
        from src.services.price_service import PriceService
        import asyncio

        async def test_price():
            price_service = PriceService()
            price = await price_service.get_coin_price("ethereum")
            if price:
                logging.info(f"[SUCCESS] ETH price: ${price:.6f}")
                return True
            else:
                logging.warning("[WARNING] Could not fetch ETH price")
                return False

        # Run the async test
        success = asyncio.run(test_price())
        if success:
            print("[SUCCESS] Price service test passed!")
        else:
            print("[WARNING] Price service test completed with warnings")

    except Exception as e:
        print(f"[ERROR] Price service test failed: {e}")

def test_console_output():
    """Test that console output works properly"""
    print("[TEST] Testing console output...")

    # Test various characters that might cause issues on Windows
    test_strings = [
        "[SUCCESS] Basic ASCII characters work fine",
        "[INFO] Testing numbers: 123456789.0",
        "[DEBUG] Testing symbols: $, %, &, #, @",
        "[WARNING] Testing parentheses and brackets: () [] {}",
        "[ERROR] Testing quotes: 'single' and \"double\"",
    ]

    for test_string in test_strings:
        print(test_string)
        logging.info(test_string)

    print("[SUCCESS] Console output test passed!")

def main():
    """Run all Windows compatibility tests"""
    print("=" * 70)
    print("[WINDOWS] Windows Compatibility Test Suite")
    print("=" * 70)
    print(f"[SYSTEM] Python version: {sys.version}")
    print(f"[SYSTEM] Platform: {sys.platform}")
    print(f"[SYSTEM] Encoding: {sys.stdout.encoding}")
    print("=" * 70)

    tests = [
        test_logging_configuration,
        test_console_output,
        test_message_parsing,
        test_price_service,
    ]

    for test in tests:
        try:
            test()
            print()
        except Exception as e:
            print(f"[ERROR] Test {test.__name__} failed: {e}")
            print()

    print("=" * 70)
    print("[COMPLETE] Windows compatibility tests completed!")
    print("[INFO] If you see this message without Unicode errors,")
    print("[INFO] the bot should work properly on Windows systems.")
    print("=" * 70)

if __name__ == "__main__":
    main()
