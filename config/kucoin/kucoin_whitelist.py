"""
KuCoin Symbol Whitelist

KuCoin-specific symbol whitelist and validation utilities.
Following Clean Code principles with clear whitelist management.
"""

import json
import os
from typing import List, Set, Dict, Any
import logging

logger = logging.getLogger(__name__)


class KucoinWhitelist:
    """
    KuCoin symbol whitelist handler.

    Provides symbol whitelist management and validation for KuCoin trading.
    """

    def __init__(self):
        """Initialize KuCoin whitelist handler."""
        self.whitelist_data: Dict[str, Any] = {}
        self.supported_symbols: Set[str] = set()
        self._load_whitelist_data()

    def _load_whitelist_data(self):
        """Load whitelist data from JSON files."""
        try:
            current_dir = os.path.dirname(os.path.abspath(__file__))

            # Load spot symbols
            spot_file = os.path.join(current_dir, "whitelists", "kucoin_spot_symbols.json")
            if os.path.exists(spot_file):
                with open(spot_file, 'r') as f:
                    spot_data = json.load(f)
                    self.whitelist_data["spot"] = spot_data
                    self.supported_symbols.update(spot_data.get("symbols", []))

            # Load futures symbols
            futures_file = os.path.join(current_dir, "whitelists", "kucoin_futures_symbols.json")
            if os.path.exists(futures_file):
                with open(futures_file, 'r') as f:
                    futures_data = json.load(f)
                    self.whitelist_data["futures"] = futures_data
                    self.supported_symbols.update(futures_data.get("symbols", []))

            # Load symbol details
            details_file = os.path.join(current_dir, "whitelists", "kucoin_symbol_details.json")
            if os.path.exists(details_file):
                with open(details_file, 'r') as f:
                    details_data = json.load(f)
                    self.whitelist_data["details"] = details_data

            logger.info(f"KuCoin whitelist loaded: {len(self.supported_symbols)} symbols")

        except Exception as e:
            logger.error(f"Failed to load KuCoin whitelist data: {e}")
            self.whitelist_data = {"spot": {"symbols": []}, "futures": {"symbols": []}, "details": {}}
            self.supported_symbols = set()

    def is_symbol_supported(self, symbol: str) -> bool:
        """
        Check if symbol is in the whitelist.

        Args:
            symbol: Trading pair symbol

        Returns:
            True if symbol is supported, False otherwise
        """
        return symbol in self.supported_symbols

    def get_spot_symbols(self) -> List[str]:
        """
        Get list of supported spot symbols.

        Returns:
            List of spot trading symbols
        """
        return self.whitelist_data.get("spot", {}).get("symbols", [])

    def get_futures_symbols(self) -> List[str]:
        """
        Get list of supported futures symbols.

        Returns:
            List of futures trading symbols
        """
        return self.whitelist_data.get("futures", {}).get("symbols", [])

    def get_symbol_details(self, symbol: str) -> Dict[str, Any]:
        """
        Get detailed information for a symbol.

        Args:
            symbol: Trading pair symbol

        Returns:
            Symbol details dictionary
        """
        return self.whitelist_data.get("details", {}).get("symbols", {}).get(symbol, {})

    def is_spot_symbol(self, symbol: str) -> bool:
        """
        Check if symbol is supported for spot trading.

        Args:
            symbol: Trading pair symbol

        Returns:
            True if symbol supports spot trading
        """
        return symbol in self.get_spot_symbols()

    def is_futures_symbol(self, symbol: str) -> bool:
        """
        Check if symbol is supported for futures trading.

        Args:
            symbol: Trading pair symbol

        Returns:
            True if symbol supports futures trading
        """
        return symbol in self.get_futures_symbols()

    def get_all_symbols(self) -> List[str]:
        """
        Get all supported symbols.

        Returns:
            List of all supported trading symbols
        """
        return list(self.supported_symbols)

    def add_symbol(self, symbol: str, symbol_type: str = "spot"):
        """
        Add symbol to whitelist.

        Args:
            symbol: Trading pair symbol
            symbol_type: Type of trading (spot/futures)
        """
        if symbol_type not in self.whitelist_data:
            self.whitelist_data[symbol_type] = {"symbols": []}

        if symbol not in self.whitelist_data[symbol_type]["symbols"]:
            self.whitelist_data[symbol_type]["symbols"].append(symbol)
            self.supported_symbols.add(symbol)
            logger.info(f"Added {symbol} to {symbol_type} whitelist")

    def remove_symbol(self, symbol: str, symbol_type: str = "spot"):
        """
        Remove symbol from whitelist.

        Args:
            symbol: Trading pair symbol
            symbol_type: Type of trading (spot/futures)
        """
        if symbol_type in self.whitelist_data:
            symbols = self.whitelist_data[symbol_type]["symbols"]
            if symbol in symbols:
                symbols.remove(symbol)
                # Remove from supported symbols if not in any other type
                if not any(symbol in self.whitelist_data[t]["symbols"]
                          for t in self.whitelist_data if t != symbol_type):
                    self.supported_symbols.discard(symbol)
                logger.info(f"Removed {symbol} from {symbol_type} whitelist")


# Global instance
kucoin_whitelist = KucoinWhitelist()


def is_symbol_supported(symbol: str) -> bool:
    """
    Check if KuCoin symbol is supported.

    Args:
        symbol: Trading pair symbol

    Returns:
        True if symbol is supported, False otherwise
    """
    return kucoin_whitelist.is_symbol_supported(symbol)


def get_spot_symbols() -> List[str]:
    """
    Get KuCoin spot symbols.

    Returns:
        List of spot trading symbols
    """
    return kucoin_whitelist.get_spot_symbols()


def get_futures_symbols() -> List[str]:
    """
    Get KuCoin futures symbols.

    Returns:
        List of futures trading symbols
    """
    return kucoin_whitelist.get_futures_symbols()


def is_spot_symbol(symbol: str) -> bool:
    """
    Check if KuCoin symbol supports spot trading.

    Args:
        symbol: Trading pair symbol

    Returns:
        True if symbol supports spot trading
    """
    return kucoin_whitelist.is_spot_symbol(symbol)


def is_futures_symbol(symbol: str) -> bool:
    """
    Check if KuCoin symbol supports futures trading.

    Args:
        symbol: Trading pair symbol

    Returns:
        True if symbol supports futures trading
    """
    return kucoin_whitelist.is_futures_symbol(symbol)
