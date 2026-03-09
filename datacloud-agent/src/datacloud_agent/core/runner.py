"""Agent runner for OpenClaw Gateway.

Provides DedupeCache, InboundDebouncer, and AgentRunner classes for handling
inbound messages with deduplication, debouncing, and queue-based execution.
"""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict
from typing import Any, Dict, Optional

from datacloud_agent.config.models import GatewayConfig
from datacloud_agent.core.registry import AgentRegistry
from datacloud_agent.core.session import SessionManager
from datacloud_agent.events.emitter import EventEmitter
from datacloud_agent.queue.enqueuer import MessageEnqueuer
from datacloud_agent.queue.manager import QueueManager
from datacloud_agent.queue.types import QueueMode, QueuedMessage, QueueSettings


class DedupeCache:
    """Cache for deduplication within a time window.

    Args:
        window_ms: Deduplication window in milliseconds.
    """

    def __init__(self, window_ms: int = 500) -> None:
        self._window_s = window_ms / 1000.0
        self._cache: dict[str, float] = {}

    def is_duplicate(self, key: str) -> bool:
        """Check if key is duplicate within the window.

        Args:
            key: The key to check.

        Returns:
            True if the key is a duplicate (seen within the window).
        """
        now = time.time()
        if key in self._cache:
            timestamp = self._cache[key]
            if now - timestamp < self._window_s:
                return True
            else:
                # Entry expired, remove it
                del self._cache[key]
        return False

    def add(self, key: str) -> None:
        """Add key to cache.

        Args:
            key: The key to add.
        """
        self._cache[key] = time.time()

    def clear(self) -> None:
        """Clear the cache."""
        self._cache.clear()


class InboundDebouncer:
    """Debouncer for inbound messages.

    Args:
        debounce_ms: Debounce time in milliseconds.
    """

    def __init__(self, debounce_ms: int = 100) -> None:
        self._debounce_s = debounce_ms / 1000.0
        self._last_processed: dict[str, float] = {}

    def should_process(self, key: str) -> bool:
        """Check if enough time has passed since last call.

        Args:
            key: The key to check.

        Returns:
            True if enough time has passed (or key never seen).
        """
        now = time.time()
        if key in self._last_processed:
            last = self._last_processed[key]
            if now - last < self._debounce_s:
                return False
        return True

    def touch(self, key: str) -> None:
        """Mark key as just processed.

        Args:
            key: The key to mark.
        """
        self._last_processed[key] = time.time()

    def clear(self) -> None:
        """Clear the debouncer state."""
        self._last_processed.clear()


