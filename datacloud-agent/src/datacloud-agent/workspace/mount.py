"""Sandbox directory mounting (design §4.2.1.2 running view).

Responsibilities
----------------
1. Ensure all writable directories exist before the sandbox starts.
2. Provide helpers to copy/link task inputs into the sandbox ``inputs/`` dir.
3. Collect ``outputs/`` contents after the Agent finishes.

The module operates on a ``TaskPaths`` object and delegates actual Docker
operations to the sandbox backend (``deepagents`` LocalDockerBackend /
RemoteDockerBackend) so it never touches env vars itself.

Running view (flattened inside the sandbox container)
------------------------------------------------------
/workspace/
├── inputs/        ← mounted from task_paths.inputs   (read-write)
├── temp/          ← mounted from task_paths.temp      (read-write)
├── outputs/       ← mounted from task_paths.outputs   (read-write)
└── skills/        ← merged read-only view of public + private skills
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datacloud_agent.workspace.paths import TaskPaths


class SandboxMounter:
    """Prepares directories before sandbox execution and collects results after.

    Args:
        task_paths: The resolved paths for the current task.
    """

    def __init__(self, task_paths: "TaskPaths") -> None:
        self._paths = task_paths

    def prepare(self) -> None:
        """Create all writable directories and ensure skills dirs exist."""
        self._paths.ensure_dirs()

    def stage_input_file(self, source: Path, filename: str | None = None) -> Path:
        """Copy an external file into the task ``inputs/`` directory.

        Args:
            source:   Path to the source file (e.g. a downloaded attachment).
            filename: Target filename inside inputs/; defaults to source.name.

        Returns:
            The destination path inside inputs/.
        """
        dest = self._paths.inputs / (filename or source.name)
        shutil.copy2(source, dest)
        return dest

    def collect_outputs(self) -> list[Path]:
        """Return all files currently inside the task ``outputs/`` directory."""
        return list(self._paths.outputs.iterdir()) if self._paths.outputs.exists() else []

    def cleanup_temp(self) -> None:
        """Remove the temp scratch directory (called after task completion)."""
        if self._paths.temp.exists():
            shutil.rmtree(self._paths.temp, ignore_errors=True)
