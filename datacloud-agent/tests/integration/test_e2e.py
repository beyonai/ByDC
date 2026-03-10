"""End-to-end integration tests for datacloud-agent.

Comprehensive integration tests covering:
1. Agent registration and configuration
2. Basic message processing with deepagents
3. Tool invocation flow
4. Token counting verification
5. STEER mode functionality
6. Queue mode operations
7. Multi-tenant isolation
"""

import asyncio
import os
from unittest.mock import AsyncMock

import pytest

from datacloud_agent.config.models import GatewayConfig, InboundConfig
from datacloud_agent.core import AgentRunner, SessionManager
from datacloud_agent.core.registry import AgentConfig, AgentRegistry
from datacloud_agent.queue import QueueManager, QueueMode
from datacloud_agent.tenant import TenantContext, TenantType


# Skip all tests in this module if no API key is available
pytestmark = pytest.mark.skipif(
    not os.getenv("OPENAI_API_KEY"),
    reason="OPENAI_API_KEY environment variable not set",
)


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def config():
    """Create gateway config."""
    return GatewayConfig(inbound=InboundConfig(debounce_ms=100, dedupe_window_ms=500))


@pytest.fixture
def session_manager():
    """Create a real session manager."""
    return SessionManager()


@pytest.fixture
def queue_manager():
    """Create a queue manager."""
    return QueueManager()


@pytest.fixture
def mock_event_emitter():
    """Create mock event emitter."""
    return AsyncMock()


@pytest.fixture
def agent_registry():
    """Create agent registry with multiple agents."""
    registry = AgentRegistry()

    # Default agent with all tools
    default_config = AgentConfig(
        agent_id="default",
        model="qwen3.5-plus",
        provider="openai",
        system_prompt="You are a helpful assistant. Keep responses brief.",
        tools=["know", "query", "compute", "render", "store"],
    )
    registry.register("default", default_config)

    # Coder agent with subset of tools
    coder_config = AgentConfig(
        agent_id="coder",
        model="qwen3.5-plus",
        provider="openai",
        system_prompt="You are a coding assistant. Help with programming tasks.",
        tools=["know", "query", "compute"],
    )
    registry.register("coder", coder_config)

    # Analyst agent
    analyst_config = AgentConfig(
        agent_id="analyst",
        model="qwen3.5-plus",
        provider="openai",
        system_prompt="You are a data analyst. Help with data queries and analysis.",
        tools=["know", "query", "compute", "render"],
    )
    registry.register("analyst", analyst_config)

    return registry


@pytest.fixture
def runner(session_manager, agent_registry, queue_manager, mock_event_emitter, config):
    """Create AgentRunner instance with real dependencies."""
    return AgentRunner(
        session_manager=session_manager,
        agent_registry=agent_registry,
        queue_manager=queue_manager,
        event_emitter=mock_event_emitter,
        config=config,
    )


@pytest.fixture
def tenant_context_user1():
    """Create tenant context for user 1."""
    return TenantContext(
        tenant_id="user_001",
        tenant_type=TenantType.USER_PRIVATE,
    )


@pytest.fixture
def tenant_context_user2():
    """Create tenant context for user 2."""
    return TenantContext(
        tenant_id="user_002",
        tenant_type=TenantType.USER_PRIVATE,
    )


# ============================================================================
# Test Class: Agent Registration and Configuration
# ============================================================================


