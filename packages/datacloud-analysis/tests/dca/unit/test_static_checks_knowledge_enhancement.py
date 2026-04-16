"""TC-37: 静态检查 — AgentState 含 knowledge_snippets / knowledge_payload 字段定义。

验证 datacloud_analysis/orchestration/state.py 中的 AgentState 包含
知识增强方案所需的两个 state 字段，防止字段被意外删除导致框架层逻辑静默失效。
"""

from __future__ import annotations

import typing


def _get_agent_state_annotations() -> dict[str, object]:
    """收集 AgentState 的全部类型注解（含继承链）。"""
    from datacloud_analysis.orchestration.state import AgentState

    # get_type_hints 会递归展开 TypedDict 继承链中的所有字段
    try:
        return typing.get_type_hints(AgentState)
    except Exception:
        # 备用：直接读 __annotations__（不展开继承，但字段定义在 AgentState 本身）
        hints: dict[str, object] = {}
        for cls in reversed(AgentState.__mro__):
            hints.update(getattr(cls, "__annotations__", {}))
        return hints


def test_tc37_agent_state_has_knowledge_payload_field() -> None:
    """AgentState 包含 knowledge_payload 字段，供 intend_node 写入、tool_wrapper 读取。"""
    hints = _get_agent_state_annotations()
    assert "knowledge_payload" in hints, (
        "AgentState 缺少 knowledge_payload 字段——知识增强方案依赖此字段在节点间传递缓存数据"
    )


def test_tc37_agent_state_has_knowledge_snippets_field() -> None:
    """AgentState 包含 knowledge_snippets 字段，供 intend_node 写入、execution_node 注入 system_prompt。"""
    hints = _get_agent_state_annotations()
    assert "knowledge_snippets" in hints, (
        "AgentState 缺少 knowledge_snippets 字段——层 A 知识注入依赖此字段"
    )


def test_tc37_knowledge_payload_allows_none() -> None:
    """knowledge_payload 字段类型允许 None（未调用 knowledge_enhancer 时的初始状态）。"""
    from datacloud_analysis.orchestration.state import AgentState

    annotation = AgentState.__annotations__.get("knowledge_payload", "")
    annotation_str = str(annotation)
    # 检查注解含 None（Optional / Union[..., None]）
    assert "None" in annotation_str, f"knowledge_payload 应允许 None，实际注解：{annotation_str}"


def test_tc37_knowledge_snippets_allows_none() -> None:
    """knowledge_snippets 字段类型允许 None（无知识增强时的透传状态）。"""
    from datacloud_analysis.orchestration.state import AgentState

    annotation = AgentState.__annotations__.get("knowledge_snippets", "")
    annotation_str = str(annotation)
    assert "None" in annotation_str, f"knowledge_snippets 应允许 None，实际注解：{annotation_str}"


def test_tc37_hook_context_has_knowledge_payload_field() -> None:
    """HookContext TypedDict 包含 knowledge_payload 字段（tool_wrapper 注入 ctx 后 before_hook 可读取）。"""
    from datacloud_analysis.tool_hook_plugins.types import HookContext

    hints = typing.get_type_hints(HookContext)
    assert "knowledge_payload" in hints, (
        "HookContext 缺少 knowledge_payload 字段——before_hook 读取缓存依赖此字段"
    )
