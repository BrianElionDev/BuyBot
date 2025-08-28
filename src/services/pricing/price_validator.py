import logging
from typing import List, Optional
from datetime import datetime
from .price_models import PriceValidationResult, CoinData

logger = logging.getLogger(__name__)


class PriceValidator:
    """Validates price data and coin information for quality and legitimacy"""

    def __init__(self):
        """Initialize the price validator"""
        self._suspicious_fragments = [
            'fake', 'scam', 'elon', 'moon', 'baby', 'inu', 'doge', 'moon',
            'pepe', 'safe', 'pump', 'wojak', 'cat', 'fork', 'wrapped'
        ]

        self._whitelist = [
            'dogecoin', 'shiba-inu', 'baby-doge-coin', 'dogelon', 'wrapped-bitcoin',
            'wrapped-ethereum', 'pepecoin', 'catcoin', 'safemoon'
        ]

    def validate_coin_data(self, coin_data: dict) -> bool:
        """
        Validate coin data to determine if it's likely legitimate

        Args:
            coin_data: Raw coin data from API

        Returns:
            True if coin appears legitimate, False otherwise
        """
        if not coin_data:
            return False

        # Check for required fields
        required_fields = ['id', 'symbol', 'name']
        for field in required_fields:
            if not coin_data.get(field):
                logger.warning(f"Missing required field '{field}' in coin data")
                return False

        # Check for suspicious characteristics
        if self._has_suspicious_characteristics(coin_data):
            return False

        # Check for legitimate characteristics
        if self._has_legitimate_characteristics(coin_data):
            return True

        # Default to suspicious if uncertain
        logger.warning(f"Coin {coin_data.get('id')} has uncertain legitimacy")
        return False

    def validate_price(self, price: float, symbol: str) -> PriceValidationResult:
        """
        Validate price data for reasonableness

        Args:
            price: Price value to validate
            symbol: Symbol for context

        Returns:
            PriceValidationResult with validation details
        """
        validation_errors = []
        warnings = []

        # Check for basic price validity
        if price is None or price <= 0:
            validation_errors.append("Price must be positive number")
            return PriceValidationResult(
                is_valid=False,
                price=price or 0,
                validation_errors=validation_errors,
                warnings=warnings,
                timestamp=datetime.now()
            )

        # Check for extreme price values
        if price > 1000000:  # $1M
            warnings.append("Price exceeds $1M - verify accuracy")

        if price < 0.000001:  # $0.000001
            warnings.append("Price below $0.000001 - verify accuracy")

        # Check for common price patterns
        if self._is_suspicious_price_pattern(price, symbol):
            warnings.append("Price pattern may be suspicious")

        is_valid = len(validation_errors) == 0

        return PriceValidationResult(
            is_valid=is_valid,
            price=price,
            validation_errors=validation_errors,
            warnings=warnings,
            timestamp=datetime.now()
        )

    def validate_symbol(self, symbol: str) -> bool:
        """
        Validate symbol format and characteristics

        Args:
            symbol: Symbol to validate

        Returns:
            True if symbol is valid, False otherwise
        """
        if not symbol:
            return False

        symbol = symbol.upper().strip()

        # Check length
        if len(symbol) < 1 or len(symbol) > 20:
            return False

        # Check for valid characters (alphanumeric and common symbols)
        valid_chars = set('ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-_')
        if not all(c in valid_chars for c in symbol):
            return False

        # Check for suspicious patterns
        if self._is_suspicious_symbol_pattern(symbol):
            return False

        return True

    def _has_suspicious_characteristics(self, coin_data: dict) -> bool:
        """Check if coin has suspicious characteristics"""
        coin_id = coin_data.get('id', '').lower()
        coin_name = coin_data.get('name', '')

        # Coins with very long names are often scams
        if len(coin_name) > 30:
            logger.warning(f"Coin name too long: {coin_name}")
            return True

        # Coins with overly complex IDs are often scams
        if len(coin_id) > 30:
            logger.warning(f"Coin ID too long: {coin_id}")
            return True

        # Check for suspicious strings in IDs
        for fragment in self._suspicious_fragments:
            if fragment in coin_id and coin_id not in self._whitelist:
                # Higher bar for suspicious tokens - must have market cap data
                has_market_cap = coin_data.get('market_cap_rank') is not None
                if not has_market_cap:
                    logger.warning(f"Rejecting suspicious token without market cap: {coin_id}")
                    return True

        return False

    def _has_legitimate_characteristics(self, coin_data: dict) -> bool:
        """Check if coin has legitimate characteristics"""
        # Check if it's in our whitelist
        if coin_data.get('id') in self._whitelist:
            return True

        # Check for market cap data
        if coin_data.get('market_cap_rank') is not None:
            return True

        # Check for reasonable name length
        if 3 <= len(coin_data.get('name', '')) <= 25:
            return True

        return False

    def _is_suspicious_price_pattern(self, price: float, symbol: str) -> bool:
        """Check for suspicious price patterns"""
        # Check for exact round numbers (often fake)
        if price == int(price) and price > 1000:
            return True

        # Check for suspicious decimal patterns
        price_str = str(price)
        if '.' in price_str:
            decimal_part = price_str.split('.')[1]
            if len(decimal_part) > 8:  # More than 8 decimal places
                return True

        return False

    def _is_suspicious_symbol_pattern(self, symbol: str) -> bool:
        """Check for suspicious symbol patterns"""
        # Check for excessive repetition
        if len(set(symbol)) < len(symbol) * 0.5:  # More than 50% repeated characters
            return True

        # Check for suspicious combinations
        suspicious_combos = ['FAKE', 'SCAM', 'PUMP', 'DUMP']
        if any(combo in symbol for combo in suspicious_combos):
            return True

        return False

    def get_validation_summary(self, validation_result: PriceValidationResult) -> str:
        """Get a human-readable validation summary"""
        if validation_result.is_valid:
            status = "✅ VALID"
        else:
            status = "❌ INVALID"

        summary = f"Price Validation: {status}\n"
        summary += f"Price: ${validation_result.price:,.6f}\n"
        summary += f"Timestamp: {validation_result.timestamp.strftime('%Y-%m-%d %H:%M:%S')}\n"

        if validation_result.validation_errors:
            summary += f"\nErrors:\n"
            for error in validation_result.validation_errors:
                summary += f"• {error}\n"

        if validation_result.warnings:
            summary += f"\nWarnings:\n"
            for warning in validation_result.warnings:
                summary += f"• {warning}\n"

        return summary