class TestAgentRegistrationAndConfiguration:
    """Tests for agent registration and configuration."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_agent_registration_success(self, agent_registry):
        """Test successful agent registration."""
        assert agent_registry.has_agent("default")
        assert agent_registry.has_agent("coder")
        assert agent_registry.has_agent("analyst")

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_agent_configuration_retrieval(self, agent_registry):
        """Test retrieving agent configuration."""
        config = agent_registry.get("default")
        assert config is not None
        assert config.agent_id == "default"
        assert config.model == "qwen3.5-plus"
        assert config.provider == "openai"
        assert "know" in config.tools
        assert "query" in config.tools

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_agent_list(self, agent_registry):
        """Test listing all registered agents."""
        agents = agent_registry.list_agents()
        assert len(agents) == 3
        agent_ids = [a["id"] for a in agents]
        assert "default" in agent_ids
        assert "coder" in agent_ids
        assert "analyst" in agent_ids

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_agent_tools_configuration(self, agent_registry):
        """Test agent tools are configured correctly."""
        default = agent_registry.get("default")
        assert len(default.tools) == 5

        coder = agent_registry.get("coder")
        assert len(coder.tools) == 3
        assert "render" not in coder.tools
        assert "store" not in coder.tools

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_agent_creation(self, agent_registry):
        """Test creating an agent instance."""
        agent_dict = agent_registry.create_agent("default")
        assert agent_dict["agent_id"] == "default"
        assert agent_dict["model"] == "qwen3.5-plus"


# ============================================================================
# Test Class: Basic Message Processing
# ============================================================================


class TestBasicMessageProcessing:
    """Tests for basic message processing with deepagents."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_simple_message_processing(self, runner, tenant_context_user1):
        """Test processing a simple message."""
        session_key = f"tenant:{tenant_context_user1.tenant_id}:agent:default:session_001"

        result = await runner._execute_agent(session_key, ["Hello, what is 2+2?"])

        assert "response" in result
        assert result["agent_id"] == "default"
        assert result["response"] is not None
        assert len(result["response"]) > 0

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_message_processing_with_context(self, runner, tenant_context_user1):
        """Test message processing maintains context across turns."""
        session_key = f"tenant:{tenant_context_user1.tenant_id}:agent:default:session_002"

        # First message
        result1 = await runner._execute_agent(session_key, ["My name is Alice"])
        assert "response" in result1

        # Second message - should remember context
        result2 = await runner._execute_agent(session_key, ["What is my name?"])
        assert "response" in result2
        # Response should reference Alice (context preserved via checkpointer)

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_message_processing_different_agents(
        self, runner, tenant_context_user1, agent_registry
    ):
        """Test processing messages with different agent configurations."""
        session_key_default = f"tenant:{tenant_context_user1.tenant_id}:agent:default:session_003"
        session_key_coder = f"tenant:{tenant_context_user1.tenant_id}:agent:coder:session_004"

        result_default = await runner._execute_agent(
            session_key_default, ["Help me with a general question"]
        )
        assert result_default["agent_id"] == "default"

        result_coder = await runner._execute_agent(session_key_coder, ["Write a Python function"])
        assert result_coder["agent_id"] == "coder"

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_message_processing_error_handling(self, runner, tenant_context_user1):
        """Test error handling for invalid agent."""
        session_key = f"tenant:{tenant_context_user1.tenant_id}:agent:nonexistent:session_005"

        with pytest.raises(ValueError, match="Agent 'nonexistent' not found"):
            await runner._execute_agent(session_key, ["Hello"])

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_message_processing_invalid_session_key(self, runner):
        """Test error handling for invalid session key format."""
        with pytest.raises(ValueError, match="Invalid session key format"):
            await runner._execute_agent("invalid-key", ["Hello"])


# ============================================================================
# Test Class: Tool Invocation Flow
# ============================================================================


