"""Event emitter for OpenClaw Gateway."""

import asyncio
from collections import deque
from collections.abc import Callable
from typing import Optional

from datacloud_agent.events.types import Event, EventType


class EventEmitter:
    """Event emitter with circular buffer history.

    Supports both sync and async handlers. Uses a circular buffer
    (deque with maxlen) for event history.

    Attributes:
        DEFAULT_HISTORY_SIZE: Default maximum number of events to store in history.
    """

    DEFAULT_HISTORY_SIZE = 100

    def __init__(self, history_size: int = DEFAULT_HISTORY_SIZE) -> None:
        """Initialize the EventEmitter.

        Args:
            history_size: Maximum number of events to store in history.
        """
        self._handlers: dict[EventType, list[Callable[[Event], None]]] = {}
        self._history: deque[Event] = deque(maxlen=history_size)
        self._history_size = history_size

    def on_event(self, event_type: EventType, handler: Callable[[Event], None]) -> None:
        """Register a callback handler for an event type.

        Args:
            event_type: The type of event to listen for.
            handler: Callback function (sync or async) that takes an Event.
        """
        if event_type not in self._handlers:
            self._handlers[event_type] = []
        self._handlers[event_type].append(handler)

    def off_event(self, event_type: EventType, handler: Callable[[Event], None]) -> None:
        """Unregister a callback handler for an event type.

        Args:
            event_type: The type of event to stop listening for.
            handler: The callback function to remove.
        """
        if event_type in self._handlers:
            try:
                self._handlers[event_type].remove(handler)
                # Clean up empty handler list
                if not self._handlers[event_type]:
                    del self._handlers[event_type]
            except ValueError:
                pass  # Handler not found, ignore

    async def emit(self, event: Event) -> None:
        """Asynchronously emit an event to all registered handlers.

        Args:
            event: The event to emit.
        """
        # Add to history
        self._history.append(event)

        # Get handlers for this event type
        handlers = self._handlers.get(event.type, [])

        # Call all handlers
        for handler in handlers:
            if asyncio.iscoroutinefunction(handler):
                await handler(event)
            else:
                handler(event)

    def emit_sync(self, event: Event) -> None:
        """Synchronously emit an event to all registered handlers.

        This is a convenience method for calling emit from synchronous code.
        It creates a new event loop if needed.

        Args:
            event: The event to emit.
        """
        # Add to history
        self._history.append(event)

        # Get handlers for this event type
        handlers = self._handlers.get(event.type, [])

        # Check if we're in an async context
        try:
            asyncio.get_running_loop()
            # We're in an async context, schedule async execution
            for handler in handlers:
                if asyncio.iscoroutinefunction(handler):
                    asyncio.create_task(handler(event))
                else:
                    handler(event)
        except RuntimeError:
            # No running event loop, call handlers directly
            for handler in handlers:
                if asyncio.iscoroutinefunction(handler):
                    # Run async handler in a new loop
                    asyncio.run(handler(event))
                else:
                    handler(event)

    def get_history(self, event_type: Optional[EventType] = None, limit: int = 100) -> list[Event]:
        """Get event history, optionally filtered by event type.

        Args:
            event_type: If provided, only return events of this type.
            limit: Maximum number of events to return (default 100).

        Returns:
            List of events, most recent first.
        """
        events = list(self._history)

        # Filter by event type if specified
        if event_type is not None:
            events = [e for e in events if e.type == event_type]

        # Return most recent events (reverse the deque order)
        events = list(reversed(events))

        # Apply limit
        return events[:limit]

    def clear_history(self) -> None:
        """Clear the event history."""
        self._history.clear()

    @property
    def history_size(self) -> int:
        """Get the maximum history size."""
        return self._history_size
