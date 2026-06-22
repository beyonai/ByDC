"""Task #5：hook_aware_tool_node after_hook 解析 hits_json 执行 Level1/2 preconditions。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_skill_md(tmp_path: Path, name: str, preconditions: list[dict]) -> str:
    """写 SKILL.md，返回绝对路径。"""
    d = tmp_path / name
    d.mkdir(parents=True, exist_ok=True)
    preconds_yaml = ""
    if preconditions:
        preconds_yaml = "preconditions:\n"
        for p in preconditions:
            preconds_yaml += f"  - type: {p['type']}\n"
            if p["type"] == "context_has":
                preconds_yaml += f"    field: {p['field']}\n"
            elif p["type"] == "keyword_match":
                kws = json.dumps(p["keywords"], ensure_ascii=False)
                preconds_yaml += f"    keywords: {kws}\n"
    content = (
        f"---\nname: {name}\ndescription: 测试skill\n"
        f"required_tools: []\ndelegation: auto\n{preconds_yaml}---\n## 执行步骤\n"
    )
    (d / "SKILL.md").write_text(content, encoding="utf-8")
    return str(d / "SKILL.md")


def _make_search_tool_message(hits: list[dict]) -> Any:
    """构造 search_ontology 返回的 ToolMessage mock。"""
    from langchain_core.messages import ToolMessage

    hits_json = json.dumps(hits, ensure_ascii=False)
    content = f"找到候选\n<!-- hits_json:{hits_json} -->"
    msg = ToolMessage(content=content, tool_call_id="tc1")
    msg.name = "search_ontology"
    return msg


class TestAfterHookSkillPreconditions:
    """after_hook 对 search_ontology 命中的 skill 执行 Level1/2 preconditions。"""

    def _get_hook_node_class(self) -> Any:
        from datacloud_analysis.orchestration.execution.hook_aware_tool_node import (
            HookAwareToolNode,
        )

        return HookAwareToolNode

    def test_context_has_pass_writes_wrapper_to_active_tools(
        self, tmp_path: Path
    ) -> None:
        """context_has 通过时，skill wrapper 写入 active_tools。"""
        skill_path = _make_skill_md(
            tmp_path, "diagnose-fault", [{"type": "context_has", "field": "trace_id"}]
        )
        hit = {
            "objectCode": "skill_diagnose-fault",
            "resultType": "skill",
            "skillPath": skill_path,
            "score": 0.9,
        }
        msg = _make_search_tool_message([hit])
        state_dict = {"user_query": "故障", "trace_id": "abc123", "active_tools": []}

        from datacloud_analysis.tools.tool_pool import TOOL_POOL, TOOL_TO_OBJECT

        # 预先注册 wrapper 到 TOOL_POOL
        fake_wrapper = MagicMock()
        fake_wrapper.name = "activate_skill_diagnose_fault"
        TOOL_POOL["activate_skill_diagnose_fault"] = fake_wrapper
        TOOL_TO_OBJECT["activate_skill_diagnose_fault"] = "skill_diagnose-fault"

        try:
            extra_state: dict[str, Any] = {}
            _apply_skill_preconditions(msg, state_dict, extra_state)
            assert "activate_skill_diagnose_fault" in extra_state.get("active_tools", [])
        finally:
            del TOOL_POOL["activate_skill_diagnose_fault"]
            del TOOL_TO_OBJECT["activate_skill_diagnose_fault"]

    def test_context_has_fail_does_not_write_wrapper(self, tmp_path: Path) -> None:
        """context_has 不通过（字段缺失）时，skill wrapper 不写入 active_tools。"""
        skill_path = _make_skill_md(
            tmp_path, "diagnose-fault", [{"type": "context_has", "field": "trace_id"}]
        )
        hit = {
            "objectCode": "skill_diagnose-fault",
            "resultType": "skill",
            "skillPath": skill_path,
            "score": 0.9,
        }
        msg = _make_search_tool_message([hit])
        state_dict = {"user_query": "故障", "active_tools": []}  # 无 trace_id

        from datacloud_analysis.tools.tool_pool import TOOL_POOL, TOOL_TO_OBJECT

        fake_wrapper = MagicMock()
        fake_wrapper.name = "activate_skill_diagnose_fault"
        TOOL_POOL["activate_skill_diagnose_fault"] = fake_wrapper
        TOOL_TO_OBJECT["activate_skill_diagnose_fault"] = "skill_diagnose-fault"

        try:
            extra_state: dict[str, Any] = {}
            _apply_skill_preconditions(msg, state_dict, extra_state)
            assert "activate_skill_diagnose_fault" not in extra_state.get("active_tools", [])
        finally:
            del TOOL_POOL["activate_skill_diagnose_fault"]
            del TOOL_TO_OBJECT["activate_skill_diagnose_fault"]

    def test_keyword_match_pass_writes_wrapper(self, tmp_path: Path) -> None:
        """keyword_match 通过时，skill wrapper 写入 active_tools。"""
        skill_path = _make_skill_md(
            tmp_path,
            "diagnose-fault",
            [{"type": "keyword_match", "keywords": ["故障", "报错"]}],
        )
        hit = {
            "objectCode": "skill_diagnose-fault",
            "resultType": "skill",
            "skillPath": skill_path,
            "score": 0.9,
        }
        msg = _make_search_tool_message([hit])
        state_dict = {"user_query": "系统报错了", "active_tools": []}

        from datacloud_analysis.tools.tool_pool import TOOL_POOL, TOOL_TO_OBJECT

        fake_wrapper = MagicMock()
        fake_wrapper.name = "activate_skill_diagnose_fault"
        TOOL_POOL["activate_skill_diagnose_fault"] = fake_wrapper
        TOOL_TO_OBJECT["activate_skill_diagnose_fault"] = "skill_diagnose-fault"

        try:
            extra_state: dict[str, Any] = {}
            _apply_skill_preconditions(msg, state_dict, extra_state)
            assert "activate_skill_diagnose_fault" in extra_state.get("active_tools", [])
        finally:
            del TOOL_POOL["activate_skill_diagnose_fault"]
            del TOOL_TO_OBJECT["activate_skill_diagnose_fault"]

    def test_keyword_match_fail_does_not_write(self, tmp_path: Path) -> None:
        """keyword_match 不通过时，skill wrapper 不写入 active_tools。"""
        skill_path = _make_skill_md(
            tmp_path,
            "diagnose-fault",
            [{"type": "keyword_match", "keywords": ["故障", "报错"]}],
        )
        hit = {
            "objectCode": "skill_diagnose-fault",
            "resultType": "skill",
            "skillPath": skill_path,
            "score": 0.9,
        }
        msg = _make_search_tool_message([hit])
        state_dict = {"user_query": "帮我查销售额", "active_tools": []}

        from datacloud_analysis.tools.tool_pool import TOOL_POOL, TOOL_TO_OBJECT

        fake_wrapper = MagicMock()
        fake_wrapper.name = "activate_skill_diagnose_fault"
        TOOL_POOL["activate_skill_diagnose_fault"] = fake_wrapper
        TOOL_TO_OBJECT["activate_skill_diagnose_fault"] = "skill_diagnose-fault"

        try:
            extra_state: dict[str, Any] = {}
            _apply_skill_preconditions(msg, state_dict, extra_state)
            assert "activate_skill_diagnose_fault" not in extra_state.get("active_tools", [])
        finally:
            del TOOL_POOL["activate_skill_diagnose_fault"]
            del TOOL_TO_OBJECT["activate_skill_diagnose_fault"]

    def test_no_preconditions_always_passes(self, tmp_path: Path) -> None:
        """无 preconditions 的 skill 应始终通过，写入 active_tools。"""
        skill_path = _make_skill_md(tmp_path, "simple-skill", [])
        hit = {
            "objectCode": "skill_simple-skill",
            "resultType": "skill",
            "skillPath": skill_path,
            "score": 0.9,
        }
        msg = _make_search_tool_message([hit])
        state_dict = {"user_query": "任意问题", "active_tools": []}

        from datacloud_analysis.tools.tool_pool import TOOL_POOL, TOOL_TO_OBJECT

        fake_wrapper = MagicMock()
        fake_wrapper.name = "activate_skill_simple_skill"
        TOOL_POOL["activate_skill_simple_skill"] = fake_wrapper
        TOOL_TO_OBJECT["activate_skill_simple_skill"] = "skill_simple-skill"

        try:
            extra_state: dict[str, Any] = {}
            _apply_skill_preconditions(msg, state_dict, extra_state)
            assert "activate_skill_simple_skill" in extra_state.get("active_tools", [])
        finally:
            del TOOL_POOL["activate_skill_simple_skill"]
            del TOOL_TO_OBJECT["activate_skill_simple_skill"]


def _apply_skill_preconditions(
    msg: Any,
    state_dict: dict[str, Any],
    extra_state: dict[str, Any],
) -> None:
    """从 hook_aware_tool_node 导入并调用 skill preconditions 辅助函数。"""
    from datacloud_analysis.orchestration.execution.hook_aware_tool_node import (
        _apply_skill_preconditions_from_message,
    )

    _apply_skill_preconditions_from_message(msg, state_dict, extra_state)