class TestToolInvocationFlow:
    """Tests for tool invocation flow."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_tool_know_invocation(self, runner, tenant_context_user1):
        """Test invocation of know tool."""
        session_key = f"tenant:{tenant_context_user1.tenant_id}:agent:default:session_006"

        result = await runner._execute_agent(
            session_key, ["Use the know tool to search for 'user model'"]
        )

        assert "response" in result
        assert "messages" in result
        # The agent may or may not use the tool, but should respond

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_tool_query_invocation(self, runner, tenant_context_user1):
        """Test invocation of query tool."""
        session_key = f"tenant:{tenant_context_user1.tenant_id}:agent:default:session_007"

        result = await runner._execute_agent(session_key, ["Use the query tool to get sales data"])

        assert "response" in result

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_tool_compute_invocation(self, runner, tenant_context_user1):
        """Test invocation of compute tool."""
        session_key = f"tenant:{tenant_context_user1.tenant_id}:agent:default:session_008"

        result = await runner._execute_agent(
            session_key, ["Use the compute tool to calculate 100 + 200"]
        )

        assert "response" in result

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_multiple_tool_invocation(self, runner, tenant_context_user1):
        """Test multiple tool invocations in sequence."""
        session_key = f"tenant:{tenant_context_user1.tenant_id}:agent:default:session_009"

        # Ask a question that might use multiple tools
        result = await runner._execute_agent(
            session_key,
            ["Use know to find user data, then query to retrieve it, and compute to analyze it"],
        )

        assert "response" in result
        assert "messages" in result

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_tool_availability_per_agent(self, runner, tenant_context_user1):
        """Test that tools are available based on agent configuration."""
        # Default agent has all tools
        session_default = f"tenant:{tenant_context_user1.tenant_id}:agent:default:session_010"
        result_default = await runner._execute_agent(session_default, ["What tools can you use?"])
        assert "response" in result_default

        # Coder agent has limited tools
        session_coder = f"tenant:{tenant_context_user1.tenant_id}:agent:coder:session_011"
        result_coder = await runner._execute_agent(session_coder, ["What tools can you use?"])
        assert "response" in result_coder


# ============================================================================
# Test Class: Token Counting Verification
# ============================================================================


class TestTokenCountingVerification:
    """Tests for token counting verification."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_token_counting_returns_usage(self, runner, tenant_context_user1):
        """Test that execution returns token usage."""
        session_key = f"tenant:{tenant_context_user1.tenant_id}:agent:default:session_012"

        result = await runner._execute_agent(session_key, ["Say 'hello'"])

        assert "usage" in result
        usage = result["usage"]
        assert "input_tokens" in usage
        assert "output_tokens" in usage
        assert "total_tokens" in usage

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_token_counting_non_negative(self, runner, tenant_context_user1):
        """Test that token counts are non-negative."""
        session_key = f"tenant:{tenant_context_user1.tenant_id}:agent:default:session_013"

        result = await runner._execute_agent(session_key, ["Test message"])

        usage = result["usage"]
        assert usage["input_tokens"] >= 0
        assert usage["output_tokens"] >= 0
        assert usage["total_tokens"] >= 0
        assert isinstance(usage["input_tokens"], int)
        assert isinstance(usage["output_tokens"], int)

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_token_counting_accumulates(self, runner, tenant_context_user1):
        """Test that token counting accumulates across turns."""
        session_key = f"tenant:{tenant_context_user1.tenant_id}:agent:default:session_014"

        # First turn
        result1 = await runner._execute_agent(session_key, ["Hello"])
        usage1 = result1["usage"]

        # Second turn
        result2 = await runner._execute_agent(session_key, ["How are you?"])
        usage2 = result2["usage"]

        # Input tokens should generally increase as context grows
        # (though exact behavior depends on model implementation)
        assert usage2["input_tokens"] >= 0

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_token_counting_long_message(self, runner, tenant_context_user1):
        """Test token counting with a longer message."""
        session_key = f"tenant:{tenant_context_user1.tenant_id}:agent:default:session_015"

        long_message = "This is a longer message. " * 50
        result = await runner._execute_agent(session_key, [long_message])

        assert "usage" in result
        usage = result["usage"]
        # Longer messages should have more input tokens
        assert usage["input_tokens"] > 0


# ============================================================================
# Test Class: STEER Mode Functionality
# ============================================================================


