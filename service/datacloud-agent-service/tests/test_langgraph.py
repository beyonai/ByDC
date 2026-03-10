"""Tests for LangGraph compatibility routes."""

import uuid
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
def mock_gateway_client(client):
    """Mock GatewayClient using dependency override."""
    mock_instance = AsyncMock()
    original_dependency = app.dependency_overrides.get(get_gateway_client)
    app.dependency_overrides[get_gateway_client] = lambda: mock_instance
    yield mock_instance
    # Restore original dependency
    if original_dependency is not None:
        app.dependency_overrides[get_gateway_client] = original_dependency
    else:
        app.dependency_overrides.pop(get_gateway_client, None)


def test_health_check(client):
    """Test GET /ok returns {"status": "ok"}."""
    response = client.get("/ok")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_thread(client):
    """Test POST /threads creates a thread and returns thread_id."""
    response = client.post("/threads", json={})
    assert response.status_code == 200
    data = response.json()
    assert "thread_id" in data
    assert isinstance(data["thread_id"], str)
    # Should be a UUID
    try:
        uuid.UUID(data["thread_id"])
    except ValueError:
        pytest.fail("thread_id is not a valid UUID")


def test_create_thread_with_metadata(client):
    """Test POST /threads with metadata."""
    metadata = {"foo": "bar"}
    response = client.post("/threads", json={"metadata": metadata})
    assert response.status_code == 200
    data = response.json()
    assert data["metadata"] == metadata


@pytest.mark.asyncio
async def test_create_run(client, mock_gateway_client):
    """Test POST /threads/{id}/runs creates a run."""
    # Mock the chat response
    mock_response = MagicMock()
    mock_response.content = "Hello, assistant!"
    mock_response.metadata = {"status": "executed"}
    mock_gateway_client.chat.return_value = mock_response

    thread_id = str(uuid.uuid4())
    request_data = {"input": "Hello, world!", "stream": False}
    response = client.post(f"/threads/{thread_id}/runs", json=request_data)
    assert response.status_code == 200
    data = response.json()
    assert "run_id" in data
    assert data["thread_id"] == thread_id
    assert data["output"] == "Hello, assistant!"
    assert data["metadata"] == {"status": "executed"}

    # Verify chat was called with correct arguments
    mock_gateway_client.chat.assert_called_once_with(
        message="Hello, world!",
        session_id=thread_id,
        agent_id=None,
        stream=False,
    )


@pytest.mark.asyncio
async def test_create_run_with_agent_id(client, mock_gateway_client):
    """Test POST /threads/{id}/runs with agent_id."""
    mock_response = MagicMock()
    mock_response.content = "Response"
    mock_response.metadata = {}
    mock_gateway_client.chat.return_value = mock_response

    thread_id = str(uuid.uuid4())
    request_data = {"input": "Hello", "agent_id": "coder"}
    response = client.post(f"/threads/{thread_id}/runs", json=request_data)
    assert response.status_code == 200
    mock_gateway_client.chat.assert_called_once_with(
        message="Hello",
        session_id=thread_id,
        agent_id="coder",
        stream=False,
    )


@pytest.mark.asyncio
async def test_create_run_stream_true(client, mock_gateway_client):
    """Test POST /threads/{id}/runs with stream=True."""
    mock_response = MagicMock()
    mock_response.content = "Streamed response"
    mock_response.metadata = {}
    mock_gateway_client.chat.return_value = mock_response

    thread_id = str(uuid.uuid4())
    request_data = {"input": "Hello", "stream": True}
    response = client.post(f"/threads/{thread_id}/runs", json=request_data)
    assert response.status_code == 200
    mock_gateway_client.chat.assert_called_once_with(
        message="Hello",
        session_id=thread_id,
        agent_id=None,
        stream=True,
    )


@pytest.mark.asyncio
async def test_create_run_chat_exception(client, mock_gateway_client):
    """Test POST /threads/{id}/runs when chat raises an exception."""
    mock_gateway_client.chat.side_effect = Exception("Something went wrong")
    thread_id = str(uuid.uuid4())
    response = client.post(f"/threads/{thread_id}/runs", json={"input": "Hello"})
    assert response.status_code == 500
    assert "Something went wrong" in response.json()["detail"]


def test_get_thread_history(client):
    """Test GET /threads/{id}/history returns empty messages for now."""
    thread_id = str(uuid.uuid4())
    response = client.get(f"/threads/{thread_id}/history")
    assert response.status_code == 200
    data = response.json()
    assert data["thread_id"] == thread_id
    assert data["messages"] == []


# Additional integration test: full flow
def test_langgraph_full_flow(client, mock_gateway_client):
    """Test a full LangGraph flow: create thread, create run, get history."""
    # 1. Create thread
    create_resp = client.post("/threads", json={})
    assert create_resp.status_code == 200
    thread_id = create_resp.json()["thread_id"]

    # 2. Create run (mock chat)
    mock_response = MagicMock()
    mock_response.content = "Mocked response"
    mock_response.metadata = {}
    mock_gateway_client.chat.return_value = mock_response

    run_resp = client.post(f"/threads/{thread_id}/runs", json={"input": "Hello"})
    assert run_resp.status_code == 200
    run_data = run_resp.json()
    assert run_data["thread_id"] == thread_id
    assert run_data["output"] == "Mocked response"

    # 3. Get history (currently empty)
    history_resp = client.get(f"/threads/{thread_id}/history")
    assert history_resp.status_code == 200
    history_data = history_resp.json()
    assert history_data["thread_id"] == thread_id
    assert history_data["messages"] == []
