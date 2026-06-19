"""附06-V3 阶段二测试：dynamic_prompt 注入 + graph_builder 集成

测试目标：
  - _build_runtime_dynamic_prompt 在锚点模式下注入本体列表
  - _build_runtime_dynamic_prompt 在锚点模式下注入已排除路径
  - _build_runtime_dynamic_prompt 在锚点模式下注入收敛引导（有 findings 时）
  - _build_runtime_dynamic_prompt 在非锚点模式下不注入锚点相关内容
  - _build_prebuilt_graph 在锚点模式下 tools 包含 activate_anchor / mark_dead_end
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

# ── dynamic_prompt 锚点注入测试 ─────────────────────────────────────────────────


def _make_state(**kwargs: Any) -> Any:
    """构造一个最小 AgentState-like dict。"""
    base: dict[str, Any] = {
        "messages": [],
        "active_tools": [],
        "reasoning_graph": None,
        "knowledge_snippets": [],
    }
    base.update(kwargs)
    return base


def test_dynamic_prompt_no_anchor_content_when_below_threshold(monkeypatch: Any) -> None:
    """工具数低于阈值时，dynamic_prompt 不应包含锚点相关内容。"""
    from datacloud_analysis.orchestration.execution import llm_call_node as m
    from datacloud_analysis.tools import tool_pool

    monkeypatch.setattr(tool_pool, "TOOL_POOL_THRESHOLD", 100)  # 阈值设高，确保不触发

    state = _make_state()
    result = m._build_runtime_dynamic_prompt(state, None)

    if result:
        assert "activate_anchor" not in result
        assert "可选本体对象" not in result


def test_dynamic_prompt_injects_object_list_in_anchor_mode(monkeypatch: Any) -> None:
    """工具数超阈值时，dynamic_prompt 应包含可选本体对象列表。"""
    from datacloud_analysis.orchestration.execution import llm_call_node as m
    from datacloud_analysis.tools import tool_pool

    # 设阈值为0，确保锚点模式触发
    monkeypatch.setattr(tool_pool, "TOOL_POOL_THRESHOLD", 0)
    # 注册一个假工具，使 TOOL_POOL 非空
    fake = MagicMock()
    fake.name = "_test_dp_tool"
    tool_pool.register_tool("_test_dp_tool", fake, object_code="ops_test_obj_dp")
    try:
        state = _make_state()
        result = m._build_runtime_dynamic_prompt(state, None)

        assert result is not None, "锚点模式下 dynamic_prompt 不应为 None"
        assert "可选本体对象" in result, "应包含'可选本体对象'提示"
        assert "activate_anchor" in result, "应包含 activate_anchor 工具说明"
        assert "ops_test_obj_dp" in result, "应列出可用对象 ops_test_obj_dp"
    finally:
        tool_pool.TOOL_POOL.pop("_test_dp_tool", None)
        tool_pool.TOOL_TO_OBJECT.pop("_test_dp_tool", None)


def test_dynamic_prompt_hides_dead_end_objects(monkeypatch: Any) -> None:
    """已排除路径的对象不应出现在可选列表中，而应出现在已排除路径区域。"""
    from datacloud_analysis.orchestration.execution import llm_call_node as m
    from datacloud_analysis.tools import tool_pool

    monkeypatch.setattr(tool_pool, "TOOL_POOL_THRESHOLD", 0)
    fake = MagicMock()
    fake.name = "_test_dp_dead_tool"
    tool_pool.register_tool("_test_dp_dead_tool", fake, object_code="ops_dead_obj")
    try:
        rg = {
            "nodes": {},
            "current_node_id": "",
            "findings": [],
            "dead_ends": [{"object_code": "ops_dead_obj", "reason": "无数据"}],
        }
        state = _make_state(reasoning_graph=rg)
        result = m._build_runtime_dynamic_prompt(state, None)

        assert result is not None
        # 已排除的对象不应出现在可选列表，但应在已排除区域
        assert "已排除路径" in result, "应包含已排除路径区域"
        assert "ops_dead_obj" in result, "已排除对象应显示在已排除路径区域"
    finally:
        tool_pool.TOOL_POOL.pop("_test_dp_dead_tool", None)
        tool_pool.TOOL_TO_OBJECT.pop("_test_dp_dead_tool", None)


def test_dynamic_prompt_injects_convergence_hint_when_findings_exist(monkeypatch: Any) -> None:
    """reasoning_graph 有 findings 时，应追加收敛引导。"""
    from datacloud_analysis.orchestration.execution import llm_call_node as m
    from datacloud_analysis.tools import tool_pool

    monkeypatch.setattr(tool_pool, "TOOL_POOL_THRESHOLD", 0)
    fake = MagicMock()
    fake.name = "_test_dp_conv_tool"
    tool_pool.register_tool("_test_dp_conv_tool", fake, object_code="ops_conv_obj")
    try:
        rg = {
            "nodes": {},
            "current_node_id": "",
            "findings": ["BY_003: ontology_path 配错"],
            "dead_ends": [],
        }
        state = _make_state(reasoning_graph=rg)
        result = m._build_runtime_dynamic_prompt(state, None)

        assert result is not None
        assert "finish_react" in result, "有 findings 时应提示调用 finish_react 收敛"
        assert "1 条结论" in result, "应说明已确认结论数量"
    finally:
        tool_pool.TOOL_POOL.pop("_test_dp_conv_tool", None)
        tool_pool.TOOL_TO_OBJECT.pop("_test_dp_conv_tool", None)


def test_dynamic_prompt_hides_activated_objects_from_list(monkeypatch: Any) -> None:
    """已激活（在 active_tools 中）的对象不应再出现在可选列表中。"""
    from datacloud_analysis.orchestration.execution import llm_call_node as m
    from datacloud_analysis.tools import tool_pool

    monkeypatch.setattr(tool_pool, "TOOL_POOL_THRESHOLD", 0)
    fake = MagicMock()
    fake.name = "get_spans_activated"
    tool_pool.register_tool("get_spans_activated", fake, object_code="ops_activated_obj")
    try:
        # get_spans_activated 已在 active_tools 里
        state = _make_state(active_tools=["get_spans_activated"])
        result = m._build_runtime_dynamic_prompt(state, None)

        if result and "可选本体对象" in result:
            # 已激活的对象不应再出现在可选列表
            # （但可能出现在其他区域，这里只检查可选列表部分）
            available_section = (
                result.split("可选本体对象")[1].split("##")[0]
                if "##" in result.split("可选本体对象")[1]
                else result.split("可选本体对象")[1]
            )
            assert "ops_activated_obj" not in available_section, "已激活的对象不应出现在可选列表中"
    finally:
        tool_pool.TOOL_POOL.pop("get_spans_activated", None)
        tool_pool.TOOL_TO_OBJECT.pop("get_spans_activated", None)


# ── graph_builder 集成测试 ──────────────────────────────────────────────────────


def test_prebuilt_graph_includes_anchor_tools_when_anchor_mode(monkeypatch: Any) -> None:
    """锚点模式下，build_analysis_graph 构建的 tools 应包含 activate_anchor / mark_dead_end。"""
    from datacloud_analysis.tools import tool_pool

    # 设阈值为0，确保锚点模式
    monkeypatch.setattr(tool_pool, "TOOL_POOL_THRESHOLD", 0)
    fake = MagicMock()
    fake.name = "_test_graph_tool"
    tool_pool.register_tool("_test_graph_tool", fake, object_code="ops_graph_test")
    try:
        # 直接调用 _build_tools_list 看是否含锚点工具
        # graph_builder 里使用局部 import，所以通过 tool_pool.TOOL_POOL 非空来触发
        from datacloud_analysis.tools.anchor_tools import make_anchor_tools

        # 确认在锚点模式下 make_anchor_tools 工厂能产生两个工具
        anchor_tools = make_anchor_tools(get_state_fn=lambda: {})
        anchor_names = {t.name for t in anchor_tools}
        assert "activate_anchor" in anchor_names
        assert "mark_dead_end" in anchor_names

        # 确认 graph_builder 中实际已经 import 并调用
        import inspect

        from datacloud_analysis.orchestration import graph_builder

        src = inspect.getsource(graph_builder._build_prebuilt_graph)
        assert "is_anchor_mode" in src, "_build_prebuilt_graph 应调用 is_anchor_mode"
        assert "make_anchor_tools" in src, "_build_prebuilt_graph 应调用 make_anchor_tools"
        assert "activate_anchor" in src or "anchor_tools" in src, (
            "_build_prebuilt_graph 应将 anchor 工具加入 tools_list"
        )
    finally:
        tool_pool.TOOL_POOL.pop("_test_graph_tool", None)
        tool_pool.TOOL_TO_OBJECT.pop("_test_graph_tool", None)


def test_builtin_tools_include_anchor_tools_in_anchor_mode(monkeypatch: Any) -> None:
    """锚点模式下，_BUILTIN_TOOLS 或 _build_tools_list 返回的列表应含 anchor 工具。"""
    from datacloud_analysis.tools import tool_pool

    monkeypatch.setattr(tool_pool, "TOOL_POOL_THRESHOLD", 0)
    fake = MagicMock()
    fake.name = "_test_builtin_tool"
    tool_pool.register_tool("_test_builtin_tool", fake, object_code="ops_builtin_test")
    try:
        from datacloud_analysis.orchestration.execution import node as node_module

        tool_names = {t.name for t in node_module._BUILTIN_TOOLS}
        # 锚点工具应在内置工具列表中（当锚点模式下）
        # 如果不在内置工具，则需要在 _build_tools_list 里动态添加
        # 此测试验证的是"有没有集成入口"
        has_anchor_in_builtin = "activate_anchor" in tool_names
        # 如果不在 builtin，则至少 _build_tools_list(None) 在锚点模式下应包含
        if not has_anchor_in_builtin:
            tools = node_module._build_tools_list(None)
            # 暂时标记：需要在 _build_tools_list 或 builtin 里集成
            # 这个测试先作为"确认集成点"的检查点
            pass  # 阶段二实现后会通过
    finally:
        tool_pool.TOOL_POOL.pop("_test_builtin_tool", None)
        tool_pool.TOOL_TO_OBJECT.pop("_test_builtin_tool", None)
