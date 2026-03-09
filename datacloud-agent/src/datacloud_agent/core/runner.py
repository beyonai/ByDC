"""Agent runner for OpenClaw Gateway.

Provides DedupeCache, InboundDebouncer, and AgentRunner classes for handling
inbound messages with deduplication, debouncing, and queue-based execution.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from collections import defaultdict
from typing import Any

from datacloud_agent.config.models import GatewayConfig
from datacloud_agent.core.registry import AgentRegistry
from datacloud_agent.core.session import SessionManager
from datacloud_agent.events.emitter import EventEmitter
from datacloud_agent.queue.enqueuer import MessageEnqueuer
from datacloud_agent.queue.manager import QueueManager
from datacloud_agent.queue.policy import QueueAction, QueuePolicy
from datacloud_agent.queue.types import QueuedMessage, QueueMode, QueueSettings


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
        self._running_tasks: dict[str, asyncio.Task] = {}

        # Message enqueuer
        self.message_enqueuer = MessageEnqueuer(queue_manager)

    async def handle_message(
        self, session_key: str, prompt: str, queue_mode: QueueMode
    ) -> dict[str, Any]:
        """Main entry point for handling incoming messages.

        Flow:
            1. Check deduplication (skip if duplicate)
            2. Check debouncing (skip if too frequent)
            3. Resolve action based on queue policy
            4. Execute action: EXECUTE, ENQUEUE, ENQUEUE_FOLLOWUP, STEER, INTERRUPT, DROP

        Args:
            session_key: Full session key.
            prompt: The user prompt/message.
            queue_mode: Queue mode (COLLECT, FOLLOWUP, STEER, STEER_BACKLOG, INTERRUPT, QUEUE).

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
            action, was_active = await self._resolve_action(session_key, queue_mode)

            if action == QueueAction.EXECUTE:
                # Session not active → mark as active and execute
                self._active_sessions.add(session_key)
                # Release lock while executing to allow other messages to enqueue
                # (they will see session as active)
                pass  # continue outside lock
            elif action == QueueAction.ENQUEUE:
                # Enqueue with original mode (COLLECT, STEER_BACKLOG, QUEUE)
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
            elif action == QueueAction.ENQUEUE_FOLLOWUP:
                # Enqueue with FOLLOWUP mode
                queue_settings = QueueSettings(mode=QueueMode.FOLLOWUP)
                message = QueuedMessage(prompt=prompt, session_key=session_key)
                success = await self.message_enqueuer.enqueue(session_key, message, queue_settings)
                if success:
                    return {
                        "status": "queued",
                        "session_key": session_key,
                        "queue_mode": QueueMode.FOLLOWUP.value,
                    }
                else:
                    return {
                        "status": "queue_full",
                        "session_key": session_key,
                        "queue_mode": QueueMode.FOLLOWUP.value,
                    }
            elif action == QueueAction.STEER:
                # STEER: interrupt active run and steer with new input
                # We'll handle outside lock (steer_run will acquire lock internally)
                # But we need to ensure session remains active
                # Release lock and call _steer_run
                pass
            elif action == QueueAction.INTERRUPT:
                # INTERRUPT: cancel active run, drop the message
                # We'll interrupt and return status
                await self._interrupt_run(session_key)
                return {
                    "status": "interrupted",
                    "session_key": session_key,
                }
            elif action == QueueAction.DROP:
                return {
                    "status": "dropped",
                    "session_key": session_key,
                }
            else:
                # Fallback: treat as ENQUEUE
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

        # Actions that require execution outside lock: EXECUTE, STEER
        if action == QueueAction.EXECUTE:
            try:
                result = await self._run_agent(session_key, [prompt])
                return {
                    "status": "executed",
                    "session_key": session_key,
                    "result": result,
                }
            finally:
                async with lock:
                    self._active_sessions.discard(session_key)
                    # _run_agent already cleaned up _running_tasks
        elif action == QueueAction.STEER:
            # STEER mode: interrupt active run and steer with new input
            result = await self._steer_run(session_key, prompt)
            return {
                "status": "steered",
                "session_key": session_key,
                "result": result,
            }
        else:
            # Should not reach here (already returned)
            raise RuntimeError(f"Unexpected action {action}")

    async def _is_active(self, session_key: str) -> bool:
        """Check if session has an active run.

        Args:
            session_key: Session key.

        Returns:
            True if session is active.
        """
        return session_key in self._active_sessions

    async def _resolve_action(
        self, session_key: str, queue_mode: QueueMode
    ) -> tuple[QueueAction, bool]:
        """Resolve the action to take for a message.

        Must be called under session lock.

        Args:
            session_key: Session key.
            queue_mode: Requested queue mode.

        Returns:
            Tuple of (action, is_active) where is_active indicates if session
            was active before this call.
        """
        is_active = session_key in self._active_sessions
        # For now, heartbeat and followup are not supported
        is_heartbeat = False
        should_followup = False
        action = QueuePolicy.resolve(
            is_active=is_active,
            is_heartbeat=is_heartbeat,
            should_followup=should_followup,
            queue_mode=queue_mode,
        )
        return action, is_active

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

    async def _steer_run(self, session_key: str, prompt: str) -> dict[str, Any]:
        """Interrupt active run and steer with new input.

        Args:
            session_key: Session key.
            prompt: New prompt to execute.

        Returns:
            Execution result.
        """
        lock = self._active_locks[session_key]
        async with lock:
            task = self._running_tasks.get(session_key)
            if task and not task.done():
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task
                # Clean up
                self._running_tasks.pop(session_key, None)
                self._active_sessions.discard(session_key)
            # Mark session as active for new execution
            self._active_sessions.add(session_key)
            # Release lock while executing
        try:
            result = await self._run_agent(session_key, [prompt])
            return result
        finally:
            async with lock:
                self._active_sessions.discard(session_key)
                # _run_agent already cleaned up _running_tasks

    async def _interrupt_run(self, session_key: str) -> None:
        """Cancel active run without starting a new one.

        Args:
            session_key: Session key.
        """
        lock = self._active_locks[session_key]
        async with lock:
            task = self._running_tasks.get(session_key)
            if task and not task.done():
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task
            self._running_tasks.pop(session_key, None)
            self._active_sessions.discard(session_key)

    async def _run_agent(self, session_key: str, messages: list[str]) -> dict[str, Any]:
        """Run agent with messages, storing task for cancellation.

        Args:
            session_key: Session key.
            messages: List of messages to process.

        Returns:
            Dictionary with execution result.
        """
        # Create task for execution
        task = asyncio.create_task(self._execute_agent(session_key, messages))
        self._running_tasks[session_key] = task
        try:
            result = await task
            return result
        except asyncio.CancelledError:
            # Task was cancelled (e.g., by steer or interrupt)
            raise
        finally:
            # Clean up if still present (may have been removed by steer/interrupt)
            self._running_tasks.pop(session_key, None)

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
        _agent = self.agent_registry.create_agent(agent_id)

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
