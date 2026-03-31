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
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, TypedDict, cast

if TYPE_CHECKING:
    from datacloud_analysis.workspace.paths import TaskPaths

logger = logging.getLogger(__name__)

# Built-in skills shipped with the SDK.
_BUILTIN_SKILLS_DIR = Path(__file__).parent.parent / "skills" / "builtin"
_DEFAULT_SKILL_RISK_LEVEL: Literal["low", "medium", "high"] = "medium"
_VALID_SKILL_RISK_LEVELS: frozenset[str] = frozenset({"low", "medium", "high"})


class SkillMeta(TypedDict, total=False):
    """Normalized metadata contract for all loaded skills."""

    name: str
    description: str
    version: str
    author: str
    risk_level: Literal["low", "medium", "high"]
    allowlist_tags: list[str]
    blocklist_tags: list[str]


def _normalize_skill_tags(raw: Any) -> list[str]:
    if isinstance(raw, str):
        text = raw.strip()
        return [text] if text else []
    if not isinstance(raw, list):
        return []
    tags: list[str] = []
    seen: set[str] = set()
    for item in raw:
        text = str(item).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        tags.append(text)
    return tags


def _normalize_risk_level(raw: Any) -> Literal["low", "medium", "high"]:
    text = str(raw or "").strip().lower()
    if text in _VALID_SKILL_RISK_LEVELS:
        return cast(Literal["low", "medium", "high"], text)
    return _DEFAULT_SKILL_RISK_LEVEL


def _normalize_skill_meta(raw: dict[str, Any], *, default_name: str) -> SkillMeta:
    name = str(raw.get("name") or default_name).strip() or default_name
    description = str(raw.get("description") or "").strip()
    normalized: SkillMeta = {"name": name, "description": description}
    if "version" in raw:
        normalized["version"] = str(raw.get("version") or "").strip()
    if "author" in raw:
        normalized["author"] = str(raw.get("author") or "").strip()
    normalized["risk_level"] = _normalize_risk_level(raw.get("risk_level"))
    normalized["allowlist_tags"] = _normalize_skill_tags(raw.get("allowlist_tags"))
    normalized["blocklist_tags"] = _normalize_skill_tags(raw.get("blocklist_tags"))
    return normalized


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


@dataclass(frozen=True)
class SkillScanLayer:
    """One scan layer in the skill loading chain."""

    source: str
    path: Path


class SkillLoader:
    """Scan skill directories and build a registry of callable skills.

    Args:
        task_paths: The resolved paths for the current task (provides
                    ``skills_public`` and ``skills_private`` directories).
    """

    def __init__(self, task_paths: TaskPaths) -> None:
        self._layers: list[SkillScanLayer] = [SkillScanLayer(source="builtin", path=_BUILTIN_SKILLS_DIR)]
        self._layers.extend(
            SkillScanLayer(source="extension", path=path) for path in _extension_skill_dirs()
        )
        self._layers.extend(
            [
                SkillScanLayer(source="public", path=task_paths.skills_public),
                SkillScanLayer(source="private", path=task_paths.skills_private),
            ]
        )
        self._registry: dict[str, dict[str, Any]] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load_all(self) -> dict[str, dict[str, Any]]:
        """Scan all skill directories and return the merged registry.

        Returns:
            ``{skill_name: {"meta": SKILL_META_dict, "run": Callable}}``
        """
        loaded_by_source: dict[str, int] = {"builtin": 0, "extension": 0, "public": 0, "private": 0}
        for layer in self._layers:
            directory = layer.path
            if not directory.exists():
                logger.debug(
                    "Skills directory not found, skipping: source=%s path=%s",
                    layer.source,
                    directory,
                )
                continue
            for skill_file in sorted(directory.glob("*.py")):
                if self._load_file(skill_file, source=layer.source):
                    loaded_by_source[layer.source] = loaded_by_source.get(layer.source, 0) + 1

        logger.info(
            "SkillLoader scan summary: total=%d by_source=%s scan_order=%s",
            len(self._registry),
            loaded_by_source,
            [layer.source for layer in self._layers],
        )
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

    def _load_file(self, path: Path, *, source: str) -> bool:
        """Dynamically import a skill file and register it."""
        try:
            spec = importlib.util.spec_from_file_location(path.stem, path)
            if spec is None or spec.loader is None:
                return False
            module = importlib.util.module_from_spec(spec)
            loader = spec.loader
            loader.exec_module(module)

            raw_meta: dict[str, Any] | None = getattr(module, "SKILL_META", None)
            run_fn: Callable[..., Any] | None = getattr(module, "run", None)

            if raw_meta is None or run_fn is None:
                logger.debug("Skipping %s: missing SKILL_META or run()", path.name)
                return False

            meta = _normalize_skill_meta(raw_meta, default_name=path.stem)
            name: str = meta["name"]
            previous_entry = self._registry.get(name)
            self._registry[name] = {"meta": meta, "run": run_fn, "source": source, "path": path}
            if previous_entry is not None:
                logger.info(
                    "Skill override: name=%s old_source=%s new_source=%s old_path=%s new_path=%s",
                    name,
                    previous_entry.get("source", "unknown"),
                    source,
                    previous_entry.get("path", "unknown"),
                    path,
                )
            else:
                logger.debug(
                    "Registered skill: name=%s source=%s path=%s",
                    name,
                    source,
                    path,
                )
            return True

        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to load skill file %s: %s", path, exc)
            return False


