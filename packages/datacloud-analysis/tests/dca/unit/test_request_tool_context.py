"""T1: RequestToolContext + ScopeEntry — 先红后绿

测试目标：
  - ScopeEntry 数据结构（code / scope_type / base_id）
  - RequestToolContext 数据结构（allowed_scope / loader / tools_map / anchor_mode / param_link_graph）
  - RequestToolContext.build() 正确决定 anchor_mode
  - RequestToolContext.is_object_allowed() 三级权限校验
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

# ── T1.1 ScopeEntry ────────────────────────────────────────────────────────────


def test_scope_entry_importable() -> None:
    from datacloud_analysis.tools.request_tool_context import ScopeEntry  # noqa: F401


def test_scope_entry_fields() -> None:
    from datacloud_analysis.tools.request_tool_context import ScopeEntry

    e = ScopeEntry(code="by_customer", scope_type="OBJECT", base_id="lib_crm")
    assert e.code == "by_customer"
    assert e.scope_type == "OBJECT"
    assert e.base_id == "lib_crm"


def test_scope_entry_base_id_default_empty() -> None:
    from datacloud_analysis.tools.request_tool_context import ScopeEntry

    e = ScopeEntry(code="by_customer", scope_type="OBJECT")
    assert e.base_id == ""


def test_scope_entry_accepts_all_scope_types() -> None:
    from datacloud_analysis.tools.request_tool_context import ScopeEntry

    for st in ("ONTOLOGY_BASE", "SCENE", "OBJECT", "VIEW"):
        e = ScopeEntry(code="x", scope_type=st)  # type: ignore[arg-type]
        assert e.scope_type == st


# ── T1.2 RequestToolContext 基本结构 ──────────────────────────────────────────


def test_request_tool_context_importable() -> None:
    from datacloud_analysis.tools.request_tool_context import RequestToolContext  # noqa: F401


def test_request_tool_context_fields() -> None:
    from datacloud_analysis.tools.request_tool_context import RequestToolContext, ScopeEntry

    loader = MagicMock()
    scope = [ScopeEntry(code="by_customer", scope_type="OBJECT")]
    ctx = RequestToolContext(allowed_scope=scope, loader=loader)

    assert ctx.allowed_scope is scope
    assert ctx.loader is loader
    assert ctx.tools_map == {}
    assert ctx.object_to_tools == {}
    assert ctx.anchor_mode is False
    assert ctx.param_link_graph is None


# ── T1.3 build() — anchor_mode 决策 ─────────────────────────────────────────


def test_build_anchor_mode_true_when_ontology_base() -> None:
    """allowed_scope 含 ONTOLOGY_BASE 时强制 anchor_mode=True。"""
    from datacloud_analysis.tools.request_tool_context import RequestToolContext, ScopeEntry

    scope = [ScopeEntry(code="lib_crm", scope_type="ONTOLOGY_BASE", base_id="lib_crm")]
    loader = MagicMock()
    tool_loader_cls = MagicMock()

    ctx = RequestToolContext.build(
        allowed_scope=scope,
        loader=loader,
        tool_loader_cls=tool_loader_cls,
    )

    assert ctx.anchor_mode is True
    tool_loader_cls.assert_not_called()  # 不应构建工具


def test_build_anchor_mode_true_when_scene() -> None:
    """allowed_scope 含 SCENE 时强制 anchor_mode=True。"""
    from datacloud_analysis.tools.request_tool_context import RequestToolContext, ScopeEntry

    scope = [ScopeEntry(code="scene_crm", scope_type="SCENE", base_id="lib_crm")]
    loader = MagicMock()
    tool_loader_cls = MagicMock()

    ctx = RequestToolContext.build(
        allowed_scope=scope,
        loader=loader,
        tool_loader_cls=tool_loader_cls,
    )

    assert ctx.anchor_mode is True
    tool_loader_cls.assert_not_called()


def test_build_anchor_mode_false_when_few_objects(monkeypatch: Any) -> None:
    """全为 OBJECT/VIEW 且工具数 ≤ threshold 时 anchor_mode=False，tools_map 已填充。"""
    from datacloud_analysis.tools.request_tool_context import RequestToolContext, ScopeEntry

    scope = [ScopeEntry(code="by_customer", scope_type="OBJECT", base_id="lib_crm")]
    loader = MagicMock()

    fake_tool_a = MagicMock()
    fake_tool_a._object_code = "by_customer"
    fake_tools = {"by_customer__query": fake_tool_a}

    fake_instance = MagicMock()
    fake_instance.load.return_value = fake_tools
    tool_loader_cls = MagicMock(return_value=fake_instance)

    ctx = RequestToolContext.build(
        allowed_scope=scope,
        loader=loader,
        tool_loader_cls=tool_loader_cls,
        threshold=30,
    )

    assert ctx.anchor_mode is False
    assert "by_customer__query" in ctx.tools_map
    assert ctx.object_to_tools["by_customer"] == ["by_customer__query"]


def test_build_anchor_mode_true_when_many_objects() -> None:
    """全为 OBJECT/VIEW 但工具数 > threshold 时 anchor_mode=True，tools_map 为空。"""
    from datacloud_analysis.tools.request_tool_context import RequestToolContext, ScopeEntry

    scope = [ScopeEntry(code=f"obj_{i}", scope_type="OBJECT") for i in range(5)]
    loader = MagicMock()

    # 模拟工具数超过 threshold=2
    fake_tools = {f"obj_{i}__query": MagicMock() for i in range(5)}
    for name, t in fake_tools.items():
        t._object_code = name.split("__")[0]
    fake_instance = MagicMock()
    fake_instance.load.return_value = fake_tools
    tool_loader_cls = MagicMock(return_value=fake_instance)

    ctx = RequestToolContext.build(
        allowed_scope=scope,
        loader=loader,
        tool_loader_cls=tool_loader_cls,
        threshold=2,
    )

    assert ctx.anchor_mode is True
    assert ctx.tools_map == {}


def test_build_param_link_graph_built_when_anchor_mode_false() -> None:
    """anchor_mode=False 时 param_link_graph 应已构建。"""
    from datacloud_analysis.tools.request_tool_context import RequestToolContext, ScopeEntry

    scope = [ScopeEntry(code="by_customer", scope_type="OBJECT", base_id="lib_crm")]
    loader = MagicMock()

    fake_tool = MagicMock()
    fake_tool._object_code = "by_customer"
    fake_tools = {"by_customer__query": fake_tool}
    fake_instance = MagicMock()
    fake_instance.load.return_value = fake_tools
    tool_loader_cls = MagicMock(return_value=fake_instance)

    fake_plg_instance = MagicMock()
    fake_plg_cls = MagicMock(return_value=fake_plg_instance)

    with patch("datacloud_analysis.tools.request_tool_context.ParamLinkGraph", fake_plg_cls):
        ctx = RequestToolContext.build(
            allowed_scope=scope,
            loader=loader,
            tool_loader_cls=tool_loader_cls,
            threshold=30,
        )

    assert ctx.param_link_graph is fake_plg_instance
    fake_plg_instance.build.assert_called_once_with(fake_tools, loader)


def test_build_param_link_graph_none_when_anchor_mode_true() -> None:
    """anchor_mode=True 时 param_link_graph 应为 None（惰性构建）。"""
    from datacloud_analysis.tools.request_tool_context import RequestToolContext, ScopeEntry

    scope = [ScopeEntry(code="lib_crm", scope_type="ONTOLOGY_BASE", base_id="lib_crm")]
    loader = MagicMock()
    tool_loader_cls = MagicMock()

    ctx = RequestToolContext.build(
        allowed_scope=scope,
        loader=loader,
        tool_loader_cls=tool_loader_cls,
    )

    assert ctx.param_link_graph is None


# ── T1.4 is_object_allowed() 三级权限校验 ────────────────────────────────────


def test_is_object_allowed_exact_object_match() -> None:
    """OBJECT 精确匹配时允许。"""
    from datacloud_analysis.tools.request_tool_context import RequestToolContext, ScopeEntry

    ctx = RequestToolContext(
        allowed_scope=[ScopeEntry(code="by_customer", scope_type="OBJECT")],
        loader=MagicMock(),
    )
    assert ctx.is_object_allowed("by_customer", scene_id=None, library_id=None) is True


def test_is_object_allowed_scene_match() -> None:
    """SCENE 匹配时允许（object_code 不在 OBJECT 列表，但 scene_id 匹配）。"""
    from datacloud_analysis.tools.request_tool_context import RequestToolContext, ScopeEntry

    ctx = RequestToolContext(
        allowed_scope=[ScopeEntry(code="scene_crm", scope_type="SCENE")],
        loader=MagicMock(),
    )
    assert ctx.is_object_allowed("any_obj", scene_id="scene_crm", library_id=None) is True


def test_is_object_allowed_ontology_base_match() -> None:
    """ONTOLOGY_BASE 匹配时允许。"""
    from datacloud_analysis.tools.request_tool_context import RequestToolContext, ScopeEntry

    ctx = RequestToolContext(
        allowed_scope=[ScopeEntry(code="lib_crm", scope_type="ONTOLOGY_BASE")],
        loader=MagicMock(),
    )
    assert ctx.is_object_allowed("any_obj", scene_id=None, library_id="lib_crm") is True


def test_is_object_allowed_denied_no_match() -> None:
    """不在任意授权范围时拒绝。"""
    from datacloud_analysis.tools.request_tool_context import RequestToolContext, ScopeEntry

    ctx = RequestToolContext(
        allowed_scope=[ScopeEntry(code="by_customer", scope_type="OBJECT")],
        loader=MagicMock(),
    )
    assert ctx.is_object_allowed("by_order", scene_id="scene_x", library_id="lib_x") is False


def test_is_object_allowed_priority_object_over_scene() -> None:
    """object_code 在 OBJECT 列表时直接允许，不需要 scene_id / library_id 匹配。"""
    from datacloud_analysis.tools.request_tool_context import RequestToolContext, ScopeEntry

    ctx = RequestToolContext(
        allowed_scope=[ScopeEntry(code="by_customer", scope_type="OBJECT")],
        loader=MagicMock(),
    )
    # scene_id 和 library_id 都不匹配，但 object_code 精确匹配 → 允许
    assert (
        ctx.is_object_allowed("by_customer", scene_id="wrong_scene", library_id="wrong_lib") is True
    )