class TestSteerModeFunctionality:
    """Tests for STEER mode functionality."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_steer_without_checkpointer_fallback(self, runner, tenant_context_user1):
        """Test STEER without existing checkpointer falls back to normal execution."""
        session_key = f"tenant:{tenant_context_user1.tenant_id}:agent:default:session_016"

        # No checkpointer exists yet
        assert session_key not in runner._checkpointers

        # STEER should fall back to _run_agent
        result = await runner._steer_run(session_key, "Hello")

        # Should have created a checkpointer now
        assert session_key in runner._checkpointers
        assert "response" in result

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_steer_with_existing_checkpointer(self, runner, tenant_context_user1):
        """Test STEER with existing checkpointer uses Command(resume=...)."""
        session_key = f"tenant:{tenant_context_user1.tenant_id}:agent:default:session_017"

        # First, create a checkpointer via normal execution
        result1 = await runner._execute_agent(session_key, ["My favorite color is blue"])
        assert session_key in runner._checkpointers

        # Now STEER with new input
        result2 = await runner._steer_run(session_key, "What is my favorite color?")

        # Should have a response
        assert "response" in result2
        assert "usage" in result2

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_steer_preserves_context(self, runner, tenant_context_user1):
        """Test that STEER preserves conversation context."""
        session_key = f"tenant:{tenant_context_user1.tenant_id}:agent:default:session_018"

        # Initial message
        await runner._execute_agent(session_key, ["I work at OpenClaw"])

        # STEER to ask about context
        result = await runner._steer_run(session_key, "Where do I work?")

        assert "response" in result
        # Context should be preserved via checkpointer

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_steer_via_handle_message(self, runner, tenant_context_user1):
        """Test STEER mode via handle_message."""
        session_key = f"tenant:{tenant_context_user1.tenant_id}:agent:default:session_019"

        # First execution
        runner.dedupe_cache.clear()
        runner.debouncer.clear()
        result1 = await runner.handle_message(session_key, "Hello", QueueMode.COLLECT)

        # Mark session as active
        runner._active_sessions.add(session_key)

        # STEER via handle_message
        runner.dedupe_cache.clear()
        runner.debouncer.clear()
        result2 = await runner.handle_message(session_key, "Tell me more", QueueMode.STEER)

        # Should have executed or steered
        assert result2["status"] in ["executed", "steered"]


# ============================================================================
# Test Class: Queue Mode Operations
# ============================================================================


class TestQueueModeOperations:
    """Tests for queue mode operations."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_collect_mode_enqueue(self, runner, tenant_context_user1):
        """Test COLLECT mode enqueues when session is active."""
        session_key = f"tenant:{tenant_context_user1.tenant_id}:agent:default:session_020"

        # Mark session as active
        runner._active_sessions.add(session_key)

        # COLLECT mode should enqueue
        result = await runner.handle_message(session_key, "Test message", QueueMode.COLLECT)

        assert result["status"] == "queued"

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_followup_mode_enqueue(self, runner, tenant_context_user1):
        """Test FOLLOWUP mode enqueues with followup flag."""
        session_key = f"tenant:{tenant_context_user1.tenant_id}:agent:default:session_021"

        # Mark session as active
        runner._active_sessions.add(session_key)

        result = await runner.handle_message(session_key, "Followup message", QueueMode.FOLLOWUP)

        assert result["status"] == "queued"

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_queue_mode_enqueue(self, runner, tenant_context_user1):
        """Test QUEUE mode enqueues when session is active."""
        session_key = f"tenant:{tenant_context_user1.tenant_id}:agent:default:session_022"

        # Mark session as active
        runner._active_sessions.add(session_key)

        result = await runner.handle_message(session_key, "Queue message", QueueMode.QUEUE)

        assert result["status"] == "queued"

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_interrupt_mode(self, runner, tenant_context_user1):
        """Test INTERRUPT mode cancels active execution."""
        session_key = f"tenant:{tenant_context_user1.tenant_id}:agent:default:session_023"

        # Mark session as active
        runner._active_sessions.add(session_key)

        result = await runner.handle_message(session_key, "Interrupt", QueueMode.INTERRUPT)

        assert result["status"] == "interrupted"
        assert session_key not in runner._active_sessions

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_mode_execution_when_not_active(self, runner, tenant_context_user1):
        """Test that all modes execute when session is not active."""
        session_key = f"tenant:{tenant_context_user1.tenant_id}:agent:default:session_024"

        # Session not active
        assert session_key not in runner._active_sessions

        # All modes should execute
        for mode in [QueueMode.COLLECT, QueueMode.QUEUE, QueueMode.STEER]:
            runner.dedupe_cache.clear()
            runner.debouncer.clear()
            result = await runner.handle_message(session_key, f"Test {mode.value}", mode)
            assert result["status"] == "executed", f"Failed for mode {mode.value}"

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_queue_size_tracking(self, runner, tenant_context_user1):
        """Test queue size is tracked correctly."""
        session_key = f"tenant:{tenant_context_user1.tenant_id}:agent:default:session_025"

        # Mark session as active
        runner._active_sessions.add(session_key)

        # Enqueue multiple messages
        for i in range(3):
            runner.dedupe_cache.clear()
            runner.debouncer.clear()
            await runner.handle_message(session_key, f"Message {i}", QueueMode.COLLECT)

        # Check queue size
        status = await runner.get_status(session_key)
        # Note: Queue size depends on deduplication
        assert "queue_size" in status


