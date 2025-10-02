#!/usr/bin/env python3
"""
KuCoin Symbol Format Converter

This module handles the conversion between bot symbol format (COINUSDT)
and KuCoin symbol format (COIN-USDT) for both spot and futures trading.
"""

import logging
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

class KucoinSymbolConverter:
    """
    Converts symbols between bot format and KuCoin format.

    Bot Format: COINUSDT (e.g., ASTERUSDT, BTCUSDT)
    KuCoin Spot Format: COIN-USDT (e.g., ASTER-USDT, BTC-USDT)
    KuCoin Futures Format: COINUSDTM (e.g., ASTERUSDTM, BTCUSDTM)
    """

    def __init__(self):
        """Initialize the symbol converter."""
        self.symbol_cache: Dict[str, str] = {}
        self.available_symbols: List[str] = []

        # Known symbol mappings for special cases
        self.special_mappings = {
            # No special mappings needed - KuCoin uses standard BTC format
        }

    def convert_bot_to_kucoin_spot(self, bot_symbol: str) -> str:
        """
        Convert bot symbol format to KuCoin spot format.

        Args:
            bot_symbol: Bot symbol format (e.g., 'ASTERUSDT')

        Returns:
            KuCoin spot symbol format (e.g., 'ASTER-USDT')
        """
        if not bot_symbol:
            return bot_symbol

        # Check special mappings first
        if bot_symbol in self.special_mappings:
            return self.special_mappings[bot_symbol]

        # Convert COINUSDT to COIN-USDT
        if bot_symbol.endswith('USDT'):
            base_coin = bot_symbol[:-4]  # Remove USDT
            return f"{base_coin}-USDT"

        # If it already has a dash, return as is
        if '-' in bot_symbol:
            return bot_symbol

        # If it doesn't end with USDT, add it
        return f"{bot_symbol}-USDT"

    def convert_bot_to_kucoin_futures(self, bot_symbol: str) -> str:
        """
        Convert bot symbol format to KuCoin futures format.

        Args:
            bot_symbol: Bot symbol format (e.g., 'ASTERUSDT')

        Returns:
            KuCoin futures symbol format (e.g., 'ASTERUSDTM')
        """
        if not bot_symbol:
            return bot_symbol

        # Check special mappings first
        if bot_symbol in self.special_mappings:
            return self.special_mappings[bot_symbol]

        # Convert COINUSDT to COINUSDTM
        if bot_symbol.endswith('USDT'):
            return f"{bot_symbol}M"

        # If it already ends with USDTM, return as is
        if bot_symbol.endswith('USDTM'):
            return bot_symbol

        # If it has a dash, convert to futures format
        if '-' in bot_symbol:
            return bot_symbol.replace('-', '') + 'M'

        # Add USDTM if it doesn't have USDT
        return f"{bot_symbol}USDTM"

    def convert_kucoin_to_bot(self, kucoin_symbol: str) -> str:
        """
        Convert KuCoin symbol format back to bot format.

        Args:
            kucoin_symbol: KuCoin symbol format (e.g., 'ASTER-USDT' or 'ASTERUSDTM')

        Returns:
            Bot symbol format (e.g., 'ASTERUSDT')
        """
        if not kucoin_symbol:
            return kucoin_symbol

        # Handle special mappings
        reverse_mappings = {v: k for k, v in self.special_mappings.items()}
        if kucoin_symbol in reverse_mappings:
            return reverse_mappings[kucoin_symbol]

        # Convert COIN-USDT to COINUSDT
        if '-' in kucoin_symbol:
            return kucoin_symbol.replace('-', '')

        # Convert COINUSDTM to COINUSDT
        if kucoin_symbol.endswith('USDTM'):
            return kucoin_symbol[:-1]  # Remove the M

        return kucoin_symbol

    def get_symbol_variants(self, bot_symbol: str) -> List[str]:
        """
        Get all possible KuCoin symbol variants for a given bot symbol.

        Args:
            bot_symbol: Bot symbol format (e.g., 'ASTERUSDT')

        Returns:
            List of possible KuCoin symbol formats
        """
        variants = []

        # Spot format
        spot_symbol = self.convert_bot_to_kucoin_spot(bot_symbol)
        variants.append(spot_symbol)

        # Futures format
        futures_symbol = self.convert_bot_to_kucoin_futures(bot_symbol)
        variants.append(futures_symbol)

        # Original format (in case it's already correct)
        variants.append(bot_symbol)

        # Remove duplicates while preserving order
        seen = set()
        unique_variants = []
        for variant in variants:
            if variant not in seen:
                seen.add(variant)
                unique_variants.append(variant)

        return unique_variants

    def find_matching_symbol(self, bot_symbol: str, available_symbols: List[str], trading_type: str = "futures") -> Optional[str]:
        """
        Find the matching KuCoin symbol from available symbols.

        Args:
            bot_symbol: Bot symbol format (e.g., 'ASTERUSDT')
            available_symbols: List of available KuCoin symbols
            trading_type: Type of trading ('futures' or 'spot')

        Returns:
            Matching KuCoin symbol or None if not found
        """
        if not available_symbols:
            logger.warning("No available symbols provided for matching")
            return None

        # Get variants based on trading type
        if trading_type.lower() == "futures":
            target_symbol = self.convert_bot_to_kucoin_futures(bot_symbol)
        else:
            target_symbol = self.convert_bot_to_kucoin_spot(bot_symbol)

        # Check if target symbol is available
        if target_symbol in available_symbols:
            logger.info(f"Found exact match for {bot_symbol}: {target_symbol}")
            return target_symbol

        # Try all variants
        variants = self.get_symbol_variants(bot_symbol)
        for variant in variants:
            if variant in available_symbols:
                logger.info(f"Found variant match for {bot_symbol}: {variant}")
                return variant

        # Try case-insensitive matching
        available_upper = [s.upper() for s in available_symbols]
        target_upper = target_symbol.upper()
        if target_upper in available_upper:
            # Find the original case version
            for symbol in available_symbols:
                if symbol.upper() == target_upper:
                    logger.info(f"Found case-insensitive match for {bot_symbol}: {symbol}")
                    return symbol

        logger.warning(f"No matching symbol found for {bot_symbol} in {len(available_symbols)} available symbols")
        return None

    def is_symbol_supported(self, bot_symbol: str, available_symbols: List[str], trading_type: str = "futures") -> bool:
        """
        Check if a bot symbol is supported on KuCoin.

        Args:
            bot_symbol: Bot symbol format (e.g., 'ASTERUSDT')
            available_symbols: List of available KuCoin symbols
            trading_type: Type of trading ('futures' or 'spot')

        Returns:
            True if supported, False otherwise
        """
        matching_symbol = self.find_matching_symbol(bot_symbol, available_symbols, trading_type)
        return matching_symbol is not None

    def get_symbol_info(self, bot_symbol: str, available_symbols: List[str], trading_type: str = "futures") -> Dict[str, any]:
        """
        Get comprehensive symbol information.

        Args:
            bot_symbol: Bot symbol format (e.g., 'ASTERUSDT')
            available_symbols: List of available KuCoin symbols
            trading_type: Type of trading ('futures' or 'spot')

        Returns:
            Dictionary with symbol information
        """
        matching_symbol = self.find_matching_symbol(bot_symbol, available_symbols, trading_type)

        return {
            "bot_symbol": bot_symbol,
            "kucoin_spot": self.convert_bot_to_kucoin_spot(bot_symbol),
            "kucoin_futures": self.convert_bot_to_kucoin_futures(bot_symbol),
            "matching_symbol": matching_symbol,
            "is_supported": matching_symbol is not None,
            "trading_type": trading_type,
            "variants": self.get_symbol_variants(bot_symbol)
        }

    def clear_cache(self) -> None:
        """Clear the symbol cache."""
        self.symbol_cache.clear()
        logger.info("KuCoin symbol converter cache cleared")

    def get_cache_stats(self) -> Dict[str, int]:
        """Get cache statistics."""
        return {
            "cached_mappings": len(self.symbol_cache),
            "available_symbols": len(self.available_symbols)
        }

# Global instance for easy access
symbol_converter = KucoinSymbolConverter()
