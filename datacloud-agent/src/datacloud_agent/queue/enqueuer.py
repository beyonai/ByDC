"""Message enqueuer for OpenClaw Gateway."""

import asyncio
import time
from datetime import datetime
from typing import Tuple

from datacloud_agent.queue.manager import QueueManager
from datacloud_agent.queue.types import (
    DropPolicy,
    QueueSettings,
    QueuedMessage,
    QueueState,
)


class MessageEnqueuer:
    """Enqueues messages with deduplication and drop policies."""

    def __init__(self, queue_manager: QueueManager):
        """Initialize the enqueuer.

        Args:
            queue_manager: The queue manager to use.
        """
        self._queue_manager = queue_manager
        # Deduplication cache: (session_key, prompt) -> timestamp
        self._dedupe_cache: dict[tuple[str, str], float] = {}
        self._dedupe_window = 5.0  # seconds

    async def enqueue(
        self,
        session_key: str,
        message: QueuedMessage,
        settings: QueueSettings,
    ) -> bool:
        """Add a message to the queue.

        Args:
            session_key: The session key.
            message: The message to enqueue.
            settings: Queue settings.

        Returns:
            True if the message was enqueued, False otherwise.
        """
        success, _ = await self.try_enqueue(session_key, message, settings)
        return success

    async def try_enqueue(
        self,
        session_key: str,
        message: QueuedMessage,
        settings: QueueSettings,
    ) -> Tuple[bool, str]:
        """Try to enqueue a message, returning success and reason.

        Args:
            session_key: The session key.
            message: The message to enqueue.
            settings: Queue settings.

        Returns:
            Tuple of (success, reason). If success is True, reason is empty.
            If success is False, reason describes why.
        """
        # Deduplication check
        if await self._is_duplicate(session_key, message.prompt):
            return False, "duplicate"

        # Get lock for the session
        lock = self._queue_manager._get_lock(session_key)
        async with lock:
            # Get or create queue (while holding lock)
            queue = self._get_or_create_queue(session_key, settings)
            # Check for duplicate prompt in queue (regardless of time)
            if any(m.prompt == message.prompt for m in queue.messages):
                return False, "duplicate"
            if len(queue.messages) >= settings.max_size:
                # Queue is full, apply drop policy
                if not self._apply_drop_policy(queue, settings.drop_policy):
                    return False, "queue_full"

            # Add message
            queue.messages.append(message)
            queue.last_activity = datetime.now()
            # Update dedupe cache
            self._dedupe_cache[(session_key, message.prompt)] = time.time()
            return True, ""

    def _get_or_create_queue(self, session_key: str, settings: QueueSettings) -> QueueState:
        """Get or create a queue while holding the lock.

        Assumes the lock for this session is already held.
        """
        if session_key not in self._queue_manager._queues:
            from datetime import datetime

            self._queue_manager._queues[session_key] = QueueState(
                session_key=session_key,
                messages=[],
                mode=settings.mode,
                is_processing=False,
                last_activity=datetime.now(),
            )
        return self._queue_manager._queues[session_key]

    async def _is_duplicate(self, session_key: str, prompt: str) -> bool:
        """Check if a prompt is a duplicate within the deduplication window.

        Also cleans up old entries from the cache.
        """
        now = time.time()
        key = (session_key, prompt)
        if key in self._dedupe_cache:
            timestamp = self._dedupe_cache[key]
            if now - timestamp < self._dedupe_window:
                return True
            else:
                # Entry expired, remove it
                del self._dedupe_cache[key]
        # Cleanup old entries (lazy cleanup)
        self._cleanup_dedupe_cache(now)
        return False

    def _cleanup_dedupe_cache(self, now: float):
        """Remove expired entries from the dedupe cache."""
        expired_keys = [
            key
            for key, timestamp in self._dedupe_cache.items()
            if now - timestamp >= self._dedupe_window
        ]
        for key in expired_keys:
            del self._dedupe_cache[key]

    def _apply_drop_policy(self, queue: QueueState, policy: DropPolicy) -> bool:
        """Apply drop policy when queue is full.

        Args:
            queue: The queue state.
            policy: The drop policy to apply.

        Returns:
            True if space was made (or policy allows), False if the new message
            should be rejected.
        """
        if policy == DropPolicy.OLD:
            # Drop the oldest message (lowest priority, oldest timestamp)
            if queue.messages:
                # Sort by priority (lowest first), then timestamp (oldest first)
                queue.messages.sort(key=lambda m: (m.priority, m.timestamp))
                queue.messages.pop(0)
                return True
            else:
                # Should not happen because queue is full
                return False
        elif policy == DropPolicy.NEW:
            # Reject new message
            return False
        elif policy == DropPolicy.SUMMARIZE:
            # Not implemented yet
            # For now, reject new message
            return False
        else:
            raise ValueError(f"Unknown drop policy: {policy}")

    async def get_queue_size(self, session_key: str) -> int:
        """Get the current size of the queue for a session.

        Args:
            session_key: The session key.

        Returns:
            Number of messages in the queue.
        """
        return await self._queue_manager.get_size(session_key)
