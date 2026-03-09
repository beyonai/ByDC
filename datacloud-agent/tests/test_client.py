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

        # Mock agent runner
        client._agent_runner.handle_message = AsyncMock(
            return_value={"message": "Hello!", "status": "success"}
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

        # Mock agent runner
        client._agent_runner.handle_message = AsyncMock(
            return_value={"message": "Response!", "status": "success"}
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

        # Mock agent runner
        client._agent_runner.handle_message = AsyncMock(
            return_value={"message": "Code response", "status": "success"}
        )

        response = await client.chat("Write code", agent_id="coder")

        assert response.agent_id == "coder"


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

        # Mock agent runner
        client._agent_runner.handle_message = AsyncMock(
            return_value={"message": "Streamed response", "status": "success"}
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
                AsyncMock(return_value={"message": "Hello! How can I help?", "status": "success"}),
            ):
                response = await client.chat("Hello!")

        assert isinstance(response, ChatResponse)
        assert response.content == "Hello! How can I help?"
        print(f"Chat response: {response.content}")
