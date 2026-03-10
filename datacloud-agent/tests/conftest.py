"""Pytest fixtures for datacloud-agent tests."""

import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from datacloud_agent.config.models import GatewayConfig


@pytest.fixture
def temp_tenant_id():
    """Generate a temporary tenant ID for test isolation."""
    return f"test-tenant-{uuid.uuid4().hex[:8]}"


@pytest.fixture
def mock_agent_runner():
    """Create a mocked AgentRunner with controlled responses."""
    mock = AsyncMock()
    mock.handle_message = AsyncMock(
        return_value={"message": "Mocked response", "status": "success"}
    )
    return mock


@pytest.fixture
def mock_session_manager():
    """Create a mocked SessionManager."""
    mock = AsyncMock()
    mock.create_session = AsyncMock()
    mock.get_session = AsyncMock()
    mock.list_sessions = AsyncMock(return_value=[])
    mock.reset_session = AsyncMock()
    return mock


@pytest.fixture
def mock_agent_registry():
    """Create a mocked AgentRegistry."""
    mock = MagicMock()
    mock.get = MagicMock(return_value=MagicMock())
    mock.list_agents = MagicMock(
        return_value=[
            {"id": "default", "name": "Default Agent"},
            {"id": "coder", "name": "Coder Agent"},
        ]
    )
    mock.create_agent = MagicMock(return_value={"agent_id": "default", "name": "Default Agent"})
    return mock


@pytest.fixture
def mock_command_router():
    """Create a mocked CommandRouter."""
    mock = MagicMock()
    mock.parse_command = MagicMock()
    return mock


@pytest.fixture
def gateway_client(
    mock_agent_runner, mock_session_manager, mock_agent_registry, mock_command_router
):
    """Create a GatewayClient with mocked dependencies."""
    with (
        patch("datacloud_agent.api.client.AgentRunner", return_value=mock_agent_runner),
        patch("datacloud_agent.api.client.SessionManager", return_value=mock_session_manager),
        patch("datacloud_agent.api.client.AgentRegistry", return_value=mock_agent_registry),
        patch("datacloud_agent.api.client.CommandRouter", return_value=mock_command_router),
    ):
        from datacloud_agent.api.client import GatewayClient

        client = GatewayClient()
        # Ensure internal components are our mocks
        client._agent_runner = mock_agent_runner
        client._session_manager = mock_session_manager
        client._agent_registry = mock_agent_registry
        client._command_router = mock_command_router
        return client


@pytest.fixture
def gateway_client_integration():
    """Create a GatewayClient with real components but mocked LLM dependencies."""
    import sys

    # Create mock modules for deepagents to avoid import errors
    mock_deepagents_module = MagicMock()
    mock_deepagents_module.create_deep_agent = MagicMock()
    mock_deepagents_module.backends = MagicMock()
    mock_deepagents_module.backends.FilesystemBackend = MagicMock()
    sys.modules["deepagents"] = mock_deepagents_module
    sys.modules["deepagents.backends"] = mock_deepagents_module.backends

    # Mock langchain if not present (but it's likely installed)
    try:
        import langchain
    except ImportError:
        mock_langchain_module = MagicMock()
        mock_langchain_module.chat_models = MagicMock()
        mock_langchain_module.chat_models.init_chat_model = MagicMock()
        sys.modules["langchain"] = mock_langchain_module
        sys.modules["langchain.chat_models"] = mock_langchain_module.chat_models

    # Now patch the specific functions
    with (
        patch("deepagents.create_deep_agent") as mock_deepagents,
        patch("deepagents.backends.FilesystemBackend") as mock_fs_backend,
        patch("langchain.chat_models.init_chat_model") as mock_langchain,
    ):
        mock_deepagents.return_value = MagicMock()
        mock_fs_backend.return_value = MagicMock()
        mock_langchain.return_value = MagicMock()

        from datacloud_agent.api.client import GatewayClient
        from datacloud_agent.core.registry import AgentConfig

        client = GatewayClient()

        # Register default agent
        default_config = AgentConfig(
            agent_id="default",
            name="Default Agent",
            description="General purpose agent",
            model="claude-sonnet-4-6",
            provider="anthropic",
            system_prompt="You are a helpful assistant.",
            tools=["know", "query", "compute", "render", "store"],
        )
        client._agent_registry.register("default", default_config)

        # Register coder agent
        coder_config = AgentConfig(
            agent_id="coder",
            name="Coder Agent",
            description="Specialized in coding tasks",
            model="claude-sonnet-4-6",
            provider="anthropic",
            system_prompt="You are a coding assistant.",
            tools=["know", "query", "compute"],
        )
        client._agent_registry.register("coder", coder_config)

        # Mock agent creation to return a mock agent dict
        client._agent_registry.create_agent = MagicMock(
            return_value={
                "agent_id": "default",
                "name": "Default Agent",
                "model": "claude-sonnet-4-6",
                "provider": "anthropic",
                "system_prompt": "You are a helpful assistant.",
                "tools": ["know", "query", "compute", "render", "store"],
            }
        )

        yield client

    # Clean up mock modules
    sys.modules.pop("deepagents", None)
    sys.modules.pop("deepagents.backends", None)
    # Only remove langchain if we added it
    if "langchain" not in sys.modules:
        sys.modules.pop("langchain", None)
        sys.modules.pop("langchain.chat_models", None)
