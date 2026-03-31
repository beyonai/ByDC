"""Pytest fixtures for datacloud-analysis tests.

Shared fixtures
---------------
initialized_sdk     Session-scoped: call bootstrap.setup() once for the whole
                    test session (integration tests only).  Requires real env vars.
workspace_paths     Function-scoped: isolated TaskPaths backed by a tmp_path;
                    sets DATACLOUD_WORKSPACE_* env vars automatically.
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

import pytest


def _ensure_backend_demo_import_path() -> None:
    repo_root = Path(__file__).resolve().parents[4]
    backend_root = repo_root / "examples" / "e_commerce_demo" / "backend"
    backend_root_str = str(backend_root)
    if backend_root.exists() and backend_root_str not in sys.path:
        sys.path.insert(0, backend_root_str)


_ensure_backend_demo_import_path()


@pytest.fixture
def temp_tenant_id() -> str:
    """Generate a temporary tenant ID for test isolation."""
    return f"test-tenant-{uuid.uuid4().hex[:8]}"


@pytest.fixture(scope="session")
async def initialized_sdk() -> None:
    """Bootstrap the SDK once for the entire test session.

    Only for integration tests that require a live PostgreSQL database.
    Requires the following env vars to be set:
        DATACLOUD_PG_CHECKPOINT_URI
        DATACLOUD_WORKSPACE_PUBLIC_ROOT
        DATACLOUD_WORKSPACE_PRIVATE_ROOT
    """
    import datacloud_analysis.bootstrap as boot  # noqa: PLC0415

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

    from datacloud_analysis.workspace.paths import build_task_paths  # noqa: PLC0415

    return build_task_paths
