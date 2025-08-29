"""
Event dispatcher for routing WebSocket events to appropriate handlers.
Manages event registration, routing, and error handling.
"""

import asyncio
import json
import logging
from typing import Dict, List, Callable, Any, Optional
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger(__name__)

@dataclass
class WebSocketEvent:
    """Represents a WebSocket event with metadata."""
    event_type: str
    data: Dict[str, Any]
    timestamp: float
    stream_name: Optional[str] = None
    connection_id: Optional[str] = None

class EventDispatcher:
    """
    Dispatches WebSocket events to registered handlers.
    """

    def __init__(self):
        """Initialize event dispatcher."""
        self.event_handlers: Dict[str, List[Callable]] = {
            'executionReport': [],
            'outboundAccountPosition': [],
            'balanceUpdate': [],
            'ticker': [],
            'trade': [],
            'depth': [],
            'error': [],
            'connection': [],
            'disconnection': [],
            'ping': [],
            'pong': []
        }
        self.middleware: List[Callable] = []
        self.running = False

    def register_handler(self, event_type: str, handler: Callable):
        """
        Register a handler for a specific event type.

        Args:
            event_type: Type of event to handle
            handler: Callback function to handle the event
        """
        if event_type not in self.event_handlers:
            self.event_handlers[event_type] = []
        
        if handler not in self.event_handlers[event_type]:
            self.event_handlers[event_type].append(handler)
            logger.debug(f"Registered handler for event type: {event_type}")

    def unregister_handler(self, event_type: str, handler: Callable):
        """
        Unregister a handler for a specific event type.

        Args:
            event_type: Type of event
            handler: Handler to unregister
        """
        if event_type in self.event_handlers and handler in self.event_handlers[event_type]:
            self.event_handlers[event_type].remove(handler)
            logger.debug(f"Unregistered handler for event type: {event_type}")

    def register_middleware(self, middleware: Callable):
        """
        Register middleware to process events before dispatching.

        Args:
            middleware: Middleware function
        """
        if middleware not in self.middleware:
            self.middleware.append(middleware)
            logger.debug("Registered middleware")

    def unregister_middleware(self, middleware: Callable):
        """
        Unregister middleware.

        Args:
            middleware: Middleware function to unregister
        """
        if middleware in self.middleware:
            self.middleware.remove(middleware)
            logger.debug("Unregistered middleware")

    async def dispatch_event(self, event: WebSocketEvent):
        """
        Dispatch an event to all registered handlers.

        Args:
            event: WebSocket event to dispatch
        """
        try:
            # Apply middleware
            processed_event = await self._apply_middleware(event)
            if processed_event is None:
                logger.debug("Event filtered out by middleware")
                return

            # Get handlers for event type
            handlers = self.event_handlers.get(processed_event.event_type, [])
            
            if not handlers:
                logger.debug(f"No handlers registered for event type: {processed_event.event_type}")
                return

            # Dispatch to all handlers
            tasks = []
            for handler in handlers:
                task = asyncio.create_task(self._execute_handler(handler, processed_event))
                tasks.append(task)

            # Wait for all handlers to complete
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)

        except Exception as e:
            logger.error(f"Error dispatching event {event.event_type}: {e}")

    async def _apply_middleware(self, event: WebSocketEvent) -> Optional[WebSocketEvent]:
        """
        Apply middleware to an event.

        Args:
            event: Original event

        Returns:
            Optional[WebSocketEvent]: Processed event or None if filtered out
        """
        processed_event = event
        
        for middleware in self.middleware:
            try:
                result = await middleware(processed_event)
                if result is None:
                    return None
                processed_event = result
            except Exception as e:
                logger.error(f"Error in middleware: {e}")
                return None

        return processed_event

    async def _execute_handler(self, handler: Callable, event: WebSocketEvent):
        """
        Execute a single event handler.

        Args:
            handler: Handler function
            event: Event to handle
        """
        try:
            if asyncio.iscoroutinefunction(handler):
                await handler(event)
            else:
                handler(event)
        except Exception as e:
            logger.error(f"Error in event handler for {event.event_type}: {e}")

    async def dispatch_raw_message(self, message: str, connection_id: str):
        """
        Parse and dispatch a raw WebSocket message.

        Args:
            message: Raw message string
            connection_id: Connection identifier
        """
        try:
            # Parse JSON message
            data = json.loads(message)
            
            # Determine event type
            event_type = self._determine_event_type(data)
            
            # Create event object
            event = WebSocketEvent(
                event_type=event_type,
                data=data,
                timestamp=datetime.now().timestamp(),
                connection_id=connection_id
            )
            
            # Dispatch event
            await self.dispatch_event(event)

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON message: {e}")
            # Handle ping/pong messages
            if message.strip() == "ping":
                event = WebSocketEvent(
                    event_type="ping",
                    data={"message": "ping"},
                    timestamp=datetime.now().timestamp(),
                    connection_id=connection_id
                )
                await self.dispatch_event(event)
            elif message.strip() == "pong":
                event = WebSocketEvent(
                    event_type="pong",
                    data={"message": "pong"},
                    timestamp=datetime.now().timestamp(),
                    connection_id=connection_id
                )
                await self.dispatch_event(event)
        except Exception as e:
            logger.error(f"Error processing raw message: {e}")

    def _determine_event_type(self, data: Dict[str, Any]) -> str:
        """
        Determine the event type from message data.

        Args:
            data: Message data

        Returns:
            str: Event type
        """
        # Check for specific event types
        if 'e' in data:
            return data['e']  # Binance event type
        elif 'event' in data:
            return data['event']  # Generic event type
        elif 'type' in data:
            return data['type']  # Alternative event type
        elif 'stream' in data:
            # Handle stream data
            stream = data['stream']
            if 'trade' in stream:
                return 'trade'
            elif 'ticker' in stream:
                return 'ticker'
            elif 'depth' in stream:
                return 'depth'
            else:
                return 'stream'
        else:
            return 'unknown'

    def get_registered_handlers(self) -> Dict[str, int]:
        """
        Get count of registered handlers for each event type.

        Returns:
            Dict: Event type to handler count mapping
        """
        return {event_type: len(handlers) for event_type, handlers in self.event_handlers.items()}

    def clear_handlers(self, event_type: Optional[str] = None):
        """
        Clear handlers for a specific event type or all handlers.

        Args:
            event_type: Event type to clear handlers for, or None for all
        """
        if event_type:
            if event_type in self.event_handlers:
                self.event_handlers[event_type].clear()
                logger.info(f"Cleared handlers for event type: {event_type}")
        else:
            for event_type in self.event_handlers:
                self.event_handlers[event_type].clear()
            logger.info("Cleared all event handlers")

    def start(self):
        """Start the event dispatcher."""
        self.running = True
        logger.info("Event dispatcher started")

    def stop(self):
        """Stop the event dispatcher."""
        self.running = False
        logger.info("Event dispatcher stopped")