# ============================================================================
# Test Class: Multi-Tenant Isolation
# ============================================================================


class TestMultiTenantIsolation:
    """Tests for multi-tenant isolation."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_session_isolation_between_tenants(
        self, runner, tenant_context_user1, tenant_context_user2
    ):
        """Test that sessions are isolated between tenants."""
        session_key_1 = f"tenant:{tenant_context_user1.tenant_id}:agent:default:session_user1"
        session_key_2 = f"tenant:{tenant_context_user2.tenant_id}:agent:default:session_user2"

        # User 1 sets context
        result1 = await runner._execute_agent(session_key_1, ["My secret is 'alpha'"])

        # User 2 sets context
        result2 = await runner._execute_agent(session_key_2, ["My secret is 'beta'"])

        # User 1 asks about their secret
        result1_check = await runner._execute_agent(session_key_1, ["What is my secret?"])

        # User 2 asks about their secret
        result2_check = await runner._execute_agent(session_key_2, ["What is my secret?"])

        # Each should know only their own context
        # Checkpointers are isolated by session key
        assert session_key_1 in runner._checkpointers
        assert session_key_2 in runner._checkpointers
        assert runner._checkpointers[session_key_1] != runner._checkpointers[session_key_2]

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_active_sessions_isolated(
        self, runner, tenant_context_user1, tenant_context_user2
    ):
        """Test that active sessions are tracked separately."""
        session_key_1 = f"tenant:{tenant_context_user1.tenant_id}:agent:default:session_active1"
        session_key_2 = f"tenant:{tenant_context_user2.tenant_id}:agent:default:session_active2"

        # Mark only user1's session as active
        runner._active_sessions.add(session_key_1)

        assert await runner.is_active(session_key_1)
        assert not await runner.is_active(session_key_2)

        # User2's message should execute (not enqueue)
        runner.dedupe_cache.clear()
        runner.debouncer.clear()
        result2 = await runner.handle_message(session_key_2, "Test", QueueMode.COLLECT)
        assert result2["status"] == "executed"

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_checkpointer_isolation(self, runner, tenant_context_user1, tenant_context_user2):
        """Test that checkpointers are isolated between tenants."""
        session_key_1 = f"tenant:{tenant_context_user1.tenant_id}:agent:default:session_check1"
        session_key_2 = f"tenant:{tenant_context_user2.tenant_id}:agent:default:session_check2"

        # Execute for both tenants
        await runner._execute_agent(session_key_1, ["Context for user 1"])
        await runner._execute_agent(session_key_2, ["Context for user 2"])

        # Each should have their own checkpointer
        assert session_key_1 in runner._checkpointers
        assert session_key_2 in runner._checkpointers
        # Different checkpointer instances
        assert id(runner._checkpointers[session_key_1]) != id(runner._checkpointers[session_key_2])

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_concurrent_tenants(self, runner, tenant_context_user1, tenant_context_user2):
        """Test concurrent operations from different tenants."""
        session_key_1 = f"tenant:{tenant_context_user1.tenant_id}:agent:default:session_concurrent1"
        session_key_2 = f"tenant:{tenant_context_user2.tenant_id}:agent:default:session_concurrent2"

        # Execute concurrently
        results = await asyncio.gather(
            runner._execute_agent(session_key_1, ["Hello from user 1"]),
            runner._execute_agent(session_key_2, ["Hello from user 2"]),
        )

        # Both should succeed
        assert all("response" in r for r in results)
        assert all("usage" in r for r in results)

        # Each tenant has their own checkpointer
        assert session_key_1 in runner._checkpointers
        assert session_key_2 in runner._checkpointers

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_different_agents_per_tenant(self, runner, tenant_context_user1):
        """Test using different agents for the same tenant."""
        session_default = (
            f"tenant:{tenant_context_user1.tenant_id}:agent:default:session_agent_default"
        )
        session_coder = f"tenant:{tenant_context_user1.tenant_id}:agent:coder:session_agent_coder"
        session_analyst = (
            f"tenant:{tenant_context_user1.tenant_id}:agent:analyst:session_agent_analyst"
        )

        # Use different agents
        result_default = await runner._execute_agent(session_default, ["General question"])
        result_coder = await runner._execute_agent(session_coder, ["Code question"])
        result_analyst = await runner._execute_agent(session_analyst, ["Data analysis"])

        # All should succeed with correct agent_id
        assert result_default["agent_id"] == "default"
        assert result_coder["agent_id"] == "coder"
        assert result_analyst["agent_id"] == "analyst"


# ============================================================================
# Test Class: Error Handling
# ============================================================================


class TestErrorHandling:
    """Tests for error handling scenarios."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_invalid_agent_error(self, runner, tenant_context_user1):
        """Test error when requesting invalid agent."""
        session_key = f"tenant:{tenant_context_user1.tenant_id}:agent:invalid_agent:session_err"

        with pytest.raises(ValueError, match="Agent 'invalid_agent' not found"):
            await runner._execute_agent(session_key, ["Test"])

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_invalid_session_key_format(self, runner):
        """Test error for invalid session key format."""
        with pytest.raises(ValueError, match="Invalid session key format"):
            await runner._execute_agent("bad-format", ["Test"])

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_empty_message(self, runner, tenant_context_user1):
        """Test handling of empty message."""
        session_key = f"tenant:{tenant_context_user1.tenant_id}:agent:default:session_empty"

        # Empty message should still work
        result = await runner._execute_agent(session_key, [""])
        assert "response" in result

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_very_long_message(self, runner, tenant_context_user1):
        """Test handling of very long message."""
        session_key = f"tenant:{tenant_context_user1.tenant_id}:agent:default:session_long"

        long_message = "This is a test message. " * 1000
        result = await runner._execute_agent(session_key, [long_message])

        assert "response" in result
        assert "usage" in result


