"""Tests for all QueueMode implementations in AgentRunner.

This test file verifies that all QueueMode values are correctly handled:
- COLLECT: Merge messages and execute
- STEER: Use Command(resume=...) to inject messages into active session
- STEER_BACKLOG: Steer and enqueue
- INTERRUPT: Cancel current run
- QUEUE: Enqueue and wait for processing
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from datacloud_agent.config.models import GatewayConfig, InboundConfig
from datacloud_agent.core import AgentRunner
from datacloud_agent.queue.policy import QueueAction, QueuePolicy
from datacloud_agent.queue.types import QueueMode


class TestQueueModesAll:
    """Comprehensive tests for all queue modes."""

    @pytest.fixture
    def runner(self):
        """Create an AgentRunner with mocked dependencies."""
        config = GatewayConfig(inbound=InboundConfig(dedupe_window_ms=1000, debounce_ms=100))
        session_manager = MagicMock()
        agent_registry = MagicMock()
        event_emitter = MagicMock()
        queue_manager = MagicMock()

        runner = AgentRunner(
            config=config,
            session_manager=session_manager,
            agent_registry=agent_registry,
            event_emitter=event_emitter,
            queue_manager=queue_manager,
        )
        return runner

    # ============================================================
    # COLLECT Mode Tests
    # ============================================================
    @pytest.mark.asyncio
    async def test_collect_mode_not_active_executes(self, runner):
        """COLLECT mode when session not active should execute immediately."""
        runner._run_agent = AsyncMock(return_value={"response": "ok"})
        result = await runner.handle_message("session1", "hello", QueueMode.COLLECT)
        assert result["status"] == "executed"
        runner._run_agent.assert_called_once_with("session1", ["hello"])

    @pytest.mark.asyncio
    async def test_collect_mode_active_enqueues(self, runner):
        """COLLECT mode when session active should enqueue message."""
        runner._active_sessions.add("session1")
        runner.message_enqueuer.enqueue = AsyncMock(return_value=True)
        result = await runner.handle_message("session1", "hello", QueueMode.COLLECT)
        assert result["status"] == "queued"
        assert result["queue_mode"] == "collect"

    # ============================================================
    # STEER Mode Tests
    # ============================================================
    @pytest.mark.asyncio
    async def test_steer_mode_not_active_executes(self, runner):
        """STEER mode when session not active should execute immediately."""
        runner._run_agent = AsyncMock(return_value={"response": "ok"})
        result = await runner.handle_message("session1", "hello", QueueMode.STEER)
        assert result["status"] == "executed"
        runner._run_agent.assert_called_once_with("session1", ["hello"])

    @pytest.mark.asyncio
    async def test_steer_mode_active_steers(self, runner):
        """STEER mode when session active should steer with new input."""
        runner._active_sessions.add("session1")
        runner._steer_run = AsyncMock(return_value={"response": "steered"})
        result = await runner.handle_message("session1", "new prompt", QueueMode.STEER)
        assert result["status"] == "steered"
        runner._steer_run.assert_called_once_with("session1", "new prompt")

    @pytest.mark.asyncio
    async def test_steer_mode_cancels_existing_task(self, runner):
        """STEER mode should cancel existing running task before steering."""
        session_key = "session1"

        # Create a running task
        async def slow_task():
            await asyncio.sleep(10)
            return None

        mock_task = asyncio.create_task(slow_task())
        runner._running_tasks[session_key] = mock_task
        runner._active_sessions.add(session_key)

        # Mock the run agent to avoid actual execution
        with patch.object(runner, "_run_agent", return_value={"response": "steered"}):
            result = await runner._steer_run(session_key, "new prompt")

        assert result["response"] == "steered"
        # Task should be cancelled and cleaned up
        assert session_key not in runner._running_tasks

    # ============================================================
    # STEER_BACKLOG Mode Tests
    # ============================================================
    @pytest.mark.asyncio
    async def test_steer_backlog_mode_not_active_executes(self, runner):
        """STEER_BACKLOG mode when session not active should execute immediately."""
        runner._run_agent = AsyncMock(return_value={"response": "ok"})
        result = await runner.handle_message("session1", "hello", QueueMode.STEER_BACKLOG)
        assert result["status"] == "executed"
        runner._run_agent.assert_called_once_with("session1", ["hello"])

    @pytest.mark.asyncio
    async def test_steer_backlog_mode_active_enqueues(self, runner):
        """STEER_BACKLOG mode when session active should enqueue with STEER_BACKLOG mode."""
        runner._active_sessions.add("session1")
        runner.message_enqueuer.enqueue = AsyncMock(return_value=True)
        result = await runner.handle_message("session1", "hello", QueueMode.STEER_BACKLOG)
        assert result["status"] == "queued"
        assert result["queue_mode"] == "steer_backlog"
        # Verify queue settings has STEER_BACKLOG mode
        call_args = runner.message_enqueuer.enqueue.call_args
        queue_settings = call_args[0][2]
        assert queue_settings.mode == QueueMode.STEER_BACKLOG

    # ============================================================
    # INTERRUPT Mode Tests
    # ============================================================
    @pytest.mark.asyncio
    async def test_interrupt_mode_not_active_executes(self, runner):
        """INTERRUPT mode when session not active should execute (edge case)."""
        runner._run_agent = AsyncMock(return_value={"response": "ok"})
        result = await runner.handle_message("session1", "hello", QueueMode.INTERRUPT)
        assert result["status"] == "executed"
        runner._run_agent.assert_called_once_with("session1", ["hello"])

    @pytest.mark.asyncio
    async def test_interrupt_mode_active_interrupts(self, runner):
        """INTERRUPT mode when session active should cancel current run."""
        runner._active_sessions.add("session1")
        runner._interrupt_run = AsyncMock()
        result = await runner.handle_message("session1", "ignored", QueueMode.INTERRUPT)
        assert result["status"] == "interrupted"
        runner._interrupt_run.assert_called_once_with("session1", skip_lock=True)

    @pytest.mark.asyncio
    async def test_interrupt_mode_policy(self, runner):
        """INTERRUPT mode policy should resolve to INTERRUPT action when active."""
        action = QueuePolicy.resolve(
            is_active=True,
            is_heartbeat=False,
            should_followup=False,
            queue_mode=QueueMode.INTERRUPT,
        )
        assert action == QueueAction.INTERRUPT

    # ============================================================
    # QUEUE Mode Tests
    # ============================================================
    @pytest.mark.asyncio
    async def test_queue_mode_not_active_executes(self, runner):
        """QUEUE mode when session not active should execute immediately."""
        runner._run_agent = AsyncMock(return_value={"response": "ok"})
        result = await runner.handle_message("session1", "hello", QueueMode.QUEUE)
        assert result["status"] == "executed"
        runner._run_agent.assert_called_once_with("session1", ["hello"])

    @pytest.mark.asyncio
    async def test_queue_mode_active_enqueues(self, runner):
        """QUEUE mode when session active should enqueue message."""
        runner._active_sessions.add("session1")
        runner.message_enqueuer.enqueue = AsyncMock(return_value=True)
        result = await runner.handle_message("session1", "hello", QueueMode.QUEUE)
        assert result["status"] == "queued"
        assert result["queue_mode"] == "queue"
        # Verify queue settings has QUEUE mode
        call_args = runner.message_enqueuer.enqueue.call_args
        queue_settings = call_args[0][2]
        assert queue_settings.mode == QueueMode.QUEUE

    # ============================================================
    # Policy Resolution Tests
    # ============================================================
    @pytest.mark.asyncio
    async def test_policy_all_modes_not_active(self, runner):
        """All modes should EXECUTE when session is not active."""
        for mode in QueueMode:
            action = QueuePolicy.resolve(
                is_active=False,
                is_heartbeat=False,
                should_followup=False,
                queue_mode=mode,
            )
            assert action == QueueAction.EXECUTE, f"Mode {mode} should EXECUTE when not active"

    @pytest.mark.asyncio
    async def test_policy_all_modes_active(self, runner):
        """Test policy resolution for all modes when session is active."""
        expected_actions = {
            QueueMode.COLLECT: QueueAction.ENQUEUE,
            QueueMode.FOLLOWUP: QueueAction.ENQUEUE_FOLLOWUP,
            QueueMode.STEER: QueueAction.STEER,
            QueueMode.STEER_BACKLOG: QueueAction.ENQUEUE,
            QueueMode.INTERRUPT: QueueAction.INTERRUPT,
            QueueMode.QUEUE: QueueAction.ENQUEUE,
        }

        for mode, expected_action in expected_actions.items():
            action = QueuePolicy.resolve(
                is_active=True,
                is_heartbeat=False,
                should_followup=False,
                queue_mode=mode,
            )
            assert action == expected_action, f"Mode {mode} should resolve to {expected_action}"


class TestQueueModeIntegration:
    """Integration tests for queue modes with full runner flow."""

    @pytest.fixture
    def runner(self):
        """Create an AgentRunner with mocked dependencies."""
        config = GatewayConfig(inbound=InboundConfig(dedupe_window_ms=1000, debounce_ms=100))
        session_manager = MagicMock()
        agent_registry = MagicMock()
        event_emitter = MagicMock()
        queue_manager = MagicMock()

        runner = AgentRunner(
            config=config,
            session_manager=session_manager,
            agent_registry=agent_registry,
            event_emitter=event_emitter,
            queue_manager=queue_manager,
        )
        return runner

    @pytest.mark.asyncio
    async def test_queue_full_returns_proper_status(self, runner):
        """When queue is full, should return queue_full status."""
        runner._active_sessions.add("session1")
        runner.message_enqueuer.enqueue = AsyncMock(return_value=False)

        result = await runner.handle_message("session1", "hello", QueueMode.COLLECT)
        assert result["status"] == "queue_full"
        assert result["queue_mode"] == "collect"

    @pytest.mark.asyncio
    async def test_dedupe_prevents_duplicate_processing(self, runner):
        """Deduplication should prevent duplicate message processing."""
        runner._run_agent = AsyncMock(return_value={"response": "ok"})

        # First message should execute
        result1 = await runner.handle_message("session1", "hello", QueueMode.COLLECT)
        assert result1["status"] == "executed"

        # Second identical message should be duplicate
        result2 = await runner.handle_message("session1", "hello", QueueMode.COLLECT)
        assert result2["status"] == "duplicate"

    @pytest.mark.asyncio
    async def test_debounce_prevents_rapid_messages(self, runner):
        """Debouncing should prevent too-rapid messages."""
        runner._run_agent = AsyncMock(return_value={"response": "ok"})

        # First message should execute
        result1 = await runner.handle_message("session1", "hello1", QueueMode.COLLECT)
        assert result1["status"] == "executed"

        # Rapid second message to same session should be debounced
        result2 = await runner.handle_message("session1", "hello2", QueueMode.COLLECT)
        assert result2["status"] == "debounced"

    @pytest.mark.asyncio
    async def test_session_becomes_inactive_after_execution(self, runner):
        """Session should become inactive after execution completes."""
        runner._run_agent = AsyncMock(return_value={"response": "ok"})

        # Execute message
        await runner.handle_message("session1", "hello", QueueMode.COLLECT)

        # Session should not be active anymore
        assert "session1" not in runner._active_sessions

    @pytest.mark.asyncio
    async def test_multiple_modes_different_sessions(self, runner):
        """Different sessions can have different modes simultaneously."""
        runner._run_agent = AsyncMock(return_value={"response": "ok"})
        runner.message_enqueuer.enqueue = AsyncMock(return_value=True)

        # Session 1: COLLECT mode (not active, executes)
        result1 = await runner.handle_message("session1", "hello", QueueMode.COLLECT)
        assert result1["status"] == "executed"

        # Session 2: QUEUE mode (not active, executes)
        result3 = await runner.handle_message("session2", "hello", QueueMode.QUEUE)
        assert result3["status"] == "executed"
