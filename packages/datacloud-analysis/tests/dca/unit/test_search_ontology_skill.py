"""Task #4：search_ontology 返回 skill 候选 + hits_json 注释块。"""

from __future__ import annotations

import json
import re
from typing import Any
from unittest.mock import MagicMock, patch


class TestSearchOntologySkillScopes:
    """_do_search_ontology 扩展：skill 类型命中返回 hits_json。"""

    def _make_skill_hit(self, name: str) -> dict[str, Any]:
        return {
            "objectCode": f"skill_{name}",
            "objectName": name,
            "resultType": "skill",
            "score": 0.9,
        }

    def _make_obj_hit(self, code: str) -> dict[str, Any]:
        return {
            "objectCode": code,
            "objectName": code,
            "resultType": "object",
            "score": 0.8,
        }

    def test_search_ontology_returns_hits_json_comment(self) -> None:
        """search_ontology 工具返回文本末尾应包含 hits_json 注释块。"""
        hits = [self._make_skill_hit("diagnose-fault"), self._make_obj_hit("ops_trace")]

        state: dict[str, Any] = {"active_tools": [], "user_query": "故障"}

        with patch(
            "datacloud_analysis.tools.anchor_tools._do_search_ontology",
            return_value=hits,
        ):
            from datacloud_analysis.tools.anchor_tools import make_anchor_tools

            tools = make_anchor_tools(get_state_fn=lambda: state)
            search_tool = next(t for t in tools if t.name == "search_ontology")

            import asyncio

            result = asyncio.run(search_tool.ainvoke({"query": "故障"}))

        assert "<!-- hits_json:" in result, "search_ontology 结果应含 hits_json 注释块"
        # 提取并验证 JSON 可解析
        m = re.search(r"<!-- hits_json:(.*?) -->", result, re.DOTALL)
        assert m is not None
        parsed = json.loads(m.group(1))
        assert isinstance(parsed, list)
        assert len(parsed) == 2

    def test_hits_json_contains_skill_result_type(self) -> None:
        """hits_json 中 skill 命中的 resultType 应为 'skill'。"""
        hits = [self._make_skill_hit("diagnose-fault")]
        state: dict[str, Any] = {"active_tools": [], "user_query": "故障"}

        with patch(
            "datacloud_analysis.tools.anchor_tools._do_search_ontology",
            return_value=hits,
        ):
            from datacloud_analysis.tools.anchor_tools import make_anchor_tools

            tools = make_anchor_tools(get_state_fn=lambda: state)
            search_tool = next(t for t in tools if t.name == "search_ontology")

            import asyncio

            result = asyncio.run(search_tool.ainvoke({"query": "故障"}))

        m = re.search(r"<!-- hits_json:(.*?) -->", result, re.DOTALL)
        assert m is not None
        parsed = json.loads(m.group(1))
        skill_hits = [h for h in parsed if h.get("resultType") == "skill"]
        assert len(skill_hits) == 1
        assert skill_hits[0]["objectCode"] == "skill_diagnose-fault"