class AgentRunner:
    """Runner for agent execution with deduplication, debouncing, and queuing.

    Args:
        session_manager: Session manager instance.
        agent_registry: Agent registry instance.
        queue_manager: Queue manager instance.
        event_emitter: Event emitter instance.
        config: Gateway configuration.
    """

    def __init__(
        self,
        session_manager: SessionManager,
        agent_registry: AgentRegistry,
        queue_manager: QueueManager,
        event_emitter: EventEmitter,
        config: GatewayConfig,
    ) -> None:
        self.session_manager = session_manager
        self.agent_registry = agent_registry
        self.queue_manager = queue_manager
        self.event_emitter = event_emitter
        self.config = config

        # Deduplication and debouncing
        self.dedupe_cache = DedupeCache(window_ms=config.inbound.dedupe_window_ms)
        self.debouncer = InboundDebouncer(debounce_ms=config.inbound.debounce_ms)

        # Active sessions tracking
        self._active_sessions: set[str] = set()
        self._active_locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

        # Message enqueuer
        self.message_enqueuer = MessageEnqueuer(queue_manager)

    async def handle_message(
        self, session_key: str, prompt: str, queue_mode: QueueMode
    ) -> dict[str, Any]:
        """Main entry point for handling incoming messages.

        Flow:
            1. Check deduplication (skip if duplicate)
            2. Check debouncing (skip if too frequent)
            3. Check if agent is active for session
            4. If not active: execute immediately
            5. If active: enqueue based on queue_mode
                - COLLECT: Add to queue, will be merged later
                - FOLLOWUP: Add to queue for sequential processing

        Args:
            session_key: Full session key.
            prompt: The user prompt/message.
            queue_mode: Queue mode (COLLECT or FOLLOWUP).

        Returns:
            Dictionary with status and details.
        """
        # Step 1: Deduplication
        dedupe_key = f"{session_key}:{prompt}"
        if self.dedupe_cache.is_duplicate(dedupe_key):
            return {"status": "duplicate", "session_key": session_key}

        # Step 2: Debouncing
        if not self.debouncer.should_process(session_key):
            return {"status": "debounced", "session_key": session_key}

        # Mark as processed for deduplication and debouncing
        self.dedupe_cache.add(dedupe_key)
        self.debouncer.touch(session_key)

        # Acquire session lock to check active status and decide
        lock = self._active_locks[session_key]
        async with lock:
            if session_key in self._active_sessions:
                # Session is active → enqueue
                queue_settings = QueueSettings(mode=queue_mode)
                message = QueuedMessage(prompt=prompt, session_key=session_key)
                success = await self.message_enqueuer.enqueue(session_key, message, queue_settings)
                if success:
                    return {
                        "status": "queued",
                        "session_key": session_key,
                        "queue_mode": queue_mode.value,
                    }
                else:
                    return {
                        "status": "queue_full",
                        "session_key": session_key,
                        "queue_mode": queue_mode.value,
                    }
            else:
                # Session not active → mark as active and execute
                self._active_sessions.add(session_key)
                # Release lock while executing to allow other messages to enqueue
                # (they will see session as active)

        # Execute agent (outside lock)
        try:
            result = await self._execute_agent(session_key, [prompt])
            return {
                "status": "executed",
                "session_key": session_key,
                "result": result,
            }
        finally:
            # Remove from active sessions after execution
            async with lock:
                self._active_sessions.discard(session_key)

    async def _is_active(self, session_key: str) -> bool:
        """Check if session has an active run.

        Args:
            session_key: Session key.

        Returns:
            True if session is active.
        """
        return session_key in self._active_sessions

    async def _handle_collect_mode(self, session_key: str, prompt: str) -> dict[str, Any]:
        """Handle COLLECT mode logic.

        In COLLECT mode, messages are added to the queue and will be merged later.

        Args:
            session_key: Session key.
            prompt: The user prompt.

        Returns:
            Dictionary with status.
        """
        queue_settings = QueueSettings(mode=QueueMode.COLLECT)
        message = QueuedMessage(prompt=prompt, session_key=session_key)
        success = await self.message_enqueuer.enqueue(session_key, message, queue_settings)
        if success:
            return {"status": "queued", "session_key": session_key, "queue_mode": "collect"}
        else:
            return {"status": "queue_full", "session_key": session_key, "queue_mode": "collect"}

    async def _handle_followup_mode(self, session_key: str, prompt: str) -> dict[str, Any]:
        """Handle FOLLOWUP mode logic.

        In FOLLOWUP mode, messages are added to the queue for sequential processing.

        Args:
            session_key: Session key.
            prompt: The user prompt.

        Returns:
            Dictionary with status.
        """
        queue_settings = QueueSettings(mode=QueueMode.FOLLOWUP)
        message = QueuedMessage(prompt=prompt, session_key=session_key)
        success = await self.message_enqueuer.enqueue(session_key, message, queue_settings)
        if success:
            return {"status": "queued", "session_key": session_key, "queue_mode": "followup"}
        else:
            return {"status": "queue_full", "session_key": session_key, "queue_mode": "followup"}

    async def _execute_agent(self, session_key: str, messages: list[str]) -> dict[str, Any]:
        """Execute agent with messages.

        Args:
            session_key: Session key.
            messages: List of messages to process.

        Returns:
            Dictionary with execution result.
        """
        # Extract agent_id from session_key
        # Format: tenant:{tenant_id}:agent:{agent_id}:{session_id}
        parts = session_key.split(":")
        if len(parts) != 5 or parts[0] != "tenant" or parts[2] != "agent":
            raise ValueError(f"Invalid session key format: {session_key}")
        agent_id = parts[3]

        # Get agent config
        config = self.agent_registry.get(agent_id)
        if config is None:
            raise ValueError(f"Agent '{agent_id}' not found in registry")

        # Create agent instance (mock for now)
        agent = self.agent_registry.create_agent(agent_id)

        # Simulate execution
        # TODO: Replace with actual agent execution
        await asyncio.sleep(0.01)
        return {
            "agent_id": agent_id,
            "messages": messages,
            "response": f"Processed {len(messages)} message(s)",
        }

    async def is_active(self, session_key: str) -> bool:
        """Check if session has active run.

        Args:
            session_key: Session key.

        Returns:
            True if session is active.
        """
        return await self._is_active(session_key)

    async def get_status(self, session_key: str) -> dict[str, Any]:
        """Get runner status for session.

        Args:
            session_key: Session key.

        Returns:
            Dictionary with status information.
        """
        is_active = await self._is_active(session_key)
        queue = self.queue_manager.get_queue(session_key)
        queue_size = len(queue.messages) if queue else 0
        return {
            "session_key": session_key,
            "active": is_active,
            "queue_size": queue_size,
            "queue_mode": queue.mode.value if queue else None,
        }
