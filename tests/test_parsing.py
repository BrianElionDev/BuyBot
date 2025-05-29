#!/usr/bin/env python3
import re

# Test message format
test_message = """👋 Trade detected:
🟢 +531,835.742 Destra Network (DSync)
🔴 - 41.5 Ether (ETH)
💰 Price per token $0.136 USD
💎 Valued at $72,466.187 USD
🛡 Ethereum Blockchain
🤑 Now holds $177,487.57 USD of Destra Network
📄 0x0Papi"""

print("Testing message parsing...")
print("Original message:")
print(test_message)
print("\n" + "="*50 + "\n")

# Test symbol extraction
print("Testing symbol extraction...")
symbol_pattern = r'🟢\s*[+\-]?[\d,]+\.?\d*\s+([^(]+)\s*\(([A-Z0-9]+)\)'
symbol_match = re.search(symbol_pattern, test_message, re.IGNORECASE)
if symbol_match:
    coin_name = symbol_match.group(1).strip()
    coin_symbol = symbol_match.group(2).upper()
    print(f"✅ Found coin: {coin_name} ({coin_symbol})")
else:
    print("❌ No symbol match found")

# Test price extraction
print("\nTesting price extraction...")
price_pattern = r'💰\s*Price per token\s*\$?([\d,]+\.?\d*)\s*USD'
price_match = re.search(price_pattern, test_message, re.IGNORECASE)
if price_match:
    price_str = price_match.group(1).replace(',', '')
    price = float(price_str)
    print(f"✅ Found price: ${price}")
else:
    print("❌ No price match found")

# Test message start detection
print("\nTesting message start detection...")
if test_message.startswith('👋 Trade detected'):
    print("✅ Message starts with '👋 Trade detected'")
elif test_message.startswith('Trade detected'):
    print("✅ Message starts with 'Trade detected'")
else:
    print("❌ Message doesn't start with expected patterns")
