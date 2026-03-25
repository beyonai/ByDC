"""Unit tests for workspace.skills_loader."""

from __future__ import annotations

from pathlib import Path

import pytest

from datacloud_analysis.workspace.paths import TaskPaths
from datacloud_analysis.workspace.skills_loader import SkillLoader


def _make_task_paths(tmp_path: Path) -> TaskPaths:
    pub_skills = tmp_path / "pub" / "skills"
    priv_skills = tmp_path / "priv" / "skills"
    pub_skills.mkdir(parents=True)
    priv_skills.mkdir(parents=True)
    return TaskPaths(
        inputs=tmp_path / "inputs",
        temp=tmp_path / "temp",
        outputs=tmp_path / "outputs",
        skills_public=pub_skills,
        skills_private=priv_skills,
    )


def _write_skill(directory: Path, name: str, description: str = "test skill") -> Path:
    skill_file = directory / f"{name}.py"
    skill_file.write_text(
        f'SKILL_META = {{"name": "{name}", "description": "{description}"}}\n'
        f"def run(*args, **kwargs):\n    return 'result'\n",
        encoding="utf-8",
    )
    return skill_file


def test_load_builtin_skills(tmp_path: Path) -> None:
    paths = _make_task_paths(tmp_path)
    loader = SkillLoader(paths)
    registry = loader.load_all()
    # At least the shipped builtin skills should be present.
    assert "group_agg" in registry
    assert "time_series" in registry


def test_user_skill_overrides_builtin(tmp_path: Path) -> None:
    paths = _make_task_paths(tmp_path)
    _write_skill(paths.skills_private, "group_agg", "custom override")
    loader = SkillLoader(paths)
    registry = loader.load_all()
    assert registry["group_agg"]["meta"]["description"] == "custom override"


def test_skill_callable(tmp_path: Path) -> None:
    paths = _make_task_paths(tmp_path)
    _write_skill(paths.skills_public, "my_skill")
    loader = SkillLoader(paths)
    loader.load_all()
    fn = loader.get("my_skill")
    assert callable(fn)
    assert fn() == "result"


def test_skill_descriptions(tmp_path: Path) -> None:
    paths = _make_task_paths(tmp_path)
    _write_skill(paths.skills_public, "skill_a", "desc A")
    loader = SkillLoader(paths)
    loader.load_all()
    descs = loader.skill_descriptions()
    names = [d["name"] for d in descs]
    assert "skill_a" in names
