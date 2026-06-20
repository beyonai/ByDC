"""activate_skill tool 单元测试。

覆盖验收用例：
  B-1   正常激活返回 SKILL.md body（去掉 frontmatter）
  B-5   会话内 skill 去重（第二次调用返回已激活提示）
  B-10  activate_skill 请求 catalog 中不存在的 skill
  B-11  本体语义类占位符保留原文并追加告警
  + 工具类占位符正常替换
  + SKILL.md 文件不存在时返回错误
  + 无 InvocationContext 时返回错误
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest
from datacloud_analysis.tools.activate_skill import activate_skill

# ─────────────────────────────────────────────────────────────────────────────
# 辅助
# ─────────────────────────────────────────────────────────────────────────────


def _make_skill_md(root: Path, name: str, body: str) -> Path:
    """在 tmp_path 下写 SKILL.md，返回文件路径。"""
    d = root / name
    d.mkdir(parents=True, exist_ok=True)
    skill_md = d / "SKILL.md"
    skill_md.write_text(f"---\nname: {name}\ndescription: 测试描述\n---\n{body}", encoding="utf-8")
    return skill_md


def _make_ctx(
    tmp_path: Path,
    skill_name: str,
    body: str = "# skill body",
    tools_dict: dict[str, Any] | None = None,
    activated_skills: set[str] | None = None,
) -> SimpleNamespace:
    """构造包含 skill_catalog 和 tools_dict 的 mock InvocationContext。"""
    skill_md = _make_skill_md(tmp_path, skill_name, body)
    catalog = [
        {
            "name": skill_name,
            "description": "测试描述",
            "location": str(skill_md),
            "scope": "personal",
        }
    ]
    extras: dict[str, Any] = {
        "skill_catalog": catalog,
        "tools_dict": tools_dict or {},
    }
    if activated_skills is not None:
        extras["activated_skills"] = activated_skills
    return SimpleNamespace(extras=extras)


# ─────────────────────────────────────────────────────────────────────────────
# 测试
# ─────────────────────────────────────────────────────────────────────────────


class TestActivateSkill:
    # ── B-1 正常激活 ──────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_returns_skill_body_without_frontmatter(self, tmp_path: Path) -> None:
        ctx = _make_ctx(tmp_path, "老鹰", body="# 战略全局分析\n\n查询步骤：...")
        with patch(
            "datacloud_analysis.tools.activate_skill.get_current_context",
            return_value=ctx,
        ):
            result = await activate_skill.ainvoke({"name": "老鹰"})

        assert "战略全局分析" in result
        assert "---" not in result or result.startswith("# Skill")  # frontmatter 已去除
        assert "测试描述" not in result  # description 字段（frontmatter 内容）不在 body

    @pytest.mark.asyncio
    async def test_result_prefixed_with_skill_name(self, tmp_path: Path) -> None:
        ctx = _make_ctx(tmp_path, "老鹰")
        with patch(
            "datacloud_analysis.tools.activate_skill.get_current_context",
            return_value=ctx,
        ):
            result = await activate_skill.ainvoke({"name": "老鹰"})

        assert "老鹰" in result

    # ── B-5 会话去重 ──────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_second_activation_returns_dedup_message(self, tmp_path: Path) -> None:
        activated: set[str] = set()
        ctx = _make_ctx(tmp_path, "老鹰", activated_skills=activated)
        with patch(
            "datacloud_analysis.tools.activate_skill.get_current_context",
            return_value=ctx,
        ):
            _ = await activate_skill.ainvoke({"name": "老鹰"})
            second = await activate_skill.ainvoke({"name": "老鹰"})

        assert "战略" not in second or "已在本会话中激活" in second
        assert "已在本会话中激活" in second
        assert "老鹰" in second

    # ── B-10 catalog 中不存在的 skill ─────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_skill_not_in_catalog_returns_error(self, tmp_path: Path) -> None:
        ctx = _make_ctx(tmp_path, "老鹰")
        with patch(
            "datacloud_analysis.tools.activate_skill.get_current_context",
            return_value=ctx,
        ):
            result = await activate_skill.ainvoke({"name": "不存在的skill"})

        assert "错误" in result
        assert "不在可用列表" in result

    # ── SKILL.md 文件不存在 ───────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_missing_skill_md_returns_error(self, tmp_path: Path) -> None:
        nonexistent = tmp_path / "ghost" / "SKILL.md"
        catalog = [{"name": "ghost", "description": "x", "location": str(nonexistent)}]
        ctx = SimpleNamespace(extras={"skill_catalog": catalog, "tools_dict": {}})
        with patch(
            "datacloud_analysis.tools.activate_skill.get_current_context",
            return_value=ctx,
        ):
            result = await activate_skill.ainvoke({"name": "ghost"})

        assert "错误" in result
        assert "不存在" in result

    # ── 工具类占位符替换 ──────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_tool_placeholder_replaced(self, tmp_path: Path) -> None:
        body = "请调用 {{query:scene_crm}} 查询数据"
        tools: dict[str, Any] = {"query_scene_crm": object()}
        ctx = _make_ctx(tmp_path, "老鹰", body=body, tools_dict=tools)
        with patch(
            "datacloud_analysis.tools.activate_skill.get_current_context",
            return_value=ctx,
        ):
            result = await activate_skill.ainvoke({"name": "老鹰"})

        assert "query_scene_crm" in result
        assert "{{query:scene_crm}}" not in result

    # ── B-11 本体语义类占位符保留并告警 ──────────────────────────────────────

    @pytest.mark.asyncio
    async def test_ontology_placeholder_kept_with_warning(self, tmp_path: Path) -> None:
        body = "本体类：{{ontology:by_customer}}，视图：{{view:scene_crm}}"
        ctx = _make_ctx(tmp_path, "老鹰", body=body)
        with patch(
            "datacloud_analysis.tools.activate_skill.get_current_context",
            return_value=ctx,
        ):
            result = await activate_skill.ainvoke({"name": "老鹰"})

        assert "{{ontology:by_customer}}" in result
        assert "{{view:scene_crm}}" in result
        assert "暂未挂载" in result

    @pytest.mark.asyncio
    async def test_mixed_tool_and_ontology_placeholders(self, tmp_path: Path) -> None:
        """工具类正常替换，本体语义类保留告警，互不影响。"""
        body = "工具：{{query:scene}} 本体：{{ontology:by_customer}}"
        tools: dict[str, Any] = {"query_scene": object()}
        ctx = _make_ctx(tmp_path, "老鹰", body=body, tools_dict=tools)
        with patch(
            "datacloud_analysis.tools.activate_skill.get_current_context",
            return_value=ctx,
        ):
            result = await activate_skill.ainvoke({"name": "老鹰"})

        assert "query_scene" in result
        assert "{{ontology:by_customer}}" in result
        assert "暂未挂载" in result

    # ── 无 InvocationContext 时降级 ───────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_no_context_returns_error(self, tmp_path: Path) -> None:
        from datacloud_data_sdk.exceptions import DatacloudError

        with patch(
            "datacloud_analysis.tools.activate_skill.get_current_context",
            side_effect=DatacloudError("no context"),
        ):
            result = await activate_skill.ainvoke({"name": "老鹰"})

        assert "错误" in result


# ─────────────────────────────────────────────────────────────────────────────
# Task #3：node.py 移除旧通用 activate_skill，内部函数保留
# ─────────────────────────────────────────────────────────────────────────────


class TestActivateSkillRemovedFromBuiltins:
    def test_activate_skill_not_in_builtin_tools(self) -> None:
        """activate_skill 通用工具不应再出现在 _BUILTIN_TOOLS。"""
        from datacloud_analysis.orchestration.execution.node import _BUILTIN_TOOLS

        names = [t.name for t in _BUILTIN_TOOLS]
        assert "activate_skill" not in names

    def test_load_skill_body_still_importable(self) -> None:
        """_load_skill_body 内部函数应保留，供 wrapper 复用。"""
        from datacloud_analysis.tools.activate_skill import _load_skill_body

        assert callable(_load_skill_body)

    def test_replace_placeholders_still_importable(self) -> None:
        """_replace_placeholders 内部函数应保留，供 wrapper 复用。"""
        from datacloud_analysis.tools.activate_skill import _replace_placeholders

        assert callable(_replace_placeholders)
