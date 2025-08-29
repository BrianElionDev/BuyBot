"""
Sync manager for orchestrating database synchronization.
Coordinates multiple sync operations and manages sync state.
"""

import asyncio
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone

from .database_sync import DatabaseSync
from .sync_models import SyncEvent, DatabaseSyncState

logger = logging.getLogger(__name__)

class SyncManager:
    """
    Manages database synchronization operations.
    """

    def __init__(self, db_manager):
        """
        Initialize sync manager.

        Args:
            db_manager: Database manager instance
        """
        self.db_manager = db_manager
        self.database_sync = DatabaseSync(db_manager)
        self.sync_queue: List[SyncEvent] = []
        self.running = False
        self.sync_tasks: List[asyncio.Task] = []

    async def start(self):
        """Start the sync manager."""
        if self.running:
            logger.warning("Sync manager is already running")
            return

        self.running = True
        logger.info("Sync manager started")

    async def stop(self):
        """Stop the sync manager."""
        if not self.running:
            return

        self.running = False
        
        # Cancel all sync tasks
        for task in self.sync_tasks:
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        logger.info("Sync manager stopped")

    async def handle_execution_report(self, data: Dict[str, Any]) -> Optional[SyncEvent]:
        """
        Handle execution report synchronization.

        Args:
            data: Execution report data

        Returns:
            Optional[SyncEvent]: Sync event if successful
        """
        try:
            # Create sync event
            sync_event = SyncEvent(
                event_type='execution_report',
                data=data,
                timestamp=datetime.now(timezone.utc),
                source='websocket',
                target='database',
                status='pending'
            )

            # Add to queue
            self.sync_queue.append(sync_event)

            # Process immediately
            result = await self.database_sync.handle_execution_report(data)
            
            if result:
                sync_event.status = 'success'
                logger.info(f"Successfully synced execution report for order {result.order_id}")
            else:
                sync_event.status = 'failed'
                logger.warning("Failed to sync execution report")

            return sync_event

        except Exception as e:
            logger.error(f"Error handling execution report sync: {e}")
            return None

    async def handle_account_position(self, data: Dict[str, Any]) -> Optional[SyncEvent]:
        """
        Handle account position synchronization.

        Args:
            data: Account position data

        Returns:
            Optional[SyncEvent]: Sync event if successful
        """
        try:
            # Create sync event
            sync_event = SyncEvent(
                event_type='account_position',
                data=data,
                timestamp=datetime.now(timezone.utc),
                source='websocket',
                target='database',
                status='pending'
            )

            # Add to queue
            self.sync_queue.append(sync_event)

            # Process immediately
            result = await self.database_sync.handle_account_position(data)
            
            if result:
                sync_event.status = 'success'
                logger.info(f"Successfully synced account position with {len(result)} positions")
            else:
                sync_event.status = 'failed'
                logger.warning("Failed to sync account position")

            return sync_event

        except Exception as e:
            logger.error(f"Error handling account position sync: {e}")
            return None

    async def handle_balance_update(self, data: Dict[str, Any]) -> Optional[SyncEvent]:
        """
        Handle balance update synchronization.

        Args:
            data: Balance update data

        Returns:
            Optional[SyncEvent]: Sync event if successful
        """
        try:
            # Create sync event
            sync_event = SyncEvent(
                event_type='balance_update',
                data=data,
                timestamp=datetime.now(timezone.utc),
                source='websocket',
                target='database',
                status='pending'
            )

            # Add to queue
            self.sync_queue.append(sync_event)

            # Process immediately
            result = await self.database_sync.handle_balance_update(data)
            
            if result:
                sync_event.status = 'success'
                logger.info(f"Successfully synced balance update for {result.asset}")
            else:
                sync_event.status = 'failed'
                logger.warning("Failed to sync balance update")

            return sync_event

        except Exception as e:
            logger.error(f"Error handling balance update sync: {e}")
            return None

    async def process_sync_queue(self):
        """Process pending sync events in the queue."""
        while self.running and self.sync_queue:
            try:
                # Process events in batches
                batch_size = min(10, len(self.sync_queue))
                batch = self.sync_queue[:batch_size]
                
                for sync_event in batch:
                    await self._process_sync_event(sync_event)
                
                # Remove processed events
                self.sync_queue = self.sync_queue[batch_size:]
                
                # Small delay to prevent overwhelming the database
                await asyncio.sleep(0.1)

            except Exception as e:
                logger.error(f"Error processing sync queue: {e}")
                await asyncio.sleep(1)

    async def _process_sync_event(self, sync_event: SyncEvent):
        """
        Process a single sync event.

        Args:
            sync_event: Sync event to process
        """
        try:
            if sync_event.event_type == 'execution_report':
                await self.database_sync.handle_execution_report(sync_event.data)
            elif sync_event.event_type == 'account_position':
                await self.database_sync.handle_account_position(sync_event.data)
            elif sync_event.event_type == 'balance_update':
                await self.database_sync.handle_balance_update(sync_event.data)
            else:
                logger.warning(f"Unknown sync event type: {sync_event.event_type}")

        except Exception as e:
            logger.error(f"Error processing sync event {sync_event.event_type}: {e}")
            sync_event.status = 'failed'

    def get_sync_state(self) -> DatabaseSyncState:
        """
        Get current synchronization state.

        Returns:
            DatabaseSyncState: Current sync state
        """
        return self.database_sync.get_sync_state()

    def get_queue_status(self) -> Dict[str, Any]:
        """
        Get sync queue status.

        Returns:
            Dict: Queue status information
        """
        return {
            'queue_size': len(self.sync_queue),
            'running': self.running,
            'active_tasks': len([t for t in self.sync_tasks if not t.done()]),
            'recent_events': [
                {
                    'type': event.event_type,
                    'status': event.status,
                    'timestamp': event.timestamp.isoformat()
                }
                for event in self.sync_queue[-10:]  # Last 10 events
            ]
        }

    def clear_queue(self):
        """Clear the sync queue."""
        self.sync_queue.clear()
        logger.info("Cleared sync queue")

    def clear_cache(self):
        """Clear all caches."""
        self.database_sync.clear_cache()
        logger.info("Cleared all sync caches")
