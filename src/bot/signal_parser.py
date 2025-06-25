import re
from typing import Dict, Optional, Tuple

class SignalParser:
    def __init__(self):
        self.patterns = [
            re.compile(
                r"👋 (?:Trade|Swap) (?:Detected|detected):\s*\n"
                r"🟢 \+ [\d,.]+\s+(?P<buy_coin>.+?)\s*\n"
                r"🔴 - [\d,.]+\s+(?P<sell_coin>.+?)\s*\n"
                r"💵 Price per token \$(?P<price>[\d.]+)"
            )
        ]

    def _cleanup_coin_name(self, coin_name: str) -> str:
        """Extracts symbol from parentheses if available, otherwise returns the name."""
        coin_name = coin_name.strip()
        paren_match = re.search(r'\((.*?)\)', coin_name)
        if paren_match:
            return paren_match.group(1).strip()
        return coin_name

    def parse_signal(self, message: str) -> Optional[Dict]:
        for pattern in self.patterns:
            match = pattern.search(message)
            if match:
                data = match.groupdict()
                return {
                    'buy_coin': self._cleanup_coin_name(data['buy_coin']),
                    'sell_coin': self._cleanup_coin_name(data['sell_coin']),
                    'price': float(data['price'])
                }
        return None

    def validate_signal(self, signal: Dict) -> Tuple[bool, Optional[str]]:
        if not all(key in signal for key in ['buy_coin', 'sell_coin', 'price']):
            return False, "Missing required fields in signal"
        if not isinstance(signal['price'], (int, float)) or signal['price'] <= 0:
            return False, "Invalid price"
        return True, None