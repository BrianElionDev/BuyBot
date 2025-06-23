import logging
from typing import Dict, List, Optional, Union, Literal, Tuple
from decimal import Decimal
from datetime import datetime
import re

logger = logging.getLogger(__name__)

def parse_entry_prices(price_str: str) -> List[float]:
    """Parses a single price or a range like '41.90/41.68'."""
    price_str = price_str.replace('$', '').strip()
    prices = re.split(r'[/-]', price_str)
    return [float(p.strip()) for p in prices]

def extract_structured_data(content: str) -> Dict:
    """
    Parses a structured signal string like 'HYPE|Entry:|41.9-41.68|SL:|40.3'
    and extracts the coin, entry prices, and stop loss.
    """
    parts = [p.strip() for p in content.split('|')]

    # Default values
    data = {
        'coin': None,
        'entry_prices': [],
        'stop_loss': None,
        'take_profits': [],
        'order_type': 'MARKET'
    }

    try:
        # The first part is usually the coin symbol
        data['coin'] = parts[0]

        # Find entry, SL, and TPs
        for i, part in enumerate(parts):
            if part.lower() == 'entry:' and i + 1 < len(parts):
                data['entry_prices'] = parse_entry_prices(parts[i+1])
            elif part.lower() == 'sl:' and i + 1 < len(parts):
                sl_val = parts[i+1]
                # Try to convert to float, otherwise store as string (e.g., 'BE')
                try:
                    data['stop_loss'] = float(sl_val)
                except (ValueError, TypeError):
                    data['stop_loss'] = sl_val
            elif part.lower() == 'tps:' and i + 1 < len(parts):
                tp_str = parts[i+1].replace('$', '')
                data['take_profits'] = [float(p.strip()) for p in tp_str.split(',')]

        if 'limit' in parts[0].lower():
            data['order_type'] = 'LIMIT'
            data['coin'] = parts[1]

    except Exception as e:
        logger.error(f"Error parsing structured signal part: '{content}' -> {e}")

    return data

class DiscordSignalParser:
    def __init__(self):
        self.base_currencies = ['ETH', 'USDC']
        self.supported_timeframes = ['1m', '5m', '15m', '1h', '4h', '1d']
        self.supported_order_types = ['LIMIT', 'MARKET', 'SPOT']

    def _split_top_level(self, s: str) -> list:
        """Split on | but not inside parentheses."""
        parts = []
        current = ''
        depth = 0
        for c in s:
            if c == '(':
                depth += 1
            elif c == ')':
                depth = max(0, depth - 1)
            if c == '|' and depth == 0:
                parts.append(current)
                current = ''
            else:
                current += c
        if current:
            parts.append(current)
        return [p.strip() for p in parts if p.strip()]

    def _post_process_interpretation(self, interpretation: Dict):
        """Post-process the interpretation to add additional context."""
        content_lower = interpretation.get('original_content', '').lower()
        if 'short' in content_lower or 'shorted' in content_lower:
            interpretation['position_type'] = 'SHORT'
        elif 'long' in content_lower or 'longed' in content_lower:
            interpretation['position_type'] = 'LONG'

        if len(interpretation.get('entry_prices', [])) > 1 and 'average_entry' not in interpretation:
            interpretation['average_entry'] = sum(interpretation['entry_prices']) / len(interpretation['entry_prices'])

        if '1% risk' in content_lower:
            interpretation['risk_percentage'] = 1.0
        elif 'half risk' in content_lower:
            interpretation['risk_percentage'] = 0.5

        if interpretation.get('symbol'):
            interpretation['trading_pair'] = f"{interpretation['symbol']}/USDT"
            interpretation['sell_coin'] = interpretation['symbol']
            interpretation['buy_coin'] = 'USDT'


    def parse_signal(self, signal_data: Dict) -> Optional[Dict]:
        """
        Parses a signal from the Discord service.
        For now, it uses the 'structured' field.
        """
        try:
            if 'structured' not in signal_data:
                return None

            structured_content = signal_data['structured']
            parsed_data = extract_structured_data(structured_content)

            if not parsed_data.get('coin') or not parsed_data.get('entry_prices'):
                logger.warning(f"Could not parse required fields from signal: {structured_content}")
                return None

            # Use the first entry price as the main signal price for now
            signal_price = parsed_data['entry_prices'][0]

            # Final signal structure
            signal = {
                'coin_symbol': parsed_data['coin'],
                'signal_price': signal_price,
                'entry_prices': parsed_data['entry_prices'],
                'stop_loss': parsed_data.get('stop_loss'),
                'take_profits': parsed_data.get('take_profits'),
                'order_type': parsed_data.get('order_type', 'MARKET'),
                'exchange_type': 'cex' # Discord signals are for CEX
            }
            return signal
        except Exception as e:
            logger.error(f"Error in parse_signal: {e}")
            return None

    def validate_signal(self, signal: Dict) -> Tuple[bool, Optional[str]]:
        if not signal.get('coin_symbol'):
            return False, "Missing coin symbol"
        if not signal.get('signal_price') or signal['signal_price'] <= 0:
            return False, "Invalid signal price"
        return True, None