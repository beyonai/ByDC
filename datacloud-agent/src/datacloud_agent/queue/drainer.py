"""Queue drainer for OpenClaw Gateway."""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from datacloud_agent.queue.manager import QueueManager
from datacloud_agent.queue.types import QueuedMessage, QueueMode


@dataclass
class _BackgroundTask:
    """Internal representation of a background drain task."""

    task: asyncio.Task[Any]
    stop_event: asyncio.Event


class QueueDrainer:
    """Drains queues and processes messages."""

    def __init__(self, queue_manager: QueueManager) -> None:
        """Initialize the drainer.

        Args:
            queue_manager: The queue manager to use.
        """
        self._queue_manager = queue_manager
        self._background_tasks: dict[str, _BackgroundTask] = {}

    def _get_queue_mode(self, session_key: str) -> QueueMode:
        """Get the queue mode for a session, defaulting to COLLECT."""
        queue = self._queue_manager.get_queue(session_key)
        if queue is None:
            return QueueMode.COLLECT
        return queue.mode

    async def drain(
        self,
        session_key: str,
        processor: Callable[[QueuedMessage], Awaitable[Any]],
    ) -> list[Any]:
        """Drain queue and process messages individually.

        Args:
            session_key: The session key.
            processor: Async function that processes a single message.

        Returns:
            List of results from processing each message.
        """
        results = []
        while True:
            message = await self._queue_manager.dequeue(session_key)
            if message is None:
                break
            result = await processor(message)
            results.append(result)
        return results

    async def drain_collect(
        self,
        session_key: str,
        processor: Callable[[list[QueuedMessage]], Awaitable[Any]],
    ) -> Any:
        """Drain queue and process all messages together (COLLECT mode).

        Args:
            session_key: The session key.
            processor: Async function that processes a list of messages.

        Returns:
            Result from processing the collected messages.
        """
        messages = []
        while True:
            message = await self._queue_manager.dequeue(session_key)
            if message is None:
                break
            messages.append(message)
        if not messages:
            # Return appropriate value? Could raise or return None.
            # Let's call processor with empty list.
            return await processor([])
        return await processor(messages)

    def start_background_drain(
        self,
        session_key: str,
        processor: Callable[..., Awaitable[Any]],
        interval: float = 1.0,
    ) -> None:
        """Start a background task that periodically drains the queue.

        Args:
            session_key: The session key.
            processor: Callable that processes messages (must be async).
            interval: Seconds between drain attempts.
        """
        if session_key in self._background_tasks:
            # Already draining, stop previous task first
            self.stop_background_drain(session_key)

        stop_event = asyncio.Event()
        task = asyncio.create_task(
            self._background_drain_loop(session_key, processor, interval, stop_event)
        )
        self._background_tasks[session_key] = _BackgroundTask(task, stop_event)

    async def _background_drain_loop(
        self,
        session_key: str,
        processor: Callable[..., Awaitable[Any]],
        interval: float,
        stop_event: asyncio.Event,
    ) -> None:
        """Background loop that drains the queue at intervals."""
        try:
            while not stop_event.is_set():
                # Determine queue mode and drain accordingly
                mode = self._get_queue_mode(session_key)
                if mode == QueueMode.COLLECT:
                    # Processor should accept list of messages
                    await self.drain_collect(session_key, processor)
                else:
                    # Processor should accept single message
                    await self.drain(session_key, processor)
                await asyncio.sleep(interval)
        except asyncio.CancelledError:
            pass
        except Exception:
            # Log error? For now, just stop.
            pass
        finally:
            # Clean up task entry if still present
            self._background_tasks.pop(session_key, None)

    def stop_background_drain(self, session_key: str) -> bool:
        """Stop the background drain task for a session.

        Args:
            session_key: The session key.

        Returns:
            True if a task was stopped, False if no task was running.
        """
        if session_key not in self._background_tasks:
            return False
        bg_task = self._background_tasks.pop(session_key)
        bg_task.stop_event.set()
        bg_task.task.cancel()
        return True

    def is_draining(self, session_key: str) -> bool:
        """Check if a background drain task is running for a session.

        Args:
            session_key: The session key.

        Returns:
            True if a background drain task is active.
        """
        return session_key in self._background_tasks
