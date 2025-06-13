import re
import logging
from typing import Dict, Optional, Tuple, Union, Literal
from decimal import Decimal

logger = logging.getLogger(__name__)

class SignalParser:
    def __init__(self):
        self.signal_patterns = {
            'trade_detected': r'👋 Trade Detected:',
            'buy_amount': r'🟢 \+ ([\d,]+\.?\d*) ([A-Za-z0-9]+)',
            'sell_amount': r'🔴 - ([\d,]+\.?\d*) ([A-Za-z0-9]+)',
            'price': r'💵 Price per token \$([\d,]+\.?\d*) USD',
            'value': r'💎 Valued at \$([\d,]+\.?\d*) USD',
            'blockchain': r'🔗 ([A-Za-z]+) Blockchain',
            'wallet_type': r'◽️ ([A-Za-z]+) Wallet'
        }

    def parse_signal(self, message: str) -> Optional[Dict[str, Union[str, float, Decimal]]]:
        """
        Parse a trading signal message and extract relevant information.

        Args:
            message: The signal message text

        Returns:
            Dictionary containing parsed signal information or None if parsing fails
        """
        try:
            # Check if this is a trade signal
            if not re.search(self.signal_patterns['trade_detected'], message):
                return None

            # Extract buy information
            buy_match = re.search(self.signal_patterns['buy_amount'], message)
            if not buy_match:
                logger.error("Could not parse buy amount from signal")
                return None
            buy_amount = Decimal(buy_match.group(1).replace(',', ''))
            buy_coin = buy_match.group(2)

            # Extract sell information
            sell_match = re.search(self.signal_patterns['sell_amount'], message)
            if not sell_match:
                logger.error("Could not parse sell amount from signal")
                return None
            sell_amount = Decimal(sell_match.group(1).replace(',', ''))
            sell_coin = sell_match.group(2)

            # Extract price information
            price_match = re.search(self.signal_patterns['price'], message)
            if not price_match:
                logger.error("Could not parse price from signal")
                return None
            price = Decimal(price_match.group(1).replace(',', ''))

            # Extract value information
            value_match = re.search(self.signal_patterns['value'], message)
            if not value_match:
                logger.error("Could not parse value from signal")
                return None
            value = Decimal(value_match.group(1).replace(',', ''))

            # Extract blockchain information
            blockchain_match = re.search(self.signal_patterns['blockchain'], message)
            blockchain = blockchain_match.group(1) if blockchain_match else None

            # Extract wallet type
            wallet_match = re.search(self.signal_patterns['wallet_type'], message)
            wallet_type = wallet_match.group(1) if wallet_match else None

            # Determine if this is a CEX or DEX trade
            is_dex = blockchain and blockchain.lower() == 'ethereum'
            exchange_type = 'dex' if is_dex else 'cex'

            # For Binance, we need to convert the trading pair format
            if exchange_type == 'cex':
                # Convert coin symbols to Binance format
                # For example: 0x0 -> 0X0USDT
                trading_pair = f"{sell_coin}USDT"
            else:
                # For DEX, we keep the original format
                trading_pair = f"{sell_coin}/{buy_coin}"

            return {
                'type': 'trade',
                'exchange_type': exchange_type,
                'trading_pair': trading_pair,
                'buy_coin': buy_coin,
                'sell_coin': sell_coin,
                'buy_amount': float(buy_amount),
                'sell_amount': float(sell_amount),
                'price': float(price),
                'value': float(value),
                'blockchain': blockchain,
                'wallet_type': wallet_type
            }

        except Exception as e:
            logger.error(f"Error parsing signal: {str(e)}")
            return None

    def validate_signal(self, signal: Dict) -> Tuple[bool, Optional[str]]:
        """
        Validate the parsed signal data.

        Args:
            signal: Dictionary containing parsed signal information

        Returns:
            Tuple of (is_valid, error_message)
        """
        if not signal:
            return False, "Invalid signal format"

        required_fields = ['type', 'exchange_type', 'trading_pair', 'buy_coin',
                         'sell_coin', 'buy_amount', 'sell_amount', 'price', 'value']

        for field in required_fields:
            if field not in signal:
                return False, f"Missing required field: {field}"

        if signal['type'] != 'trade':
            return False, "Invalid signal type"

        if signal['exchange_type'] not in ['cex', 'dex']:
            return False, "Invalid exchange type"

        if signal['buy_amount'] <= 0 or signal['sell_amount'] <= 0:
            return False, "Invalid amounts"

        if signal['price'] <= 0:
            return False, "Invalid price"

        if signal['value'] <= 0:
            return False, "Invalid value"

        return True, None