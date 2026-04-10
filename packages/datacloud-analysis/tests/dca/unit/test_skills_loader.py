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


def test_extension_skill_dir_overrides_builtin(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = _make_task_paths(tmp_path)
    ext_dir = tmp_path / "ext_skill_plugins"
    ext_dir.mkdir(parents=True, exist_ok=True)
    _write_skill(ext_dir, "group_agg", "ext override")
    monkeypatch.setenv("DATACLOUD_SKILL_PLUGIN_DIRS", str(ext_dir))

    loader = SkillLoader(paths)
    registry = loader.load_all()
    assert registry["group_agg"]["meta"]["description"] == "ext override"


def test_skill_load_order_extension_public_private(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = _make_task_paths(tmp_path)
    ext_dir = tmp_path / "ext_skill_plugins"
    ext_dir.mkdir(parents=True, exist_ok=True)
    _write_skill(ext_dir, "group_agg", "from extension")
    _write_skill(paths.skills_public, "group_agg", "from public")
    _write_skill(paths.skills_private, "group_agg", "from private")
    monkeypatch.setenv("DATACLOUD_SKILL_PLUGIN_DIRS", str(ext_dir))

    loader = SkillLoader(paths)
    registry = loader.load_all()
    assert registry["group_agg"]["meta"]["description"] == "from private"
    assert registry["group_agg"]["source"] == "private"


def test_skill_override_audit_log_emitted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    paths = _make_task_paths(tmp_path)
    ext_dir = tmp_path / "ext_skill_plugins"
    ext_dir.mkdir(parents=True, exist_ok=True)
    _write_skill(ext_dir, "group_agg", "from extension")
    _write_skill(paths.skills_public, "group_agg", "from public")
    monkeypatch.setenv("DATACLOUD_SKILL_PLUGIN_DIRS", str(ext_dir))
    caplog.set_level("INFO")

    loader = SkillLoader(paths)
    loader.load_all()

    messages = [record.getMessage() for record in caplog.records]
    assert any("Skill override: name=group_agg old_source=builtin new_source=extension" in m for m in messages)
    assert any("Skill override: name=group_agg old_source=extension new_source=public" in m for m in messages)
    assert any("SkillLoader scan summary:" in m for m in messages)


def test_skill_meta_defaults_are_normalized(tmp_path: Path) -> None:
    paths = _make_task_paths(tmp_path)
    _write_skill(paths.skills_public, "meta_defaults", "meta defaults")
    loader = SkillLoader(paths)
    registry = loader.load_all()
    meta = registry["meta_defaults"]["meta"]
    assert meta["risk_level"] == "medium"
    assert meta["allowlist_tags"] == []
    assert meta["blocklist_tags"] == []


def test_skill_meta_risk_and_tags_are_normalized(tmp_path: Path) -> None:
    paths = _make_task_paths(tmp_path)
    skill_file = paths.skills_public / "meta_normalize.py"
    skill_file.write_text(
        "SKILL_META = {\n"
        '    "name": "meta_normalize",\n'
        '    "description": "normalize",\n'
        '    "risk_level": "HIGH",\n'
        '    "allowlist_tags": ["tenant_a", "tenant_a", " "],\n'
        '    "blocklist_tags": "scene_x",\n'
        "}\n"
        "def run(*args, **kwargs):\n    return 'ok'\n",
        encoding="utf-8",
    )
    loader = SkillLoader(paths)
    registry = loader.load_all()
    meta = registry["meta_normalize"]["meta"]
    assert meta["risk_level"] == "high"
    assert meta["allowlist_tags"] == ["tenant_a"]
    assert meta["blocklist_tags"] == ["scene_x"]
