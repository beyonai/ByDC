"""Tests for GatewayClient high-level API."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from datacloud_agent.api.client import GatewayClient
from datacloud_agent.api.exceptions import (
    AgentNotFoundError,
    SessionNotFoundError,
)
from datacloud_agent.api.types import ChatChunk, ChatResponse
from datacloud_agent.config.models import GatewayConfig


class TestGatewayClientInit:
    """Tests for GatewayClient initialization."""

    def test_default_init(self):
        """Test initialization with default values."""
        client = GatewayClient()
        assert client.config is not None
        assert client.tenant_id == "default"

    def test_custom_config(self):
        """Test initialization with custom config."""
        config = GatewayConfig(port=8080)
        client = GatewayClient(config=config)
        assert client.config.port == 8080

    def test_custom_tenant_id(self):
        """Test initialization with custom tenant ID."""
        client = GatewayClient(tenant_id="tenant_123")
        assert client.tenant_id == "tenant_123"


class TestGatewayClientChat:
    """Tests for GatewayClient.chat method."""

    @pytest.fixture
    def client(self):
        """Create a GatewayClient with mocked dependencies."""
        client = GatewayClient()
        # Mock internal components
        client._session_manager = MagicMock()
        client._agent_runner = MagicMock()
        client._agent_registry = MagicMock()
        return client

    @pytest.mark.asyncio
    async def test_chat_new_session(self, client):
        """Test chat creates new session when none provided."""
        # Mock session creation
        mock_session = MagicMock()
        mock_session.session_id = "session-123"
        mock_session.session_key = "tenant:default:agent:default:session-123"
        mock_session.agent_id = "default"
        client._session_manager.create_session = AsyncMock(return_value=mock_session)

        # Mock agent runner - using actual return format from handle_message
        client._agent_runner.handle_message = AsyncMock(
            return_value={
                "status": "executed",
                "session_key": "tenant:default:agent:default:session-123",
                "result": {"response": "Hello!", "agent_id": "default"},
            }
        )

        response = await client.chat("Hello!")

        assert isinstance(response, ChatResponse)
        assert response.content == "Hello!"
        assert response.session_id == "session-123"
        assert response.agent_id == "default"

    @pytest.mark.asyncio
    async def test_chat_existing_session(self, client):
        """Test chat with existing session."""
        # Mock session retrieval
        mock_session = MagicMock()
        mock_session.session_id = "existing-session"
        mock_session.session_key = "tenant:default:agent:default:existing-session"
        mock_session.agent_id = "default"
        client._session_manager.get_session = AsyncMock(return_value=mock_session)

        # Mock agent runner - using actual return format from handle_message
        client._agent_runner.handle_message = AsyncMock(
            return_value={
                "status": "executed",
                "session_key": "tenant:default:agent:default:existing-session",
                "result": {"response": "Response!", "agent_id": "default"},
            }
        )

        response = await client.chat("Hello!", session_id="existing-session")

        assert response.content == "Response!"
        assert response.session_id == "existing-session"

    @pytest.mark.asyncio
    async def test_chat_with_agent_id(self, client):
        """Test chat with specific agent ID."""
        # Mock session creation
        mock_session = MagicMock()
        mock_session.session_id = "session-456"
        mock_session.session_key = "tenant:default:agent:coder:session-456"
        mock_session.agent_id = "coder"
        client._session_manager.create_session = AsyncMock(return_value=mock_session)

        # Mock agent runner - using actual return format from handle_message
        client._agent_runner.handle_message = AsyncMock(
            return_value={
                "status": "executed",
                "session_key": "tenant:default:agent:coder:session-456",
                "result": {"response": "Code response", "agent_id": "coder"},
            }
        )

        response = await client.chat("Write code", agent_id="coder")

        assert response.agent_id == "coder"

    @pytest.mark.asyncio
    async def test_chat_with_timeout_success(self, client):
        """Test chat with timeout parameter completes successfully."""
        # Mock session creation
        mock_session = MagicMock()
        mock_session.session_id = "session-123"
        mock_session.session_key = "tenant:default:agent:default:session-123"
        mock_session.agent_id = "default"
        client._session_manager.create_session = AsyncMock(return_value=mock_session)

        # Mock agent runner with delayed response
        async def delayed_response(*args, **kwargs):
            await asyncio.sleep(0.01)  # Small delay
            return {
                "status": "executed",
                "session_key": "tenant:default:agent:default:session-123",
                "result": {"response": "Hello!", "agent_id": "default"},
            }

        client._agent_runner.handle_message = AsyncMock(side_effect=delayed_response)

        # Should complete successfully within timeout
        response = await client.chat("Hello!", timeout=1.0)

        assert isinstance(response, ChatResponse)
        assert response.content == "Hello!"

    @pytest.mark.asyncio
    async def test_chat_with_timeout_exceeded(self, client):
        """Test chat raises TimeoutError when timeout is exceeded."""
        # Mock session creation
        mock_session = MagicMock()
        mock_session.session_id = "session-123"
        mock_session.session_key = "tenant:default:agent:default:session-123"
        mock_session.agent_id = "default"
        client._session_manager.create_session = AsyncMock(return_value=mock_session)

        # Mock agent runner with long delay
        async def slow_response(*args, **kwargs):
            await asyncio.sleep(10.0)  # Long delay that exceeds timeout
            return {"status": "executed", "result": {"response": "Too late!"}}

        client._agent_runner.handle_message = AsyncMock(side_effect=slow_response)

        # Should raise TimeoutError
        with pytest.raises(TimeoutError, match="timed out"):
            await client.chat("Hello!", timeout=0.01)  # Very short timeout

    @pytest.mark.asyncio
    async def test_chat_without_timeout_uses_default(self, client):
        """Test chat without timeout parameter (backward compatibility)."""
        # Mock session creation
        mock_session = MagicMock()
        mock_session.session_id = "session-123"
        mock_session.session_key = "tenant:default:agent:default:session-123"
        mock_session.agent_id = "default"
        client._session_manager.create_session = AsyncMock(return_value=mock_session)

        # Mock agent runner
        client._agent_runner.handle_message = AsyncMock(
            return_value={
                "status": "executed",
                "session_key": "tenant:default:agent:default:session-123",
                "result": {"response": "Hello!", "agent_id": "default"},
            }
        )

        # Should work without timeout parameter (backward compatibility)
        response = await client.chat("Hello!")

        assert isinstance(response, ChatResponse)
        assert response.content == "Hello!"

    @pytest.mark.asyncio
    async def test_chat_stream_with_timeout(self, client):
        """Test chat_stream with timeout parameter."""
        # Mock session creation
        mock_session = MagicMock()
        mock_session.session_id = "session-123"
        mock_session.session_key = "tenant:default:agent:default:session-123"
        mock_session.agent_id = "default"
        client._session_manager.create_session = AsyncMock(return_value=mock_session)

        # Mock agent runner with delayed response
        async def delayed_response(*args, **kwargs):
            await asyncio.sleep(0.01)
            return {
                "status": "executed",
                "session_key": "tenant:default:agent:default:session-123",
                "result": {"response": "Hello!", "agent_id": "default"},
            }

        client._agent_runner.handle_message = AsyncMock(side_effect=delayed_response)

        # Should complete successfully within timeout
        chunks = []
        async for chunk in client.chat_stream("Hello!", timeout=1.0):
            chunks.append(chunk)

        assert len(chunks) > 0
        assert chunks[0].content == "Hello!"


class TestGatewayClientChatStream:
    """Tests for GatewayClient.chat_stream method."""

    @pytest.fixture
    def client(self):
        """Create a GatewayClient with mocked dependencies."""
        client = GatewayClient()
        client._session_manager = MagicMock()
        client._agent_runner = MagicMock()
        return client

    @pytest.mark.asyncio
    async def test_chat_stream(self, client):
        """Test streaming chat response."""
        # Mock session
        mock_session = MagicMock()
        mock_session.session_id = "session-789"
        mock_session.session_key = "tenant:default:agent:default:session-789"
        mock_session.agent_id = "default"
        client._session_manager.create_session = AsyncMock(return_value=mock_session)

        # Mock agent runner - using actual return format from handle_message
        client._agent_runner.handle_message = AsyncMock(
            return_value={
                "status": "executed",
                "session_key": "tenant:default:agent:default:session-789",
                "result": {"response": "Streamed response", "agent_id": "default"},
            }
        )

        chunks = []
        async for chunk in client.chat_stream("Hello!"):
            chunks.append(chunk)

        assert len(chunks) == 1
        assert isinstance(chunks[0], ChatChunk)
        assert chunks[0].content == "Streamed response"
        assert chunks[0].is_last is True


class TestGatewayClientSwitchAgent:
    """Tests for GatewayClient.switch_agent method."""

    @pytest.fixture
    def client(self):
        """Create a GatewayClient with mocked dependencies."""
        client = GatewayClient()
        client._session_manager = MagicMock()
        client._agent_registry = MagicMock()
        return client

    @pytest.mark.asyncio
    async def test_switch_agent_success(self, client):
        """Test successful agent switch."""
        # Mock agent exists
        client._agent_registry.get = MagicMock(return_value=MagicMock())

        # Mock session
        mock_session = MagicMock()
        mock_session.session_id = "session-1"
        mock_session.agent_id = "old_agent"
        client._session_manager.get_session = AsyncMock(return_value=mock_session)

        await client.switch_agent("new_agent", session_id="session-1")

        assert mock_session.agent_id == "new_agent"

    @pytest.mark.asyncio
    async def test_switch_agent_not_found(self, client):
        """Test switch to non-existent agent raises error."""
        client._agent_registry.get = MagicMock(return_value=None)

        with pytest.raises(AgentNotFoundError):
            await client.switch_agent("nonexistent")


class TestGatewayClientResetSession:
    """Tests for GatewayClient.reset_session method."""

    @pytest.fixture
    def client(self):
        """Create a GatewayClient with mocked dependencies."""
        client = GatewayClient()
        client._session_manager = MagicMock()
        return client

    @pytest.mark.asyncio
    async def test_reset_specific_session(self, client):
        """Test resetting a specific session."""
        mock_session = MagicMock()
        mock_session.session_id = "session-1"
        mock_session.session_key = "tenant:default:agent:default:session-1"
        client._session_manager.list_sessions = AsyncMock(return_value=[mock_session])
        client._session_manager.reset_session = AsyncMock()

        await client.reset_session(session_id="session-1")

        client._session_manager.reset_session.assert_called_once_with(
            "tenant:default:agent:default:session-1"
        )

    @pytest.mark.asyncio
    async def test_reset_all_sessions(self, client):
        """Test resetting all sessions for tenant."""
        mock_session1 = MagicMock()
        mock_session1.session_key = "key-1"
        mock_session2 = MagicMock()
        mock_session2.session_key = "key-2"
        client._session_manager.list_sessions = AsyncMock(
            return_value=[mock_session1, mock_session2]
        )
        client._session_manager.reset_session = AsyncMock()

        await client.reset_session()

        assert client._session_manager.reset_session.call_count == 2

    @pytest.mark.asyncio
    async def test_reset_session_not_found(self, client):
        """Test resetting non-existent session raises error."""
        client._session_manager.list_sessions = AsyncMock(return_value=[])

        with pytest.raises(SessionNotFoundError):
            await client.reset_session(session_id="nonexistent")


class TestGatewayClientListAgents:
    """Tests for GatewayClient.list_agents method."""

    @pytest.fixture
    def client(self):
        """Create a GatewayClient with mocked dependencies."""
        client = GatewayClient()
        client._agent_registry = MagicMock()
        return client

    def test_list_agents(self, client):
        """Test listing agents."""
        client._agent_registry.list_agents = MagicMock(
            return_value=[
                {"id": "default", "name": "Default Agent"},
                {"id": "coder", "name": "Coder Agent"},
            ]
        )

        agents = client.list_agents()

        assert len(agents) == 2
        assert agents[0]["id"] == "default"
        assert agents[1]["id"] == "coder"


class TestGatewayClientExecuteCommand:
    """Tests for GatewayClient.execute_command method."""

    @pytest.fixture
    def client(self):
        """Create a GatewayClient with mocked dependencies."""
        client = GatewayClient()
        client._command_router = MagicMock()
        client._agent_registry = MagicMock()
        client._session_manager = MagicMock()
        return client

    @pytest.mark.asyncio
    async def test_execute_model_command(self, client):
        """Test executing /model command."""
        from datacloud_agent.core.router import CommandResult

        client._command_router.parse_command = MagicMock(
            return_value=CommandResult(command="model", args=["coder"], raw="/model coder")
        )
        client._agent_registry.get = MagicMock(return_value=MagicMock())
        client._session_manager.list_sessions = AsyncMock(return_value=[])
        client._session_manager.create_session = AsyncMock(
            return_value=MagicMock(session_id="new-session")
        )

        result = await client.execute_command("/model coder")

        assert result["success"] is True
        assert result["command"] == "model"
        assert result["agent_id"] == "coder"

    @pytest.mark.asyncio
    async def test_execute_reset_command(self, client):
        """Test executing /reset command."""
        from datacloud_agent.core.router import CommandResult

        client._command_router.parse_command = MagicMock(
            return_value=CommandResult(command="reset", args=[], raw="/reset")
        )
        client._session_manager.list_sessions = AsyncMock(return_value=[])

        result = await client.execute_command("/reset")

        assert result["success"] is True
        assert result["command"] == "reset"

    @pytest.mark.asyncio
    async def test_execute_help_command(self, client):
        """Test executing /help command."""
        from datacloud_agent.core.router import CommandResult

        client._command_router.parse_command = MagicMock(
            return_value=CommandResult(command="help", args=[], raw="/help")
        )

        result = await client.execute_command("/help")

        assert result["success"] is True
        assert result["command"] == "help"

    @pytest.mark.asyncio
    async def test_execute_invalid_command(self, client):
        """Test executing invalid command."""
        client._command_router.parse_command = MagicMock(return_value=None)

        result = await client.execute_command("invalid")

        assert result["success"] is False
        assert "error" in result


class TestGatewayClientSessionContext:
    """Tests for session context preservation across multiple chats."""

    @pytest.fixture
    def client(self):
        """Create a GatewayClient with mocked dependencies."""
        client = GatewayClient()
        client._session_manager = MagicMock()
        client._agent_runner = MagicMock()
        client._agent_registry = MagicMock()
        return client

    @pytest.mark.asyncio
    async def test_chat_with_same_session_id_preserves_context(self, client):
        """Test that using the same session_id preserves conversation context.

        This is the key test for the context bug fix. When a user provides
        the same session_id for multiple chat calls, the same session should
        be used, enabling conversation continuity.
        """
        custom_session_id = "user-provided-session-123"

        # First chat - session doesn't exist yet, should create with custom ID
        mock_session_1 = MagicMock()
        mock_session_1.session_id = custom_session_id
        mock_session_1.session_key = f"tenant:default:agent:default:{custom_session_id}"
        mock_session_1.agent_id = "default"

        # Mock: first get_session returns None (not found), then create_session returns mock
        client._session_manager.get_session = AsyncMock(return_value=None)
        client._session_manager.create_session = AsyncMock(return_value=mock_session_1)

        client._agent_runner.handle_message = AsyncMock(
            return_value={
                "status": "executed",
                "session_key": f"tenant:default:agent:default:{custom_session_id}",
                "result": {"response": "Hello! How can I help?", "agent_id": "default"},
            }
        )

        # First chat
        response1 = await client.chat("Hello!", session_id=custom_session_id)
        assert response1.session_id == custom_session_id

        # Verify create_session was called with the custom session_id
        client._session_manager.create_session.assert_called_once()
        call_kwargs = client._session_manager.create_session.call_args.kwargs
        assert call_kwargs.get("session_id") == custom_session_id

        # Second chat - session now exists
        mock_session_2 = MagicMock()
        mock_session_2.session_id = custom_session_id
        mock_session_2.session_key = f"tenant:default:agent:default:{custom_session_id}"
        mock_session_2.agent_id = "default"

        # Reset mocks: now get_session should return the existing session
        client._session_manager.get_session = AsyncMock(return_value=mock_session_2)
        client._session_manager.create_session.reset_mock()

        client._agent_runner.handle_message = AsyncMock(
            return_value={
                "status": "executed",
                "session_key": f"tenant:default:agent:default:{custom_session_id}",
                "result": {"response": "You said Hello!", "agent_id": "default"},
            }
        )

        response2 = await client.chat("What did I say?", session_id=custom_session_id)
        assert response2.session_id == custom_session_id

        # Verify create_session was NOT called this time (session was found)
        client._session_manager.create_session.assert_not_called()

    @pytest.mark.asyncio
    async def test_chat_with_different_session_ids_isolates_context(self, client):
        """Test that different session_ids create isolated sessions."""
        session_id_1 = "session-1"
        session_id_2 = "session-2"

        # First session
        mock_session_1 = MagicMock()
        mock_session_1.session_id = session_id_1
        mock_session_1.session_key = f"tenant:default:agent:default:{session_id_1}"
        mock_session_1.agent_id = "default"

        client._session_manager.get_session = AsyncMock(return_value=None)
        client._session_manager.create_session = AsyncMock(return_value=mock_session_1)
        client._agent_runner.handle_message = AsyncMock(
            return_value={
                "status": "executed",
                "session_key": f"tenant:default:agent:default:{session_id_1}",
                "result": {"response": "Response 1", "agent_id": "default"},
            }
        )

        response1 = await client.chat("Message 1", session_id=session_id_1)
        assert response1.session_id == session_id_1

        # Second session - should create a different session
        mock_session_2 = MagicMock()
        mock_session_2.session_id = session_id_2
        mock_session_2.session_key = f"tenant:default:agent:default:{session_id_2}"
        mock_session_2.agent_id = "default"

        client._session_manager.create_session = AsyncMock(return_value=mock_session_2)
        client._agent_runner.handle_message = AsyncMock(
            return_value={
                "status": "executed",
                "session_key": f"tenant:default:agent:default:{session_id_2}",
                "result": {"response": "Response 2", "agent_id": "default"},
            }
        )

        response2 = await client.chat("Message 2", session_id=session_id_2)
        assert response2.session_id == session_id_2

        # Verify create_session was called with different session_ids
        assert client._session_manager.create_session.call_count == 1
        call_kwargs = client._session_manager.create_session.call_args.kwargs
        assert call_kwargs.get("session_id") == session_id_2

    @pytest.mark.asyncio
    async def test_chat_without_session_id_generates_new_uuid(self, client):
        """Test that chat without session_id generates a new UUID."""
        mock_session = MagicMock()
        mock_session.session_id = "auto-generated-uuid"
        mock_session.session_key = "tenant:default:agent:default:auto-generated-uuid"
        mock_session.agent_id = "default"

        client._session_manager.create_session = AsyncMock(return_value=mock_session)
        client._agent_runner.handle_message = AsyncMock(
            return_value={
                "status": "executed",
                "session_key": "tenant:default:agent:default:auto-generated-uuid",
                "result": {"response": "Hello!", "agent_id": "default"},
            }
        )

        response = await client.chat("Hello!")

        # Verify create_session was called without session_id (None)
        client._session_manager.create_session.assert_called_once()
        call_kwargs = client._session_manager.create_session.call_args.kwargs
        assert call_kwargs.get("session_id") is None


class TestGatewayClientIntegration:
    """Integration tests for GatewayClient."""

    @pytest.mark.asyncio
    async def test_qa_scenario_import(self):
        """QA Scenario: Import GatewayClient and related types."""
        from datacloud_agent import (
            AgentNotFoundError,
            ChatChunk,
            ChatResponse,
            GatewayClient,
            GatewayConnectionError,
            GatewayError,
            GatewayTimeoutError,
            SessionNotFoundError,
        )

        # Just verify imports work
        assert GatewayClient is not None
        assert ChatResponse is not None
        assert ChatChunk is not None
        assert GatewayError is not None
        print("All imports successful!")

    @pytest.mark.asyncio
    async def test_qa_scenario_basic_chat(self):
        """QA Scenario: Basic chat flow."""
        client = GatewayClient()

        # Mock the internal methods
        mock_session = MagicMock()
        mock_session.session_id = "test-session"
        mock_session.session_key = "test-key"
        mock_session.agent_id = "default"

        with patch.object(
            client._session_manager, "create_session", AsyncMock(return_value=mock_session)
        ):
            with patch.object(
                client._agent_runner,
                "handle_message",
                AsyncMock(
                    return_value={
                        "status": "executed",
                        "session_key": "test-key",
                        "result": {"response": "Hello! How can I help?", "agent_id": "default"},
                    }
                ),
            ):
                response = await client.chat("Hello!")

        assert isinstance(response, ChatResponse)
        assert response.content == "Hello! How can I help?"
        print(f"Chat response: {response.content}")
