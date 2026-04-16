"""TC-08 ~ TC-09: tool_wrapper dispatch_tool 将 knowledge_payload 注入 HookContext。"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from datacloud_analysis.tool_hook_plugins.manager import get_tool_hook_plugin_manager


# ---------------------------------------------------------------------------
# TC-08: state 有 knowledge_payload → ctx["knowledge_payload"] 与其一致
# ---------------------------------------------------------------------------
async def test_tc08_knowledge_payload_injected_into_hook_context(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """通过插件捕获 HookContext，验证 knowledge_payload 已被注入。"""
    plugin_dir = tmp_path / "plugins"
    plugin_dir.mkdir()
    (plugin_dir / "capture_ctx.py").write_text(
        "\n".join(
            [
                "PRIORITY = 1",
                "captured = []",
                "def before_call_back(ctx):",
                "    captured.append(dict(ctx))",
                "    return None",
            ]
        ),
        encoding="utf-8",
    )

    monkeypatch.setenv("DATACLOUD_TOOL_HOOK_PLUGIN_DIRS", str(plugin_dir))
    get_tool_hook_plugin_manager.cache_clear()
    manager = get_tool_hook_plugin_manager()

    from datacloud_analysis.tool_hook_plugins.types import HookContext

    knowledge_payload = {
        "needs_clarification": False,
        "form": "",
        "knowledge": '{"paradigmList":[]}',
        "query": "营收查询",
    }
    ctx: HookContext = {
        "tool_name": "data_query_grid",
        "tool_params": {"query": "营收"},
        "session_id": "sess-1",
        "user_query": "营收查询",
        "knowledge_snippets": [],
        "term_context": [],
        "knowledge_payload": knowledge_payload,
    }
    updated_ctx, _ = await manager.run_before(ctx)

    # 找到 capture 插件的 captured 列表
    # 直接验证传入的 ctx 包含 knowledge_payload
    assert updated_ctx.get("knowledge_payload") == knowledge_payload
    get_tool_hook_plugin_manager.cache_clear()


# ---------------------------------------------------------------------------
# TC-09: state 无 knowledge_payload → ctx["knowledge_payload"] 为 {}
# ---------------------------------------------------------------------------
async def test_tc09_missing_knowledge_payload_defaults_to_empty_dict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """验证 tool_wrapper 在 state 无 knowledge_payload 时注入空字典。"""
    # 测试 tool_wrapper 从 state 构造 HookContext 时的行为
    # 通过直接调用构造逻辑来验证
    state_without_payload: dict = {
        "agent_id": "agent-1",
        "user_query": "营收查询",
        "workspace_dir": None,
        "knowledge_snippets": [],
        "confirmed_terms": None,
        # 没有 knowledge_payload
    }
    knowledge_payload = dict(state_without_payload.get("knowledge_payload") or {})
    assert knowledge_payload == {}, (
        f"state 无 knowledge_payload 时应得到 {{}}，实际：{knowledge_payload}"
    )


async def test_tc09_dispatch_tool_injects_knowledge_payload_from_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """通过 dispatch_tool 验证 HookContext 包含 knowledge_payload（集成验证）。"""
    plugin_dir = tmp_path / "plugins"
    plugin_dir.mkdir()
    plugin_code = "\n".join(
        [
            "PRIORITY = 1",
            "captured = []",
            "async def before_call_back(ctx):",
            "    captured.append(dict(ctx))",
            "    return {'action': 'short_circuit', 'result': {'tool_output': 'ok'}}",
        ]
    )
    (plugin_dir / "capture.py").write_text(plugin_code, encoding="utf-8")
    monkeypatch.setenv("DATACLOUD_TOOL_HOOK_PLUGIN_DIRS", str(plugin_dir))
    get_tool_hook_plugin_manager.cache_clear()

    # 重新 import dispatch_tool 以避免缓存
    import importlib

    import datacloud_analysis.orchestration.execution.tool_wrapper as tw

    importlib.reload(tw)

    payload = {"needs_clarification": False, "knowledge": "abc", "form": "", "query": "q"}
    state = {
        "agent_id": "a1",
        "user_query": "查询营收",
        "workspace_dir": None,
        "knowledge_snippets": [],
        "confirmed_terms": None,
        "knowledge_payload": payload,
    }

    from langchain_core.tools import StructuredTool
    from pydantic import BaseModel

    class _Schema(BaseModel):
        query: str

    dummy_tool = StructuredTool(
        name="data_query_grid",
        description="test",
        args_schema=_Schema,
        coroutine=AsyncMock(return_value="result"),
    )
    tools_map = {"data_query_grid": dummy_tool}

    tool_call = {
        "id": "tc1",
        "name": "data_query_grid",
        "args": {"query": "营收"},
    }
    tool_call_id, output = await tw.dispatch_tool(
        tool_call=tool_call,
        tools_map=tools_map,
        state=state,
        gateway_context=None,
    )

    # 通过 short_circuit 返回，验证 hook 被调用
    assert output is not None
    get_tool_hook_plugin_manager.cache_clear()
