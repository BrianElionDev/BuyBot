import asyncio
import json
import logging
from discord_bot.discord_bot import discord_bot

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_timestamp_processing():
    """Test the new timestamp-based signal processing logic"""

    # Test 1: Initial Signal with timestamp (no 'trade' field)
    print("\n=== Testing Initial Signal with Timestamp ===")
    initial_signal = {
        "timestamp": "2025-06-12T19:02:33.311Z",  # Has 'Z' that should be truncated
        "content": "@Woods\nHype scalp risky 42.23 stop 41.03 (edited)",
        "structured": "HYPE|Entry:|42.23|SL:|41.03",
        "trader": "@Woods"
    }

    try:
        result = await discord_bot.process_signal(initial_signal)
        print(f"Initial Signal Result: {json.dumps(result, indent=2)}")
    except Exception as e:
        print(f"Initial Signal Error: {e}")

    # Test 2: Follow-up Signal (has 'trade' field)
    print("\n=== Testing Follow-up Signal ===")
    followup_signal = {
        "discord_id": "1386336471073689725",
        "trader": "@Johnny",
        "trade": "1386135724197154887",  # This references the original signal_id
        "timestamp": "2025-06-22T13:26:11.590Z",
        "content": " ETH 🚀｜trades: Stopped out @Johnny",
        "structured": ""
    }

    try:
        result = await discord_bot.process_signal(followup_signal)
        print(f"Follow-up Signal Result: {json.dumps(result, indent=2)}")
    except Exception as e:
        print(f"Follow-up Signal Error: {e}")

    # Test 3: Test timestamp cleaning function directly
    print("\n=== Testing Timestamp Cleaning ===")
    from discord_bot.database import find_trade_by_timestamp

    timestamps_to_test = [
        "2025-06-12T19:02:33.311Z",  # With Z
        "2025-06-12T19:02:33.311",   # Without Z
        "2025-06-22T13:26:11.590Z",  # Another with Z
    ]

    for ts in timestamps_to_test:
        clean_ts = ts.rstrip('Z') if ts.endswith('Z') else ts
        print(f"Original: {ts} → Cleaned: {clean_ts}")

        try:
            trade = await find_trade_by_timestamp(ts)
            print(f"  Found trade: {trade is not None}")
        except Exception as e:
            print(f"  Database timestamp search error: {e}")

def test_signal_classification():
    """Test signal classification logic"""
    print("\n=== Testing Signal Classification ===")

    # Test signals
    signals = [
        {
            "name": "Initial Signal (timestamp-based)",
            "data": {
                "timestamp": "2025-06-12T19:02:33.311Z",
                "content": "@Woods\nHype scalp risky 42.23 stop 41.03 (edited)",
                "structured": "HYPE|Entry:|42.23|SL:|41.03"
            }
        },
        {
            "name": "Follow-up Signal (signal_id-based)",
            "data": {
                "discord_id": "1386336471073689725",
                "trader": "@Johnny",
                "trade": "1386135724197154887",
                "timestamp": "2025-06-22T13:26:11.590Z",
                "content": " ETH 🚀｜trades: Stopped out @Johnny"
            }
        }
    ]

    for signal in signals:
        has_trade_field = "trade" in signal["data"]
        signal_type = "Follow-up (signal_id)" if has_trade_field else "Initial (timestamp)"
        print(f"{signal['name']}: Classified as {signal_type} signal")

async def main():
    """Run all tests"""
    print("Starting Timestamp-Based Signal Processing Logic Tests")
    print("="*60)

    # Test signal classification
    test_signal_classification()

    # Test the full processing logic
    await test_timestamp_processing()

    print("\n" + "="*60)
    print("Tests completed!")
    print("\nKey Changes:")
    print("- Initial signals now use timestamp matching (with Z truncation)")
    print("- Follow-up signals still use signal_id matching")
    print("- No more content string matching issues")

if __name__ == "__main__":
    asyncio.run(main())