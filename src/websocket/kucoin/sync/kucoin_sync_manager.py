"""
Sync manager for orchestrating KuCoin database synchronization.
Coordinates multiple sync operations and manages sync state.
"""

import asyncio
import logging
from typing import Dict, Any, Optional
from datetime import datetime, timezone

from .kucoin_database_sync import KucoinDatabaseSync
from src.websocket.sync.sync_models import SyncEvent, DatabaseSyncState

logger = logging.getLogger(__name__)

class KucoinSyncManager:
    """
    Manages KuCoin database synchronization operations.
    """

    def __init__(self, db_manager):
        """
        Initialize sync manager.

        Args:
            db_manager: Database manager instance
        """
        self.db_manager = db_manager
        self.database_sync = KucoinDatabaseSync(db_manager)
        self.sync_queue: list[SyncEvent] = []
        self.running = False
        self.sync_tasks: list[asyncio.Task] = []

    async def start(self):
        """Start the sync manager."""
        if self.running:
            logger.warning("[KC-Sync] Manager is already running")
            return

        self.running = True
        logger.info("[KC-Sync] Manager started")

    async def stop(self):
        """Stop the sync manager."""
        if not self.running:
            return

        self.running = False

        for task in self.sync_tasks:
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        logger.info("[KC-Sync] Manager stopped")

    async def handle_execution_report(self, data: Dict[str, Any]) -> Optional[SyncEvent]:
        """
        Handle execution report synchronization.

        Args:
            data: Execution report data

        Returns:
            Optional[SyncEvent]: Sync event if successful
        """
        try:
            sync_event = SyncEvent(
                event_type='execution_report',
                data=data,
                timestamp=datetime.now(timezone.utc),
                source='websocket',
                target='database',
                status='pending'
            )

            self.sync_queue.append(sync_event)

            result = await self.database_sync.handle_execution_report(data)

            if result:
                sync_event.status = 'success'
                logger.info(f"[KC-Sync] Successfully synced execution report for order {result.order_id}")
            else:
                sync_event.status = 'failed'
                logger.warning("[KC-Sync] Failed to sync execution report")

            return sync_event

        except Exception as e:
            logger.error(f"[KC-Sync] Error handling execution report sync: {e}")
            return None

    async def handle_order_change(self, data: Dict[str, Any]) -> Optional[SyncEvent]:
        """
        Handle order change synchronization.

        Args:
            data: Order change data

        Returns:
            Optional[SyncEvent]: Sync event if successful
        """
        try:
            sync_event = SyncEvent(
                event_type='order_change',
                data=data,
                timestamp=datetime.now(timezone.utc),
                source='websocket',
                target='database',
                status='pending'
            )

            self.sync_queue.append(sync_event)

            result = await self.database_sync.handle_order_change(data)

            if result:
                sync_event.status = 'success'
                logger.info(f"[KC-Sync] Successfully synced order change for order {result.order_id}")
            else:
                sync_event.status = 'failed'
                logger.warning("[KC-Sync] Failed to sync order change")

            return sync_event

        except Exception as e:
            logger.error(f"[KC-Sync] Error handling order change sync: {e}")
            return None

    def get_sync_state(self) -> DatabaseSyncState:
        """
        Get current synchronization state.

        Returns:
            DatabaseSyncState: Current sync state
        """
        return DatabaseSyncState(
            last_sync_time=datetime.now(timezone.utc),
            sync_status='active' if self.running else 'idle',
            pending_events=len(self.sync_queue),
            failed_events=0,
            successful_events=0
        )

    def clear_queue(self):
        """Clear the sync queue."""
        self.sync_queue.clear()
        logger.info("[KC-Sync] Cleared sync queue")

    def clear_cache(self):
        """Clear all caches."""
        self.database_sync.clear_cache()
        logger.info("[KC-Sync] Cleared all sync caches")
