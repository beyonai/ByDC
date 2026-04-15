"""TC-26, TC-28: ToolHookPluginManager GraphBubbleUp 透传修复测试。"""
from __future__ import annotations

from pathlib import Path

import pytest

from datacloud_analysis.tool_hook_plugins.manager import (
    ToolHookPluginManager,
    _LoadedToolHookPlugin,
)
from datacloud_analysis.tool_hook_plugins.types import HookContext


# ---------------------------------------------------------------------------
# 辅助：尝试导入 GraphBubbleUp，不可用时用自定义类代替
# ---------------------------------------------------------------------------
try:
    from langgraph.errors import GraphBubbleUp
except ImportError:
    class GraphBubbleUp(Exception):  # type: ignore[no-redef]
        """Placeholder for langgraph.errors.GraphBubbleUp."""


def _make_plugin(before_cb) -> _LoadedToolHookPlugin:
    return _LoadedToolHookPlugin(
        plugin_id="test.plugin",
        priority=1,
        enabled=True,
        tool_allowlist=(),
        tool_blocklist=(),
        before_call_back=before_cb,
        after_call_back=None,
        source="test",
    )


def _make_ctx(tool_name: str = "data_query_grid") -> HookContext:
    return {
        "tool_name": tool_name,
        "tool_params": {},
        "user_query": "test",
        "knowledge_payload": {},
        "knowledge_snippets": [],
        "term_context": [],
    }


# ---------------------------------------------------------------------------
# TC-26: before_call_back 抛出 GraphBubbleUp → 不被 except Exception 吞掉，透传
# ---------------------------------------------------------------------------
async def test_tc26_graph_bubble_up_propagates_through_manager() -> None:
    def raising_callback(ctx):
        raise GraphBubbleUp("interrupt signal")

    plugin = _make_plugin(raising_callback)
    manager = ToolHookPluginManager([plugin])

    with pytest.raises(GraphBubbleUp, match="interrupt signal"):
        await manager.run_before(_make_ctx())


# ---------------------------------------------------------------------------
# TC-28: before_call_back 抛出普通 Exception → 被记录，返回 None，执行继续
# ---------------------------------------------------------------------------
async def test_tc28_ordinary_exception_is_swallowed_and_logged(
    caplog: pytest.LogCaptureFixture,
) -> None:
    def bad_callback(ctx):
        raise ValueError("plugin error")

    plugin = _make_plugin(bad_callback)
    manager = ToolHookPluginManager([plugin])

    import logging
    with caplog.at_level(logging.WARNING):
        ctx, decision = await manager.run_before(_make_ctx())

    assert decision is None, "普通异常不应导致 fail decision（非 strict 模式）"
    # 日志应有警告
    assert any("plugin error" in r.message or "bad_callback" in r.message or "test.plugin" in r.message
                for r in caplog.records), f"应有警告日志，实际：{[r.message for r in caplog.records]}"


# ---------------------------------------------------------------------------
# 额外：GraphBubbleUp 在 async callback 中也能透传
# ---------------------------------------------------------------------------
async def test_tc26_async_graph_bubble_up_propagates() -> None:
    async def async_raising_callback(ctx):
        raise GraphBubbleUp("async interrupt")

    plugin = _make_plugin(async_raising_callback)
    manager = ToolHookPluginManager([plugin])

    with pytest.raises(GraphBubbleUp, match="async interrupt"):
        await manager.run_before(_make_ctx())
