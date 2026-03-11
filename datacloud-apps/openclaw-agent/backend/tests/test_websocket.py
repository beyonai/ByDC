"""Tests for WebSocket endpoint.

Tests the WebSocket connection and OpenClaw protocol handler integration.
"""

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
    """Mock GatewayClient for testing."""
    mock = AsyncMock()
    mock._agent_registry = MagicMock()
    mock._agent_registry.get = MagicMock(return_value=None)
    mock._agent_registry.register = MagicMock()
    return mock


class TestWebSocketConnection:
    """Test WebSocket connection establishment."""

    def test_websocket_connection_established(self, client):
        """Test that WebSocket connection can be established."""
        with client.websocket_connect("/ws") as websocket:
            # Connection should be established without errors
            assert websocket is not None

    def test_websocket_accepts_valid_frame(self, client):
        """Test that valid protocol frames are accepted."""
        with client.websocket_connect("/ws") as websocket:
            # Send a valid request frame
            frame = {"type": "req", "id": "test-123", "method": "health", "params": {}}
            websocket.send_json(frame)

            # Should receive a response
            response = websocket.receive_json()
            assert response["type"] == "res"
            assert response["id"] == "test-123"
            assert response["ok"] is True
            assert response["payload"]["status"] == "healthy"


class TestWebSocketErrorHandling:
    """Test error handling in WebSocket."""

    def test_invalid_json(self, client):
        """Test handling of invalid JSON."""
        with client.websocket_connect("/ws") as websocket:
            websocket.send_text("invalid json")

            response = websocket.receive_json()
            assert response["type"] == "res"
            assert response["ok"] is False
            assert "Invalid JSON" in response["error"]

    def test_unknown_method(self, client):
        """Test handling of unknown method."""
        with client.websocket_connect("/ws") as websocket:
            frame = {"type": "req", "id": "test-unknown", "method": "unknown.method", "params": {}}
            websocket.send_json(frame)

            response = websocket.receive_json()
            assert response["type"] == "res"
            assert response["ok"] is False
            assert "Unknown method" in response["error"]


