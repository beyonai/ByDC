"""Tests for AgentRunner and supporting classes."""

import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from datacloud_agent.config.models import GatewayConfig, InboundConfig
from datacloud_agent.core import AgentRunner, DedupeCache, InboundDebouncer
from datacloud_agent.queue.types import QueueMode


class TestDedupeCache:
    """Tests for DedupeCache."""

    def test_init_default(self):
        cache = DedupeCache()
        assert cache._window_s == 0.5  # 500 ms

    def test_init_custom_window(self):
        cache = DedupeCache(window_ms=1000)
        assert cache._window_s == 1.0

    def test_is_duplicate_fresh(self):
        cache = DedupeCache(window_ms=500)
        cache.add("key1")
        assert cache.is_duplicate("key1") is True

    def test_is_duplicate_expired(self):
        cache = DedupeCache(window_ms=100)
        cache.add("key1")
        time.sleep(0.2)  # wait longer than window
        assert cache.is_duplicate("key1") is False

    def test_is_duplicate_unknown(self):
        cache = DedupeCache()
        assert cache.is_duplicate("unknown") is False

    def test_clear(self):
        cache = DedupeCache()
        cache.add("key1")
        cache.clear()
        assert cache.is_duplicate("key1") is False


class TestInboundDebouncer:
    """Tests for InboundDebouncer."""

    def test_init_default(self):
        debouncer = InboundDebouncer()
        assert debouncer._debounce_s == 0.1  # 100 ms

    def test_init_custom_debounce(self):
        debouncer = InboundDebouncer(debounce_ms=500)
        assert debouncer._debounce_s == 0.5

    def test_should_process_first_time(self):
        debouncer = InboundDebouncer()
        assert debouncer.should_process("key1") is True

    def test_should_process_within_window(self):
        debouncer = InboundDebouncer(debounce_ms=500)
        debouncer.touch("key1")
        assert debouncer.should_process("key1") is False

    def test_should_process_after_window(self):
        debouncer = InboundDebouncer(debounce_ms=100)
        debouncer.touch("key1")
        time.sleep(0.2)  # wait longer than debounce
        assert debouncer.should_process("key1") is True

    def test_clear(self):
        debouncer = InboundDebouncer()
        debouncer.touch("key1")
        debouncer.clear()
        assert debouncer.should_process("key1") is True


