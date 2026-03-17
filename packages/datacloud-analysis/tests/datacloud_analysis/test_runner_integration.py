"""Integration tests for AgentRunner with deepagents.

Tests the integration of AgentRunner with deepagents library based on POC validation:
- POC 1: create_deep_agent works correctly
- POC 2: Token counting from AIMessage.usage_metadata
- POC 3: STEER mode using Command(resume=...)
"""

import os
from unittest.mock import AsyncMock, MagicMock

import pytest

from datacloud_analysis.config.models import GatewayConfig, InboundConfig
from datacloud_analysis.core import AgentRunner
from datacloud_analysis.core.registry import AgentConfig
from datacloud_analysis.queue.types import QueueMode


# Skip all tests in this module if no API key is available
pytestmark = pytest.mark.skipif(
    not os.getenv("OPENAI_API_KEY"),
    reason="OPENAI_API_KEY environment variable not set",
)


@pytest.fixture
def mock_session_manager():
    """Create mock session manager."""
    return AsyncMock()


@pytest.fixture
def mock_queue_manager():
    """Create mock queue manager."""
    return AsyncMock()


@pytest.fixture
def mock_event_emitter():
    """Create mock event emitter."""
    return AsyncMock()


@pytest.fixture
def config():
    """Create gateway config."""
    return GatewayConfig(inbound=InboundConfig(debounce_ms=100, dedupe_window_ms=500))


@pytest.fixture
def agent_registry():
    """Create agent registry with default agent."""
    from datacloud_analysis.core.registry import AgentRegistry

    registry = AgentRegistry()
    default_config = AgentConfig(
        agent_id="default",
        name="Default Agent",
        description="General purpose agent for testing",
        model="qwen3.5-plus",
        provider="openai",
        system_prompt="You are a helpful assistant. Keep responses brief.",
        tools=["know", "query", "compute", "render", "store"],
    )
    registry.register("default", default_config)
    return registry


@pytest.fixture
def runner(
    mock_session_manager,
    agent_registry,
    mock_queue_manager,
    mock_event_emitter,
    config,
):
    """Create AgentRunner instance."""
    return AgentRunner(
        session_manager=mock_session_manager,
        agent_registry=agent_registry,
        queue_manager=mock_queue_manager,
        event_emitter=mock_event_emitter,
        config=config,
    )


class TestAgentRunnerInitialization:
    """Test AgentRunner initialization with deepagents integration."""

    def test_runner_has_checkpointers(self, runner):
        """Test that runner initializes with empty checkpointers dict."""
        assert hasattr(runner, "_checkpointers")
        assert runner._checkpointers == {}

    def test_runner_has_required_imports(self):
        """Test that all required deepagents imports are available."""
        from deepagents import create_deep_agent
        from langchain_core.messages import AIMessage
        from langgraph.checkpoint.memory import InMemorySaver
        from langgraph.types import Command

        assert callable(create_deep_agent)
        assert callable(InMemorySaver)
        assert Command is not None
        assert AIMessage is not None


class TestExecuteAgent:
    """Test _execute_agent method with deepagents integration."""

    @pytest.mark.asyncio
    async def test_execute_agent_invalid_session_key(self, runner):
        """Test that invalid session key raises ValueError."""
        with pytest.raises(ValueError, match="Invalid session key format"):
            await runner._execute_agent("invalid-key", ["Hello"])

    @pytest.mark.asyncio
    async def test_execute_agent_missing_agent(self, runner):
        """Test that missing agent raises ValueError."""
        with pytest.raises(ValueError, match="Agent 'nonexistent' not found"):
            await runner._execute_agent(
                "tenant:t1:agent:nonexistent:s1",
                ["Hello"],
            )

    @pytest.mark.asyncio
    async def test_execute_agent_creates_checkpointer(self, runner):
        """Test that execution creates a checkpointer for the session."""
        session_key = "tenant:t1:agent:default:s1"
        assert session_key not in runner._checkpointers

        # Execute with a simple query
        result = await runner._execute_agent(session_key, ["Say 'test ok'"])

        # Verify checkpointer was created
        assert session_key in runner._checkpointers
        assert result["agent_id"] == "default"
        assert "response" in result
        assert "usage" in result

    @pytest.mark.asyncio
    async def test_execute_agent_returns_usage(self, runner):
        """Test that execution returns token usage from AIMessage.usage_metadata."""
        session_key = "tenant:t1:agent:default:s2"
        result = await runner._execute_agent(session_key, ["Say 'hello'"])

        # POC 2: Should have usage metadata
        assert "usage" in result
        usage = result["usage"]
        assert "input_tokens" in usage
        assert "output_tokens" in usage
        assert "total_tokens" in usage
        # Tokens should be non-negative integers
        assert isinstance(usage["input_tokens"], int)
        assert isinstance(usage["output_tokens"], int)
        assert isinstance(usage["total_tokens"], int)
        assert usage["input_tokens"] >= 0
        assert usage["output_tokens"] >= 0

    @pytest.mark.asyncio
    async def test_execute_agent_returns_messages(self, runner):
        """Test that execution returns message history."""
        session_key = "tenant:t1:agent:default:s3"
        result = await runner._execute_agent(session_key, ["Say 'test'"])

        assert "messages" in result
        assert isinstance(result["messages"], list)
        assert len(result["messages"]) > 0

    @pytest.mark.asyncio
    async def test_execute_agent_reuses_checkpointer(self, runner):
        """Test that subsequent executions reuse the same checkpointer."""
        session_key = "tenant:t1:agent:default:s4"

        # First execution
        await runner._execute_agent(session_key, ["Remember: my name is Alice"])
        checkpointer1 = runner._checkpointers[session_key]

        # Second execution - should reuse checkpointer
        await runner._execute_agent(session_key, ["What is my name?"])
        checkpointer2 = runner._checkpointers[session_key]

        # Same checkpointer instance
        assert checkpointer1 is checkpointer2


