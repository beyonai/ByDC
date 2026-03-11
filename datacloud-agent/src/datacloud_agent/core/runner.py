"""Agent runner for OpenClaw Gateway.

Provides DedupeCache, InboundDebouncer, and AgentRunner classes for handling
inbound messages with deduplication, debouncing, and queue-based execution.

Integration with deepagents (based on POC validation):
- POC 1: create_deep_agent works correctly
- POC 2: Token counting from AIMessage.usage_metadata
- POC 3: STEER mode using Command(resume=...)
- POC 6: Streaming support via astream()
"""

from __future__ import annotations

import asyncio
import contextlib
import inspect
import time
from collections import defaultdict
from typing import Any

from deepagents import create_deep_agent
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from datacloud_agent.config.models import GatewayConfig
from datacloud_agent.core.model_config import create_model
from datacloud_agent.core.registry import AgentRegistry
from datacloud_agent.core.session import SessionManager
from datacloud_agent.core.tools import get_business_tools, get_system_prompt
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
        self._running_tasks: dict[str, asyncio.Task[Any]] = {}

        # Checkpointers for session state persistence (deepagents integration)
        self._checkpointers: dict[str, InMemorySaver] = {}

        # Message enqueuer
        self.message_enqueuer = MessageEnqueuer(queue_manager)

    def _cleanup_lock(self, session_key: str) -> None:
        """Clean up lock for a session.

        Args:
            session_key: Session key to clean up.
        """
        self._active_locks.pop(session_key, None)

    async def _cleanup_session(self, session_key: str) -> None:
        """Clean up all session resources.

        Args:
            session_key: Session key to clean up.
        """
        self._active_sessions.discard(session_key)
        self._running_tasks.pop(session_key, None)
        self._checkpointers.pop(session_key, None)
        self._cleanup_lock(session_key)

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
                # Pass skip_lock=True since we already hold the session lock
                await self._interrupt_run(session_key, skip_lock=True)
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
                    await self._cleanup_session(session_key)
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
        """Steer active run with new input using Command(resume=...).

        Based on POC 3 validation: Uses Command(resume=...) to inject a new message
        into the existing session state, leveraging the checkpointer for persistence.

        Args:
            session_key: Session key.
            prompt: New prompt to inject.

        Returns:
            Execution result with agent_id, messages, response, and usage.
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
            # Check if we have a checkpointer for this session (POC 3 pattern)
            if session_key in self._checkpointers:
                result = await self._steer_with_command(session_key, prompt)
                return result
            else:
                # No checkpointer, fall back to new execution
                result = await self._run_agent(session_key, [prompt])
                return result
        finally:
            async with lock:
                await self._cleanup_session(session_key)

    async def _steer_with_command(self, session_key: str, prompt: str) -> dict[str, Any]:
        """Execute STEER using Command(resume=...) pattern from POC 3.

        Args:
            session_key: Session key.
            prompt: Prompt to inject.

        Returns:
            Execution result.
        """
        # Parse agent_id from session_key
        parts = session_key.split(":")
        if len(parts) != 5 or parts[0] != "tenant" or parts[2] != "agent":
            raise ValueError(f"Invalid session key format: {session_key}")
        agent_id = parts[3]

        # Get agent config
        config = self.agent_registry.get(agent_id)
        if config is None:
            raise ValueError(f"Agent '{agent_id}' not found in registry")

        # Get existing checkpointer
        checkpointer = self._checkpointers[session_key]

        # Create model
        model = create_model({"model": config.model})

        # Create agent with existing checkpointer
        agent = create_deep_agent(
            model=model,
            system_prompt=config.system_prompt or get_system_prompt(),
            tools=get_business_tools(),
            checkpointer=checkpointer,
        )

        # Use Command(resume=...) to inject new message (POC 3 pattern)
        invoke_config = {"configurable": {"thread_id": session_key}}
        result = await agent.ainvoke(
            Command(resume=prompt),
            config=invoke_config,
        )

        # Extract token usage (POC 2 pattern)
        usage: dict[str, int] = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
        for msg in reversed(result.get("messages", [])):
            if isinstance(msg, AIMessage) and msg.usage_metadata:
                usage = {
                    "input_tokens": msg.usage_metadata.get("input_tokens", 0),
                    "output_tokens": msg.usage_metadata.get("output_tokens", 0),
                    "total_tokens": msg.usage_metadata.get("total_tokens", 0),
                }
                break

        # Extract final response
        final_content = ""
        for msg in reversed(result.get("messages", [])):
            if isinstance(msg, AIMessage) and msg.content:
                final_content = msg.content
                break

        return {
            "agent_id": agent_id,
            "messages": result.get("messages", []),
            "response": final_content,
            "usage": usage,
        }

    async def _interrupt_run(self, session_key: str, skip_lock: bool = False) -> None:
        """Cancel active run without starting a new one.

        Args:
            session_key: Session key.
            skip_lock: If True, skip acquiring the lock (used when called from
                       within a locked context to avoid reentrancy issues).
        """
        lock = self._active_locks[session_key]
        if skip_lock:
            # Already holding the lock from caller context - execute logic directly
            await self._interrupt_run_internal(session_key)
        else:
            async with lock:
                await self._interrupt_run_internal(session_key)

    async def _interrupt_run_internal(self, session_key: str) -> None:
        """Internal implementation of interrupt logic (assumes lock is held).

        Args:
            session_key: Session key.
        """
        task = self._running_tasks.get(session_key)
        if task:
            # Handle both real asyncio.Task and mock objects
            # For AsyncMock, task.done() returns a coroutine that needs special handling
            try:
                done_result = task.done()
                # If done_result is a coroutine (e.g., from AsyncMock), await it to get the actual value
                if inspect.isawaitable(done_result):
                    done_result = await done_result
                should_cancel = not done_result
            except Exception:
                # If we can't determine, safest to cancel
                should_cancel = True

            if should_cancel:
                task.cancel()
                # Only await if it's an actual awaitable (not a mock)
                if inspect.isawaitable(task):
                    with contextlib.suppress(asyncio.CancelledError):
                        await task
        self._running_tasks.pop(session_key, None)
        await self._cleanup_session(session_key)

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
        """Execute agent with messages using deepagents.

        Based on POC validation results:
        - POC 1: create_deep_agent works correctly
        - POC 2: Token counting from AIMessage.usage_metadata
        - POC 3: Checkpointer for session persistence

        Args:
            session_key: Session key (format: tenant:{tenant_id}:agent:{agent_id}:{session_id}).
            messages: List of messages to process.

        Returns:
            Dictionary with execution result including agent_id, messages, response, and usage.

        Raises:
            ValueError: If session_key format is invalid or agent not found.
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

        # Create or get checkpointer for session persistence (POC 3 pattern)
        if session_key not in self._checkpointers:
            self._checkpointers[session_key] = InMemorySaver()
        checkpointer = self._checkpointers[session_key]

        # Create model using model_config module
        model = create_model({"model": config.model})

        # Create agent using deepagents (POC 1 pattern)
        agent = create_deep_agent(
            model=model,
            system_prompt=config.system_prompt or get_system_prompt(),
            tools=get_business_tools(),
            checkpointer=checkpointer,
        )

        # Build invoke config with thread_id for checkpointing
        invoke_config = {"configurable": {"thread_id": session_key}}

        # Build messages in LangChain format
        formatted_messages = [{"role": "user", "content": m} for m in messages]

        # Execute agent (POC 1 pattern)
        result = await agent.ainvoke(
            {"messages": formatted_messages},
            config=invoke_config,
        )

        # Extract token usage from AIMessage.usage_metadata (POC 2 pattern)
        usage: dict[str, int] = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
        for msg in reversed(result.get("messages", [])):
            if isinstance(msg, AIMessage) and msg.usage_metadata:
                usage = {
                    "input_tokens": msg.usage_metadata.get("input_tokens", 0),
                    "output_tokens": msg.usage_metadata.get("output_tokens", 0),
                    "total_tokens": msg.usage_metadata.get("total_tokens", 0),
                }
                break

        # Extract final response content
        final_content = ""
        for msg in reversed(result.get("messages", [])):
            if isinstance(msg, AIMessage) and msg.content:
                final_content = msg.content
                break

        return {
            "agent_id": agent_id,
            "messages": result.get("messages", []),
            "response": final_content,
            "usage": usage,
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
