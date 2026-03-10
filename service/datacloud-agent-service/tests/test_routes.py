"""Tests for HTTP API routes (T17)."""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from deps import get_gateway_client
from server import app


@pytest.fixture
def client():
    """Test client fixture."""
    return TestClient(app)


@pytest.fixture
def mock_gateway_client():
    """Mock GatewayClient using dependency override."""
    mock_instance = MagicMock()
    # Configure async method to return awaitable
    mock_instance.chat = AsyncMock()
    # Note: chat_stream is configured in each test since it needs specific async iterator

    original_dependency = app.dependency_overrides.get(get_gateway_client)
    app.dependency_overrides[get_gateway_client] = lambda: mock_instance
    yield mock_instance
    # Restore original dependency
    if original_dependency is not None:
        app.dependency_overrides[get_gateway_client] = original_dependency
    else:
        app.dependency_overrides.pop(get_gateway_client, None)


class TestChatRoutes:
    """Tests for chat completion routes."""

    def test_chat_completion_non_streaming(self, client, mock_gateway_client):
        """Test POST /v1/chat/completions (non-streaming)."""
        # Mock the chat response
        mock_gateway_client.chat.return_value = AsyncMock(
            content="Hello, world!",
            session_id="session-123",
            agent_id="default",
            metadata={},
        )

        request_data = {
            "messages": [{"role": "user", "content": "Hello"}],
            "model": "default",
            "session_id": "session-123",
            "stream": False,
        }
        response = client.post("/v1/chat/completions", json=request_data)
        assert response.status_code == 200
        data = response.json()
        assert data["object"] == "chat.completion"
        assert len(data["choices"]) == 1
        assert data["choices"][0]["message"]["content"] == "Hello, world!"
        assert data["choices"][0]["finish_reason"] == "stop"
        assert data["model"] == "default"
        # Verify the mock was called correctly
        mock_gateway_client.chat.assert_called_once_with(
            message="Hello",
            session_id="session-123",
            agent_id="default",
            stream=False,
        )

    def test_chat_completion_streaming(self, client, mock_gateway_client):
        """Test POST /v1/chat/completions (streaming)."""
        calls = []

        async def mock_chat_stream(*args, **kwargs):
            calls.append((args, kwargs))
            mock_chunk = MagicMock()
            mock_chunk.content = "Hello, world!"
            mock_chunk.is_last = True
            yield mock_chunk

        # Replace chat_stream with our async generator
        mock_gateway_client.chat_stream = mock_chat_stream

        request_data = {
            "messages": [{"role": "user", "content": "Hello"}],
            "model": "default",
            "session_id": "session-123",
            "stream": True,
        }
        response = client.post("/v1/chat/completions", json=request_data)
        assert response.status_code == 200
        assert response.headers["content-type"] == "text/event-stream; charset=utf-8"
        # Parse SSE events
        lines = response.text.strip().split("\n")
        # Expect at least one data line
        data_lines = [line for line in lines if line.startswith("data: ")]
        assert len(data_lines) > 0
        # Check that the last line is [DONE] or contains the chunk
        last_data = data_lines[-1]
        if last_data != "data: [DONE]":
            chunk_data = json.loads(last_data[6:])  # remove "data: "
            assert chunk_data["object"] == "chat.completion.chunk"
            assert chunk_data["choices"][0]["delta"]["content"] == "Hello, world!"
        # Verify the mock was called correctly
        assert len(calls) == 1
        _, kwargs = calls[0]
        assert kwargs["message"] == "Hello"
        assert kwargs["session_id"] == "session-123"
        assert kwargs["agent_id"] == "default"

    def test_chat_completion_no_user_message(self, client):
        """Test POST /v1/chat/completions with no user message."""
        request_data = {
            "messages": [{"role": "assistant", "content": "Hi"}],
            "stream": False,
        }
        response = client.post("/v1/chat/completions", json=request_data)
        assert response.status_code == 400
        assert "At least one user or system message is required" in response.text


