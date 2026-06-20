"""Skill 目录扫描与元数据解析。"""

from __future__ import annotations

import logging
import re
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_SKILL_CATALOG_CACHE: dict[str, tuple[float, list[dict[str, Any]]]] = {}
_SKILL_CATALOG_TTL: float = 300.0

_STEP_RE = re.compile(r"^### Step \d+", re.MULTILINE)


def scan_skill_catalog(
    skill_dirs: list[str | Path],
    rel_skills: set[str] | None = None,
) -> list[dict[str, Any]]:
    """扫描 skill 目录列表，返回元数据列表。

    同名 skill 后面目录覆盖前面目录（个人级目录放最后即可覆盖 agent 级）。
    rel_skills 非空时作为白名单过滤，空集合或 None 表示不过滤。

    Args:
        skill_dirs: 有序目录列表，已由调用方负责路径构建
        rel_skills:  skill 名称白名单；None / 空集合=不过滤

    Returns:
        list of {"name", "description", "location", "scope",
                 "delegation", "required_tools", "step_count", "preconditions"}
    """
    dirs_key = ":".join(str(d) for d in skill_dirs)
    filter_key = ",".join(sorted(rel_skills)) if rel_skills else ""
    cache_key = f"{dirs_key}|{filter_key}"

    now = time.monotonic()
    if cache_key in _SKILL_CATALOG_CACHE:
        ts, cached = _SKILL_CATALOG_CACHE[cache_key]
        if now - ts < _SKILL_CATALOG_TTL:
            return cached

    catalog: dict[str, dict[str, Any]] = {}

    for idx, raw_dir in enumerate(skill_dirs):
        skill_root = Path(raw_dir)
        if not skill_root.is_dir():
            continue
        scope = "personal" if idx > 0 else "agent"
        for skill_dir in sorted(skill_root.iterdir()):
            try:
                if not skill_dir.is_dir():
                    continue
            except OSError:
                logger.warning("scan_skill_catalog: cannot access %s, skipping", skill_dir)
                continue
            if rel_skills and skill_dir.name not in rel_skills:
                continue
            props = parse_skill_frontmatter(skill_dir)
            if props:
                catalog[props["name"]] = {**props, "scope": scope}

    result = list(catalog.values())
    _SKILL_CATALOG_CACHE[cache_key] = (now, result)
    return result


def parse_skill_frontmatter(skill_dir: Path) -> dict[str, Any] | None:
    """解析 skill 目录下 SKILL.md 的 frontmatter，提取元数据。

    Returns:
        dict with name/description/location/delegation/required_tools/step_count/preconditions，
        解析失败返回 None
    """
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        return None
    try:
        text = skill_md.read_text(encoding="utf-8")
    except OSError as exc:
        logger.warning("parse_skill_frontmatter: %s: %s", skill_md, exc)
        return None

    if not text.startswith("---"):
        return None
    end = text.find("\n---", 3)
    if end == -1:
        return None

    frontmatter_text = text[3:end].strip()
    body_text = text[end + 4 :]

    try:
        import yaml  # noqa: PLC0415

        fm: dict[str, Any] = yaml.safe_load(frontmatter_text) or {}
    except Exception:  # noqa: BLE001
        # yaml 不可用时回退到手工解析（仅基础字段）
        fm = _parse_frontmatter_basic(frontmatter_text)

    name: str = str(fm.get("name") or "").strip()
    description: str = str(fm.get("description") or "").strip()

    if not name or not description:
        logger.warning("parse_skill_frontmatter: missing name/description in %s", skill_md)
        return None

    step_count = len(_STEP_RE.findall(body_text))

    return {
        "name": name,
        "description": description,
        "location": str(skill_md),
        "delegation": str(fm.get("delegation") or "auto"),
        "required_tools": list(fm.get("required_tools") or []),
        "step_count": step_count,
        "preconditions": list(fm.get("preconditions") or []),
    }


def _parse_frontmatter_basic(text: str) -> dict[str, Any]:
    """简单手工解析 frontmatter（仅标量字段，不支持嵌套结构）。"""
    result: dict[str, Any] = {}
    for line in text.splitlines():
        if ":" in line and not line.startswith(" "):
            key, _, val = line.partition(":")
            result[key.strip()] = val.strip().strip("\"'")
    return result


def build_available_skills_xml(skills: list[dict[str, Any]]) -> str:
    """将 skill 元数据列表序列化为 <available_skills> XML 块。"""
    if not skills:
        return ""
    parts = ["<available_skills>"]
    for s in skills:
        parts += [
            "  <skill>",
            f"    <name>{s['name']}</name>",
            f"    <description>{s['description']}</description>",
            f"    <location>{s['location']}</location>",
            "  </skill>",
        ]
    parts.append("</available_skills>")
    return "\n".join(parts)
