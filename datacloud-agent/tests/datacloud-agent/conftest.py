"""Package-level fixtures for tests/datacloud-agent/.

All fixtures here are available to unit/, integration/, and e2e/ sub-directories.
Only put fixtures here that are genuinely shared across test types.
Type-specific fixtures belong in the conftest.py of their own subdirectory.
"""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture()
def workspace_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Isolated TaskPaths backed by a temporary directory.

    Sets DATACLOUD_WORKSPACE_* env vars so that ``build_task_paths`` and
    ``WorkspaceSettings`` work without a real filesystem layout.

    Returns the ``build_task_paths`` factory; call it with ``(user_id, task_id)``.
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
