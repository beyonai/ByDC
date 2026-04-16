"""Unit tests for workspace.skills_loader."""

from __future__ import annotations

from pathlib import Path

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
