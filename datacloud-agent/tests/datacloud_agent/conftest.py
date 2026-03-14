"""Pytest fixtures for datacloud-agent tests.

Shared fixtures
---------------
initialized_sdk     Session-scoped: call bootstrap.setup() once for the whole
                    test session (integration tests only).  Requires real env vars.
workspace_paths     Function-scoped: isolated TaskPaths backed by a tmp_path;
                    sets DATACLOUD_WORKSPACE_* env vars automatically.
"""

from __future__ import annotations

import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Legacy fixtures (kept for backward compatibility with existing tests)
# ---------------------------------------------------------------------------
try:
    from datacloud_agent.config.models import GatewayConfig  # old models module
except ImportError:
    GatewayConfig = None  # type: ignore[assignment,misc]


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
            provider="anthropic",
            model="claude-sonnet-4-6",
            system_prompt="You are a helpful assistant.",
            tools=["know", "query", "compute", "render", "store"],
            subagents=[],
        )
        client._agent_registry.register("default", default_config)

        # Register coder agent
        coder_config = AgentConfig(
            agent_id="coder",
            provider="anthropic",
            model="claude-sonnet-4-6",
            system_prompt="You are a coding assistant.",
            tools=["know", "query", "compute"],
            subagents=[],
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


# ---------------------------------------------------------------------------
# New fixtures for the superagent framework
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
async def initialized_sdk():
    """Bootstrap the SDK once for the entire test session.

    Only for integration tests that require a live PostgreSQL database.
    Requires the following env vars to be set:
        DATACLOUD_PG_CHECKPOINT_URI
        DATACLOUD_WORKSPACE_PUBLIC_ROOT
        DATACLOUD_WORKSPACE_PRIVATE_ROOT
    """
    import datacloud_agent.bootstrap as boot  # noqa: PLC0415

    await boot.setup()
    yield
    await boot.teardown()


@pytest.fixture()
def workspace_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Isolated TaskPaths backed by a temporary directory.

    Automatically sets DATACLOUD_WORKSPACE_* env vars so that
    ``build_task_paths`` and ``WorkspaceSettings`` work without real config.

    Returns a factory: ``workspace_paths(user_id, task_id) -> TaskPaths``.
    """
    pub = tmp_path / "public"
    priv = tmp_path / "users"
    pub.mkdir()
    priv.mkdir()
    (pub / "skills").mkdir()

    monkeypatch.setenv("DATACLOUD_WORKSPACE_PUBLIC_ROOT", str(pub))
    monkeypatch.setenv("DATACLOUD_WORKSPACE_PRIVATE_ROOT", str(priv))
    monkeypatch.delenv("DATACLOUD_WORKSPACE_TASKS_ROOT", raising=False)

    from datacloud_agent.workspace.paths import build_task_paths  # noqa: PLC0415

    return build_task_paths