class TestSessionRoutes:
    """Tests for session management routes."""

    def test_create_session(self, client, mock_gateway_client):
        """Test POST /v1/sessions."""
        from datetime import datetime

        # Mock the session manager
        mock_session = MagicMock()
        mock_session.session_id = "session-456"
        mock_session.session_key = "tenant:default:agent:default:session-456"
        mock_session.tenant_id = "default"
        mock_session.agent_id = "default"
        mock_session.created_at = datetime.now()
        mock_session.updated_at = datetime.now()
        mock_session.metadata = {}

        # Set up mock structure - async methods need awaitables
        mock_gateway_client._session_manager = AsyncMock()
        mock_gateway_client._session_manager.create_session = AsyncMock(return_value=mock_session)
        mock_gateway_client._tenant_ctx = MagicMock()
        mock_gateway_client.tenant_id = "default"

        request_data = {"agent_id": "default", "metadata": {"foo": "bar"}}
        response = client.post("/v1/sessions", json=request_data)
        assert response.status_code == 200
        data = response.json()
        assert data["session_id"] == "session-456"
        assert data["agent_id"] == "default"
        # Verify the mock was called
        mock_gateway_client._session_manager.create_session.assert_called_once()

    def test_get_session(self, client, mock_gateway_client):
        """Test GET /v1/sessions/{session_id}."""
        from datetime import datetime

        # Mock list_sessions
        mock_session = MagicMock()
        mock_session.session_id = "session-456"
        mock_session.session_key = "tenant:default:agent:default:session-456"
        mock_session.tenant_id = "default"
        mock_session.agent_id = "default"
        mock_session.created_at = datetime.now()
        mock_session.updated_at = datetime.now()
        mock_session.metadata = {}

        # Set up mock structure - async methods need awaitables
        mock_gateway_client._session_manager = AsyncMock()
        mock_gateway_client._session_manager.list_sessions = AsyncMock(return_value=[mock_session])
        mock_gateway_client.tenant_id = "default"

        response = client.get("/v1/sessions/session-456")
        assert response.status_code == 200
        data = response.json()
        assert data["session_id"] == "session-456"

    def test_get_session_not_found(self, client, mock_gateway_client):
        """Test GET /v1/sessions/{session_id} when session does not exist."""
        mock_gateway_client._session_manager = AsyncMock()
        mock_gateway_client._session_manager.list_sessions = AsyncMock(return_value=[])
        mock_gateway_client.tenant_id = "default"

        response = client.get("/v1/sessions/nonexistent")
        assert response.status_code == 404
        assert "Session not found" in response.text

    def test_delete_session(self, client, mock_gateway_client):
        """Test DELETE /v1/sessions/{session_id}."""
        from datetime import datetime

        # Mock list_sessions to return a session
        mock_session = MagicMock()
        mock_session.session_id = "session-456"
        mock_session.session_key = "tenant:default:agent:default:session-456"
        mock_session.tenant_id = "default"
        mock_session.agent_id = "default"
        mock_session.created_at = datetime.now()
        mock_session.updated_at = datetime.now()
        mock_session.metadata = {}

        # Set up mock structure - async methods need awaitables
        mock_gateway_client._session_manager = AsyncMock()
        mock_gateway_client._session_manager.list_sessions = AsyncMock(return_value=[mock_session])
        mock_gateway_client._session_manager.delete_session = AsyncMock(return_value=None)
        mock_gateway_client.tenant_id = "default"

        response = client.delete("/v1/sessions/session-456")
        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Session deleted successfully"
        # Verify delete was called
        mock_gateway_client._session_manager.delete_session.assert_called_once_with(
            mock_session.session_key
        )

    def test_list_sessions(self, client, mock_gateway_client):
        """Test GET /v1/sessions."""
        from datetime import datetime

        mock_session = MagicMock()
        mock_session.session_id = "session-456"
        mock_session.session_key = "tenant:default:agent:default:session-456"
        mock_session.tenant_id = "default"
        mock_session.agent_id = "default"
        mock_session.created_at = datetime.now()
        mock_session.updated_at = datetime.now()
        mock_session.metadata = {}
        # Set up mock structure - async methods need awaitables
        mock_gateway_client._session_manager = AsyncMock()
        mock_gateway_client._session_manager.list_sessions = AsyncMock(return_value=[mock_session])
        mock_gateway_client.tenant_id = "default"

        response = client.get("/v1/sessions")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert len(data["sessions"]) == 1
        assert data["sessions"][0]["session_id"] == "session-456"


class TestAgentRoutes:
    """Tests for agent management routes."""

    def test_list_agents(self, client, mock_gateway_client):
        """Test GET /v1/agents."""
        mock_agents = [
            {
                "agent_id": "default",
                "name": "Default Agent",
                "description": "General purpose agent",
                "model": "claude-sonnet-4-6",
                "provider": "anthropic",
                "system_prompt": "You are helpful.",
                "tools": ["know", "query"],
                "metadata": {},
            }
        ]
        # list_agents is a synchronous method, so we need to mock it as a regular method
        mock_gateway_client.list_agents = MagicMock(return_value=mock_agents)

        response = client.get("/v1/agents")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert len(data["agents"]) == 1
        assert data["agents"][0]["agent_id"] == "default"
        assert data["agents"][0]["name"] == "Default Agent"

    def test_get_agent(self, client, mock_gateway_client):
        """Test GET /v1/agents/{agent_id}."""
        mock_agents = [
            {
                "agent_id": "default",
                "name": "Default Agent",
                "description": "General purpose agent",
                "model": "claude-sonnet-4-6",
                "provider": "anthropic",
                "system_prompt": "You are helpful.",
                "tools": ["know", "query"],
                "metadata": {},
            }
        ]
        mock_gateway_client.list_agents = MagicMock(return_value=mock_agents)

        response = client.get("/v1/agents/default")
        assert response.status_code == 200
        data = response.json()
        assert data["agent_id"] == "default"
        assert data["name"] == "Default Agent"

    def test_get_agent_not_found(self, client, mock_gateway_client):
        """Test GET /v1/agents/{agent_id} when agent does not exist."""
        mock_gateway_client.list_agents = MagicMock(return_value=[])

        response = client.get("/v1/agents/nonexistent")
        assert response.status_code == 404
        assert "Agent not found" in response.text
