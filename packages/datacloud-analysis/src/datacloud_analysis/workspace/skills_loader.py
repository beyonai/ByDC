"""Skill scanning and registration (design 搂鍥?/ skills loading).

Skill types and priority (lower 鈫?higher, higher overrides lower)
-----------------------------------------------------------------
1. Built-in  : shipped with the SDK package  (``skills/builtin/``)
2. Enterprise: uploaded by admin to ``PUBLIC_ROOT/skills/``
3. User      : uploaded by user or written by ``build_skill`` tool
               into ``PRIVATE_ROOT/{user_id}/workspaces/skills/``

Loading order: built-in 鈫?enterprise 鈫?user.
Same-name skills: later (higher-priority) overrides earlier.

Skill file convention
---------------------
Each skill is a ``.py`` file that must define:
- ``SKILL_META`` dict with at least ``name`` (str) and ``description`` (str).
- ``run(...)`` callable as the unified entry point.

Example::

    SKILL_META = {
        "name": "group_agg",
        "description": "Group-by aggregation helper.",
        "version": "1.0.0",
    }

    def run(df, group_by, agg_col, method="sum"):
        return df.groupby(group_by)[agg_col].agg(method).reset_index()
"""

from __future__ import annotations

import importlib.util
import logging
import os
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from datacloud_analysis.workspace.paths import TaskPaths

logger = logging.getLogger(__name__)

# Built-in skills shipped with the SDK.
_BUILTIN_SKILLS_DIR = Path(__file__).parent.parent / "skills" / "builtin"


def _find_repo_root() -> Path | None:
    current = Path(__file__).resolve()
    for parent in current.parents:
        marker = parent / "examples" / "e_commerce_demo" / "backend" / "datacloud_service" / "plugins"
        if marker.exists():
            return parent
    return None


def _extension_skill_dirs() -> list[Path]:
    dirs: list[Path] = []
    env_raw = os.getenv("DATACLOUD_SKILL_PLUGIN_DIRS", "").strip()
    if env_raw:
        dirs.extend(Path(item.strip()) for item in env_raw.split(os.pathsep) if item.strip())

    repo_root = _find_repo_root()
    if repo_root is not None:
        dirs.append(
            repo_root
            / "examples"
            / "e_commerce_demo"
            / "backend"
            / "datacloud_service"
            / "plugins"
            / "skill_plugins"
        )
    return dirs


class SkillLoader:
    """Scan skill directories and build a registry of callable skills.

    Args:
        task_paths: The resolved paths for the current task (provides
                    ``skills_public`` and ``skills_private`` directories).
    """

    def __init__(self, task_paths: TaskPaths) -> None:
        self._dirs: list[Path] = [_BUILTIN_SKILLS_DIR]
        self._dirs.extend(_extension_skill_dirs())
        self._dirs.extend([task_paths.skills_public, task_paths.skills_private])
        self._registry: dict[str, dict[str, Any]] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load_all(self) -> dict[str, dict[str, Any]]:
        """Scan all skill directories and return the merged registry.

        Returns:
            ``{skill_name: {"meta": SKILL_META_dict, "run": Callable}}``
        """
        for directory in self._dirs:
            if not directory.exists():
                logger.debug("Skills directory not found, skipping: %s", directory)
                continue
            for skill_file in sorted(directory.glob("*.py")):
                self._load_file(skill_file)

        logger.info("SkillLoader: loaded %d skills.", len(self._registry))
        return self._registry

    def get(self, name: str) -> Callable[..., Any] | None:
        """Return the ``run`` callable for a named skill, or ``None``."""
        entry = self._registry.get(name)
        return entry["run"] if entry else None

    def skill_descriptions(self) -> list[dict[str, str]]:
        """Return a compact list of ``{name, description}`` for prompt injection."""
        return [
            {"name": v["meta"]["name"], "description": v["meta"].get("description", "")}
            for v in self._registry.values()
        ]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_file(self, path: Path) -> None:
        """Dynamically import a skill file and register it."""
        try:
            spec = importlib.util.spec_from_file_location(path.stem, path)
            if spec is None or spec.loader is None:
                return
            module = importlib.util.module_from_spec(spec)
            loader = spec.loader
            loader.exec_module(module)

            meta: dict[str, Any] | None = getattr(module, "SKILL_META", None)
            run_fn: Callable[..., Any] | None = getattr(module, "run", None)

            if meta is None or run_fn is None:
                logger.debug("Skipping %s: missing SKILL_META or run()", path.name)
                return

            name: str = meta.get("name", path.stem)
            self._registry[name] = {"meta": meta, "run": run_fn}
            logger.debug("Registered skill: %s (from %s)", name, path)

        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to load skill file %s: %s", path, exc)