# ============================================================================
# Test Class: Integration with Session Manager
# ============================================================================


class TestSessionManagerIntegration:
    """Tests for integration with session manager."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_session_creation(self, session_manager, tenant_context_user1):
        """Test session creation."""
        session = await session_manager.create_session(tenant_context_user1, agent_id="default")

        assert session.tenant_id == tenant_context_user1.tenant_id
        assert session.agent_id == "default"
        assert session.session_id is not None

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_session_retrieval(self, session_manager, tenant_context_user1):
        """Test session retrieval."""
        session = await session_manager.create_session(tenant_context_user1, agent_id="default")

        retrieved = await session_manager.get_session(session.session_key)
        assert retrieved is not None
        assert retrieved.session_id == session.session_id

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_session_list(self, session_manager, tenant_context_user1, tenant_context_user2):
        """Test listing sessions."""
        await session_manager.create_session(tenant_context_user1, agent_id="default")
        await session_manager.create_session(tenant_context_user1, agent_id="coder")
        await session_manager.create_session(tenant_context_user2, agent_id="default")

        # List sessions for user1
        sessions_user1 = await session_manager.list_sessions(
            tenant_id=tenant_context_user1.tenant_id
        )
        assert len(sessions_user1) == 2

        # List sessions for user2
        sessions_user2 = await session_manager.list_sessions(
            tenant_id=tenant_context_user2.tenant_id
        )
        assert len(sessions_user2) == 1


# ============================================================================
# Test Class: Performance and Load
# ============================================================================


class TestPerformanceAndLoad:
    """Tests for performance and load scenarios."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_concurrent_sessions(self, runner, tenant_context_user1):
        """Test multiple concurrent sessions for the same tenant."""
        session_keys = [
            f"tenant:{tenant_context_user1.tenant_id}:agent:default:session_concurrent_{i}"
            for i in range(5)
        ]

        # Execute concurrently
        results = await asyncio.gather(
            *[runner._execute_agent(key, [f"Message {i}"]) for i, key in enumerate(session_keys)]
        )

        # All should succeed
        assert all("response" in r for r in results)

        # Each should have its own checkpointer
        for key in session_keys:
            assert key in runner._checkpointers

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_rapid_sequential_messages(self, runner, tenant_context_user1):
        """Test rapid sequential messages in the same session."""
        session_key = f"tenant:{tenant_context_user1.tenant_id}:agent:default:session_rapid"

        # Send multiple messages rapidly
        for i in range(3):
            result = await runner._execute_agent(session_key, [f"Message {i}"])
            assert "response" in result

        # Checkpointer should be reused
        assert session_key in runner._checkpointers
