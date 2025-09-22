"""
Symbol-based Cooldown System

Manages cooldowns for trading symbols to prevent rapid multiple trades
and position conflicts.
"""

import time
import logging
from typing import Dict, Optional, Tuple
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)


class SymbolCooldownManager:
    """
    Manages cooldowns for trading symbols.

    This prevents rapid multiple trades for the same symbol and helps
    manage position aggregation conflicts.
    """

    def __init__(self, default_cooldown: int = 300, position_cooldown: int = 600):
        """
        Initialize the cooldown manager.

        Args:
            default_cooldown: Default cooldown in seconds (5 minutes)
            position_cooldown: Cooldown when position exists (10 minutes)
        """
        self.default_cooldown = default_cooldown
        self.position_cooldown = position_cooldown
        self.cooldowns: Dict[str, Dict[str, float]] = {}
        self.position_cooldowns: Dict[str, Dict[str, float]] = {}

    def is_on_cooldown(self, symbol: str, trader: str = None) -> Tuple[bool, Optional[str]]:
        """
        Check if a symbol is on cooldown.

        Args:
            symbol: Trading symbol
            trader: Optional trader identifier for trader-specific cooldowns

        Returns:
            Tuple of (is_on_cooldown, reason)
        """
        current_time = time.time()

        # Check general symbol cooldown
        if symbol in self.cooldowns:
            cooldown_end = self.cooldowns[symbol].get('end_time', 0)
            if current_time < cooldown_end:
                remaining = int(cooldown_end - current_time)
                return True, f"Symbol {symbol} on cooldown for {remaining} seconds"

        # Check trader-specific cooldown
        if trader:
            trader_key = f"{symbol}_{trader}"
            if trader_key in self.cooldowns:
                cooldown_end = self.cooldowns[trader_key].get('end_time', 0)
                if current_time < cooldown_end:
                    remaining = int(cooldown_end - current_time)
                    return True, f"Trader {trader} on cooldown for {symbol} for {remaining} seconds"

        # Check position-based cooldown
        if symbol in self.position_cooldowns:
            cooldown_end = self.position_cooldowns[symbol].get('end_time', 0)
            if current_time < cooldown_end:
                remaining = int(cooldown_end - current_time)
                return True, f"Position cooldown for {symbol} for {remaining} seconds"

        return False, None

    def set_cooldown(self, symbol: str, trader: str = None,
                    cooldown_duration: int = None) -> None:
        """
        Set a cooldown for a symbol.

        Args:
            symbol: Trading symbol
            trader: Optional trader identifier
            cooldown_duration: Cooldown duration in seconds (uses default if None)
        """
        if cooldown_duration is None:
            cooldown_duration = self.default_cooldown

        current_time = time.time()
        end_time = current_time + cooldown_duration

        if trader:
            trader_key = f"{symbol}_{trader}"
            self.cooldowns[trader_key] = {
                'end_time': end_time,
                'duration': cooldown_duration,
                'set_at': current_time
            }
            logger.info(f"Set cooldown for trader {trader} on {symbol} for {cooldown_duration} seconds")
        else:
            self.cooldowns[symbol] = {
                'end_time': end_time,
                'duration': cooldown_duration,
                'set_at': current_time
            }
            logger.info(f"Set cooldown for {symbol} for {cooldown_duration} seconds")

    def set_position_cooldown(self, symbol: str, cooldown_duration: int = None) -> None:
        """
        Set a position-based cooldown for a symbol.

        This is used when a position already exists for the symbol.

        Args:
            symbol: Trading symbol
            cooldown_duration: Cooldown duration in seconds (uses position default if None)
        """
        if cooldown_duration is None:
            cooldown_duration = self.position_cooldown

        current_time = time.time()
        end_time = current_time + cooldown_duration

        self.position_cooldowns[symbol] = {
            'end_time': end_time,
            'duration': cooldown_duration,
            'set_at': current_time
        }

        logger.info(f"Set position cooldown for {symbol} for {cooldown_duration} seconds")

    def clear_cooldown(self, symbol: str, trader: str = None) -> None:
        """
        Clear cooldown for a symbol.

        Args:
            symbol: Trading symbol
            trader: Optional trader identifier
        """
        if trader:
            trader_key = f"{symbol}_{trader}"
            if trader_key in self.cooldowns:
                del self.cooldowns[trader_key]
                logger.info(f"Cleared cooldown for trader {trader} on {symbol}")
        else:
            if symbol in self.cooldowns:
                del self.cooldowns[symbol]
                logger.info(f"Cleared cooldown for {symbol}")

        # Also clear position cooldown
        if symbol in self.position_cooldowns:
            del self.position_cooldowns[symbol]
            logger.info(f"Cleared position cooldown for {symbol}")

    def get_cooldown_status(self, symbol: str, trader: str = None) -> Dict[str, any]:
        """
        Get detailed cooldown status for a symbol.

        Args:
            symbol: Trading symbol
            trader: Optional trader identifier

        Returns:
            Dictionary with cooldown status information
        """
        current_time = time.time()
        status = {
            'symbol': symbol,
            'trader': trader,
            'is_on_cooldown': False,
            'cooldowns': []
        }

        # Check general symbol cooldown
        if symbol in self.cooldowns:
            cooldown = self.cooldowns[symbol]
            remaining = max(0, cooldown['end_time'] - current_time)
            if remaining > 0:
                status['is_on_cooldown'] = True
                status['cooldowns'].append({
                    'type': 'symbol',
                    'remaining_seconds': int(remaining),
                    'total_duration': cooldown['duration'],
                    'set_at': cooldown['set_at']
                })

        # Check trader-specific cooldown
        if trader:
            trader_key = f"{symbol}_{trader}"
            if trader_key in self.cooldowns:
                cooldown = self.cooldowns[trader_key]
                remaining = max(0, cooldown['end_time'] - current_time)
                if remaining > 0:
                    status['is_on_cooldown'] = True
                    status['cooldowns'].append({
                        'type': 'trader',
                        'remaining_seconds': int(remaining),
                        'total_duration': cooldown['duration'],
                        'set_at': cooldown['set_at']
                    })

        # Check position-based cooldown
        if symbol in self.position_cooldowns:
            cooldown = self.position_cooldowns[symbol]
            remaining = max(0, cooldown['end_time'] - current_time)
            if remaining > 0:
                status['is_on_cooldown'] = True
                status['cooldowns'].append({
                    'type': 'position',
                    'remaining_seconds': int(remaining),
                    'total_duration': cooldown['duration'],
                    'set_at': cooldown['set_at']
                })

        return status

    def cleanup_expired_cooldowns(self) -> int:
        """
        Clean up expired cooldowns.

        Returns:
            Number of expired cooldowns removed
        """
        current_time = time.time()
        expired_count = 0

        # Clean up general cooldowns
        expired_symbols = []
        for symbol, cooldown in self.cooldowns.items():
            if current_time >= cooldown['end_time']:
                expired_symbols.append(symbol)

        for symbol in expired_symbols:
            del self.cooldowns[symbol]
            expired_count += 1

        # Clean up position cooldowns
        expired_position_symbols = []
        for symbol, cooldown in self.position_cooldowns.items():
            if current_time >= cooldown['end_time']:
                expired_position_symbols.append(symbol)

        for symbol in expired_position_symbols:
            del self.position_cooldowns[symbol]
            expired_count += 1

        if expired_count > 0:
            logger.info(f"Cleaned up {expired_count} expired cooldowns")

        return expired_count

    def get_all_cooldowns(self) -> Dict[str, any]:
        """
        Get all active cooldowns.

        Returns:
            Dictionary with all active cooldowns
        """
        current_time = time.time()
        active_cooldowns = {
            'general': {},
            'position': {}
        }

        # Get general cooldowns
        for symbol, cooldown in self.cooldowns.items():
            remaining = max(0, cooldown['end_time'] - current_time)
            if remaining > 0:
                active_cooldowns['general'][symbol] = {
                    'remaining_seconds': int(remaining),
                    'total_duration': cooldown['duration'],
                    'set_at': cooldown['set_at']
                }

        # Get position cooldowns
        for symbol, cooldown in self.position_cooldowns.items():
            remaining = max(0, cooldown['end_time'] - current_time)
            if remaining > 0:
                active_cooldowns['position'][symbol] = {
                    'remaining_seconds': int(remaining),
                    'total_duration': cooldown['duration'],
                    'set_at': cooldown['set_at']
                }

        return active_cooldowns
