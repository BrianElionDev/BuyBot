import re

# Test patterns
test_text = "🟢 +531,835.742 Destra Network (DSync)"
print(f"Testing text: {test_text}")

# Pattern to extract symbol
pattern = r'\(([A-Z0-9]+)\)'
match = re.search(pattern, test_text)
if match:
    symbol = match.group(1)
    print(f"Symbol found: {symbol}")
else:
    print("No symbol found")

# Pattern to extract name and symbol
pattern2 = r'([^(]+)\s*\(([A-Z0-9]+)\)'
match2 = re.search(pattern2, test_text)
if match2:
    name = match2.group(1).strip()
    symbol = match2.group(2)
    print(f"Name: {name}, Symbol: {symbol}")

# Test price pattern
price_text = "💰 Price per token $0.136 USD"
price_pattern = r'Price per token\s*\$?([\d,]+\.?\d*)\s*USD'
price_match = re.search(price_pattern, price_text)
if price_match:
    price = float(price_match.group(1))
    print(f"Price: ${price}")
