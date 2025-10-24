"""
Alert Deduplication Service

This module provides centralized alert deduplication to prevent duplicate
failure notifications from being sent across different systems.
"""

import hashlib
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Set, Optional, Any
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class AlertKey:
    """Unique key for alert deduplication."""
    trade_id: str
    error_type: str
    symbol: str
    exchange: str
    timestamp_window: str  # Hour-based window for grouping similar alerts


class AlertDeduplicator:
    """
    Centralized alert deduplication service.

    Prevents duplicate alerts by tracking sent notifications and
    implementing time-based deduplication windows.
    """

    def __init__(self, dedup_window_minutes: int = 5):
        """
        Initialize the alert deduplicator.

        Args:
            dedup_window_minutes: Time window in minutes for deduplication (default: 5)
        """
        self.dedup_window = timedelta(minutes=dedup_window_minutes)
        self.sent_alerts: Dict[str, datetime] = {}
        self._cleanup_threshold = 1000  # Clean up when we have too many entries

    def _generate_alert_key(self, trade_id: str, error_type: str, symbol: str, exchange: str) -> str:
        """
        Generate a unique key for alert deduplication.

        Args:
            trade_id: Trade identifier
            error_type: Type of error (e.g., 'EXECUTION_FAILED', 'SYMBOL_NOT_FOUND')
            symbol: Trading symbol
            exchange: Exchange name

        Returns:
            Unique alert key string
        """
        # Create a time window key (hour-based) to group similar alerts
        now = datetime.now(timezone.utc)
        time_window = now.replace(minute=0, second=0, microsecond=0)
        timestamp_window = time_window.isoformat()

        # Create the deduplication key
        key_data = f"{trade_id}:{error_type}:{symbol}:{exchange}:{timestamp_window}"
        return hashlib.sha256(key_data.encode()).hexdigest()

    def _is_alert_duplicate(self, alert_key: str) -> bool:
        """
        Check if an alert is a duplicate within the deduplication window.

        Args:
            alert_key: Unique alert key

        Returns:
            True if this is a duplicate alert
        """
        if alert_key not in self.sent_alerts:
            return False

        # Check if the alert is within the deduplication window
        last_sent = self.sent_alerts[alert_key]
        now = datetime.now(timezone.utc)

        if now - last_sent < self.dedup_window:
            logger.info(f"Duplicate alert detected: {alert_key[:16]}... (last sent: {last_sent})")
            return True

        return False

    def _cleanup_old_entries(self):
        """Clean up old alert entries to prevent memory growth."""
        if len(self.sent_alerts) < self._cleanup_threshold:
            return

        now = datetime.now(timezone.utc)
        cutoff_time = now - self.dedup_window * 2  # Keep entries for 2x the dedup window

        # Remove old entries
        old_keys = [
            key for key, timestamp in self.sent_alerts.items()
            if timestamp < cutoff_time
        ]

        for key in old_keys:
            del self.sent_alerts[key]

        logger.info(f"Cleaned up {len(old_keys)} old alert entries")

    def should_send_alert(self, trade_id: str, error_type: str, symbol: str, exchange: str) -> bool:
        """
        Check if an alert should be sent (not a duplicate).

        Args:
            trade_id: Trade identifier
            error_type: Type of error
            symbol: Trading symbol
            exchange: Exchange name

        Returns:
            True if alert should be sent, False if it's a duplicate
        """
        alert_key = self._generate_alert_key(trade_id, error_type, symbol, exchange)

        if self._is_alert_duplicate(alert_key):
            return False

        # Mark this alert as sent
        self.sent_alerts[alert_key] = datetime.now(timezone.utc)

        # Cleanup if needed
        self._cleanup_old_entries()

        return True

    def mark_alert_sent(self, trade_id: str, error_type: str, symbol: str, exchange: str):
        """
        Manually mark an alert as sent (for cases where we want to prevent duplicates
        without actually sending the alert).

        Args:
            trade_id: Trade identifier
            error_type: Type of error
            symbol: Trading symbol
            exchange: Exchange name
        """
        alert_key = self._generate_alert_key(trade_id, error_type, symbol, exchange)
        self.sent_alerts[alert_key] = datetime.now(timezone.utc)
        self._cleanup_old_entries()

    def get_stats(self) -> Dict[str, Any]:
        """Get deduplication statistics."""
        now = datetime.now(timezone.utc)
        recent_alerts = sum(
            1 for timestamp in self.sent_alerts.values()
            if now - timestamp < self.dedup_window
        )

        return {
            "total_tracked_alerts": len(self.sent_alerts),
            "recent_alerts_in_window": recent_alerts,
            "dedup_window_minutes": self.dedup_window.total_seconds() / 60,
            "cleanup_threshold": self._cleanup_threshold
        }


# Global instance for easy access
alert_deduplicator = AlertDeduplicator()
