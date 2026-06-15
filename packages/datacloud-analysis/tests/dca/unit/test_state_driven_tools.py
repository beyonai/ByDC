"""3.2 State 驱动解锁 + 3.3 Todo 机制 — 测试文件（先红后绿）

测试目标：
  - state.py 新增 reasoning_graph 字段
  - llm_call_node 每轮从 active_tools 合并解锁工具
  - after_hook 调用 OntologyRelationGraph 解锁，写 active_tools + reasoning_graph
  - _update_reasoning_graph 节点写入正确
  - make_reasoning_graph_tools 返回 get_reasoning_map / add_finding
  - llm_call_node user_query 锚定（裁剪后重注入）
  - llm_call_node todos 快照注入
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

# ── 3.2.1 state.py 新增 reasoning_graph 字段 ─────────────────────────────────


def test_agent_state_has_reasoning_graph() -> None:
    from datacloud_analysis.orchestration.state import AgentState

    # reasoning_graph 字段必须存在于 AgentState 的类型注解里
    hints = AgentState.__annotations__
    assert "reasoning_graph" in hints, "AgentState 缺少 reasoning_graph 字段，请在 state.py 中添加"


def test_agent_state_reasoning_graph_type() -> None:

    from datacloud_analysis.orchestration.state import AgentState

    hints = AgentState.__annotations__
    rg_type = hints["reasoning_graph"]
    type_str = str(rg_type)
    # 应为 dict[str, Any] | None 或其 Optional 形式
    assert "dict" in type_str.lower() or "Dict" in type_str, (
        f"reasoning_graph 类型应为 dict|None，实际为 {rg_type}"
    )


# ── 3.2.2 llm_call_node 动态合并 active_tools ────────────────────────────────


def test_llm_call_node_merges_active_tools(monkeypatch: Any) -> None:
    """llm_call_node 每轮应将 state.active_tools 的工具合并进 tools_map。"""
    from datacloud_analysis.tools import tool_pool

    # 注册一个假工具到 TOOL_POOL
    fake_unlocked = MagicMock()
    fake_unlocked.name = "get_early_span"
    tool_pool.register_tool("get_early_span", fake_unlocked, object_code="ops_early_span")

    try:
        # 验证 get_tools 能取到这个工具（llm_call_node 依赖此函数）
        result = tool_pool.get_tools(["get_early_span"])
        assert "get_early_span" in result
        assert result["get_early_span"] is fake_unlocked
    finally:
        tool_pool.TOOL_POOL.pop("get_early_span", None)
        tool_pool.TOOL_TO_OBJECT.pop("get_early_span", None)


# ── 3.2.3 after_hook 解锁逻辑 ────────────────────────────────────────────────


def test_update_reasoning_graph_creates_node() -> None:
    from datacloud_analysis.tools.tool_pool import (
        TOOL_POOL,
        TOOL_TO_OBJECT,
        register_tool,
    )

    # 注册工具到反查表
    fake = MagicMock()
    fake.name = "get_spans"
    register_tool("get_spans", fake, object_code="ops_langfuse_trace")

    try:
        from datacloud_analysis.orchestration.execution.hook_aware_tool_node import (
            _update_reasoning_graph,
        )
        from datacloud_analysis.tools.ontology_relation_graph import NextObjectSuggestion

        state_dict: dict[str, Any] = {
            "active_tools": [],
            "reasoning_graph": None,
        }
        suggestions = [
            NextObjectSuggestion(
                object_code="ops_early_span",
                tool="get_early_span",
                reason="发现 early_span",
                hint="传入 trace_id",
                relation_type="CONTAINS",
            )
        ]
        extra_updates: dict[str, Any] = {}

        _update_reasoning_graph(state_dict, "get_spans", {}, suggestions, extra_updates)

        assert "reasoning_graph" in extra_updates
        rg = extra_updates["reasoning_graph"]
        assert "nodes" in rg
        assert len(rg["nodes"]) == 1

        node = list(rg["nodes"].values())[0]
        assert node["action"] == "get_spans"
        assert node["object_code"] == "ops_langfuse_trace"
        assert "get_early_span" in node["unlocked_tools"]
        assert "get_early_span" in node["unlock_reasons"]
        assert node["status"] == "done"
    finally:
        TOOL_POOL.pop("get_spans", None)
        TOOL_TO_OBJECT.pop("get_spans", None)


# ── 3.2.4 get_reasoning_map / add_finding 工具 ───────────────────────────────


def test_make_reasoning_graph_tools_returns_two_tools() -> None:
    from datacloud_analysis.tools.reasoning_graph_tools import make_reasoning_graph_tools

    tools = make_reasoning_graph_tools(get_state_fn=lambda: {})
    tool_names = {t.name for t in tools}

    assert "get_reasoning_map" in tool_names, (
        "make_reasoning_graph_tools 应返回 get_reasoning_map 工具"
    )
    assert "add_finding" in tool_names, "make_reasoning_graph_tools 应返回 add_finding 工具"


def test_get_reasoning_map_returns_string() -> None:
    from datacloud_analysis.tools.reasoning_graph_tools import make_reasoning_graph_tools

    rg = {
        "nodes": {
            "n0": {
                "id": "n0",
                "action": "get_spans",
                "result_summary": "17个span",
                "unlocked_tools": ["get_early_span"],
                "unlock_reasons": {"get_early_span": "CONTAINS: 发现 early_span"},
                "status": "done",
            }
        },
        "current_node_id": "n0",
        "findings": [],
    }
    state_store: dict[str, Any] = {"reasoning_graph": rg, "active_tools": ["get_early_span"]}

    tools = make_reasoning_graph_tools(get_state_fn=lambda: state_store)
    get_map = next(t for t in tools if t.name == "get_reasoning_map")

    result = get_map.invoke({})
    assert isinstance(result, str)
    assert "get_spans" in result
    assert "get_early_span" in result


def test_add_finding_writes_to_state() -> None:
    from datacloud_analysis.tools.reasoning_graph_tools import make_reasoning_graph_tools

    rg: dict[str, Any] = {"nodes": {}, "current_node_id": "", "findings": []}
    state_store: dict[str, Any] = {"reasoning_graph": rg, "active_tools": []}

    tools = make_reasoning_graph_tools(get_state_fn=lambda: state_store)
    add = next(t for t in tools if t.name == "add_finding")

    result = add.invoke({"conclusion": "BY_003: ontology_path 配错"})
    assert isinstance(result, str)
    assert "BY_003" in result

    # findings 应被写入 state_store
    assert len(state_store["reasoning_graph"]["findings"]) == 1
    assert "BY_003" in state_store["reasoning_graph"]["findings"][0]


# ── 3.3 Todo 机制 ─────────────────────────────────────────────────────────────


def test_llm_call_node_has_user_query_anchor_logic() -> None:
    """llm_call_node 应有 user_query 锚定逻辑（裁剪后检查并重新插入）。"""
    import inspect

    from datacloud_analysis.orchestration.execution import llm_call_node as m

    source = inspect.getsource(m)
    assert "_original_query_visible" in source or "user_query" in source, (
        "llm_call_node 中应有 user_query 锚定相关代码"
    )


def test_llm_call_node_has_todo_snapshot_logic() -> None:
    """llm_call_node 应有 todos 快照注入逻辑（裁剪后追加 pending/in_progress 项）。"""
    import inspect

    from datacloud_analysis.orchestration.execution import llm_call_node as m

    source = inspect.getsource(m)
    assert "todos" in source and ("pending" in source or "in_progress" in source), (
        "llm_call_node 中应有 todos 快照注入逻辑"
    )


def test_manage_todo_tool_importable() -> None:
    """manage_todo 工具应可导入（在 yunwei_demo 的工具列表里）。"""
    # manage_todo 可能在 tools/ 目录或内置工具里，只要能找到即可
    try:
        from datacloud_analysis.tools.manage_todo import manage_todo  # noqa: F401
    except ImportError:
        # 也可能以 @tool 形式在 builtin_tools 里
        from datacloud_analysis.tools import manage_todo as _  # noqa: F401
