#!/usr/bin/env python3
"""
Test the improved pattern matching for trade signals
"""

def test_pattern_matching():
    """Test if our pattern matching logic works correctly"""

    # Test messages that should be detected
    test_messages = [
        "👋  Trade Detected:\n🟢 +4,424.102 Nuklai (NAI)\n💰 Price per token $0.025 USD",
        "👋 Trade Detected:\n🟢 +531,835.742 Destra Network (DSync)\n💰 Price per token $0.136 USD",
        "Trade Detected:\n[GREEN] +1,000.000 Test Token (TEST)\n[PRICE] Price per token $1.00 USD",
        "[TRADE] Trade Detected:\nSome trade information",
        "TRADE DETECTED: All caps version",
        "trade detected: lowercase version",
        "👋  trade detected:",  # Double space and lowercase
        "👋 trade detected:",   # Single space and lowercase
    ]

    # Test messages that should NOT be detected
    non_trade_messages = [
        "Regular message about trading",
        "This message mentions trade but not detected",
        "Hello world",
        "🎯 Target reached",
        "Some random emoji message 🚀"
    ]

    print("Testing improved pattern matching...")
    print("=" * 60)

    for i, message in enumerate(test_messages, 1):
        print(f"\nTest {i}: SHOULD DETECT")
        print(f"Message: {repr(message[:50])}...")

        # Apply our pattern matching logic
        message_lower = message.lower() if message else ""
        is_trade_signal = (
            'trade detected' in message_lower or
            '[trade] trade detected' in message_lower or
            # Handle variations with emoji, spaces, and punctuation
            ('👋' in message and 'trade detected' in message_lower) or
            ('👋' in message and 'trade signal' in message_lower) or
            # Handle text format variations
            '[trade]' in message_lower or
            # Direct pattern matches for common formats
            message_lower.strip().startswith('trade detected') or
            '👋  trade detected' in message_lower or  # Double space
            '👋 trade detected' in message_lower       # Single space
        )

        print(f"Result: {'✅ DETECTED' if is_trade_signal else '❌ NOT DETECTED'}")
        if not is_trade_signal:
            print("⚠️  THIS SHOULD HAVE BEEN DETECTED!")

    print("\n" + "=" * 60)

    for i, message in enumerate(non_trade_messages, 1):
        print(f"\nNon-trade {i}: SHOULD NOT DETECT")
        print(f"Message: {repr(message[:50])}...")

        # Apply our pattern matching logic
        message_lower = message.lower() if message else ""
        is_trade_signal = (
            'trade detected' in message_lower or
            '[trade] trade detected' in message_lower or
            # Handle variations with emoji, spaces, and punctuation
            ('👋' in message and 'trade detected' in message_lower) or
            ('👋' in message and 'trade signal' in message_lower) or
            # Handle text format variations
            '[trade]' in message_lower or
            # Direct pattern matches for common formats
            message_lower.strip().startswith('trade detected') or
            '👋  trade detected' in message_lower or  # Double space
            '👋 trade detected' in message_lower       # Single space
        )

        print(f"Result: {'❌ INCORRECTLY DETECTED' if is_trade_signal else '✅ CORRECTLY IGNORED'}")
        if is_trade_signal:
            print("⚠️  THIS SHOULD NOT HAVE BEEN DETECTED!")

if __name__ == "__main__":
    test_pattern_matching()
