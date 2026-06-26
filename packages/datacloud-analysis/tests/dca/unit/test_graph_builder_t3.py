"""T3: graph_builder.py 改造 — 先红后绿

测试覆盖：
  - build_analysis_graph() 接受 tool_context 参数
  - _build_prebuilt_graph() 接受 tool_context 参数
  - tool_context.anchor_mode=True 时添加 anchor_tools（优先于 is_anchor_mode()）
  - tool_context.anchor_mode=False 时不添加 anchor_tools
  - 无 tool_context 时降级为旧 is_anchor_mode() 逻辑
  - tool_context 传递给 make_anchor_tools 的 get_tool_context_fn
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

# ── T3.1 build_analysis_graph 接受 tool_context 参数 ─────────────────────────


def test_build_analysis_graph_accepts_tool_context() -> None:
    """build_analysis_graph() 应接受 tool_context 关键字参数且不报 TypeError。"""
    from datacloud_analysis.orchestration.graph_builder import build_analysis_graph
    from datacloud_analysis.tools.request_tool_context import RequestToolContext, ScopeEntry

    RequestToolContext(
        allowed_scope=[ScopeEntry(code="lib_crm", scope_type="ONTOLOGY_BASE")],
        loader=MagicMock(),
        anchor_mode=True,
    )

    # 只验证签名可接受参数，不实际构建图（图构建依赖外部环境）
    import inspect

    sig = inspect.signature(build_analysis_graph)
    assert "tool_context" in sig.parameters


def test_build_prebuilt_graph_accepts_tool_context() -> None:
    """_build_prebuilt_graph() 应接受 tool_context 关键字参数。"""
    import inspect

    from datacloud_analysis.orchestration.graph_builder import _build_prebuilt_graph

    sig = inspect.signature(_build_prebuilt_graph)
    assert "tool_context" in sig.parameters


# ── T3.2 anchor_mode 来源改造 ────────────────────────────────────────────────


def test_tool_context_anchor_mode_true_adds_anchor_tools() -> None:
    """tool_context.anchor_mode=True 时应添加 anchor_tools，不调用 is_anchor_mode()。"""
    from datacloud_analysis.tools.request_tool_context import RequestToolContext, ScopeEntry

    tool_context = RequestToolContext(
        allowed_scope=[ScopeEntry(code="lib_crm", scope_type="ONTOLOGY_BASE")],
        loader=MagicMock(),
        anchor_mode=True,
    )

    captured_make_anchor_calls: list[dict] = []

    def fake_make_anchor_tools(get_state_fn, get_tool_context_fn=None):
        captured_make_anchor_calls.append({"get_tool_context_fn": get_tool_context_fn})
        return [MagicMock(name="goto_ontology")]

    with (
        patch(
            "datacloud_analysis.orchestration.graph_builder.make_anchor_tools",
            side_effect=fake_make_anchor_tools,
        ),
        patch(
            "datacloud_analysis.orchestration.graph_builder.is_anchor_mode",
            return_value=False,  # 即使 is_anchor_mode 返回 False，tool_context 优先
        ),
        patch(
            "datacloud_analysis.orchestration.graph_builder._build_tools_list",
            return_value=[],
        ),
    ):
        try:
            from datacloud_analysis.orchestration.graph_builder import _build_prebuilt_graph

            _build_prebuilt_graph(tool_context=tool_context)
        except Exception:
            pass  # 图构建可能失败，但我们关心的是 make_anchor_tools 是否被调用

    # make_anchor_tools 必须被调用过，且传了 get_tool_context_fn
    assert len(captured_make_anchor_calls) > 0
    assert captured_make_anchor_calls[0]["get_tool_context_fn"] is not None


def test_tool_context_anchor_mode_false_skips_anchor_tools() -> None:
    """tool_context.anchor_mode=False 时不应调用 make_anchor_tools。"""
    from datacloud_analysis.tools.request_tool_context import RequestToolContext, ScopeEntry

    tool_context = RequestToolContext(
        allowed_scope=[ScopeEntry(code="by_customer", scope_type="OBJECT")],
        loader=MagicMock(),
        anchor_mode=False,
    )

    make_anchor_calls: list = []

    def fake_make_anchor_tools(*args, **kwargs):
        make_anchor_calls.append(True)
        return [MagicMock()]

    with (
        patch(
            "datacloud_analysis.orchestration.graph_builder.make_anchor_tools",
            side_effect=fake_make_anchor_tools,
        ),
        patch(
            "datacloud_analysis.orchestration.graph_builder.is_anchor_mode",
            return_value=True,  # 即使 is_anchor_mode 返回 True，tool_context 优先
        ),
        patch(
            "datacloud_analysis.orchestration.graph_builder._build_tools_list",
            return_value=[],
        ),
    ):
        try:
            from datacloud_analysis.orchestration.graph_builder import _build_prebuilt_graph

            _build_prebuilt_graph(tool_context=tool_context)
        except Exception:
            pass

    # tool_context.anchor_mode=False 时不应调用 make_anchor_tools
    assert len(make_anchor_calls) == 0


def test_no_tool_context_falls_back_to_is_anchor_mode() -> None:
    """无 tool_context 时仍用旧 is_anchor_mode() 逻辑。"""
    make_anchor_calls: list = []

    def fake_make_anchor_tools(*args, **kwargs):
        make_anchor_calls.append(True)
        return [MagicMock()]

    with (
        patch(
            "datacloud_analysis.orchestration.graph_builder.make_anchor_tools",
            side_effect=fake_make_anchor_tools,
        ),
        patch(
            "datacloud_analysis.orchestration.graph_builder.is_anchor_mode",
            return_value=True,
        ),
        patch(
            "datacloud_analysis.orchestration.graph_builder._build_tools_list",
            return_value=[],
        ),
    ):
        try:
            from datacloud_analysis.orchestration.graph_builder import _build_prebuilt_graph

            _build_prebuilt_graph(tool_context=None)
        except Exception:
            pass

    assert len(make_anchor_calls) > 0


# ── T3.3 tool_context 通过 get_tool_context_fn 传递到 anchor_tools ─────────────


def test_get_tool_context_fn_returns_same_tool_context() -> None:
    """传入 tool_context 后，make_anchor_tools 拿到的 get_tool_context_fn() 应返回同一对象。"""
    from datacloud_analysis.tools.request_tool_context import RequestToolContext, ScopeEntry

    tool_context = RequestToolContext(
        allowed_scope=[ScopeEntry(code="lib_crm", scope_type="ONTOLOGY_BASE")],
        loader=MagicMock(),
        anchor_mode=True,
    )

    returned_ctx: list = []

    def fake_make_anchor_tools(get_state_fn, get_tool_context_fn=None):
        if get_tool_context_fn is not None:
            returned_ctx.append(get_tool_context_fn())
        return [MagicMock(name="goto_ontology")]

    with (
        patch(
            "datacloud_analysis.orchestration.graph_builder.make_anchor_tools",
            side_effect=fake_make_anchor_tools,
        ),
        patch(
            "datacloud_analysis.orchestration.graph_builder.is_anchor_mode",
            return_value=False,
        ),
        patch(
            "datacloud_analysis.orchestration.graph_builder._build_tools_list",
            return_value=[],
        ),
    ):
        try:
            from datacloud_analysis.orchestration.graph_builder import _build_prebuilt_graph

            _build_prebuilt_graph(tool_context=tool_context)
        except Exception:
            pass

    assert len(returned_ctx) > 0
    assert returned_ctx[0] is tool_context
