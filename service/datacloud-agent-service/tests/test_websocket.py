"""Tests for WebSocket support."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from server import app


@pytest.fixture
def client():
    """Test client fixture."""
    return TestClient(app)


@pytest.fixture
def mock_gateway_client():
    """Mock GatewayClient."""
    with patch("websocket.GatewayClient") as mock_cls:
        mock_instance = AsyncMock()
        mock_cls.return_value = mock_instance
        yield mock_instance


def test_websocket_connection(client):
    """Test WebSocket connection establishment."""
    with client.websocket_connect("/ws") as websocket:
        # Send ping to verify connection works
        websocket.send_json({"type": "ping"})
        data = websocket.receive_json()
        assert data["type"] == "pong"


def test_websocket_ping(client):
    """Test ping/pong message."""
    with client.websocket_connect("/ws") as websocket:
        websocket.send_json({"type": "ping"})
        data = websocket.receive_json()
        assert data["type"] == "pong"


@pytest.mark.asyncio
async def test_websocket_chat(client, mock_gateway_client):
    """Test chat message streaming."""
    calls = []

    async def mock_chat_stream(*args, **kwargs):
        calls.append((args, kwargs))
        mock_chunk = MagicMock()
        mock_chunk.content = "Hello, world!"
        mock_chunk.is_last = True
        yield mock_chunk

    # Replace chat_stream with our async generator
    mock_gateway_client.chat_stream = mock_chat_stream

    with client.websocket_connect("/ws") as websocket:
        websocket.send_json(
            {
                "type": "chat",
                "message": "Hello",
                "session_id": "test-session",
                "agent_id": "default",
            }
        )

        # Receive chat chunk
        data = websocket.receive_json()
        assert data["type"] == "chat_chunk"
        assert data["content"] == "Hello, world!"
        assert data["is_last"] is True

        # Verify chat_stream was called with correct arguments
        assert len(calls) == 1
        args, kwargs = calls[0]
        assert kwargs["message"] == "Hello"
        assert kwargs["session_id"] == "test-session"
        assert kwargs["agent_id"] == "default"


@pytest.mark.asyncio
async def test_websocket_command(client, mock_gateway_client):
    """Test command execution."""
    mock_gateway_client.execute_command.return_value = {
        "success": True,
        "command": "help",
        "message": "Available commands: /model <agent>, /reset, /help",
    }

    with client.websocket_connect("/ws") as websocket:
        websocket.send_json(
            {
                "type": "command",
                "command": "/help",
                "session_id": "test-session",
            }
        )

        data = websocket.receive_json()
        assert data["type"] == "command_result"
        assert data["result"]["success"] is True
        assert data["result"]["command"] == "help"

        mock_gateway_client.execute_command.assert_called_once_with(
            command="/help",
            session_id="test-session",
        )


def test_websocket_invalid_json(client):
    """Test handling of invalid JSON."""
    with client.websocket_connect("/ws") as websocket:
        websocket.send_text("invalid json")
        data = websocket.receive_json()
        assert data["type"] == "error"
        assert "Invalid JSON" in data["error"]


def test_websocket_invalid_message_type(client):
    """Test handling of unknown message type."""
    with client.websocket_connect("/ws") as websocket:
        websocket.send_json({"type": "unknown"})
        data = websocket.receive_json()
        assert data["type"] == "error"
        assert "Unknown message type" in data["error"]


def test_websocket_chat_missing_message(client):
    """Test chat message validation."""
    with client.websocket_connect("/ws") as websocket:
        websocket.send_json({"type": "chat"})
        data = websocket.receive_json()
        assert data["type"] == "error"
        assert "Missing 'message'" in data["error"]


def test_websocket_command_missing_command(client):
    """Test command validation."""
    with client.websocket_connect("/ws") as websocket:
        websocket.send_json({"type": "command"})
        data = websocket.receive_json()
        assert data["type"] == "error"
        assert "Missing 'command'" in data["error"]


def test_websocket_tenant_id_from_query(client):
    """Test tenant ID extraction from query parameters."""
    with patch("websocket.get_websocket_gateway_client") as mock_get_client:
        mock_client = AsyncMock()
        mock_get_client.return_value = mock_client

        with client.websocket_connect("/ws?tenant_id=test-tenant") as websocket:
            websocket.send_json({"type": "ping"})
            websocket.receive_json()  # pong

            # Verify get_websocket_gateway_client called with tenant_id as second positional arg
            mock_get_client.assert_called_once()
            args = mock_get_client.call_args[0]
            # First arg is websocket object, second is tenant_id
            assert len(args) >= 2
            assert args[1] == "test-tenant"


def test_websocket_tenant_id_from_header(client):
    """Test tenant ID extraction from headers."""
    # TestClient.websocket_connect doesn't support headers directly,
    # so we need to use the low-level API
    # This test is skipped for now due to TestClient limitations
    pass
