"""T2: anchor_tools.py 改造 — 先红后绿

测试覆盖：
  - _activate_object_with_context() 权限校验、缓存路径、按需构建路径
  - _build_scope_filter() 授权范围 → search_ontology 参数
  - make_anchor_tools() 新 get_tool_context_fn 参数
  - goto_ontology / activate_anchor 调用 _activate_object 时透传 tool_context
"""
from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

# ── T2.1 _activate_object_with_context 可从模块级导入 ──────────────────────────


def test_activate_object_with_context_importable() -> None:
    from datacloud_analysis.tools.anchor_tools import _activate_object_with_context  # noqa: F401


# ── T2.1.a 权限拒绝 ────────────────────────────────────────────────────────────


def test_activate_object_with_context_denied_when_not_allowed() -> None:
    """is_object_allowed 返回 False 时返回 ([], <错误消息>)。"""
    from datacloud_analysis.tools.anchor_tools import _activate_object_with_context
    from datacloud_analysis.tools.request_tool_context import RequestToolContext, ScopeEntry

    tool_context = RequestToolContext(
        allowed_scope=[ScopeEntry(code="by_customer", scope_type="OBJECT")],
        loader=MagicMock(),
    )

    fake_platform = MagicMock()
    fake_platform.get_term_scope_info.return_value = {
        "library_id": "lib_other",
        "scene_id": "scene_other",
    }

    state: dict[str, Any] = {}

    with patch(
        "datacloud_analysis.tools.anchor_tools.get_platform",
        return_value=fake_platform,
    ):
        new_tools, err = _activate_object_with_context(state, "by_order", tool_context)

    assert new_tools == []
    assert "by_order" in err
    assert "拒绝" in err or "授权" in err


# ── T2.1.b 命中缓存，不重复构建 ───────────────────────────────────────────────


def test_activate_object_with_context_uses_cache() -> None:
    """object_code 已在 object_to_tools 中时，直接返回缓存工具，不调用 get_scene_details。"""
    from datacloud_analysis.tools.anchor_tools import _activate_object_with_context
    from datacloud_analysis.tools.request_tool_context import RequestToolContext, ScopeEntry

    tool_context = RequestToolContext(
        allowed_scope=[ScopeEntry(code="by_customer", scope_type="OBJECT")],
        loader=MagicMock(),
        object_to_tools={"by_customer": ["by_customer__query", "by_customer__count"]},
    )

    fake_platform = MagicMock()
    fake_platform.get_term_scope_info.return_value = {
        "library_id": "lib_crm",
        "scene_id": "scene_crm",
    }

    state: dict[str, Any] = {}

    with patch(
        "datacloud_analysis.tools.anchor_tools.get_platform",
        return_value=fake_platform,
    ):
        new_tools, err = _activate_object_with_context(state, "by_customer", tool_context)

    assert err == ""
    assert set(new_tools) == {"by_customer__query", "by_customer__count"}
    assert set(state.get("active_tools", [])) >= {"by_customer__query", "by_customer__count"}
    fake_platform.get_scene_details.assert_not_called()


def test_activate_object_with_context_cache_skips_already_active() -> None:
    """缓存命中但工具已在 active_tools 中时，new_tools 为空。"""
    from datacloud_analysis.tools.anchor_tools import _activate_object_with_context
    from datacloud_analysis.tools.request_tool_context import RequestToolContext, ScopeEntry

    tool_context = RequestToolContext(
        allowed_scope=[ScopeEntry(code="by_customer", scope_type="OBJECT")],
        loader=MagicMock(),
        object_to_tools={"by_customer": ["by_customer__query"]},
    )

    fake_platform = MagicMock()
    fake_platform.get_term_scope_info.return_value = {
        "library_id": "lib_crm",
        "scene_id": "scene_crm",
    }

    state: dict[str, Any] = {"active_tools": ["by_customer__query"]}

    with patch(
        "datacloud_analysis.tools.anchor_tools.get_platform",
        return_value=fake_platform,
    ):
        new_tools, err = _activate_object_with_context(state, "by_customer", tool_context)

    assert err == ""
    assert new_tools == []


