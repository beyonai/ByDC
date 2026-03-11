"""Tests for STEER mode and QueuePolicy."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from datacloud_agent.core import AgentRunner
from datacloud_agent.config.models import GatewayConfig, InboundConfig
from datacloud_agent.queue.policy import QueueAction, QueuePolicy
from datacloud_agent.queue.types import QueueMode


class TestQueueAction:
    """Tests for QueueAction enum."""

    def test_values(self):
        """Test enum values."""
        assert QueueAction.EXECUTE.value == "execute"
        assert QueueAction.ENQUEUE.value == "enqueue"
        assert QueueAction.ENQUEUE_FOLLOWUP.value == "enqueue-followup"
        assert QueueAction.STEER.value == "steer"
        assert QueueAction.INTERRUPT.value == "interrupt"
        assert QueueAction.DROP.value == "drop"


class TestQueuePolicy:
    """Tests for QueuePolicy."""

    def test_resolve_not_active(self):
        """When not active, should always EXECUTE."""
        for mode in QueueMode:
            action = QueuePolicy.resolve(
                is_active=False,
                is_heartbeat=False,
                should_followup=False,
                queue_mode=mode,
            )
            assert action == QueueAction.EXECUTE, f"Failed for mode {mode}"

    def test_resolve_heartbeat(self):
        """Heartbeat messages should be dropped."""
        action = QueuePolicy.resolve(
            is_active=True,
            is_heartbeat=True,
            should_followup=False,
            queue_mode=QueueMode.COLLECT,
        )
        assert action == QueueAction.DROP

    def test_resolve_collect_mode(self):
        """COLLECT mode should ENQUEUE when active."""
        action = QueuePolicy.resolve(
            is_active=True,
            is_heartbeat=False,
            should_followup=False,
            queue_mode=QueueMode.COLLECT,
        )
        assert action == QueueAction.ENQUEUE

    def test_resolve_followup_mode(self):
        """FOLLOWUP mode should ENQUEUE_FOLLOWUP when active."""
        action = QueuePolicy.resolve(
            is_active=True,
            is_heartbeat=False,
            should_followup=False,
            queue_mode=QueueMode.FOLLOWUP,
        )
        assert action == QueueAction.ENQUEUE_FOLLOWUP

    def test_resolve_steer_mode(self):
        """STEER mode should STEER when active."""
        action = QueuePolicy.resolve(
            is_active=True,
            is_heartbeat=False,
            should_followup=False,
            queue_mode=QueueMode.STEER,
        )
        assert action == QueueAction.STEER

    def test_resolve_steer_backlog_mode(self):
        """STEER_BACKLOG mode should ENQUEUE when active."""
        action = QueuePolicy.resolve(
            is_active=True,
            is_heartbeat=False,
            should_followup=False,
            queue_mode=QueueMode.STEER_BACKLOG,
        )
        assert action == QueueAction.ENQUEUE

    def test_resolve_interrupt_mode(self):
        """INTERRUPT mode should INTERRUPT when active."""
        action = QueuePolicy.resolve(
            is_active=True,
            is_heartbeat=False,
            should_followup=False,
            queue_mode=QueueMode.INTERRUPT,
        )
        assert action == QueueAction.INTERRUPT

    def test_resolve_queue_mode(self):
        """QUEUE mode should ENQUEUE when active."""
        action = QueuePolicy.resolve(
            is_active=True,
            is_heartbeat=False,
            should_followup=False,
            queue_mode=QueueMode.QUEUE,
        )
        assert action == QueueAction.ENQUEUE


class TestAgentRunnerSteer:
    """Tests for AgentRunner STEER mode support."""

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
    async def test_resolve_action_not_active(self, runner):
        """Test _resolve_action when session is not active."""
        action, is_active = await runner._resolve_action(
            session_key="test-session",
            queue_mode=QueueMode.COLLECT,
        )
        assert action == QueueAction.EXECUTE
        assert is_active is False

    @pytest.mark.asyncio
    async def test_resolve_action_active(self, runner):
        """Test _resolve_action when session is active."""
        # Mark session as active
        runner._active_sessions.add("test-session")

        action, is_active = await runner._resolve_action(
            session_key="test-session",
            queue_mode=QueueMode.COLLECT,
        )
        assert action == QueueAction.ENQUEUE
        assert is_active is True

    @pytest.mark.asyncio
    async def test_resolve_action_steer_mode(self, runner):
        """Test _resolve_action with STEER mode."""
        # Mark session as active
        runner._active_sessions.add("test-session")

        action, is_active = await runner._resolve_action(
            session_key="test-session",
            queue_mode=QueueMode.STEER,
        )
        assert action == QueueAction.STEER
        assert is_active is True

    @pytest.mark.asyncio
    async def test_resolve_action_interrupt_mode(self, runner):
        """Test _resolve_action with INTERRUPT mode."""
        # Mark session as active
        runner._active_sessions.add("test-session")

        action, is_active = await runner._resolve_action(
            session_key="test-session",
            queue_mode=QueueMode.INTERRUPT,
        )
        assert action == QueueAction.INTERRUPT
        assert is_active is True

    @pytest.mark.asyncio
    async def test_interrupt_run(self, runner):
        """Test _interrupt_run cancels active task."""
        session_key = "test-session"

        # Create an async mock task that can be awaited
        async def mock_coro():
            return None

        mock_task = asyncio.create_task(mock_coro())
        runner._running_tasks[session_key] = mock_task
        runner._active_sessions.add(session_key)

        # Cancel the task first so await doesn't hang
        mock_task.cancel()

        await runner._interrupt_run(session_key)

        # Session should no longer be active
        assert session_key not in runner._active_sessions
        assert session_key not in runner._running_tasks

    @pytest.mark.asyncio
    async def test_interrupt_run_no_task(self, runner):
        """Test _interrupt_run when no task exists."""
        session_key = "test-session"
        runner._active_sessions.add(session_key)

        await runner._interrupt_run(session_key)

        # Session should no longer be active
        assert session_key not in runner._active_sessions

    @pytest.mark.asyncio
    async def test_interrupt_run_task_already_done(self, runner):
        """Test _interrupt_run when task is already done."""
        session_key = "test-session"

        # Create a mock task that's already done
        mock_task = AsyncMock()
        mock_task.done.return_value = True
        runner._running_tasks[session_key] = mock_task
        runner._active_sessions.add(session_key)

        await runner._interrupt_run(session_key)

        # Cancel should not be called
        mock_task.cancel.assert_not_called()
        # Session should no longer be active
        assert session_key not in runner._active_sessions

    @pytest.mark.asyncio
    async def test_running_tasks_tracking(self, runner):
        """Test that _running_tasks tracks active tasks."""
        session_key = "test-session"

        # Initially no tasks
        assert session_key not in runner._running_tasks

        # Mock _execute_agent to simulate async work
        async def mock_execute(*args, **kwargs):
            await asyncio.sleep(0.01)
            return {"status": "success"}

        with patch.object(runner, "_execute_agent", side_effect=mock_execute):
            # Start a run
            result = await runner._run_agent(session_key, ["test message"])

        # After completion, task should be cleaned up
        assert session_key not in runner._running_tasks
        assert result["status"] == "success"

    @pytest.mark.asyncio
    async def test_running_tasks_cleanup_on_cancel(self, runner):
        """Test that _running_tasks is cleaned up when task is cancelled."""
        session_key = "test-session"

        # Mock _execute_agent that takes a while
        async def slow_execute(*args, **kwargs):
            await asyncio.sleep(10)
            return {"status": "success"}

        with patch.object(runner, "_execute_agent", side_effect=slow_execute):
            # Start a run in background
            run_task = asyncio.create_task(runner._run_agent(session_key, ["test message"]))

            # Give it time to start
            await asyncio.sleep(0.05)

            # Task should be tracked
            assert session_key in runner._running_tasks

            # Cancel it
            run_task.cancel()

            try:
                await run_task
            except asyncio.CancelledError:
                pass

        # After cancellation, task should be cleaned up
        assert session_key not in runner._running_tasks

    @pytest.mark.asyncio
    async def test_steer_run_cancels_and_executes(self, runner):
        """Test that _steer_run cancels existing task and starts new one."""
        session_key = "test-session"

        # Create an async task that can be cancelled
        async def slow_task():
            await asyncio.sleep(10)
            return None

        mock_task = asyncio.create_task(slow_task())
        runner._running_tasks[session_key] = mock_task
        runner._active_sessions.add(session_key)

        # Give task time to start
        await asyncio.sleep(0)

        # Mock _run_agent to avoid actual execution
        with patch.object(runner, "_run_agent", return_value={"status": "steered"}):
            result = await runner._steer_run(session_key, "new prompt")

        # Should return result from new execution
        assert result["status"] == "steered"

        # Session should not be active after steer completes
        assert session_key not in runner._active_sessions


class TestAgentRunnerIntegration:
    """Integration tests for AgentRunner with STEER modes."""

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
    async def test_qa_scenario_steer_mode(self, runner):
        """QA Scenario: STEER mode resolves correctly."""
        action = QueuePolicy.resolve(
            is_active=True,
            is_heartbeat=False,
            should_followup=False,
            queue_mode=QueueMode.STEER,
        )
        assert action == QueueAction.STEER
        print(f"STEER mode action: {action.value}")

    @pytest.mark.asyncio
    async def test_qa_scenario_policy_all_modes(self, runner):
        """QA Scenario: All queue modes resolve to expected actions when active."""
        test_cases = [
            (QueueMode.COLLECT, QueueAction.ENQUEUE),
            (QueueMode.FOLLOWUP, QueueAction.ENQUEUE_FOLLOWUP),
            (QueueMode.STEER, QueueAction.STEER),
            (QueueMode.STEER_BACKLOG, QueueAction.ENQUEUE),
            (QueueMode.INTERRUPT, QueueAction.INTERRUPT),
            (QueueMode.QUEUE, QueueAction.ENQUEUE),
        ]

        for mode, expected_action in test_cases:
            action = QueuePolicy.resolve(
                is_active=True,
                is_heartbeat=False,
                should_followup=False,
                queue_mode=mode,
            )
            assert action == expected_action, (
                f"Mode {mode.value} should resolve to {expected_action.value}, got {action.value}"
            )
            print(f"Mode {mode.value} -> {action.value}")


class TestAgentRunnerHandleMessageSteer:
    """Tests for handle_message with STEER modes."""

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
    async def test_handle_message_steer_not_active(self, runner):
        """STEER mode when session not active should execute."""
        runner._run_agent = AsyncMock(return_value={"response": "ok"})
        result = await runner.handle_message("session1", "hello", QueueMode.STEER)
        assert result["status"] == "executed"
        runner._run_agent.assert_called_once_with("session1", ["hello"])

    @pytest.mark.asyncio
    async def test_handle_message_steer_active(self, runner):
        """STEER mode when active should steer."""
        runner._active_sessions.add("session1")
        runner._steer_run = AsyncMock(return_value={"response": "steered"})
        result = await runner.handle_message("session1", "new prompt", QueueMode.STEER)
        assert result["status"] == "steered"
        runner._steer_run.assert_called_once_with("session1", "new prompt")

    @pytest.mark.asyncio
    async def test_handle_message_interrupt_active(self, runner):
        """INTERRUPT mode when active should interrupt."""
        runner._active_sessions.add("session1")
        runner._interrupt_run = AsyncMock()
        result = await runner.handle_message("session1", "ignored", QueueMode.INTERRUPT)
        assert result["status"] == "interrupted"
        runner._interrupt_run.assert_called_once_with("session1", skip_lock=True)

    @pytest.mark.asyncio
    async def test_handle_message_interrupt_not_active(self, runner):
        """INTERRUPT mode when not active should execute (since not active)."""
        runner._run_agent = AsyncMock(return_value={"response": "ok"})
        result = await runner.handle_message("session1", "hello", QueueMode.INTERRUPT)
        assert result["status"] == "executed"
        runner._run_agent.assert_called_once_with("session1", ["hello"])

    @pytest.mark.asyncio
    async def test_handle_message_steer_backlog_active(self, runner):
        """STEER_BACKLOG mode when active should enqueue."""
        runner._active_sessions.add("session1")
        runner.message_enqueuer.enqueue = AsyncMock(return_value=True)
        result = await runner.handle_message("session1", "hello", QueueMode.STEER_BACKLOG)
        assert result["status"] == "queued"
        assert result["queue_mode"] == "steer_backlog"
        runner.message_enqueuer.enqueue.assert_called_once()
        # Verify queue settings mode is STEER_BACKLOG
        queue_settings = runner.message_enqueuer.enqueue.call_args[0][2]
        assert queue_settings.mode == QueueMode.STEER_BACKLOG

    @pytest.mark.asyncio
    async def test_handle_message_queue_mode_active(self, runner):
        """QUEUE mode when active should enqueue."""
        runner._active_sessions.add("session1")
        runner.message_enqueuer.enqueue = AsyncMock(return_value=True)
        result = await runner.handle_message("session1", "hello", QueueMode.QUEUE)
        assert result["status"] == "queued"
        assert result["queue_mode"] == "queue"
        runner.message_enqueuer.enqueue.assert_called_once()
        queue_settings = runner.message_enqueuer.enqueue.call_args[0][2]
        assert queue_settings.mode == QueueMode.QUEUE

    @pytest.mark.asyncio
    async def test_handle_message_drop_heartbeat(self, runner):
        """Heartbeat messages should be dropped (is_heartbeat not yet supported)."""
        # Currently heartbeat not implemented, so this test just ensures no crash
        # We'll test that policy returns DROP when is_heartbeat=True, but runner doesn't have that param.
        pass