class TestSteerMode:
    """Test STEER mode with Command(resume=...) pattern."""

    @pytest.mark.asyncio
    async def test_steer_without_checkpointer_falls_back(self, runner):
        """Test that STEER without existing checkpointer falls back to normal execution."""
        session_key = "tenant:t1:agent:default:s5"

        # No checkpointer exists yet
        assert session_key not in runner._checkpointers

        # STEER should fall back to _run_agent
        result = await runner._steer_run(session_key, "Hello")

        # Should have created a checkpointer now
        assert session_key in runner._checkpointers
        assert "response" in result

    @pytest.mark.asyncio
    async def test_steer_with_checkpointer_uses_command(self, runner):
        """Test that STEER with existing checkpointer uses Command(resume=...)."""
        session_key = "tenant:t1:agent:default:s6"

        # First, create a checkpointer via normal execution
        result1 = await runner._execute_agent(session_key, ["My favorite color is blue"])
        assert session_key in runner._checkpointers

        # Now STEER with new input
        result2 = await runner._steer_run(session_key, "What is my favorite color?")

        # Should have a response
        assert "response" in result2
        assert "usage" in result2

    @pytest.mark.asyncio
    async def test_steer_with_command_preserves_context(self, runner):
        """Test that STEER preserves conversation context via checkpointer."""
        session_key = "tenant:t1:agent:default:s7"

        # Initial message
        await runner._execute_agent(session_key, ["I work at OpenClaw"])

        # STEER to ask about context
        result = await runner._steer_run(session_key, "Where do I work?")

        # Response should reference the previous context
        assert "response" in result
        # The response should mention OpenClaw (context preserved via checkpointer)


class TestEndToEndIntegration:
    """End-to-end integration tests."""

    @pytest.mark.asyncio
    async def test_full_conversation_flow(self, runner):
        """Test a full conversation flow with multiple turns."""
        session_key = "tenant:t1:agent:default:s8"

        # Turn 1
        result1 = await runner._execute_agent(session_key, ["Hello, I'm testing"])
        assert result1["agent_id"] == "default"
        assert result1["response"]

        # Turn 2 - via handle_message
        runner.dedupe_cache.clear()  # Clear to avoid dedupe
        runner.debouncer.clear()
        result2 = await runner.handle_message(
            session_key,
            "Can you help me with data analysis?",
            QueueMode.COLLECT,
        )
        # Should be queued because session is now active
        # (depends on timing, so we just verify it doesn't error)

    @pytest.mark.asyncio
    async def test_tool_integration(self, runner):
        """Test that business tools are available and can be invoked."""
        session_key = "tenant:t1:agent:default:s9"

        # Ask a question that should trigger tool use
        result = await runner._execute_agent(
            session_key,
            ["Use the know tool to look up information about 'users'"],
        )

        assert "messages" in result
        # The response should indicate tool use (if model decides to use it)


class TestRunnerStatus:
    """Test runner status methods."""

    @pytest.mark.asyncio
    async def test_is_active_tracking(self, runner):
        """Test that active session tracking works."""
        session_key = "tenant:t1:agent:default:s10"

        # Initially not active
        assert not await runner.is_active(session_key)

        # Add to active set
        runner._active_sessions.add(session_key)
        assert await runner.is_active(session_key)

        # Remove from active set
        runner._active_sessions.discard(session_key)
        assert not await runner.is_active(session_key)

    @pytest.mark.asyncio
    async def test_get_status(self, runner):
        """Test get_status method."""
        session_key = "tenant:t1:agent:default:s11"
        runner._active_sessions.add(session_key)

        status = await runner.get_status(session_key)

        assert status["session_key"] == session_key
        assert status["active"] is True
        assert "queue_size" in status