# ── T2.1.c 按需构建：调用 platform + tool_loader ────────────────────────────────


def test_activate_object_with_context_builds_tools_on_miss() -> None:
    """缓存未命中时，调用 get_scene_details + load_from_content + OntologyToolLoader。"""
    from datacloud_analysis.tools.anchor_tools import _activate_object_with_context
    from datacloud_analysis.tools.request_tool_context import RequestToolContext, ScopeEntry

    loader = MagicMock()
    tool_context = RequestToolContext(
        allowed_scope=[ScopeEntry(code="by_customer", scope_type="OBJECT")],
        loader=loader,
    )

    fake_scene_detail = {"objects": [{"code": "by_customer"}]}
    fake_platform = MagicMock()
    fake_platform.get_term_scope_info.return_value = {
        "library_id": "lib_crm",
        "scene_id": "scene_crm",
    }
    fake_platform.get_scene_details.return_value = fake_scene_detail

    fake_tool = MagicMock()
    fake_tool._object_code = "by_customer"
    fake_tool_loader_instance = MagicMock()
    fake_tool_loader_instance.load.return_value = {"by_customer__query": fake_tool}
    fake_tool_loader_cls = MagicMock(return_value=fake_tool_loader_instance)

    state: dict[str, Any] = {}

    with (
        patch(
            "datacloud_analysis.tools.anchor_tools.get_platform",
            return_value=fake_platform,
        ),
        patch(
            "datacloud_analysis.tools.anchor_tools.OntologyToolLoader",
            fake_tool_loader_cls,
        ),
    ):
        new_tools, err = _activate_object_with_context(state, "by_customer", tool_context)

    assert err == ""
    assert "by_customer__query" in new_tools
    assert "by_customer__query" in tool_context.tools_map
    assert tool_context.object_to_tools["by_customer"] == ["by_customer__query"]
    loader.load_from_content.assert_called_once_with(fake_scene_detail)


# ── T2.3 _build_scope_filter ────────────────────────────────────────────────────


def test_build_scope_filter_importable() -> None:
    from datacloud_analysis.tools.anchor_tools import _build_scope_filter  # noqa: F401


def test_build_scope_filter_ontology_base() -> None:
    from datacloud_analysis.tools.anchor_tools import _build_scope_filter
    from datacloud_analysis.tools.request_tool_context import ScopeEntry

    scope = [ScopeEntry(code="lib_crm", scope_type="ONTOLOGY_BASE")]
    result = _build_scope_filter(scope)

    assert result["base_ids"] == ["lib_crm"]
    assert result["scene_ids"] == []
    assert result["object_codes"] == []
    assert result["view_codes"] == []


def test_build_scope_filter_scene() -> None:
    from datacloud_analysis.tools.anchor_tools import _build_scope_filter
    from datacloud_analysis.tools.request_tool_context import ScopeEntry

    scope = [ScopeEntry(code="scene_crm", scope_type="SCENE")]
    result = _build_scope_filter(scope)

    assert result["scene_ids"] == ["scene_crm"]
    assert result["base_ids"] == []


def test_build_scope_filter_object_and_view() -> None:
    from datacloud_analysis.tools.anchor_tools import _build_scope_filter
    from datacloud_analysis.tools.request_tool_context import ScopeEntry

    scope = [
        ScopeEntry(code="by_customer", scope_type="OBJECT"),
        ScopeEntry(code="v_sales", scope_type="VIEW"),
    ]
    result = _build_scope_filter(scope)

    assert result["object_codes"] == ["by_customer"]
    assert result["view_codes"] == ["v_sales"]
    assert result["base_ids"] == []
    assert result["scene_ids"] == []


def test_build_scope_filter_mixed() -> None:
    from datacloud_analysis.tools.anchor_tools import _build_scope_filter
    from datacloud_analysis.tools.request_tool_context import ScopeEntry

    scope = [
        ScopeEntry(code="lib_crm", scope_type="ONTOLOGY_BASE"),
        ScopeEntry(code="scene_sales", scope_type="SCENE"),
        ScopeEntry(code="by_order", scope_type="OBJECT"),
    ]
    result = _build_scope_filter(scope)

    assert result["base_ids"] == ["lib_crm"]
    assert result["scene_ids"] == ["scene_sales"]
    assert result["object_codes"] == ["by_order"]
    assert result["view_codes"] == []


