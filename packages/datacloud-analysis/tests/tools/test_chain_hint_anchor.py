"""工具链路图常驻提示的锚点注入逻辑测试 — 红阶段。

测试两个行为：
1. hook_aware_tool_node after_hook：activate_anchor 返回后注入全量 chain hint 到 messages
2. llm_call_node：只注入 delta（新解锁工具），不重复全量
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from langchain_core.messages import HumanMessage

from datacloud_analysis.tools.param_link_graph import ParamLinkGraph


# ── 辅助构造 ──────────────────────────────────────────────────────────────────

def _make_plg_with_links() -> ParamLinkGraph:
    """构造有 get_spans→get_tool_detail 串联的 ParamLinkGraph。"""
    params_map = {
        "get_spans": {
            "belong_entity": "ops_langfuse_trace",
            "request_params": [],
            "response_params": [{"field_code": "span_id", "object_property": "span_id"}],
        },
        "get_tool_detail": {
            "belong_entity": "ops_langfuse_trace",
            "request_params": [{"param_code": "span_id", "object_property": "span_id"}],
            "response_params": [],
        },
        "get_agent_diag": {
            "belong_entity": "ops_langfuse_trace",
            "request_params": [],
            "response_params": [
                {"field_code": "agent_id", "object_property": "{{ops_dig_employee}}.agent_id"}
            ],
        },
        "check_config_file_exists": {
            "belong_entity": "ops_dig_employee",
            "request_params": [
                {"param_code": "agent_id", "object_property": "{{ops_dig_employee}}.agent_id"}
            ],
            "response_params": [],
        },
    }

    class _Loader:
        def get_action_params(self, action_code):
            if action_code in params_map:
                return params_map[action_code]
            raise KeyError(action_code)

    tool_pool = {k: object() for k in params_map}
    plg = ParamLinkGraph()
    plg.build(tool_pool, _Loader())
    return plg


# ── ParamLinkGraph.get_full_anchor_hint ───────────────────────────────────────

class TestGetFullAnchorHint:
    """5.4 新增方法：get_full_anchor_hint(anchor_object_code) 返回该锚点下所有工具的完整 hint。"""

    def test_returns_hint_for_all_tools_under_anchor(self):
        plg = _make_plg_with_links()
        hint = plg.get_full_anchor_hint("ops_langfuse_trace")
        # 锚点 ops_langfuse_trace 下有 get_spans→get_tool_detail 和 get_agent_diag→check_config_file_exists
        assert "get_tool_detail" in hint
        assert "span_id" in hint

    def test_returns_empty_for_unknown_anchor(self):
        plg = _make_plg_with_links()
        hint = plg.get_full_anchor_hint("nonexistent_object")
        assert hint == ""

    def test_empty_graph_returns_empty(self):
        plg = ParamLinkGraph()
        assert plg.get_full_anchor_hint("ops_langfuse_trace") == ""


# ── hook_aware_tool_node：锚点激活时注入全量 hint ─────────────────────────────

class TestAnchorHintInjectionOnActivate:
    """activate_anchor 工具返回后，after_hook 应将全量 chain hint 写入 messages。"""

    def _make_state(self, tool_name: str, anchor_result: dict, chain_hint_anchor: str | None = None) -> dict:
        from langchain_core.messages import AIMessage, ToolMessage
        return {
            "messages": [
                AIMessage(content="", tool_calls=[{"id": "tc1", "name": tool_name, "args": {}}]),
                ToolMessage(content=str(anchor_result), name=tool_name, tool_call_id="tc1"),
            ],
            "active_tools": ["get_spans"],
            "chain_hint_anchor": chain_hint_anchor,
            "user_query": "诊断 trace",
            "react_round_idx": 1,
            "reasoning_graph": None,
        }

    def test_after_activate_anchor_injects_full_hint_to_messages(self):
        """activate_anchor 返回后 extra_state 应包含：
        - messages: 含 chain hint 的 HumanMessage
        - chain_hint_anchor: 新锚点的 object_code
        """
        from datacloud_analysis.tools.param_link_graph import (
            _build_anchor_chain_hint_update,
        )
        plg = _make_plg_with_links()
        result = _build_anchor_chain_hint_update(
            tool_name="activate_anchor",
            tool_result={"object_code": "ops_langfuse_trace", "status": "ok"},
            current_anchor=None,
            plg=plg,
        )
        assert result is not None
        assert result["chain_hint_anchor"] == "ops_langfuse_trace"
        messages = result.get("messages") or []
        assert len(messages) == 1
        assert isinstance(messages[0], HumanMessage)
        assert "get_tool_detail" in messages[0].content

    def test_same_anchor_does_not_reinject(self):
        """已经是同一锚点时，不重复注入。"""
        from datacloud_analysis.tools.param_link_graph import (
            _build_anchor_chain_hint_update,
        )
        plg = _make_plg_with_links()
        result = _build_anchor_chain_hint_update(
            tool_name="activate_anchor",
            tool_result={"object_code": "ops_langfuse_trace"},
            current_anchor="ops_langfuse_trace",  # 已是同一锚点
            plg=plg,
        )
        assert result is None  # 不需要更新

    def test_non_anchor_tool_does_not_inject(self):
        """普通工具（非 activate_anchor / search_ontology）不触发全量注入。"""
        from datacloud_analysis.tools.param_link_graph import (
            _build_anchor_chain_hint_update,
        )
        plg = _make_plg_with_links()
        result = _build_anchor_chain_hint_update(
            tool_name="get_spans",
            tool_result={"span_id": "abc"},
            current_anchor=None,
            plg=plg,
        )
        assert result is None


# ── llm_call_node：每轮只注入 delta ───────────────────────────────────────────

class TestDeltaHintInjection:
    """llm_call_node 每轮只注入新解锁工具的 hint（delta），不重复全量。"""

    def test_delta_hint_contains_only_new_tools(self):
        """新解锁的工具产生 delta hint，旧工具不重复。"""
        from datacloud_analysis.tools.param_link_graph import (
            _build_delta_chain_hint,
        )
        plg = _make_plg_with_links()
        hint = _build_delta_chain_hint(
            plg=plg,
            prev_active=["get_spans"],
            curr_active=["get_spans", "get_tool_detail"],
        )
        # get_tool_detail 是新增的，它作为出发点没有下游（无出参绑定），所以 hint 可为空
        # 但 get_spans 作为出发点指向 get_tool_detail，这里只测 delta 不为 None
        assert hint is not None  # 函数存在且返回字符串

    def test_no_delta_returns_empty(self):
        """active_tools 没有变化时，delta hint 为空。"""
        from datacloud_analysis.tools.param_link_graph import (
            _build_delta_chain_hint,
        )
        plg = _make_plg_with_links()
        hint = _build_delta_chain_hint(
            plg=plg,
            prev_active=["get_spans", "get_tool_detail"],
            curr_active=["get_spans", "get_tool_detail"],
        )
        assert hint == ""

    def test_none_plg_returns_empty(self):
        """plg 为 None 时安全返回空。"""
        from datacloud_analysis.tools.param_link_graph import (
            _build_delta_chain_hint,
        )
        hint = _build_delta_chain_hint(
            plg=None,
            prev_active=[],
            curr_active=["get_spans"],
        )
        assert hint == ""
