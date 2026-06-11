"""datacloud_analysis.skills.catalog 模块单元测试（红阶段）。

覆盖：
  scan_skill_catalog    - 双目录扫描、rel_skills 过滤、TTL 缓存
  parse_skill_frontmatter
  build_available_skills_xml
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from datacloud_analysis.skills.catalog import (
    _SKILL_CATALOG_CACHE,
    _SKILL_CATALOG_TTL,
    build_available_skills_xml,
    parse_skill_frontmatter,
    scan_skill_catalog,
)


# ─────────────────────────────────────────────────────────────────────────────
# 辅助
# ─────────────────────────────────────────────────────────────────────────────


def _write_skill(root: Path, name: str, description: str = "描述文本") -> Path:
    d = root / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {description}\n---\n# body",
        encoding="utf-8",
    )
    return d


# ─────────────────────────────────────────────────────────────────────────────
# parse_skill_frontmatter
# ─────────────────────────────────────────────────────────────────────────────


class TestParseSkillFrontmatter:
    def test_inline_description(self, tmp_path: Path) -> None:
        _write_skill(tmp_path, "老鹰", "战略全局分析")
        result = parse_skill_frontmatter(tmp_path / "老鹰")
        assert result is not None
        assert result["name"] == "老鹰"
        assert "战略全局分析" in result["description"]
        assert "SKILL.md" in result["location"]

    def test_multiline_description(self, tmp_path: Path) -> None:
        d = tmp_path / "skill-x"
        d.mkdir()
        (d / "SKILL.md").write_text(
            "---\nname: skill-x\ndescription: |\n  第一行\n  第二行\n---\nbody",
            encoding="utf-8",
        )
        result = parse_skill_frontmatter(d)
        assert result is not None
        assert "第一行" in result["description"]

    def test_missing_description_returns_none(self, tmp_path: Path) -> None:
        d = tmp_path / "no-desc"
        d.mkdir()
        (d / "SKILL.md").write_text("---\nname: no-desc\n---\nbody", encoding="utf-8")
        assert parse_skill_frontmatter(d) is None

    def test_missing_name_returns_none(self, tmp_path: Path) -> None:
        d = tmp_path / "no-name"
        d.mkdir()
        (d / "SKILL.md").write_text(
            "---\ndescription: some desc\n---\nbody", encoding="utf-8"
        )
        assert parse_skill_frontmatter(d) is None

    def test_no_frontmatter_returns_none(self, tmp_path: Path) -> None:
        d = tmp_path / "bare"
        d.mkdir()
        (d / "SKILL.md").write_text("# just markdown", encoding="utf-8")
        assert parse_skill_frontmatter(d) is None

    def test_missing_skill_md_returns_none(self, tmp_path: Path) -> None:
        d = tmp_path / "empty-dir"
        d.mkdir()
        assert parse_skill_frontmatter(d) is None


# ─────────────────────────────────────────────────────────────────────────────
# build_available_skills_xml
# ─────────────────────────────────────────────────────────────────────────────


class TestBuildAvailableSkillsXml:
    def test_empty_returns_empty_string(self) -> None:
        assert build_available_skills_xml([]) == ""

    def test_single_skill_xml_structure(self) -> None:
        skills = [{"name": "老鹰", "description": "战略分析", "location": "/s/SKILL.md"}]
        xml = build_available_skills_xml(skills)
        assert "<available_skills>" in xml
        assert "<name>老鹰</name>" in xml
        assert "<description>战略分析</description>" in xml
        assert "</available_skills>" in xml

    def test_multiple_skills_count(self) -> None:
        skills = [
            {"name": "老鹰", "description": "战略", "location": "/a/SKILL.md"},
            {"name": "猎手", "description": "漏斗", "location": "/b/SKILL.md"},
        ]
        xml = build_available_skills_xml(skills)
        assert xml.count("<skill>") == 2


# ─────────────────────────────────────────────────────────────────────────────
# scan_skill_catalog — 新签名：接收显式目录列表
# ─────────────────────────────────────────────────────────────────────────────


class TestScanSkillCatalog:
    def test_single_dir_returns_skills(self, tmp_path: Path) -> None:
        _write_skill(tmp_path, "skill-A")
        _write_skill(tmp_path, "skill-B")

        _SKILL_CATALOG_CACHE.clear()
        result = scan_skill_catalog([tmp_path], rel_skills=set())

        names = [s["name"] for s in result]
        assert "skill-A" in names
        assert "skill-B" in names

    def test_rel_skills_whitelist(self, tmp_path: Path) -> None:
        _write_skill(tmp_path, "skill-A")
        _write_skill(tmp_path, "skill-B")
        _write_skill(tmp_path, "skill-C")

        _SKILL_CATALOG_CACHE.clear()
        result = scan_skill_catalog([tmp_path], rel_skills={"skill-A"})

        names = [s["name"] for s in result]
        assert names == ["skill-A"]

    def test_later_dir_overrides_earlier_same_name(self, tmp_path: Path) -> None:
        dir1 = tmp_path / "d1"
        dir2 = tmp_path / "d2"
        _write_skill(dir1, "老鹰", description="agent版本")
        _write_skill(dir2, "老鹰", description="personal版本")

        _SKILL_CATALOG_CACHE.clear()
        result = scan_skill_catalog([dir1, dir2], rel_skills=set())

        entries = {s["name"]: s for s in result}
        assert "老鹰" in entries
        assert "personal版本" in entries["老鹰"]["description"]

    def test_missing_dir_safe_skip(self, tmp_path: Path) -> None:
        nonexistent = tmp_path / "no_such_dir"
        _SKILL_CATALOG_CACHE.clear()
        result = scan_skill_catalog([nonexistent], rel_skills=set())
        assert result == []

    def test_invalid_skill_md_skipped(self, tmp_path: Path) -> None:
        broken = tmp_path / "broken"
        broken.mkdir()
        (broken / "SKILL.md").write_text("---\nname: broken\n---\nbody", encoding="utf-8")
        _write_skill(tmp_path, "skill-ok")

        _SKILL_CATALOG_CACHE.clear()
        result = scan_skill_catalog([tmp_path], rel_skills=set())
        names = [s["name"] for s in result]
        assert "skill-ok" in names
        assert "broken" not in names

    def test_cache_hit_within_ttl(self, tmp_path: Path) -> None:
        _write_skill(tmp_path, "skill-A")
        _SKILL_CATALOG_CACHE.clear()

        r1 = scan_skill_catalog([tmp_path], rel_skills=set())
        _write_skill(tmp_path, "skill-B")  # 加了新 skill，但缓存命中
        r2 = scan_skill_catalog([tmp_path], rel_skills=set())

        assert r1 == r2

    def test_cache_expired_rescans(self, tmp_path: Path) -> None:
        _write_skill(tmp_path, "skill-A")
        _SKILL_CATALOG_CACHE.clear()

        scan_skill_catalog([tmp_path], rel_skills=set())

        # 强制过期
        key = next(iter(_SKILL_CATALOG_CACHE))
        ts, cached = _SKILL_CATALOG_CACHE[key]
        _SKILL_CATALOG_CACHE[key] = (ts - _SKILL_CATALOG_TTL - 1, cached)

        _write_skill(tmp_path, "skill-B")
        result = scan_skill_catalog([tmp_path], rel_skills=set())
        names = [s["name"] for s in result]
        assert "skill-B" in names
