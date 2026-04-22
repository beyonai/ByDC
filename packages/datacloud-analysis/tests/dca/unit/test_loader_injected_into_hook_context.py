"""T19-1 ~ T19-3：loader 注入 HookContext["metadata"]["loader"] 验证。

Bug 描述：
    create_agent(loader=X) 中的 loader 只被 OntologyToolLoader 消费（生成工具闭包），
    但 dispatch_tool 构建 HookContext 时没有 "metadata" 键，
    导致 query_clarification_plugin 的字段映射功能无法获取 loader，
    字段名→字段码映射功能形同虚设（总是 loader not available 警告）。

修复要求：
    dispatch_tool 新增 keyword-only 参数 loader，
    在构建 HookContext 时写入 ctx["metadata"]["loader"]。
    build_analysis_graph / execution_node 将 loader 透传到 dispatch_tool。
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ── T19-1：dispatch_tool 将 loader 写入 ctx["metadata"]["loader"] ─────────────


@pytest.mark.asyncio
async def test_T19_1_dispatch_tool_injects_loader_into_ctx() -> None:
    """T19-1：dispatch_tool 传入 loader 时，before_call_back 收到的 ctx 含 metadata.loader。"""
    from datacloud_analysis.orchestration.execution.tool_wrapper import dispatch_tool

    captured_ctx: dict = {}

    async def _fake_before(ctx: dict) -> tuple[dict, None]:
        captured_ctx.update(ctx)
        return ctx, None

    async def _fake_after(ctx: dict) -> tuple[dict, None]:
        return ctx, None

    fake_hook_manager = MagicMock()
    fake_hook_manager.run_before = AsyncMock(side_effect=_fake_before)
    fake_hook_manager.run_after = AsyncMock(side_effect=_fake_after)

    fake_tool = AsyncMock(return_value={"result": "ok"})
    fake_tool._is_agent_delegate = False

    fake_loader = MagicMock(name="OntologyLoader")

    state = {"agent_id": "test-session", "user_query": "测试查询"}
    tool_call = {"name": "query_foo", "args": {"reason": "test", "query": "test"}, "id": "tc-1"}

    with patch(
        "datacloud_analysis.orchestration.execution.tool_wrapper.get_tool_hook_plugin_manager",
        return_value=fake_hook_manager,
    ):
        await dispatch_tool(
            tool_call,
            {"query_foo": fake_tool},
            state,
            loader=fake_loader,
        )

    assert "metadata" in captured_ctx, "HookContext 应包含 'metadata' 键"
    assert captured_ctx["metadata"].get("loader") is fake_loader, (
        f"ctx['metadata']['loader'] 应为传入的 loader，实际: {captured_ctx.get('metadata')}"
    )


# ── T19-2：不传 loader 时 metadata 键为空字典（不报错）────────────────────────


@pytest.mark.asyncio
async def test_T19_2_dispatch_tool_no_loader_metadata_empty() -> None:
    """T19-2：dispatch_tool 不传 loader（默认 None）时，ctx['metadata'] 为空字典。"""
    from datacloud_analysis.orchestration.execution.tool_wrapper import dispatch_tool

    captured_ctx: dict = {}

    async def _fake_before(ctx: dict) -> tuple[dict, None]:
        captured_ctx.update(ctx)
        return ctx, None

    async def _fake_after(ctx: dict) -> tuple[dict, None]:
        return ctx, None

    fake_hook_manager = MagicMock()
    fake_hook_manager.run_before = AsyncMock(side_effect=_fake_before)
    fake_hook_manager.run_after = AsyncMock(side_effect=_fake_after)

    fake_tool = AsyncMock(return_value={"result": "ok"})
    fake_tool._is_agent_delegate = False

    state = {"agent_id": "test-session", "user_query": "测试"}
    tool_call = {"name": "query_bar", "args": {"reason": "test", "query": "test"}, "id": "tc-2"}

    with patch(
        "datacloud_analysis.orchestration.execution.tool_wrapper.get_tool_hook_plugin_manager",
        return_value=fake_hook_manager,
    ):
        await dispatch_tool(
            tool_call,
            {"query_bar": fake_tool},
            state,
            # 不传 loader，应默认为 None
        )

    # metadata 键应存在但 loader 为 None（_get_field_catalog 中有 None 判断）
    assert "metadata" in captured_ctx, "不传 loader 时 HookContext 也应包含 'metadata' 键"
    assert captured_ctx["metadata"].get("loader") is None, (
        f"不传 loader 时 metadata.loader 应为 None，实际: {captured_ctx.get('metadata')}"
    )


# ── T19-3：build_analysis_graph 接受 loader 并传递到 execution_node ───────────


def test_T19_3_build_analysis_graph_accepts_loader() -> None:
    """T19-3：build_analysis_graph 应接受 loader 参数，不抛出 TypeError。"""
    from datacloud_analysis.orchestration.graph_builder import build_analysis_graph

    fake_loader = MagicMock(name="OntologyLoader")

    # 不应抛 TypeError
    graph = build_analysis_graph(loader=fake_loader)
    assert graph is not None, "build_analysis_graph 应返回 StateGraph"
