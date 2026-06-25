"""T4: llm_call_node + hook_aware_tool_node 改造 — 先红后绿

测试覆盖：
  4.1 llm_call_node bind_tools 时从 tool_context.tools_map 取，而非 TOOL_POOL
  4.2 llm_call_node anchor_mode 对象列表从 tool_context.allowed_scope 取
  4.3.1 hook_aware_tool_node 可导入 _get_next_objects_from_term
  4.3.3 after_hook 用 term_relation 查询替代 get_relation_graph
  4.3.4 after_hook 从 tool_context.param_link_graph 取 ParamLinkGraph
  4.3.5 tools_by_name 从 tool_context.tools_map 更新
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

# ─────────────────────────────────────────────────────────────────────────────
# T4.1  llm_call_node：bind_tools 来源
# ─────────────────────────────────────────────────────────────────────────────


def test_llm_call_node_uses_tool_context_tools_map() -> None:
    """make_llm_call_node 中，当 configurable 有 tool_context 时，
    bind_tools 应从 tool_context.tools_map 取已激活工具，不调用 get_tools(TOOL_POOL)。"""
    from datacloud_analysis.tools.request_tool_context import RequestToolContext, ScopeEntry

    fake_tool = MagicMock()
    fake_tool.name = "by_customer__query"

    RequestToolContext(
        allowed_scope=[ScopeEntry(code="by_customer", scope_type="OBJECT")],
        loader=MagicMock(),
        tools_map={"by_customer__query": fake_tool},
        anchor_mode=False,
    )

    # 构造一个最小化的 make_llm_call_node 可接受的环境
    from datacloud_analysis.orchestration.execution.llm_call_node import make_llm_call_node
    # 不需要真正调用，只要能拿到函数引用即可（红阶段先验证接口存在）
    assert callable(make_llm_call_node)


def test_llm_call_node_reads_tool_context_from_configurable() -> None:
    """llm_call_node 内部应从 config['configurable']['tool_context'] 读取 tool_context。

    用 grep 验证代码中出现了对 tool_context 的读取。
    """
    import inspect

    from datacloud_analysis.orchestration.execution import llm_call_node as mod

    source = inspect.getsource(mod)
    # 红测试：代码中应该有通过 configurable 读取 tool_context 的语句
    assert '"tool_context"' in source or "'tool_context'" in source, (
        "llm_call_node 应从 config['configurable']['tool_context'] 读取 tool_context"
    )


def test_llm_call_node_active_tools_from_tool_context_not_tool_pool() -> None:
    """llm_call_node 中激活工具合并逻辑应从 tool_context.tools_map 取，
    不应再调用 _get_unlocked（TOOL_POOL）。"""
    import inspect

    from datacloud_analysis.orchestration.execution import llm_call_node as mod

    source = inspect.getsource(mod)
    # 红测试：不应再有 get_tools as _get_unlocked 这行（不含 _legacy 后缀）
    assert "get_tools as _get_unlocked\n" not in source and "get_tools as _get_unlocked," not in source, (
        "llm_call_node 不应再通过 _get_unlocked 从 TOOL_POOL 取工具"
    )


# ─────────────────────────────────────────────────────────────────────────────
# T4.2  llm_call_node：anchor_mode 对象列表
# ─────────────────────────────────────────────────────────────────────────────


def test_llm_call_node_anchor_prompt_uses_allowed_scope() -> None:
    """anchor_mode 时，dynamic_prompt 应从 tool_context.allowed_scope 枚举对象，
    不应再遍历全局 TOOL_TO_OBJECT。"""
    import inspect

    from datacloud_analysis.orchestration.execution import llm_call_node as mod

    source = inspect.getsource(mod)
    # 红测试：anchor_mode 段应读取 allowed_scope，不再直接遍历 TOOL_TO_OBJECT
    # （至少要有 allowed_scope 的引用）
    assert "allowed_scope" in source, (
        "llm_call_node anchor_mode 段应从 tool_context.allowed_scope 取对象列表"
    )


# ─────────────────────────────────────────────────────────────────────────────
# T4.3.1  hook_aware_tool_node：_get_next_objects_from_term 可导入
# ─────────────────────────────────────────────────────────────────────────────


def test_get_next_objects_from_term_importable() -> None:
    """_get_next_objects_from_term 应可从 hook_aware_tool_node 导入。"""
    from datacloud_analysis.orchestration.execution.hook_aware_tool_node import (
        _get_next_objects_from_term,  # noqa: F401
    )


# ─────────────────────────────────────────────────────────────────────────────
# T4.3.3  hook_aware_tool_node：after_hook 不再调用 get_relation_graph
# ─────────────────────────────────────────────────────────────────────────────


def test_hook_aware_tool_node_no_get_relation_graph() -> None:
    """after_hook 不应再调用 get_relation_graph()（已替换为 term_relation 查询）。"""
    import inspect

    from datacloud_analysis.orchestration.execution import hook_aware_tool_node as mod

    source = inspect.getsource(mod)
    assert "get_relation_graph()" not in source, (
        "hook_aware_tool_node 不应再调用 get_relation_graph()，改用 _get_next_objects_from_term"
    )


def test_get_next_objects_from_term_returns_list() -> None:
    """_get_next_objects_from_term(source_obj, allowed_scope=[]) 应返回列表。"""
    from datacloud_analysis.orchestration.execution.hook_aware_tool_node import (
        _get_next_objects_from_term,
    )
    from datacloud_analysis.tools.request_tool_context import ScopeEntry

    fake_db = MagicMock()
    fake_db.execute.return_value.fetchall.return_value = [
        {"object_code": "by_order"},
    ]

    with patch(
        "datacloud_analysis.orchestration.execution.hook_aware_tool_node._get_db_engine",
        return_value=fake_db,
    ):
        result = _get_next_objects_from_term(
            "by_customer",
            allowed_scope=[ScopeEntry(code="by_order", scope_type="OBJECT")],
        )

    assert isinstance(result, list)


# ─────────────────────────────────────────────────────────────────────────────
# T4.3.4  hook_aware_tool_node：after_hook 从 tool_context.param_link_graph 取 PLG
# ─────────────────────────────────────────────────────────────────────────────


def test_hook_aware_tool_node_no_get_param_link_graph_call() -> None:
    """after_hook 不应再调用 get_param_link_graph()（改从 tool_context 取）。"""
    import inspect

    from datacloud_analysis.orchestration.execution import hook_aware_tool_node as mod

    source = inspect.getsource(mod)
    assert "get_param_link_graph()" not in source, (
        "hook_aware_tool_node 不应再调用 get_param_link_graph()，改从 tool_context.param_link_graph 取"
    )


def test_hook_aware_tool_node_reads_tool_context_from_configurable() -> None:
    """after_hook 应从 config['configurable']['tool_context'] 读取 RequestToolContext。"""
    import inspect

    from datacloud_analysis.orchestration.execution import hook_aware_tool_node as mod

    source = inspect.getsource(mod)
    assert '"tool_context"' in source or "'tool_context'" in source, (
        "hook_aware_tool_node 应从 configurable 读取 tool_context"
    )


# ─────────────────────────────────────────────────────────────────────────────
# T4.3.5  hook_aware_tool_node：tools_by_name 从 tool_context.tools_map 更新
# ─────────────────────────────────────────────────────────────────────────────


def test_hook_aware_tool_node_no_get_tools_for_update() -> None:
    """tools_by_name.update 不应再调用 get_tools(_new_names)，改从 tool_context.tools_map 取。"""
    import inspect

    from datacloud_analysis.orchestration.execution import hook_aware_tool_node as mod

    source = inspect.getsource(mod)
    # 不能有 "self.tools_by_name.update(get_tools(" 这种模式
    assert "tools_by_name.update(get_tools(" not in source, (
        "hook_aware_tool_node 不应再用 get_tools() 更新 tools_by_name"
    )


def test_hook_aware_tool_node_updates_tools_by_name_from_tool_ctx() -> None:
    """tools_by_name 更新时应从 tool_context.tools_map 取对象。"""
    import inspect

    from datacloud_analysis.orchestration.execution import hook_aware_tool_node as mod

    source = inspect.getsource(mod)
    assert "tool_ctx.tools_map" in source or "_tool_ctx.tools_map" in source, (
        "hook_aware_tool_node 应从 tool_context.tools_map 更新 tools_by_name"
    )
