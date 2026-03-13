"""Unit tests for workspace.paths — no real filesystem required."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from datacloud_agent.workspace.paths import TaskPaths, build_task_paths


@pytest.fixture()
def workspace_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    pub = tmp_path / "public"
    priv = tmp_path / "users"
    pub.mkdir()
    priv.mkdir()
    monkeypatch.setenv("DATACLOUD_WORKSPACE_PUBLIC_ROOT", str(pub))
    monkeypatch.setenv("DATACLOUD_WORKSPACE_PRIVATE_ROOT", str(priv))
    monkeypatch.delenv("DATACLOUD_WORKSPACE_TASKS_ROOT", raising=False)
    return {"public": pub, "private": priv}


def test_build_task_paths_returns_task_paths(workspace_env: dict[str, Path]) -> None:
    paths = build_task_paths("user-1", "task-abc")
    assert isinstance(paths, TaskPaths)


def test_inputs_under_task_dir(workspace_env: dict[str, Path]) -> None:
    paths = build_task_paths("user-1", "task-abc")
    assert "task_task-abc" in str(paths.inputs)
    assert str(paths.inputs).endswith("inputs")


def test_skills_public_under_public_root(workspace_env: dict[str, Path]) -> None:
    paths = build_task_paths("user-1", "task-abc")
    assert str(paths.skills_public).startswith(str(workspace_env["public"]))


def test_skills_private_under_private_root(workspace_env: dict[str, Path]) -> None:
    paths = build_task_paths("user-1", "task-abc")
    assert str(paths.skills_private).startswith(str(workspace_env["private"]))


def test_ensure_dirs_creates_directories(workspace_env: dict[str, Path]) -> None:
    paths = build_task_paths("user-1", "task-abc")
    paths.ensure_dirs()
    assert paths.inputs.exists()
    assert paths.temp.exists()
    assert paths.outputs.exists()


def test_custom_tasks_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pub = tmp_path / "pub"
    priv = tmp_path / "priv"
    tasks = tmp_path / "tasks"
    pub.mkdir()
    priv.mkdir()
    tasks.mkdir()
    monkeypatch.setenv("DATACLOUD_WORKSPACE_PUBLIC_ROOT", str(pub))
    monkeypatch.setenv("DATACLOUD_WORKSPACE_PRIVATE_ROOT", str(priv))
    monkeypatch.setenv("DATACLOUD_WORKSPACE_TASKS_ROOT", str(tasks))
    paths = build_task_paths("u2", "t2")
    assert str(paths.inputs).startswith(str(tasks))
