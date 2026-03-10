"""Queue manager for OpenClaw Gateway."""

import asyncio
from datetime import datetime

from datacloud_agent.queue.types import (
    QueueSettings,
    QueuedMessage,
    QueueState,
)


class QueueManager:
    """Manages queues for different sessions."""

    def __init__(self):
        """Initialize the queue manager."""
        self._queues: dict[str, QueueState] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    def _get_lock(self, session_key: str) -> asyncio.Lock:
        """Get or create a lock for the session."""
        if session_key not in self._locks:
            self._locks[session_key] = asyncio.Lock()
        return self._locks[session_key]

    async def get_or_create(self, session_key: str, settings: QueueSettings) -> QueueState:
        """Get or create a queue for a session."""
        lock = self._get_lock(session_key)
        async with lock:
            if session_key not in self._queues:
                self._queues[session_key] = QueueState(
                    session_key=session_key,
                    messages=[],
                    mode=settings.mode,
                    is_processing=False,
                    last_activity=datetime.now(),
                )
            return self._queues[session_key]

    def get_queue(self, session_key: str) -> QueueState | None:
        """Get a queue for a session without creating it."""
        return self._queues.get(session_key)

    async def delete_queue(self, session_key: str) -> bool:
        """Delete a queue for a session."""
        lock = self._get_lock(session_key)
        async with lock:
            if session_key in self._queues:
                del self._queues[session_key]
                if session_key in self._locks:
                    del self._locks[session_key]
                return True
            return False

    async def enqueue(self, session_key: str, message: QueuedMessage) -> bool:
        """Add a message to the queue."""
        lock = self._get_lock(session_key)
        async with lock:
            if session_key not in self._queues:
                return False

            queue = self._queues[session_key]
            # Check if queue is full and apply drop policy
            if len(queue.messages) >= 100:  # default max_size
                # For now, reject new messages (DropPolicy.NEW behavior)
                return False

            queue.messages.append(message)
            queue.last_activity = datetime.now()
            return True

    async def dequeue(self, session_key: str) -> QueuedMessage | None:
        """Remove and return the first message from the queue."""
        lock = self._get_lock(session_key)
        async with lock:
            if session_key not in self._queues:
                return None

            queue = self._queues[session_key]
            if not queue.messages:
                return None

            # Sort by priority (highest first), then by timestamp (oldest first)
            queue.messages.sort(key=lambda m: (-m.priority, m.timestamp))
            message = queue.messages.pop(0)
            queue.last_activity = datetime.now()
            return message

    async def peek(self, session_key: str) -> QueuedMessage | None:
        """View the first message without removing it."""
        lock = self._get_lock(session_key)
        async with lock:
            if session_key not in self._queues:
                return None

            queue = self._queues[session_key]
            if not queue.messages:
                return None

            # Sort by priority (highest first), then by timestamp (oldest first)
            sorted_messages = sorted(queue.messages, key=lambda m: (-m.priority, m.timestamp))
            return sorted_messages[0]

    async def clear(self, session_key: str) -> bool:
        """Clear all messages from the queue."""
        lock = self._get_lock(session_key)
        async with lock:
            if session_key not in self._queues:
                return False

            self._queues[session_key].messages = []
            self._queues[session_key].last_activity = datetime.now()
            return True

    def list_queues(self) -> list[str]:
        """List all session keys with queues."""
        return list(self._queues.keys())

    async def get_size(self, session_key: str) -> int:
        """Get the number of messages in the queue."""
        lock = self._get_lock(session_key)
        async with lock:
            if session_key not in self._queues:
                return 0
            return len(self._queues[session_key].messages)
