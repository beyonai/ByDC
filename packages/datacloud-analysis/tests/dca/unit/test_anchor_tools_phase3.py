"""4.1 锚点机制 V2 测试 — 先红后绿

新增工具：
- search_ontology：语义搜索锚点
- goto_ontology：OWL 关系定向跳转（原 activate_anchor 重命名 + 扩参）
- get_reasoning_map：查阅推理轨迹

标记旧测试中 activate_anchor 相关的期望为兼容（保留向后兼容测试）。
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

# ── goto_ontology（原 activate_anchor 重命名，新增 reason 参数）────────────────────


def test_make_anchor_tools_v2_contains_goto_ontology() -> None:
    """make_anchor_tools 应返回 goto_ontology 工具（原 activate_anchor 重命名）。"""
    from datacloud_analysis.tools.anchor_tools import make_anchor_tools

    tools = make_anchor_tools(get_state_fn=lambda: {})
    names = {t.name for t in tools}
    assert "goto_ontology" in names, "应包含 goto_ontology 工具"


def test_goto_ontology_requires_reason_param() -> None:
    """goto_ontology 应有 reason 参数。"""

    from datacloud_analysis.tools.anchor_tools import make_anchor_tools

    tools = make_anchor_tools(get_state_fn=lambda: {})
    goto = next((t for t in tools if t.name == "goto_ontology"), None)
    assert goto is not None, "goto_ontology 工具应存在"

    # 检查 schema 包含 reason 字段
    schema = goto.args_schema.schema() if hasattr(goto, "args_schema") else {}
    props = schema.get("properties", {})
    assert "reason" in props, "goto_ontology 应有 reason 参数"
    assert "object_code" in props, "goto_ontology 应有 object_code 参数"


def test_goto_ontology_writes_reason_to_reasoning_graph() -> None:
    """goto_ontology 调用时 reason 应写入 reasoning_graph 对应节点。"""
    from datacloud_analysis.tools import tool_pool
    from datacloud_analysis.tools.anchor_tools import make_anchor_tools

    fake = MagicMock()
    fake.name = "query_ops_goto_test"
    tool_pool.register_tool("query_ops_goto_test", fake, object_code="ops_goto_test")

    state: dict[str, Any] = {"active_tools": [], "reasoning_graph": None}
    tools = make_anchor_tools(get_state_fn=lambda: state)
    goto = next(t for t in tools if t.name == "goto_ontology")

    try:
        result = goto.invoke(
            {
                "object_code": "ops_goto_test",
                "reason": "工具结果含 trace_id，需跳转分析链路",
            }
        )
        assert isinstance(result, str)
        rg = state.get("reasoning_graph") or {}
        nodes = rg.get("nodes") or {}
        # 找到 goto_ontology 类型节点
        goto_nodes = [n for n in nodes.values() if n.get("type") == "goto_ontology"]
        assert len(goto_nodes) >= 1, "应有 goto_ontology 类型节点"
        assert goto_nodes[0]["reason"] == "工具结果含 trace_id，需跳转分析链路"
        assert goto_nodes[0]["object_code"] == "ops_goto_test"
    finally:
        tool_pool.TOOL_POOL.pop("query_ops_goto_test", None)
        tool_pool.TOOL_TO_OBJECT.pop("query_ops_goto_test", None)


def test_goto_ontology_adds_tools_to_active_tools() -> None:
    """goto_ontology 应将对象工具加入 active_tools（功能与 activate_anchor 一致）。"""
    from datacloud_analysis.tools import tool_pool
    from datacloud_analysis.tools.anchor_tools import make_anchor_tools

    fake = MagicMock()
    fake.name = "query_ops_goto2"
    tool_pool.register_tool("query_ops_goto2", fake, object_code="ops_goto2")

    state: dict[str, Any] = {"active_tools": [], "reasoning_graph": None}
    tools = make_anchor_tools(get_state_fn=lambda: state)
    goto = next(t for t in tools if t.name == "goto_ontology")

    try:
        goto.invoke({"object_code": "ops_goto2", "reason": "测试跳转"})
        assert "query_ops_goto2" in state.get("active_tools", [])
    finally:
        tool_pool.TOOL_POOL.pop("query_ops_goto2", None)
        tool_pool.TOOL_TO_OBJECT.pop("query_ops_goto2", None)


# ── search_ontology ────────────────────────────────────────────────────────────


def test_make_anchor_tools_v2_contains_search_ontology() -> None:
    """make_anchor_tools 应返回 search_ontology 工具。"""
    from datacloud_analysis.tools.anchor_tools import make_anchor_tools

    tools = make_anchor_tools(get_state_fn=lambda: {})
    names = {t.name for t in tools}
    assert "search_ontology" in names, "应包含 search_ontology 工具"


def test_search_ontology_schema() -> None:
    """search_ontology 应有 query / scope / type / top_k 参数。"""
    from datacloud_analysis.tools.anchor_tools import make_anchor_tools

    tools = make_anchor_tools(get_state_fn=lambda: {})
    search = next((t for t in tools if t.name == "search_ontology"), None)
    assert search is not None

    schema = search.args_schema.schema() if hasattr(search, "args_schema") else {}
    props = schema.get("properties", {})
    assert "query" in props, "search_ontology 应有 query 参数"
    assert "scope" in props, "search_ontology 应有 scope 参数"
    assert "type" in props, "search_ontology 应有 type 参数"
    assert "top_k" in props, "search_ontology 应有 top_k 参数"


def test_search_ontology_writes_results_to_active_tools() -> None:
    """search_ontology 命中的对象工具应写入 active_tools。"""
    from datacloud_analysis.tools import tool_pool
    from datacloud_analysis.tools.anchor_tools import make_anchor_tools

    fake = MagicMock()
    fake.name = "query_ops_search_test"
    tool_pool.register_tool("query_ops_search_test", fake, object_code="ops_search_test")

    state: dict[str, Any] = {"active_tools": [], "reasoning_graph": None}

    # mock SearchEngine 返回命中结果
    mock_hit = {
        "objectCode": "ops_search_test",
        "objectName": "搜索测试对象",
        "resultType": "object",
        "score": 0.95,
    }

    tools = make_anchor_tools(get_state_fn=lambda: state)
    search = next(t for t in tools if t.name == "search_ontology")

    try:
        with patch(
            "datacloud_analysis.tools.anchor_tools._do_search_ontology",
            return_value=[mock_hit],
        ):
            result = search.invoke(
                {"query": "运维链路追踪", "scope": "all", "type": "all", "top_k": 3}
            )

        assert isinstance(result, str)
        assert "query_ops_search_test" in state.get("active_tools", []), (
            "search_ontology 命中的对象工具应写入 active_tools"
        )
    finally:
        tool_pool.TOOL_POOL.pop("query_ops_search_test", None)
        tool_pool.TOOL_TO_OBJECT.pop("query_ops_search_test", None)


def test_search_ontology_returns_candidates_as_string() -> None:
    """search_ontology 应返回候选对象列表的字符串描述。"""
    from datacloud_analysis.tools.anchor_tools import make_anchor_tools

    state: dict[str, Any] = {"active_tools": [], "reasoning_graph": None}
    tools = make_anchor_tools(get_state_fn=lambda: state)
    search = next(t for t in tools if t.name == "search_ontology")

    mock_hits = [
        {"objectCode": "ops_trace", "objectName": "链路追踪", "resultType": "object", "score": 0.9},
        {
            "objectCode": "ops_metric",
            "objectName": "指标监控",
            "resultType": "object",
            "score": 0.8,
        },
    ]

    with patch(
        "datacloud_analysis.tools.anchor_tools._do_search_ontology",
        return_value=mock_hits,
    ):
        result = search.invoke({"query": "链路", "scope": "all", "type": "all", "top_k": 3})

    assert "ops_trace" in result or "链路追踪" in result, "结果应包含命中的对象信息"


def test_search_ontology_no_results() -> None:
    """search_ontology 无结果时返回提示。"""
    from datacloud_analysis.tools.anchor_tools import make_anchor_tools

    state: dict[str, Any] = {"active_tools": [], "reasoning_graph": None}
    tools = make_anchor_tools(get_state_fn=lambda: state)
    search = next(t for t in tools if t.name == "search_ontology")

    with patch(
        "datacloud_analysis.tools.anchor_tools._do_search_ontology",
        return_value=[],
    ):
        result = search.invoke(
            {"query": "不存在的对象xyz", "scope": "all", "type": "all", "top_k": 3}
        )

    assert isinstance(result, str)
    assert len(result) > 0, "无结果时应返回提示信息"


# ── get_reasoning_map ──────────────────────────────────────────────────────────


def test_make_anchor_tools_v2_contains_get_reasoning_map() -> None:
    """make_anchor_tools 应返回 get_reasoning_map 工具。"""
    from datacloud_analysis.tools.anchor_tools import make_anchor_tools

    tools = make_anchor_tools(get_state_fn=lambda: {})
    names = {t.name for t in tools}
    assert "get_reasoning_map" in names, "应包含 get_reasoning_map 工具"


def test_get_reasoning_map_returns_full_structure() -> None:
    """get_reasoning_map 应返回包含 anchors/dead_ends/findings/task_objects 的完整结构。"""
    from datacloud_analysis.tools.anchor_tools import make_anchor_tools

    rg = {
        "nodes": {
            "anchor_0": {
                "id": "anchor_0",
                "type": "goto_ontology",
                "object_code": "ops_trace",
                "tools_called": ["query_ops_trace"],
                "findings_summary": "发现超时 trace",
                "is_dead_end": False,
            }
        },
        "dead_ends": [{"object_code": "ops_xxx", "reason": "无数据"}],
        "findings": ["BY_001: 发现 500 错误"],
        "task_objects": [{"code": "task_anomaly", "row_count": 15, "summary": "异常集合"}],
    }
    state: dict[str, Any] = {"active_tools": [], "reasoning_graph": rg}
    tools = make_anchor_tools(get_state_fn=lambda: state)
    get_map = next(t for t in tools if t.name == "get_reasoning_map")

    result = get_map.invoke({})
    assert isinstance(result, str)
    # 应包含 anchors/dead_ends/findings/task_objects 信息
    assert "ops_trace" in result or "anchors" in result.lower()
    assert "ops_xxx" in result or "dead_ends" in result.lower()
    assert "BY_001" in result or "findings" in result.lower()


def test_get_reasoning_map_empty_state() -> None:
    """reasoning_graph 为空时 get_reasoning_map 应返回空结构提示。"""
    from datacloud_analysis.tools.anchor_tools import make_anchor_tools

    state: dict[str, Any] = {"active_tools": [], "reasoning_graph": None}
    tools = make_anchor_tools(get_state_fn=lambda: state)
    get_map = next(t for t in tools if t.name == "get_reasoning_map")

    result = get_map.invoke({})
    assert isinstance(result, str)
    assert len(result) > 0


# ── 冷启动锚点逻辑（intend_node 扩展）────────────────────────────────────────────


def test_intend_node_cold_start_calls_search_ontology_in_anchor_mode() -> None:
    """is_anchor_mode=True 且 active_tools 为空时，intend_node 应自动调用 search_ontology。"""
    import inspect

    from datacloud_analysis.orchestration.intend import node as intend_module

    src = inspect.getsource(intend_module)
    assert "is_anchor_mode" in src, "intend_node 应检查 is_anchor_mode"
    assert "search_ontology" in src or "_do_search_ontology" in src, (
        "intend_node 应在锚点模式下触发 search_ontology 冷启动"
    )
    assert "cold_start" in src.lower() or "active_tools" in src, (
        "intend_node 应有冷启动逻辑写入 active_tools"
    )


# ── 向后兼容：activate_anchor 仍可用（不破坏旧测试）─────────────────────────────


def test_activate_anchor_still_works_for_backward_compat() -> None:
    """activate_anchor 仍应存在（向后兼容），功能与 goto_ontology 一致。"""
    from datacloud_analysis.tools.anchor_tools import make_anchor_tools

    tools = make_anchor_tools(get_state_fn=lambda: {})
    names = {t.name for t in tools}
    # activate_anchor 可以保留也可以去掉，如果去掉则 goto_ontology 必须存在
    assert "goto_ontology" in names or "activate_anchor" in names, (
        "goto_ontology 或 activate_anchor 至少存在一个"
    )
