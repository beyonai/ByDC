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

    def test_should_process_new_key(self):
        debouncer = InboundDebouncer(debounce_ms=200)
        assert debouncer.should_process("key1") is True

    def test_should_process_recent(self):
        debouncer = InboundDebouncer(debounce_ms=200)
        debouncer.touch("key1")
        assert debouncer.should_process("key1") is False

    def test_should_process_after_debounce(self):
        debouncer = InboundDebouncer(debounce_ms=100)
        debouncer.touch("key1")
        time.sleep(0.15)
        assert debouncer.should_process("key1") is True

    def test_clear(self):
        debouncer = InboundDebouncer()
        debouncer.touch("key1")
        debouncer.clear()
        assert debouncer.should_process("key1") is True


class TestAgentRunner:
    """Tests for AgentRunner."""

    @pytest.fixture
    def mock_session_manager(self):
        return AsyncMock()

    @pytest.fixture
    def mock_agent_registry(self):
        return AsyncMock()

    @pytest.fixture
    def mock_queue_manager(self):
        return AsyncMock()

    @pytest.fixture
    def mock_event_emitter(self):
        return AsyncMock()

    @pytest.fixture
    def config(self):
        return GatewayConfig(inbound=InboundConfig(debounce_ms=100, dedupe_window_ms=500))

    @pytest.fixture
    def runner(
        self,
        mock_session_manager,
        mock_agent_registry,
        mock_queue_manager,
        mock_event_emitter,
        config,
    ):
        return AgentRunner(
            session_manager=mock_session_manager,
            agent_registry=mock_agent_registry,
            queue_manager=mock_queue_manager,
            event_emitter=mock_event_emitter,
            config=config,
        )

    def test_init(self, runner):
        assert runner.session_manager is not None
        assert runner.agent_registry is not None
        assert runner.queue_manager is not None
        assert runner.event_emitter is not None
        assert runner.config is not None
        assert isinstance(runner.dedupe_cache, DedupeCache)
        assert isinstance(runner.debouncer, InboundDebouncer)

    @pytest.mark.asyncio
    async def test_handle_message_duplicate(self, runner):
        # Add duplicate key
        runner.dedupe_cache.add("session1:hello")
        result = await runner.handle_message("session1", "hello", QueueMode.COLLECT)
        assert result["status"] == "duplicate"
        assert result["session_key"] == "session1"

    @pytest.mark.asyncio
    async def test_handle_message_debounced(self, runner):
        # Touch debouncer
        runner.debouncer.touch("session1")
        result = await runner.handle_message("session1", "hello", QueueMode.COLLECT)
        assert result["status"] == "debounced"
        assert result["session_key"] == "session1"

    @pytest.mark.asyncio
    async def test_handle_message_not_active_executes(self, runner):
        # Session not active
        runner._active_sessions = set()
        # Mock _execute_agent
        runner._execute_agent = AsyncMock(return_value={"response": "ok"})
        result = await runner.handle_message("session1", "hello", QueueMode.COLLECT)
        assert result["status"] == "executed"
        assert result["session_key"] == "session1"
        assert "result" in result
        runner._execute_agent.assert_called_once_with("session1", ["hello"])

    @pytest.mark.asyncio
    async def test_handle_message_active_collect(self, runner):
        # Session active
        runner._active_sessions = {"session1"}
        # Mock enqueuer
        runner.message_enqueuer.enqueue = AsyncMock(return_value=True)
        result = await runner.handle_message("session1", "hello", QueueMode.COLLECT)
        assert result["status"] == "queued"
        assert result["queue_mode"] == "collect"
        runner.message_enqueuer.enqueue.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_message_active_followup(self, runner):
        runner._active_sessions = {"session1"}
        runner.message_enqueuer.enqueue = AsyncMock(return_value=True)
        result = await runner.handle_message("session1", "hello", QueueMode.FOLLOWUP)
        assert result["status"] == "queued"
        assert result["queue_mode"] == "followup"
        runner.message_enqueuer.enqueue.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_message_queue_full(self, runner):
        runner._active_sessions = {"session1"}
        runner.message_enqueuer.enqueue = AsyncMock(return_value=False)
        result = await runner.handle_message("session1", "hello", QueueMode.COLLECT)
        assert result["status"] == "queue_full"
        assert result["queue_mode"] == "collect"

    @pytest.mark.asyncio
    async def test_is_active(self, runner):
        runner._active_sessions = {"session1"}
        assert await runner.is_active("session1") is True
        assert await runner.is_active("session2") is False

    @pytest.mark.asyncio
    async def test_get_status(self, runner):
        runner._active_sessions = {"session1"}
        # Mock queue
        mock_queue = MagicMock()
        mock_queue.messages = [MagicMock(), MagicMock()]
        mock_queue.mode = QueueMode.COLLECT
        runner.queue_manager.get_queue = MagicMock(return_value=mock_queue)
        status = await runner.get_status("session1")
        assert status["session_key"] == "session1"
        assert status["active"] is True
        assert status["queue_size"] == 2
        assert status["queue_mode"] == "collect"

    @pytest.mark.asyncio
    async def test_get_status_no_queue(self, runner):
        runner._active_sessions = {"session1"}
        runner.queue_manager.get_queue = MagicMock(return_value=None)
        status = await runner.get_status("session1")
        assert status["session_key"] == "session1"
        assert status["active"] is True
        assert status["queue_size"] == 0
        assert status["queue_mode"] is None

    @pytest.mark.asyncio
    async def test_execute_agent_valid_session_key(self, runner):
        # Mock agent registry
        mock_config = MagicMock()
        mock_config.agent_id = "default"
        runner.agent_registry.get = MagicMock(return_value=mock_config)
        runner.agent_registry.create_agent = MagicMock(return_value={"agent_id": "default"})
        result = await runner._execute_agent("tenant:t1:agent:default:session1", ["hello"])
        assert result["agent_id"] == "default"
        assert result["messages"] == ["hello"]
        runner.agent_registry.get.assert_called_once_with("default")
        runner.agent_registry.create_agent.assert_called_once_with("default")

    @pytest.mark.asyncio
    async def test_execute_agent_invalid_session_key(self, runner):
        with pytest.raises(ValueError, match="Invalid session key format"):
            await runner._execute_agent("invalid", ["hello"])

    @pytest.mark.asyncio
    async def test_execute_agent_not_found(self, runner):
        runner.agent_registry.get = MagicMock(return_value=None)
        with pytest.raises(ValueError, match="Agent 'default' not found"):
            await runner._execute_agent("tenant:t1:agent:default:session1", ["hello"])

    @pytest.mark.asyncio
    async def test_handle_collect_mode(self, runner):
        runner.message_enqueuer.enqueue = AsyncMock(return_value=True)
        result = await runner._handle_collect_mode("session1", "hello")
        assert result["status"] == "queued"
        assert result["queue_mode"] == "collect"
        runner.message_enqueuer.enqueue.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_followup_mode(self, runner):
        runner.message_enqueuer.enqueue = AsyncMock(return_value=True)
        result = await runner._handle_followup_mode("session1", "hello")
        assert result["status"] == "queued"
        assert result["queue_mode"] == "followup"
        runner.message_enqueuer.enqueue.assert_called_once()
