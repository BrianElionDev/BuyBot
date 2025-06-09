#!/usr/bin/env python3
"""
Test script to verify the enhanced signal parsing works correctly.
"""

import re

def test_parse_signal(text: str):
    """Test the signal parsing logic"""
    print(f"\n{'='*80}")
    print(f"TESTING SIGNAL PARSING")
    print(f"{'='*80}")
    print(f"Input text:\n{text}")
    print(f"{'='*80}")

    sell_coin = None
    buy_coin = None
    price = None

    # Patterns for SELLING (green line with minus)
    sell_patterns = [
        # Format: 🟢 - 0.75 ETH (Ethereum (https://etherscan.io/address/...))
        r'🟢\s*-\s*[\d,.]+\s*([A-Z0-9]{1,10})\s*\(',
        # Format: 🟢 - 0.75 ETH (Ethereum)
        r'🟢\s*-\s*[\d,.]+\s*([A-Z0-9]{1,10})\s*\(',
        # Format: 🟢 - 0.75 ETH
        r'🟢\s*-\s*[\d,.]+\s*([A-Z0-9]{1,10})',
        # More flexible patterns
        r'🟢[^A-Z]*([A-Z0-9]{2,10})',
    ]

    # Patterns for BUYING (red line with plus)
    buy_patterns = [
        # Format: 🔴 + 2,550 USD Coin (USDC (https://etherscan.io/address/...))
        r'🔴\s*\+\s*[\d,.]+\s*[^(]*\(([A-Z0-9]{1,10})\s*\(',
        # Format: 🔴 + 2,550 USD Coin (USDC)
        r'🔴\s*\+\s*[\d,.]+\s*[^(]*\(([A-Z0-9]{1,10})\)',
        # Format: 🔴 + 2,550 USDC
        r'🔴\s*\+\s*[\d,.]+\s*([A-Z0-9]{1,10})',
        # More flexible patterns
        r'🔴[^(]*\(([A-Z0-9]{2,10})\)',
    ]

    # Find sell coin (green line with minus)
    print("\nTesting SELL patterns (🟢 with minus):")
    for i, pattern in enumerate(sell_patterns):
        match = re.search(pattern, text, re.IGNORECASE)
        print(f"  Pattern {i+1}: {pattern}")
        if match:
            sell_coin = match.group(1).upper().strip()
            print(f"  ✅ MATCH! Found sell coin: {sell_coin}")
            break
        else:
            print(f"  ❌ No match")

    if not sell_coin:
        # Extract green line for debugging
        green_line_match = re.search(r'(🟢[^\n\r]*)', text)
        if green_line_match:
            green_line = green_line_match.group(1).strip()
            print(f"\nGreen line extracted: {green_line}")

            # Try simple extraction for common tokens
            for token in ['ETH', 'BTC', 'WBTC', 'USDC', 'USDT']:
                if token in green_line.upper():
                    sell_coin = token
                    print(f"✅ Found sell coin using fallback: {sell_coin}")
                    break

    # Find buy coin (red line with plus)
    print("\nTesting BUY patterns (🔴 with plus):")
    for i, pattern in enumerate(buy_patterns):
        match = re.search(pattern, text, re.IGNORECASE)
        print(f"  Pattern {i+1}: {pattern}")
        if match:
            buy_coin = match.group(1).upper().strip()
            print(f"  ✅ MATCH! Found buy coin: {buy_coin}")
            break
        else:
            print(f"  ❌ No match")

    if not buy_coin:
        # Extract red line for debugging
        red_line_match = re.search(r'(🔴[^\n\r]*)', text)
        if red_line_match:
            red_line = red_line_match.group(1).strip()
            print(f"\nRed line extracted: {red_line}")

            # Try simple extraction for common tokens
            for token in ['USDC', 'USDT', 'DAI', 'ETH', 'BTC']:
                if token in red_line.upper():
                    buy_coin = token
                    print(f"✅ Found buy coin using fallback: {buy_coin}")
                    break

    # Extract price
    print("\nTesting PRICE patterns:")
    price_patterns = [
        r'💰.*?Price per token\s*\$?([\d,]+\.?\d*)\s*USD',  # 💰 Price per token $0.136 USD
        r'💵.*?Price per token\s*\$?([\d,]+\.?\d*)\s*USD',  # 💵 Price per token $0.008 USD
        r'Price per token\s*\$?([\d,]+\.?\d*)\s*USD',      # Generic pattern
    ]

    for i, pattern in enumerate(price_patterns):
        match = re.search(pattern, text, re.IGNORECASE)
        print(f"  Price pattern {i+1}: {pattern}")
        if match:
            try:
                price_str = match.group(1).replace(',', '')
                price = float(price_str)
                print(f"  ✅ MATCH! Found price: ${price}")
                break
            except (ValueError, IndexError):
                print(f"  ❌ Match but failed to parse: {match.group(1)}")
                continue
        else:
            print(f"  ❌ No match")

    print(f"\n{'='*80}")
    print(f"FINAL RESULTS:")
    print(f"Sell coin: {sell_coin}")
    print(f"Buy coin: {buy_coin}")
    print(f"Price: ${price}")
    print(f"Valid: {sell_coin is not None and buy_coin is not None}")
    print(f"{'='*80}")

    return sell_coin, buy_coin, price

if __name__ == "__main__":
    # Test signal 1: ETH -> USDC
    signal1 = """👋 Trade Detected:
🟢 - 0.75 ETH (Ethereum (https://etherscan.io/address/0xplaceholder_eth_address))
🔴 + 2,550 USD Coin (USDC (https://etherscan.io/address/0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48))
💵 Price per token $3,400.00 USD
💎 Valued at $2,550.0 USD
🔗 Ethereum Blockchain
🍰 Now holds $2,550.0 USD of USDC
◽️ Public Wallet"""

    # Test signal 2: BTC -> USDC
    signal2 = """👋 Trade Detected:
🟢 - 4.5 BTC (Wrapped Bitcoin (WBTC) (https://etherscan.io/address/0x2260fac54fe5542f77e65839f3796d1947b73b5a))
🔴 + 270,000 USD Coin (USDC (https://etherscan.io/address/0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48))
💵 Price per token $60,000.00 USD
💎 Valued at $270,000.0 USD
🔗 Ethereum Blockchain
🍰 Now holds $270,000.0 USD of USDC
◽️ Public Wallet"""

    # Test both signals
    test_parse_signal(signal1)
    test_parse_signal(signal2)