# ── T2.2 make_anchor_tools 新签名 ──────────────────────────────────────────────


def test_make_anchor_tools_accepts_get_tool_context_fn() -> None:
    """make_anchor_tools 应接受 get_tool_context_fn 关键字参数。"""
    from datacloud_analysis.tools.anchor_tools import make_anchor_tools

    get_state_fn = MagicMock(return_value={})
    get_tool_context_fn = MagicMock(return_value=None)

    # 不应抛 TypeError
    tools = make_anchor_tools(get_state_fn, get_tool_context_fn=get_tool_context_fn)
    assert isinstance(tools, list)
    assert len(tools) > 0


def test_make_anchor_tools_old_signature_still_works() -> None:
    """仅传 get_state_fn 的旧调用方式不应报错（向后兼容）。"""
    from datacloud_analysis.tools.anchor_tools import make_anchor_tools

    get_state_fn = MagicMock(return_value={})
    tools = make_anchor_tools(get_state_fn)
    assert isinstance(tools, list)


# ── T2.4 goto_ontology 透传 tool_context ────────────────────────────────────────


def test_goto_ontology_passes_tool_context_to_activate() -> None:
    """goto_ontology 内部调用 _activate_object 时传入 tool_context。"""
    from datacloud_analysis.tools.anchor_tools import make_anchor_tools
    from datacloud_analysis.tools.request_tool_context import RequestToolContext, ScopeEntry

    tool_context = RequestToolContext(
        allowed_scope=[ScopeEntry(code="by_customer", scope_type="OBJECT")],
        loader=MagicMock(),
        object_to_tools={"by_customer": ["by_customer__query"]},
    )

    state: dict[str, Any] = {}
    get_state_fn = MagicMock(return_value=state)
    get_tool_context_fn = MagicMock(return_value=tool_context)

    tools = make_anchor_tools(get_state_fn, get_tool_context_fn=get_tool_context_fn)
    goto = next(t for t in tools if t.name == "goto_ontology")

    fake_platform = MagicMock()
    fake_platform.get_term_scope_info.return_value = {
        "library_id": "lib_crm",
        "scene_id": "scene_crm",
    }

    with patch(
        "datacloud_analysis.tools.anchor_tools.get_platform",
        return_value=fake_platform,
    ):
        result = goto.invoke({"object_code": "by_customer", "reason": "测试跳转"})

    assert "by_customer" in result
    # get_tool_context_fn 被调用说明 goto_ontology 确实拿到了 tool_context
    get_tool_context_fn.assert_called()


def test_activate_anchor_passes_tool_context() -> None:
    """activate_anchor（别名）同样透传 tool_context。"""
    from datacloud_analysis.tools.anchor_tools import make_anchor_tools
    from datacloud_analysis.tools.request_tool_context import RequestToolContext, ScopeEntry

    tool_context = RequestToolContext(
        allowed_scope=[ScopeEntry(code="by_customer", scope_type="OBJECT")],
        loader=MagicMock(),
        object_to_tools={"by_customer": ["by_customer__query"]},
    )

    state: dict[str, Any] = {}
    get_state_fn = MagicMock(return_value=state)
    get_tool_context_fn = MagicMock(return_value=tool_context)

    tools = make_anchor_tools(get_state_fn, get_tool_context_fn=get_tool_context_fn)
    activate = next(t for t in tools if t.name == "activate_anchor")

    fake_platform = MagicMock()
    fake_platform.get_term_scope_info.return_value = {
        "library_id": "lib_crm",
        "scene_id": "scene_crm",
    }

    with patch(
        "datacloud_analysis.tools.anchor_tools.get_platform",
        return_value=fake_platform,
    ):
        result = activate.invoke({"object_code": "by_customer"})

    assert "by_customer" in result
    get_tool_context_fn.assert_called()
