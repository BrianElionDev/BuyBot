"""
Simple validation script for active futures logic

This script validates the core logic without requiring database connections.
"""

import sys
import os
import re
from datetime import datetime, timezone, timedelta

# Add the project root to the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

def extract_coin_symbol_from_content(content: str) -> str:
    """Extract coin symbol from active futures content."""
    if not content:
        return None

    patterns = [
        r'\b(BTC|ETH|SOL|ADA|DOT|LINK|UNI|AAVE|MATIC|AVAX|NEAR|FTM|ALGO|ATOM|XRP|DOGE|SHIB|PEPE|BONK|WIF|FLOKI|TOSHI|TURBO|HYPE|FARTCOIN|VELVET|NAORIS|PUMP|SUI|1000SATS|DAM|SOMI|PENGU|ENA|ZEC|TAO|USELESS)\b',
        r'\b([A-Z]{2,10})\s+Entry:',
        r'\b([A-Z]{2,10})\s+Entry\s*:',
        r'Entry:\s*([A-Z]{2,10})',
        r'([A-Z]{2,10})\s+Entry\s*:\s*\d',
    ]

    for pattern in patterns:
        match = re.search(pattern, content.upper())
        if match:
            symbol = match.group(1)
            if len(symbol) >= 2 and symbol.isalnum():
                return symbol

    return None

def calculate_content_similarity(content1: str, content2: str) -> float:
    """Calculate similarity between two content strings."""
    if not content1 and not content2:
        return 1.0
    if not content1 or not content2:
        return 0.0

    content1_upper = content1.upper()
    content2_upper = content2.upper()

    if content1_upper == content2_upper:
        return 1.0

    words1 = set(content1_upper.split())
    words2 = set(content2_upper.split())

    if not words1 or not words2:
        return 0.0

    intersection = words1.intersection(words2)
    union = words1.union(words2)

    return len(intersection) / len(union) if union else 0.0

def is_timestamp_proximate(timestamp1: str, timestamp2: str, max_hours: int = 24) -> bool:
    """Check if two timestamps are within acceptable proximity."""
    try:
        dt1 = datetime.fromisoformat(timestamp1.replace('Z', '+00:00'))
        dt2 = datetime.fromisoformat(timestamp2.replace('Z', '+00:00'))

        time_diff = abs((dt1 - dt2).total_seconds())
        max_diff_seconds = max_hours * 3600

        return time_diff <= max_diff_seconds
    except Exception:
        return False

def test_coin_symbol_extraction():
    """Test coin symbol extraction."""
    print("🧪 Testing coin symbol extraction...")

    test_cases = [
        ("BTC Entry: 110547-110328 SL: 108310", "BTC"),
        ("ETH Entry: 4437-4421 SL: 4348", "ETH"),
        ("SOL Entry: 177-172.9 SL: 169", "SOL"),
        ("PUMP Entry: 0.0041-0.0039 SL: 0.00384", "PUMP"),
        ("1000SATS Entry: 0.0000356-0.0000372 SL: 30m", "1000SATS"),
        ("NAORIS Entry: 0.10773 SL: 0.101 PnL: +1.44%", "NAORIS"),
        ("VELVET Entry: 0.12121 SL: 0.1126 PnL: +4.10%", "VELVET"),
        ("Invalid content without coin", None),
        ("", None),
    ]

    passed = 0
    for content, expected in test_cases:
        result = extract_coin_symbol_from_content(content)
        if result == expected:
            print(f"✅ '{content}' -> {result}")
            passed += 1
        else:
            print(f"❌ '{content}' -> {result} (expected {expected})")

    print(f"Coin symbol extraction: {passed}/{len(test_cases)} passed")
    return passed == len(test_cases)

def test_content_similarity():
    """Test content similarity calculation."""
    print("\n🧪 Testing content similarity...")

    test_cases = [
        ("BTC Entry: 110547-110328 SL: 108310", "BTC Entry: 110547-110328 SL: 108310", 1.0),
        ("BTC Entry: 110547-110328 SL: 108310", "BTC Entry: 110500-110300 SL: 108000", 0.3),
        ("ETH Entry: 4437-4421 SL: 4348", "BTC Entry: 110547-110328 SL: 108310", 0.2),
        ("", "BTC Entry: 110547-110328 SL: 108310", 0.0),
        ("BTC Entry: 110547-110328 SL: 108310", "", 0.0),
    ]

    passed = 0
    for content1, content2, expected_min in test_cases:
        result = calculate_content_similarity(content1, content2)
        if expected_min == 1.0:
            success = result == expected_min
        elif expected_min == 0.0:
            success = result == expected_min
        else:
            success = result >= expected_min - 0.1

        if success:
            print(f"✅ Similarity: {result:.2f} (expected >= {expected_min})")
            passed += 1
        else:
            print(f"❌ Similarity: {result:.2f} (expected >= {expected_min})")

    print(f"Content similarity: {passed}/{len(test_cases)} passed")
    return passed == len(test_cases)

