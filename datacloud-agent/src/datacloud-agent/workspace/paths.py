"""Per-task workspace path construction (design §三 / §4.2).

This is the **only** module allowed to read ``DATACLOUD_WORKSPACE_*`` env vars.
All other modules receive a ``TaskPaths`` dataclass and must not touch env vars.

Storage layout (from design §4.2.1.1 / §4.2.2.1)
-------------------------------------------------
{TASKS_ROOT}/{user_id}/task_{task_id}/
    inputs/    ← read-write: materials pushed by gateway
    temp/      ← read-write: model-generated scratch files
    outputs/   ← read-write: deliverables collected by gateway

Skills (read-only mounts in running view §4.2.1.2)
--------------------------------------------------
{PUBLIC_ROOT}/skills/                             ← enterprise public skills
{PRIVATE_ROOT}/{user_id}/workspaces/skills/       ← user private + build_skill output
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from datacloud_agent.config.env import WorkspaceSettings


@dataclass(frozen=True)
class TaskPaths:
    """All filesystem paths relevant to one Agent task execution.

    ``inputs``, ``temp``, ``outputs`` are read-write sandboxed directories.
    ``skills_public`` and ``skills_private`` are read-only skill library mounts.
    """

    inputs: Path
    temp: Path
    outputs: Path
    skills_public: Path
    skills_private: Path

    def ensure_dirs(self) -> None:
        """Create all writable directories if they do not exist yet."""
        for directory in (self.inputs, self.temp, self.outputs):
            directory.mkdir(parents=True, exist_ok=True)


def build_task_paths(user_id: str, task_id: str) -> TaskPaths:
    """Construct the ``TaskPaths`` for a specific user+task.

    Args:
        user_id:  The user who owns this task (injected at runtime by gateway).
        task_id:  The unique task identifier (injected at runtime by gateway).

    Returns:
        A frozen ``TaskPaths`` with all paths fully resolved.

    Note:
        ``WorkspaceSettings`` is instantiated here (reads env vars).  If env
        vars are missing a ``pydantic.ValidationError`` is raised immediately,
        satisfying the fail-fast requirement.
    """
    ws = WorkspaceSettings()

    # Task sandbox root: use dedicated TASKS_ROOT if configured, else derive
    # from PRIVATE_ROOT so operators don't need an extra env var.
    if ws.tasks_root is not None:
        task_base = ws.tasks_root / user_id / f"task_{task_id}"
    else:
        task_base = ws.private_root / user_id / "workspaces" / "tasks" / f"task_{task_id}"

    return TaskPaths(
        inputs=task_base / "inputs",
        temp=task_base / "temp",
        outputs=task_base / "outputs",
        # Skills dirs: resolved from public & private roots — operators control
        # where they live; code never hardcodes a path.
        skills_public=ws.public_root / "skills",
        skills_private=ws.private_root / user_id / "workspaces" / "skills",
    )
