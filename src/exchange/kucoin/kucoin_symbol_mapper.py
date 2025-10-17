"""
KuCoin Symbol Mapping Utility

Handles symbol resolution and mapping between different KuCoin trading formats.
This addresses the issue where symbols like DAM-USDT are not directly supported.
"""

import logging
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class KucoinSymbolMapper:
    """
    Maps trading symbols to KuCoin-specific formats.

    KuCoin has different symbol formats for different trading types:
    - Spot: BTC-USDT
    - Futures: BTCUSDTM (perpetual) or BTCUSDT (delivery)
    - Margin: BTC-USDT
    """

    def __init__(self):
        """Initialize the symbol mapper."""
        self.symbol_cache: Dict[str, str] = {}
        self.available_symbols: List[str] = []
        # Known KuCoin aliases (key: common base, value: KuCoin base)
        self.alias_map: Dict[str, str] = {
            "BTC": "XBT",  # KuCoin futures uses XBT for Bitcoin
        }

    def get_symbol_variants(self, symbol: str) -> List[str]:
        """
        Get all possible KuCoin symbol variants for a given symbol.

        Args:
            symbol: Trading symbol (e.g., 'DAM-USDT', 'BTC-USDT')

        Returns:
            List of possible KuCoin symbol formats
        """
        base = symbol.split('-')[0].upper()

        # Handle BTC -> XBT mapping for KuCoin
        if base == "BTC":
            variants = [
                symbol.upper(),              # BTC-USDT (spot format)
                "XBT-USDT",                  # XBT-USDT (KuCoin spot format)
                "BTCUSDT",                   # BTCUSDT (delivery)
                "XBTUSDT",                   # XBTUSDT (KuCoin delivery)
                "BTCUSDTM",                  # BTCUSDTM (perpetual)
                "XBTUSDTM",                  # XBTUSDTM (KuCoin perpetual)
            ]
        else:
            variants = [
                symbol.upper(),              # DAM-USDT (spot format)
                f"{base}USDT",              # DAMUSDT (delivery)
                f"{base}USDTM",             # DAMUSDTM (perpetual)
            ]

        # Remove duplicates while preserving order
        seen = set()
        unique_variants = []
        for variant in variants:
            if variant not in seen:
                seen.add(variant)
                unique_variants.append(variant)

        return unique_variants

    def map_to_futures_symbol(self, symbol: str, available_symbols: List[str]) -> Optional[str]:
        """
        Map a symbol to the correct KuCoin futures format.

        Args:
            symbol: Trading symbol (e.g., 'DAM-USDT')
            available_symbols: List of available KuCoin futures symbols

        Returns:
            Mapped KuCoin futures symbol or None if not found
        """
        if not available_symbols:
            logger.warning("No available symbols provided for mapping")
            return None

        # Check cache first
        if symbol in self.symbol_cache:
            cached_symbol = self.symbol_cache[symbol]
            if cached_symbol in available_symbols:
                return cached_symbol
            else:
                # Remove from cache if no longer available
                del self.symbol_cache[symbol]

        variants = self.get_symbol_variants(symbol)

        # Add alias variants (e.g., BTC -> XBT)
        base = symbol.split('-')[0].upper()
        alias = self.alias_map.get(base)
        if alias:
            variants.extend([f"{alias}-USDT", f"{alias}USDT", f"{alias}USDTM"])

        for variant in variants:
            if variant in available_symbols:
                # Cache the successful mapping
                self.symbol_cache[symbol] = variant
                logger.info(f"Mapped {symbol} to KuCoin futures symbol: {variant}")
                return variant

        # Heuristic fallback: look for symbols that end with USDTM and contain the base or alias
        search_terms = [base]
        if alias:
            search_terms.append(alias)
        upper_avail = [s.upper() for s in available_symbols]
        for term in search_terms:
            for s in upper_avail:
                if s.endswith("USDTM") and term in s:
                    self.symbol_cache[symbol] = s
                    logger.info(f"Heuristically mapped {symbol} to {s}")
                    return s

        logger.warning(f"Could not map {symbol} to any available KuCoin futures symbol. Tried: {variants}")
        return None

    def map_to_spot_symbol(self, symbol: str, available_symbols: List[str]) -> Optional[str]:
        """
        Map a symbol to the correct KuCoin spot format.

        Args:
            symbol: Trading symbol (e.g., 'DAM-USDT')
            available_symbols: List of available KuCoin spot symbols

        Returns:
            Mapped KuCoin spot symbol or None if not found
        """
        if not available_symbols:
            logger.warning("No available symbols provided for spot mapping")
            return None

        # For spot, try the original format first
        if symbol in available_symbols:
            return symbol

        # Try without dash
        no_dash = symbol.replace('-', '')
        if no_dash in available_symbols:
            return no_dash

        logger.warning(f"Could not map {symbol} to any available KuCoin spot symbol")
        return None

    def is_symbol_supported(self, symbol: str, available_symbols: List[str], trading_type: str = "futures") -> bool:
        """
        Check if a symbol is supported on KuCoin.

        Args:
            symbol: Trading symbol
            available_symbols: List of available symbols
            trading_type: Type of trading ('futures' or 'spot')

        Returns:
            True if supported, False otherwise
        """
        if trading_type.lower() == "futures":
            mapped_symbol = self.map_to_futures_symbol(symbol, available_symbols)
        else:
            mapped_symbol = self.map_to_spot_symbol(symbol, available_symbols)

        return mapped_symbol is not None

    def get_symbol_info(self, symbol: str, available_symbols: List[str], trading_type: str = "futures") -> Optional[Dict[str, str]]:
        """
        Get symbol mapping information.

        Args:
            symbol: Trading symbol
            available_symbols: List of available symbols
            trading_type: Type of trading ('futures' or 'spot')

        Returns:
            Dictionary with mapping information or None if not found
        """
        if trading_type.lower() == "futures":
            mapped_symbol = self.map_to_futures_symbol(symbol, available_symbols)
        else:
            mapped_symbol = self.map_to_spot_symbol(symbol, available_symbols)

        if mapped_symbol:
            return {
                "original_symbol": symbol,
                "kucoin_symbol": mapped_symbol,
                "trading_type": trading_type,
                "is_supported": True
            }
        else:
            return {
                "original_symbol": symbol,
                "kucoin_symbol": None,
                "trading_type": trading_type,
                "is_supported": False
            }

    def clear_cache(self) -> None:
        """Clear the symbol mapping cache."""
        self.symbol_cache.clear()
        logger.info("KuCoin symbol mapping cache cleared")

    def get_cache_stats(self) -> Dict[str, int]:
        """Get cache statistics."""
        return {
            "cached_mappings": len(self.symbol_cache),
            "available_symbols": len(self.available_symbols)
        }


# Global instance for easy access
symbol_mapper = KucoinSymbolMapper()
