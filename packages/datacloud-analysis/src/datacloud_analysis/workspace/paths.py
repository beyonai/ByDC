"""Workspace path construction helpers."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class TaskPaths:
    """Filesystem paths for one execution task."""

    inputs: Path
    temp: Path
    outputs: Path
    skills_public: Path
    skills_private: Path

    def ensure_dirs(self) -> None:
        for directory in (self.inputs, self.temp, self.outputs):
            directory.mkdir(parents=True, exist_ok=True)


def build_task_paths(*, user_id: str, task_id: str) -> TaskPaths:
    """Build default task paths from workspace env vars."""
    public_root = Path(
        os.getenv("DATACLOUD_WORKSPACE_PUBLIC_ROOT", str(Path.cwd() / "workspace" / "public"))
    ).resolve()
    private_root = Path(
        os.getenv("DATACLOUD_WORKSPACE_PRIVATE_ROOT", str(Path.cwd() / "workspace" / "private"))
    ).resolve()
    tasks_root_raw = os.getenv("DATACLOUD_WORKSPACE_TASKS_ROOT", "").strip()

    if tasks_root_raw:
        task_base = Path(tasks_root_raw).resolve() / user_id / f"task_{task_id}"
    else:
        task_base = private_root / user_id / "workspaces" / "tasks" / f"task_{task_id}"

    return TaskPaths(
        inputs=task_base / "inputs",
        temp=task_base / "temp",
        outputs=task_base / "outputs",
        skills_public=public_root / "skills",
        skills_private=private_root / user_id / "workspaces" / "skills",
    )


__all__ = ["TaskPaths", "build_task_paths"]

