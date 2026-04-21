"""Workspace package - file-system path management and runtime helpers.

Sub-modules
-----------
paths          Resolve task-scoped workspace directories.
runtime        Resolve shared workspace visibility rules.
"""

from .paths import TaskPaths, build_task_paths

__all__ = ["TaskPaths", "build_task_paths"]