class TestWebSocketTenantId:
    """Test tenant ID extraction from WebSocket connection."""

    def test_tenant_id_from_query(self, client):
        """Test tenant ID extraction from query parameters."""
        with patch("websocket.get_websocket_gateway_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_get_client.return_value = mock_client

            with client.websocket_connect("/ws?tenant_id=test-tenant") as websocket:
                # Send health check to trigger client creation
                frame = {"type": "req", "id": "test", "method": "health", "params": {}}
                websocket.send_json(frame)
                websocket.receive_json()

                # Verify get_websocket_gateway_client called with tenant_id
                mock_get_client.assert_called_once()
                args = mock_get_client.call_args[0]
                assert len(args) >= 2
                assert args[1] == "test-tenant"


class TestWebSocketProtocolMethods:
    """Test OpenClaw protocol methods via WebSocket."""

    def test_health_method(self, client):
        """Test health check via WebSocket."""
        with client.websocket_connect("/ws") as websocket:
            frame = {"type": "req", "id": "health-check", "method": "health", "params": {}}
            websocket.send_json(frame)

            response = websocket.receive_json()
            assert response["type"] == "res"
            assert response["ok"] is True
            assert response["payload"]["status"] == "healthy"
            assert "service" in response["payload"]

    def test_sessions_list_method(self, client):
        """Test sessions.list method."""
        with client.websocket_connect("/ws") as websocket:
            frame = {
                "type": "req",
                "id": "sessions-list",
                "method": "sessions.list",
                "params": {},
            }
            websocket.send_json(frame)

            response = websocket.receive_json()
            assert response["type"] == "res"
            assert response["ok"] is True
            assert response["payload"] == []

    def test_sessions_create_method(self, client):
        """Test sessions.create method."""
        with client.websocket_connect("/ws") as websocket:
            frame = {
                "type": "req",
                "id": "session-create",
                "method": "sessions.create",
                "params": {"title": "Test Session"},
            }
            websocket.send_json(frame)

            response = websocket.receive_json()
            assert response["type"] == "res"
            assert response["ok"] is True
            assert "id" in response["payload"]
            assert response["payload"]["title"] == "Test Session"
            assert "createdAt" in response["payload"]
            assert "updatedAt" in response["payload"]

    def test_chat_history_method(self, client):
        """Test chat.history method."""
        with client.websocket_connect("/ws") as websocket:
            frame = {
                "type": "req",
                "id": "chat-history",
                "method": "chat.history",
                "params": {"sessionId": "test-session"},
            }
            websocket.send_json(frame)

            response = websocket.receive_json()
            assert response["type"] == "res"
            assert response["ok"] is True
            assert response["payload"] == []

    def test_chat_send_mock_mode(self, client):
        """Test chat.send in mock mode (no API key)."""
        with patch("openclaw_protocol._HAS_API_KEY", False):
            with client.websocket_connect("/ws") as websocket:
                # Create session first
                session_frame = {
                    "type": "req",
                    "id": "create-session",
                    "method": "sessions.create",
                    "params": {},
                }
                websocket.send_json(session_frame)
                session_response = websocket.receive_json()
                session_id = session_response["payload"]["id"]

                # Send chat message
                chat_frame = {
                    "type": "req",
                    "id": "chat-send",
                    "method": "chat.send",
                    "params": {"sessionId": session_id, "message": "Hello!"},
                }
                websocket.send_json(chat_frame)

                # Should receive immediate response confirming streaming started
                response = websocket.receive_json()
                assert response["type"] == "res"
                assert response["ok"] is True
                assert response["payload"]["status"] == "streaming"
                assert "sessionId" in response["payload"]

    def test_chat_send_missing_message(self, client):
        """Test chat.send with missing message returns error."""
        with client.websocket_connect("/ws") as websocket:
            frame = {
                "type": "req",
                "id": "chat-error",
                "method": "chat.send",
                "params": {"sessionId": "test-session"},
            }
            websocket.send_json(frame)

            response = websocket.receive_json()
            assert response["type"] == "res"
            assert response["ok"] is False
            assert "Message is required" in response["error"]


class TestWebSocketFullWorkflow:
    """Integration tests for complete WebSocket workflows."""

    def test_complete_chat_workflow(self, client):
        """Test complete workflow: connect -> create session -> send message."""
        with patch("openclaw_protocol._HAS_API_KEY", False):
            with client.websocket_connect("/ws") as websocket:
                # Step 1: Create a session
                session_frame = {
                    "type": "req",
                    "id": "workflow-session",
                    "method": "sessions.create",
                    "params": {"title": "Integration Test"},
                }
                websocket.send_json(session_frame)
                session_response = websocket.receive_json()

                assert session_response["ok"] is True
                session_id = session_response["payload"]["id"]
                assert session_response["payload"]["title"] == "Integration Test"

                # Step 2: Send a message
                chat_frame = {
                    "type": "req",
                    "id": "workflow-chat",
                    "method": "chat.send",
                    "params": {"sessionId": session_id, "message": "What can you do?"},
                }
                websocket.send_json(chat_frame)

                # Step 3: Verify streaming started
                response = websocket.receive_json()
                assert response["ok"] is True
                assert response["payload"]["status"] == "streaming"
                assert "sessionId" in response["payload"]

    def test_multiple_sessions(self, client):
        """Test creating multiple sessions."""
        with client.websocket_connect("/ws") as websocket:
            session_ids = []

            for i in range(3):
                frame = {
                    "type": "req",
                    "id": f"multi-session-{i}",
                    "method": "sessions.create",
                    "params": {"title": f"Session {i}"},
                }
                websocket.send_json(frame)
                response = websocket.receive_json()

                assert response["ok"] is True
                session_ids.append(response["payload"]["id"])

            # Verify all sessions have unique IDs
            assert len(set(session_ids)) == 3
