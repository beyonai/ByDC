"""Workspace package — file-system path management.

Sub-modules
-----------
paths    Build per-task ``TaskPaths`` from env vars + runtime IDs.
mount    Mount inputs/temp/outputs into a backend.
runtime  Runtime workspace helpers.

Note: skills_loader has been removed. Skill discovery is now handled by
SkillsMiddleware (Deep Agents SDK) reading SKILL.md files from skills/builtin/.
"""

from .paths import TaskPaths, build_task_paths

__all__ = ["TaskPaths", "build_task_paths"]
