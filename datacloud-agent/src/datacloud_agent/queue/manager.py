"""Queue manager for OpenClaw Gateway."""

import asyncio
import os
from datetime import datetime

from deepagents import create_deep_agent
from langchain.chat_models import init_chat_model

from datacloud_agent.queue.types import (
    DropPolicy,
    QueuedMessage,
    QueueSettings,
    QueueState,
)


class QueueManager:
    """Manages queues for different sessions."""

    def __init__(self) -> None:
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
                    max_size=settings.max_size,
                    drop_policy=settings.drop_policy,
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
            if len(queue.messages) >= queue.max_size:
                if queue.drop_policy == DropPolicy.NEW:
                    # Reject new messages
                    return False
                elif queue.drop_policy == DropPolicy.OLD:
                    # Drop oldest message
                    queue.messages.pop(0)
                elif queue.drop_policy == DropPolicy.SUMMARIZE:
                    # Summarize old messages asynchronously
                    await self._summarize_old_messages(session_key, queue)

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

    async def _summarize_old_messages(self, session_key: str, queue: QueueState) -> None:
        """
        Summarize old messages (keep most recent 10, summarize the rest).

        Uses lightweight model for asynchronous summarization.
        """
        if len(queue.messages) <= 10:
            # Too few messages, just drop the oldest
            queue.messages.pop(0)
            return

        # Keep most recent 10, summarize the rest
        messages_to_summarize = queue.messages[:-10]
        queue.messages = queue.messages[-10:]

        # Asynchronous summarization (non-blocking for queue operations)
        asyncio.create_task(self._async_summarize(session_key, messages_to_summarize))

    async def _async_summarize(self, session_key: str, messages: list[QueuedMessage]) -> None:
        """
        Asynchronously summarize messages using lightweight model.

        Uses environment variables for API configuration:
        - OPENAI_API_KEY: API key for the model
        - OPENAI_BASE_URL: Base URL for the API

        On failure, silently drops messages without blocking the queue.
        """
        try:
            # Build summary prompt
            content = "\n".join(
                [
                    f"[{m.timestamp.strftime('%Y-%m-%d %H:%M:%S')}] {m.prompt[:100]}..."
                    for m in messages
                ]
            )

            # Initialize lightweight model using environment variables
            api_key = os.getenv("OPENAI_API_KEY")
            base_url = os.getenv("OPENAI_BASE_URL")

            if not api_key:
                # No API key configured, skip summarization
                print("Warning: OPENAI_API_KEY not set, skipping summarization")
                return

            model = init_chat_model(
                "openai:qwen3.5-plus",
                api_key=api_key,
                base_url=base_url,
            )

            # Create agent for summarization
            agent = create_deep_agent(
                model=model,
                system_prompt="Summarize the following conversation messages concisely in Chinese.",
            )

            # Invoke summarization
            result = await agent.ainvoke({"messages": [{"role": "user", "content": content}]})

            # Extract summary from result
            summary = "[Summary unavailable]"
            if result.get("messages"):
                last_message = result["messages"][-1]
                summary = getattr(last_message, "content", str(last_message))

            # Create summary message
            summary_msg = QueuedMessage(
                prompt=f"[历史消息总结] {summary[:500]}",
                session_key=session_key,
                priority=10,  # High priority
                metadata={"is_summary": True, "message_count": len(messages)},
            )

            # Insert summary at the beginning of the queue
            lock = self._get_lock(session_key)
            async with lock:
                if session_key in self._queues:
                    self._queues[session_key].messages.insert(0, summary_msg)

        except Exception as e:
            # Summarization failed, log but don't block
            print(f"Summarization failed for session {session_key}: {e}")
            # Messages already removed from queue, summary insertion failed
