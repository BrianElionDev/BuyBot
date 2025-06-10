#!/usr/bin/env python3
"""
Test the updated buy/sell parsing logic
"""
import sys
import os
import re
import logging

# Setup logging for testing
logging.basicConfig(level=logging.INFO, format='%(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def parse_enhanced_signal(text: str):
    """
    Enhanced parsing to extract sell_coin, buy_coin, price, and validate ETH/USDC requirement
    Returns: (sell_coin, buy_coin, price, is_valid_transaction)
    """
    logger.info(f"Enhanced parsing: {text[:200]}...")

    sell_coin = None
    buy_coin = None
    price = None
    is_valid_transaction = False

    # Extract coins based on the actual signal logic:
    # 🟢 + COIN = BUYING COIN (green with plus)
    # 🔴 - COIN = SPENDING COIN to buy (red with minus)
    # 🟢 - COIN = SELLING COIN (green with minus)
    # 🔴 + COIN = GETTING COIN from selling (red with plus)

    # First, determine if this is a BUY or SELL transaction
    transaction_type = None

    # Check for BUY pattern: 🟢 + [coin] and 🔴 - [coin]
    green_plus_match = re.search(r'🟢\s*\+', text)
    red_minus_match = re.search(r'🔴\s*-', text)

    # Check for SELL pattern: 🟢 - [coin] and 🔴 + [coin]
    green_minus_match = re.search(r'🟢\s*-', text)
    red_plus_match = re.search(r'🔴\s*\+', text)

    if green_plus_match and red_minus_match:
        transaction_type = "BUY"
        logger.info(f"[TRANSACTION] Detected BUY transaction (🟢+ and 🔴-)")
    elif green_minus_match and red_plus_match:
        transaction_type = "SELL"
        logger.info(f"[TRANSACTION] Detected SELL transaction (🟢- and 🔴+)")
    else:
        logger.warning(f"[WARNING] Could not determine transaction type")

    # Patterns for extracting coins from green lines
    green_patterns = [
        # Format: 🟢 + 1,200 LINK (Chainlink (https://etherscan.io/address/...))
        r'🟢\s*[+-]\s*[\d,.]+\s*([A-Z0-9]{1,10})\s*\(',
        # Format: 🟢 + 1,200 LINK
        r'🟢\s*[+-]\s*[\d,.]+\s*([A-Z0-9]{1,10})',
        # More flexible patterns
        r'🟢[^A-Z]*([A-Z0-9]{2,10})',
    ]

    # Patterns for extracting coins from red lines
    red_patterns = [
        # Format: 🔴 - 18,000 USD Coin (USDC (https://etherscan.io/address/...))
        r'🔴\s*[+-]\s*[\d,.]+\s*[^(]*\(([A-Z0-9]{1,10})\s*\(',
        # Format: 🔴 - 18,000 USD Coin (USDC)
        r'🔴\s*[+-]\s*[\d,.]+\s*[^(]*\(([A-Z0-9]{1,10})\)',
        # Format: 🔴 + 2,550 USDC
        r'🔴\s*[+-]\s*[\d,.]+\s*([A-Z0-9]{1,10})',
        # More flexible patterns
        r'🔴[^(]*\(([A-Z0-9]{2,10})\)',
    ]

    # Extract coins from green and red lines
    green_coin = None
    red_coin = None

    # Find coin in green line
    for i, pattern in enumerate(green_patterns):
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            green_coin = match.group(1).upper().strip()
            logger.info(f"Found green coin: {green_coin} using pattern {i+1}")
            break

    if not green_coin:
        logger.warning(f"⚠️ Failed to parse green coin. Check regex patterns")
        # Extract green line for debugging
        green_line_match = re.search(r'(🟢[^\n\r]*)', text)
        if green_line_match:
            green_line = green_line_match.group(1).strip()
            logger.warning(f"Green line content: {green_line}")
            # Try simple extraction for common tokens
            for token in ['ETH', 'BTC', 'WBTC', 'USDC', 'USDT', 'LINK']:
                if token in green_line.upper():
                    green_coin = token
                    logger.info(f"Found green coin using fallback: {green_coin}")
                    break

    # Find coin in red line
    for i, pattern in enumerate(red_patterns):
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            red_coin = match.group(1).upper().strip()
            logger.info(f"Found red coin: {red_coin} using pattern {i+1}")
            break

    if not red_coin:
        logger.warning(f"⚠️ Failed to parse red coin. Check regex patterns")
        # Extract red line for debugging
        red_line_match = re.search(r'(🔴[^\n\r]*)', text)
        if red_line_match:
            red_line = red_line_match.group(1).strip()
            logger.warning(f"Red line content: {red_line}")
            # Try simple extraction for common tokens
            for token in ['USDC', 'USDT', 'DAI', 'ETH', 'BTC', 'LINK']:
                if token in red_line.upper():
                    red_coin = token
                    logger.info(f"Found red coin using fallback: {red_coin}")
                    break

    # Determine buy_coin and sell_coin based on transaction type
    if transaction_type == "BUY":
        # BUY: 🟢 + [buy_coin], 🔴 - [sell_coin]
        buy_coin = green_coin  # What we're getting (green +)
        sell_coin = red_coin   # What we're spending (red -)
        logger.info(f"[BUY] Buying {buy_coin} with {sell_coin}")
    elif transaction_type == "SELL":
        # SELL: 🟢 - [sell_coin], 🔴 + [buy_coin]
        sell_coin = green_coin  # What we're selling (green -)
        buy_coin = red_coin     # What we're getting (red +)
        logger.info(f"[SELL] Selling {sell_coin} for {buy_coin}")
    else:
        # Fallback - try to determine from the coins themselves
        logger.warning(f"[FALLBACK] Could not determine transaction type, using fallback logic")
        # If one is ETH/USDC and the other isn't, assume we're trading the base currency
        if green_coin in ['ETH', 'USDC'] and red_coin not in ['ETH', 'USDC']:
            sell_coin = green_coin
            buy_coin = red_coin
        elif red_coin in ['ETH', 'USDC'] and green_coin not in ['ETH', 'USDC']:
            sell_coin = red_coin
            buy_coin = green_coin
        else:
            sell_coin = green_coin
            buy_coin = red_coin

    # Validate that sell coin is ETH or USDC
    if sell_coin and sell_coin in ['ETH', 'USDC']:
        is_valid_transaction = True
        logger.info(f"✅ Valid transaction: Selling {sell_coin}")
    elif sell_coin:
        logger.warning(f"❌ Invalid transaction: Selling {sell_coin} (only ETH/USDC allowed)")
        is_valid_transaction = False
    else:
        logger.warning(f"❌ Could not determine sell coin")
        is_valid_transaction = False

    # Extract price
    price_patterns = [
        r'💰.*?Price per token\s*\$?([\d,]+\.?\d*)\s*USD',  # 💰 Price per token $0.136 USD
        r'💵.*?Price per token\s*\$?([\d,]+\.?\d*)\s*USD',  # 💵 Price per token $0.008 USD
        r'Price per token\s*\$?([\d,]+\.?\d*)\s*USD',      # Generic pattern
    ]

    for pattern in price_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            try:
                price_str = match.group(1).replace(',', '')
                price = float(price_str)
                logger.info(f"Found price: ${price}")
                break
            except (ValueError, IndexError):
                continue

    logger.info(f"Parsed result: sell={sell_coin}, buy={buy_coin}, price=${price}, valid={is_valid_transaction}")
    return sell_coin, buy_coin, price, is_valid_transaction

def test_signals():
    """Test the parsing with the provided signals"""

    # Test 1: Should be BUY LINK with USDC
    buy_signal = """👋 Trade Detected:
🟢 + 1,200 LINK (Chainlink (https://etherscan.io/address/0x514910771af9ca6536fe0a82fcd9fcdfd0a3fec4))
🔴 - 18,000 USD Coin (USDC (https://etherscan.io/address/0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48))
💵 Price per token $15.00 USD
💎 Valued at $18,000.0 USD
🔗 Ethereum Blockchain
🍰 Now holds $18,000.0 USD of Chainlink
◽️ Public Wallet"""

    # Test 2: Should be SELL ETH for USDC
    sell_signal = """👋 Trade Detected:
🟢 - 0.75 ETH (Ethereum (https://etherscan.io/address/0xplaceholder_eth_address))
🔴 + 2,550 USD Coin (USDC (https://etherscan.io/address/0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48))
💵 Price per token $3,400.00 USD
💎 Valued at $2,550.0 USD
🔗 Ethereum Blockchain
🍰 Now holds $2,550.0 USD of USDC
◽️ Public Wallet"""

    print("=" * 80)
    print("Testing BUY Signal (should buy LINK with USDC)")
    print("=" * 80)
    sell_coin, buy_coin, price, is_valid = parse_enhanced_signal(buy_signal)
    print(f"\nResult: sell={sell_coin}, buy={buy_coin}, price=${price}, valid={is_valid}")
    print(f"Expected: sell=USDC, buy=LINK, price=$15.0, valid=True")
    print(f"✅ CORRECT" if (sell_coin == 'USDC' and buy_coin == 'LINK' and price == 15.0 and is_valid) else "❌ INCORRECT")

    print("\n" + "=" * 80)
    print("Testing SELL Signal (should sell ETH for USDC)")
    print("=" * 80)
    sell_coin, buy_coin, price, is_valid = parse_enhanced_signal(sell_signal)
    print(f"\nResult: sell={sell_coin}, buy={buy_coin}, price=${price}, valid={is_valid}")
    print(f"Expected: sell=ETH, buy=USDC, price=$3400.0, valid=True")
    print(f"✅ CORRECT" if (sell_coin == 'ETH' and buy_coin == 'USDC' and price == 3400.0 and is_valid) else "❌ INCORRECT")

if __name__ == "__main__":
    test_signals()