class TestAgentRunner:
    """Tests for AgentRunner."""

    @pytest.fixture
    def config(self):
        return GatewayConfig(inbound=InboundConfig(dedupe_window_ms=500, debounce_ms=100))

    @pytest.fixture
    def mock_session_manager(self):
        return MagicMock()

    @pytest.fixture
    def mock_agent_registry(self):
        return MagicMock()

    @pytest.fixture
    def mock_queue_manager(self):
        return MagicMock()

    @pytest.fixture
    def mock_event_emitter(self):
        return MagicMock()

    @pytest.mark.asyncio
    async def test_is_active(
        self,
        config,
        mock_session_manager,
        mock_agent_registry,
        mock_queue_manager,
        mock_event_emitter,
    ):
        """Test is_active returns correct status."""
        runner = AgentRunner(
            session_manager=mock_session_manager,
            agent_registry=mock_agent_registry,
            queue_manager=mock_queue_manager,
            event_emitter=mock_event_emitter,
            config=config,
        )

        session_key = "tenant:test:agent:default:session1"

        # Initially not active
        assert await runner.is_active(session_key) is False

        # Add to active set
        runner._active_sessions.add(session_key)
        assert await runner.is_active(session_key) is True

    @pytest.mark.asyncio
    async def test_cleanup_session_preserves_checkpointer_by_default(
        self,
        mock_session_manager,
        mock_agent_registry,
        mock_queue_manager,
        mock_event_emitter,
        config,
    ):
        """Test that _cleanup_session preserves checkpointer by default."""
        runner = AgentRunner(
            session_manager=mock_session_manager,
            agent_registry=mock_agent_registry,
            queue_manager=mock_queue_manager,
            event_emitter=mock_event_emitter,
            config=config,
        )

        session_key = "tenant:test:agent:default:session1"

        # Setup: Add session resources
        runner._active_sessions.add(session_key)
        mock_checkpointer = MagicMock()
        runner._checkpointers[session_key] = mock_checkpointer
        runner._running_tasks[session_key] = MagicMock()

        # Execute cleanup (default: cleanup_checkpointer=False)
        await runner._cleanup_session(session_key)

        # Verify active sessions and tasks are cleaned
        assert session_key not in runner._active_sessions
        assert session_key not in runner._running_tasks
        # But checkpointer should be preserved!
        assert session_key in runner._checkpointers
        assert runner._checkpointers[session_key] is mock_checkpointer

    @pytest.mark.asyncio
    async def test_cleanup_session_removes_checkpointer_when_requested(
        self,
        mock_session_manager,
        mock_agent_registry,
        mock_queue_manager,
        mock_event_emitter,
        config,
    ):
        """Test that _cleanup_session removes checkpointer when cleanup_checkpointer=True."""
        runner = AgentRunner(
            session_manager=mock_session_manager,
            agent_registry=mock_agent_registry,
            queue_manager=mock_queue_manager,
            event_emitter=mock_event_emitter,
            config=config,
        )

        session_key = "tenant:test:agent:default:session1"

        # Setup: Add session resources
        runner._active_sessions.add(session_key)
        runner._checkpointers[session_key] = MagicMock()
        runner._running_tasks[session_key] = MagicMock()

        # Execute cleanup with cleanup_checkpointer=True
        await runner._cleanup_session(session_key, cleanup_checkpointer=True)

        # Verify all resources are removed including checkpointer
        assert session_key not in runner._active_sessions
        assert session_key not in runner._checkpointers
        assert session_key not in runner._running_tasks

    @pytest.mark.asyncio
    async def test_cleanup_checkpointer_explicitly(
        self,
        mock_session_manager,
        mock_agent_registry,
        mock_queue_manager,
        mock_event_emitter,
        config,
    ):
        """Test cleanup_checkpointer method removes checkpointer for a session."""
        runner = AgentRunner(
            session_manager=mock_session_manager,
            agent_registry=mock_agent_registry,
            queue_manager=mock_queue_manager,
            event_emitter=mock_event_emitter,
            config=config,
        )

        session_key = "tenant:test:agent:default:session1"
        mock_checkpointer = MagicMock()
        runner._checkpointers[session_key] = mock_checkpointer

        # Verify checkpointer exists
        assert session_key in runner._checkpointers

        # Clean up checkpointer
        runner.cleanup_checkpointer(session_key)

        # Verify checkpointer is removed
        assert session_key not in runner._checkpointers

    def test_cleanup_checkpointer_safe_for_nonexistent_session(
        self,
        mock_session_manager,
        mock_agent_registry,
        mock_queue_manager,
        mock_event_emitter,
        config,
    ):
        """Test that cleanup_checkpointer is safe when session doesn't exist."""
        runner = AgentRunner(
            session_manager=mock_session_manager,
            agent_registry=mock_agent_registry,
            queue_manager=mock_queue_manager,
            event_emitter=mock_event_emitter,
            config=config,
        )

        session_key = "tenant:test:agent:default:nonexistent"

        # Should not raise even if session never existed
        runner.cleanup_checkpointer(session_key)

        # Verify no error raised and session still not in checkpointers
        assert session_key not in runner._checkpointers

    @pytest.mark.asyncio
    async def test_context_preserved_between_messages(
        self,
        mock_session_manager,
        mock_agent_registry,
        mock_queue_manager,
        mock_event_emitter,
        config,
    ):
        """Test that checkpointer is preserved between multiple messages in same session."""
        runner = AgentRunner(
            session_manager=mock_session_manager,
            agent_registry=mock_agent_registry,
            queue_manager=mock_queue_manager,
            event_emitter=mock_event_emitter,
            config=config,
        )

        session_key = "tenant:test:agent:default:session1"
        mock_checkpointer = MagicMock()
        runner._checkpointers[session_key] = mock_checkpointer

        # Simulate first message handling
        runner._active_sessions.add(session_key)
        await runner._cleanup_session(session_key)

        # Checkpointer should still exist after first message cleanup
        assert session_key in runner._checkpointers
        assert runner._checkpointers[session_key] is mock_checkpointer

        # Simulate second message handling
        runner._active_sessions.add(session_key)
        await runner._cleanup_session(session_key)

        # Checkpointer should still exist after second message cleanup
        assert session_key in runner._checkpointers
        assert runner._checkpointers[session_key] is mock_checkpointer

    @pytest.mark.asyncio
    async def test_cleanup_lock_safe_for_nonexistent_session(
        self,
        mock_session_manager,
        mock_agent_registry,
        mock_queue_manager,
        mock_event_emitter,
        config,
    ):
        """Test that _cleanup_lock is safe when session doesn't exist."""
        runner = AgentRunner(
            session_manager=mock_session_manager,
            agent_registry=mock_agent_registry,
            queue_manager=mock_queue_manager,
            event_emitter=mock_event_emitter,
            config=config,
        )

        session_key = "tenant:test:agent:default:nonexistent"

        # Should not raise even if session never existed
        runner._cleanup_lock(session_key)

        # Should be safe to call multiple times
        runner._cleanup_lock(session_key)
