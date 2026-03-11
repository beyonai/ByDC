"""Tests for OpenClaw protocol handler.

Tests the WebSocket protocol handler that enables communication between
datacloud-agent-service and OpenClaw UI.
"""

import asyncio
import json
import os
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


@pytest.fixture
def mock_chat_response():
    """Mock chat response."""
    response = MagicMock()
    response.content = "Hello! I am DataCloud Agent. How can I help you?"
    return response


class TestOpenClawProtocolConnection:
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


class TestOpenClawProtocolSessions:
    """Test session management endpoints."""

    def test_sessions_list(self, client):
        """Test listing sessions returns empty list."""
        with client.websocket_connect("/ws") as websocket:
            frame = {
                "type": "req",
                "id": "test-sessions-list",
                "method": "sessions.list",
                "params": {},
            }
            websocket.send_json(frame)

            response = websocket.receive_json()
            assert response["type"] == "res"
            assert response["ok"] is True
            assert response["payload"] == []

    def test_sessions_create(self, client):
        """Test creating a new session."""
        with client.websocket_connect("/ws") as websocket:
            frame = {
                "type": "req",
                "id": "test-session-create",
                "method": "sessions.create",
                "params": {"title": "Test Chat"},
            }
            websocket.send_json(frame)

            response = websocket.receive_json()
            assert response["type"] == "res"
            assert response["ok"] is True
            assert "id" in response["payload"]
            assert response["payload"]["title"] == "Test Chat"
            assert "createdAt" in response["payload"]
            assert "updatedAt" in response["payload"]

    def test_sessions_create_without_title(self, client):
        """Test creating a session without title uses default."""
        with client.websocket_connect("/ws") as websocket:
            frame = {
                "type": "req",
                "id": "test-session-create-no-title",
                "method": "sessions.create",
                "params": {},
            }
            websocket.send_json(frame)

            response = websocket.receive_json()
            assert response["type"] == "res"
            assert response["ok"] is True
            assert response["payload"]["title"] == "New Chat"


class TestOpenClawProtocolChat:
    """Test chat functionality with OpenClaw UI."""

    def test_chat_send_mock_mode(self, client):
        """Test sending a chat message in mock mode (no API key).

        Note: This test verifies the immediate response. The streaming chunks
        are sent asynchronously and may not be received in the test environment.
        """
        with patch("openclaw_protocol._HAS_API_KEY", False):
            with client.websocket_connect("/ws") as websocket:
                # First create a session
                session_frame = {
                    "type": "req",
                    "id": "test-session",
                    "method": "sessions.create",
                    "params": {},
                }
                websocket.send_json(session_frame)
                session_response = websocket.receive_json()
                session_id = session_response["payload"]["id"]

                # Send chat message
                chat_frame = {
                    "type": "req",
                    "id": "test-chat",
                    "method": "chat.send",
                    "params": {"sessionId": session_id, "message": "Hello, who are you?"},
                }
                websocket.send_json(chat_frame)

                # Should receive immediate response confirming streaming started
                response = websocket.receive_json()
                assert response["type"] == "res"
                assert response["ok"] is True
                assert response["payload"]["status"] == "streaming"
                assert "sessionId" in response["payload"]

    @pytest.mark.asyncio
    async def test_chat_send_with_real_api(self, client, mock_gateway_client):
        """Test sending a chat message with real API."""
        # Mock the chat response
        mock_response = MagicMock()
        mock_response.content = "I am DataCloud Agent, here to help you with data analysis."
        mock_gateway_client.chat = AsyncMock(return_value=mock_response)

        with patch("openclaw_protocol._HAS_API_KEY", True):
            with patch("openclaw_protocol.GatewayClient") as mock_client_cls:
                mock_client_cls.return_value = mock_gateway_client

                with client.websocket_connect("/ws") as websocket:
                    # Create session and send chat
                    session_frame = {
                        "type": "req",
                        "id": "test-session",
                        "method": "sessions.create",
                        "params": {},
                    }
                    websocket.send_json(session_frame)
                    session_response = websocket.receive_json()
                    session_id = session_response["payload"]["id"]

                    chat_frame = {
                        "type": "req",
                        "id": "test-chat",
                        "method": "chat.send",
                        "params": {"sessionId": session_id, "message": "Hello"},
                    }
                    websocket.send_json(chat_frame)

                    # Receive response
                    response = websocket.receive_json()
                    assert response["type"] == "res"
                    assert response["ok"] is True

    def test_chat_send_missing_message(self, client):
        """Test chat.send with missing message field returns error."""
        with client.websocket_connect("/ws") as websocket:
            frame = {
                "type": "req",
                "id": "test-chat-error",
                "method": "chat.send",
                "params": {"sessionId": "test-session"},
            }
            websocket.send_json(frame)

            response = websocket.receive_json()
            assert response["type"] == "res"
            assert response["ok"] is False
            assert "Message is required" in response["error"]

    def test_chat_history(self, client):
        """Test getting chat history returns empty list."""
        with client.websocket_connect("/ws") as websocket:
            frame = {
                "type": "req",
                "id": "test-history",
                "method": "chat.history",
                "params": {"sessionId": "test-session-123"},
            }
            websocket.send_json(frame)

            response = websocket.receive_json()
            assert response["type"] == "res"
            assert response["ok"] is True
            assert response["payload"] == []


class TestOpenClawProtocolErrorHandling:
    """Test error handling in protocol handler."""

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

    def test_missing_frame_type(self, client):
        """Test handling of frame without type field."""
        with client.websocket_connect("/ws") as websocket:
            frame = {"id": "test-no-type", "method": "health", "params": {}}
            websocket.send_json(frame)

            # Should not crash, but may not respond
            # The handler returns early for non-req types


class TestOpenClawProtocolIntegration:
    """Integration tests simulating OpenClaw UI workflow."""

    def test_full_chat_workflow_mock(self, client):
        """Test complete chat workflow: connect -> create session -> send message.

        Note: This test verifies the protocol handshake. Streaming chunks are sent
        asynchronously via background tasks and may not be received in test environment.
        """
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
                assert "title" in session_response["payload"]
                assert session_response["payload"]["title"] == "Integration Test"

                # Step 2: Send a message
                message = "What can you do?"
                chat_frame = {
                    "type": "req",
                    "id": "workflow-chat",
                    "method": "chat.send",
                    "params": {"sessionId": session_id, "message": message},
                }
                websocket.send_json(chat_frame)

                # Step 3: Verify streaming started (immediate response)
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

    def test_health_check(self, client):
        """Test health check endpoint via WebSocket."""
        with client.websocket_connect("/ws") as websocket:
            frame = {"type": "req", "id": "health-check", "method": "health", "params": {}}
            websocket.send_json(frame)

            response = websocket.receive_json()
            assert response["type"] == "res"
            assert response["ok"] is True
            assert response["payload"]["status"] == "healthy"
            assert response["payload"]["service"] == "datacloud-agent-service"