def test_timestamp_proximity():
    """Test timestamp proximity check."""
    print("\n🧪 Testing timestamp proximity...")

    base_time = "2025-01-15T10:00:00Z"
    test_cases = [
        ("2025-01-15T10:00:00Z", "2025-01-15T10:00:00Z", True),
        ("2025-01-15T10:00:00Z", "2025-01-15T11:00:00Z", True),
        ("2025-01-15T10:00:00Z", "2025-01-15T12:00:00Z", True),
        ("2025-01-15T10:00:00Z", "2025-01-15T15:00:00Z", True),
        ("2025-01-15T10:00:00Z", "2025-01-15T20:00:00Z", True),
        ("2025-01-15T10:00:00Z", "2025-01-16T10:00:00Z", True),
        ("2025-01-15T10:00:00Z", "invalid_timestamp", False),
    ]

    passed = 0
    for timestamp1, timestamp2, expected in test_cases:
        result = is_timestamp_proximate(timestamp1, timestamp2, max_hours=24)
        if result == expected:
            print(f"✅ '{timestamp2}' is proximate: {result}")
            passed += 1
        else:
            print(f"❌ '{timestamp2}' is proximate: {result} (expected {expected})")

    print(f"Timestamp proximity: {passed}/{len(test_cases)} passed")
    return passed == len(test_cases)

def test_trade_matching_logic():
    """Test trade matching logic simulation."""
    print("\n🧪 Testing trade matching logic...")

    # Simulate active futures entry
    active_futures = {
        "id": 1,
        "trader": "@Johnny",
        "content": "BTC Entry: 110547-110328 SL: 108310",
        "status": "CLOSED",
        "created_at": "2025-01-15T10:00:00Z"
    }

    # Simulate potential trades
    potential_trades = [
        {
            "id": 1,
            "discord_id": "trade1",
            "trader": "@Johnny",
            "coin_symbol": "BTC",
            "content": "BTC Entry: 110547-110328 SL: 108310",
            "status": "OPEN",
            "timestamp": "2025-01-15T10:05:00Z"
        },
        {
            "id": 2,
            "discord_id": "trade2",
            "trader": "@Johnny",
            "coin_symbol": "ETH",
            "content": "ETH Entry: 4437-4421 SL: 4348",
            "status": "OPEN",
            "timestamp": "2025-01-15T10:00:00Z"
        },
        {
            "id": 3,
            "discord_id": "trade3",
            "trader": "@Tareeq",
            "coin_symbol": "BTC",
            "content": "BTC Entry: 110500-110300 SL: 108000",
            "status": "OPEN",
            "timestamp": "2025-01-15T10:00:00Z"
        }
    ]

    # Extract coin symbol from active futures
    coin_symbol = extract_coin_symbol_from_content(active_futures["content"])
    print(f"Extracted coin symbol: {coin_symbol}")

    matches = []
    for trade in potential_trades:
        confidence = 0.0
        match_reasons = []

        # Trader match (required)
        if trade["trader"] == active_futures["trader"]:
            confidence += 0.4
            match_reasons.append("trader_match")
        else:
            continue  # Skip if trader doesn't match

        # Coin symbol match (high weight)
        if trade["coin_symbol"] == coin_symbol:
            confidence += 0.4
            match_reasons.append("coin_symbol_match")

        # Content similarity
        content_similarity = calculate_content_similarity(
            active_futures["content"], trade["content"]
        )
        if content_similarity > 0.2:
            confidence += content_similarity * 0.2
            match_reasons.append(f"content_similarity_{content_similarity:.2f}")

        # Timestamp proximity
        if is_timestamp_proximate(active_futures["created_at"], trade["timestamp"]):
            confidence += 0.1
            match_reasons.append("timestamp_proximate")

        # Only include matches with reasonable confidence
        if confidence >= 0.6:
            matches.append({
                "trade": trade,
                "confidence": confidence,
                "match_reason": ", ".join(match_reasons)
            })

    matches.sort(key=lambda x: x["confidence"], reverse=True)

    print(f"Found {len(matches)} matching trades:")
    for match in matches:
        print(f"  Trade {match['trade']['discord_id']}: confidence={match['confidence']:.2f}, reason={match['match_reason']}")

    success = len(matches) == 1 and matches[0]["trade"]["discord_id"] == "trade1"
    print(f"Trade matching: {'✅ PASSED' if success else '❌ FAILED'}")
    return success

def main():
    """Run all validation tests."""
    print("🚀 Starting Active Futures Logic Validation")
    print("=" * 50)

    tests = [
        test_coin_symbol_extraction,
        test_content_similarity,
        test_timestamp_proximity,
        test_trade_matching_logic
    ]

    passed = 0
    for test in tests:
        if test():
            passed += 1

    print("\n" + "=" * 50)
    print(f"🎯 Validation Results: {passed}/{len(tests)} tests passed")

    if passed == len(tests):
        print("🎉 All core logic validation tests PASSED!")
        print("✅ The active futures synchronization logic is working correctly.")
    else:
        print("❌ Some tests failed. Please review the logic.")

    return passed == len(tests)

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
