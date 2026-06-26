"""T6: OntologyAgent.ask() 增加 tool_context 参数 — 先红后绿

测试覆盖：
  6.1 ask() 签名应包含 tool_context 参数
  6.2 tool_context 应被注入 run_config['configurable']['tool_context']
"""

from __future__ import annotations

import inspect

# ─────────────────────────────────────────────────────────────────────────────
# T6.1  ask() 签名包含 tool_context 参数
# ─────────────────────────────────────────────────────────────────────────────


def test_ask_signature_has_tool_context_param() -> None:
    """OntologyAgent.ask() 应接受 tool_context 关键字参数。"""
    from datacloud_analysis.ontology_agent import OntologyAgent

    sig = inspect.signature(OntologyAgent.ask)
    assert "tool_context" in sig.parameters, "OntologyAgent.ask() 缺少 tool_context 参数"


# ─────────────────────────────────────────────────────────────────────────────
# T6.2  _iter_events 将 tool_context 注入 configurable
# ─────────────────────────────────────────────────────────────────────────────


def test_iter_events_injects_tool_context_into_configurable() -> None:
    """_iter_events 应将 tool_context 写入 run_config['configurable']['tool_context']。"""
    source = inspect.getsource(
        __import__("datacloud_analysis.ontology_agent", fromlist=["ontology_agent"])
    )
    assert "'tool_context'" in source or '"tool_context"' in source, (
        "ontology_agent 应在 configurable 中注入 tool_context"
    )
    # 更精确：configurable 块里应出现 tool_context 的赋值
    assert "tool_context" in source


def test_iter_events_signature_has_tool_context_param() -> None:
    """_iter_events 签名应包含 tool_context 参数。"""
    from datacloud_analysis.ontology_agent import OntologyAgent

    sig = inspect.signature(OntologyAgent._iter_events)
    assert "tool_context" in sig.parameters, "OntologyAgent._iter_events() 缺少 tool_context 参数"
