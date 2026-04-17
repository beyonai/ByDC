"""TC-10, TC-11, TC-36: 知识增强管道集成测试（无需 LLM，无需外部 API）。

测试范围（单进程内全真实调用，run_react_loop 除外）：
- TC-10: knowledge_enhancer（async callable）→ intend_node 写入 knowledge_snippets，
         execution_node 将其注入 system_prompt；用 mock enhancer 模拟真实返回值
- TC-11: knowledge_snippets 格式为可读中文字段映射（"营收 → 企业总营收（万元）"），
         不含原始 JSON 结构
- TC-36: v2 设计：ambiguous_params=[] → 插件跳过，_call_query_clarification 不触发；
         ambiguous_params 非空 → _call_query_clarification 被调用

注：mock enhancer 的返回数据与 datacloud-knowledge 包的 rule-based 实现一致，
    因此本测试既不依赖特定包版本，也不需要网络。
"""

from __future__ import annotations

import json
import sys
import types
from contextlib import contextmanager, suppress
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import HumanMessage


@contextmanager
def _patch_analyze_query_clarification(mock_result: Any):
    """临时注入 datacloud_knowledge.intent.analyze_query_clarification 的 mock。

    插件通过动态 import 调用此函数，直接 patch sys.modules 里的模块属性
    可以覆盖正式加载和动态加载两种场景。

    注意：仅在模块已存在时修改属性；如需创建假模块则在退出时删除，避免污染后续测试。
    """
    dk_key = "datacloud_knowledge"
    intent_key = "datacloud_knowledge.intent"

    created_dk = dk_key not in sys.modules
    created_intent = intent_key not in sys.modules

    if created_dk:
        sys.modules[dk_key] = types.ModuleType(dk_key)
    if created_intent:
        sys.modules[intent_key] = types.ModuleType(intent_key)

    intent_mod = sys.modules[intent_key]
    had_attr = hasattr(intent_mod, "analyze_query_clarification")
    original = getattr(intent_mod, "analyze_query_clarification", None)
    call_count = [0]

    async def _fake_analyze(*args: Any, **kwargs: Any) -> Any:
        call_count[0] += 1
        return mock_result

    intent_mod.analyze_query_clarification = _fake_analyze  # type: ignore[attr-defined]
    try:
        yield call_count
    finally:
        if had_attr and original is not None:
            intent_mod.analyze_query_clarification = original  # type: ignore[attr-defined]
        else:
            with suppress(AttributeError):
                delattr(intent_mod, "analyze_query_clarification")
        if created_intent:
            sys.modules.pop(intent_key, None)
        if created_dk:
            sys.modules.pop(dk_key, None)


# ---------------------------------------------------------------------------
# 辅助：模拟 knowledge enhancer 的返回对象
# ---------------------------------------------------------------------------

_GRID_KNOWLEDGE_JSON = json.dumps(
    {
        "paradigmList": [
            {"name": "营收", "fieldName": "企业总营收（万元）"},
            {"name": "利润", "fieldName": "企业总利润（万元）"},
            {"name": "亩产", "fieldName": "物理网格亩产效益（万元/亩）"},
        ]
    },
    ensure_ascii=False,
)

_INDUSTRY_FORM_JSON = json.dumps(
    {
        "paradigmList": [
            {"name": "产业链", "fieldName": ""},
            {"name": "环节", "fieldName": "所属产业环节名称"},
        ]
    },
    ensure_ascii=False,
)


def _make_knowledge_result(
    *,
    needs_clarification: bool = False,
    form: str = "",
    knowledge: str = "",
    query: str = "原始查询",
) -> Any:
    """构造模拟 analyze_query_clarification 返回的 ClarificationResult 对象。"""
    result = MagicMock()
    result.needs_clarification = needs_clarification
    result.form = form
    result.knowledge = knowledge
    result.query = query
    return result


async def _grid_knowledge_enhancer(
    query: str, gateway_context: Any = None, message_pid: str = ""
) -> Any:
    """模拟高效益网格知识查询的 enhancer（有 knowledge，无歧义）。"""
    return _make_knowledge_result(
        needs_clarification=False,
        knowledge=_GRID_KNOWLEDGE_JSON,
        query="高效益网格的营收、利润、亩产汇总",
    )


async def _industry_clarification_enhancer(
    query: str, gateway_context: Any = None, message_pid: str = ""
) -> Any:
    """模拟产业链查询的 enhancer（有歧义，无 knowledge）。"""
    return _make_knowledge_result(
        needs_clarification=True,
        form=_INDUSTRY_FORM_JSON,
        knowledge="",
        query="信息技术链上游龙头企业数汇总",
    )


async def _passthrough_enhancer(
    query: str, gateway_context: Any = None, message_pid: str = ""
) -> Any:
    """模拟透传查询的 enhancer（无知识，无歧义）。"""
    return _make_knowledge_result(
        needs_clarification=False,
        knowledge="",
        query=query,
    )


def _make_state(query: str, **extra: Any) -> dict:
    return {
        "messages": [HumanMessage(content=query)],
        "agent_id": "test-integration",
        "workspace_dir": None,
        "user_query": None,
        "knowledge_payload": None,
        "knowledge_snippets": None,
        **extra,
    }


def _make_config() -> dict:
    return {"configurable": {}}


# ---------------------------------------------------------------------------
# TC-10: enhancer 返回 knowledge → intend_node 写入 knowledge_snippets
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tc10_knowledge_enhancer_produces_snippets() -> None:
    """TC-10: knowledge 非空 → intend_node 写入 knowledge_snippets。"""
    from datacloud_analysis.orchestration.intend.node import intend_node

    result = await intend_node(
        _make_state("高效益网格的营收"),
        _make_config(),
        knowledge_enhancer=_grid_knowledge_enhancer,
    )

    snippets = result.get("knowledge_snippets")
    assert snippets is not None, "knowledge 非空时 intend_node 应写入 knowledge_snippets"
    assert isinstance(snippets, list)
    assert len(snippets) >= 1


@pytest.mark.asyncio
async def test_tc10_knowledge_payload_written_by_intend_node() -> None:
    """TC-10: intend_node 将 enhancer 结果缓存到 knowledge_payload。"""
    from datacloud_analysis.orchestration.intend.node import intend_node

    result = await intend_node(
        _make_state("高效益网格的营收"),
        _make_config(),
        knowledge_enhancer=_grid_knowledge_enhancer,
    )

    payload = result.get("knowledge_payload")
    assert payload is not None
    assert isinstance(payload.get("knowledge"), str)
    assert payload["knowledge"] != ""
    assert payload.get("needs_clarification") is False


# ---------------------------------------------------------------------------
# TC-11: knowledge_snippets 格式为可读中文字段映射
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tc11_knowledge_snippets_are_readable_field_mapping() -> None:
    """TC-11: knowledge_snippets 为可读字段映射格式（含 →），不含 JSON 键。"""
    from datacloud_analysis.orchestration.intend.node import intend_node

    result = await intend_node(
        _make_state("高效益网格的营收"),
        _make_config(),
        knowledge_enhancer=_grid_knowledge_enhancer,
    )

    snippets = result.get("knowledge_snippets") or []
    combined = "\n".join(str(s) for s in snippets)
    assert "→" in combined, f"snippets 应为可读字段映射格式：{combined!r}"
    assert "paradigmList" not in combined, f"snippets 不应含原始 JSON 键：{combined!r}"
    assert '"keyword"' not in combined


@pytest.mark.asyncio
async def test_tc11_knowledge_snippets_contain_chinese_field_names() -> None:
    """TC-11: snippets 包含中文字段名（营收 → 企业总营收（万元））。"""
    from datacloud_analysis.orchestration.intend.node import intend_node

    result = await intend_node(
        _make_state("营收查询"),
        _make_config(),
        knowledge_enhancer=_grid_knowledge_enhancer,
    )

    snippets = result.get("knowledge_snippets") or []
    combined = "\n".join(str(s) for s in snippets)
    assert "营收 → 企业总营收（万元）" in combined, f"snippets 应含中文字段映射：{combined!r}"
    assert "利润 → 企业总利润（万元）" in combined


# ---------------------------------------------------------------------------
# TC-10/11 full pipeline: intend_node → state → execution_node system_prompt
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tc10_tc11_full_pipeline_system_prompt_contains_knowledge() -> None:
    """TC-10/11 集成：intend_node 写入 snippets → execution_node 将其注入 system_prompt。"""
    from datacloud_analysis.orchestration.execution.node import execution_node
    from datacloud_analysis.orchestration.intend.node import intend_node

    query = "高效益网格的营收利润"
    state = _make_state(query)
    config = _make_config()

    # Step 1: intend_node with mock enhancer
    intend_updates = await intend_node(state, config, knowledge_enhancer=_grid_knowledge_enhancer)

    # Step 2: 合并 state
    merged_state = {
        **state,
        **intend_updates,
        "confirmed_terms": None,
        "react_rounds": None,
        "react_checkpoint": None,
        "react_final": None,
        "execution_status": "execution",
    }
    merged_state["user_query"] = merged_state.get("user_query") or query

    # Step 3: execution_node，mock run_react_loop 以捕获 system_prompt
    captured_prompts: list[str] = []

    async def _mock_react_loop(
        state: Any,
        tools_list: Any,
        system_prompt: str,
        max_rounds: int,
        gateway_context: Any = None,
    ) -> dict:
        captured_prompts.append(system_prompt)
        return {
            "react_rounds": 0,
            "react_final": {"answer": "", "result_type": "text"},
            "messages": [],
        }

    with patch(
        "datacloud_analysis.orchestration.execution.node.run_react_loop",
        side_effect=_mock_react_loop,
    ):
        await execution_node(merged_state, config)

    assert captured_prompts, "run_react_loop 应被调用一次"
    system_prompt = captured_prompts[0]

    assert "数据查询知识增强" in system_prompt, (
        f"system_prompt 应含知识增强段落，实际长度 {len(system_prompt)}"
    )
    assert "→" in system_prompt, "system_prompt 应含可读字段映射（→）"
    assert "paradigmList" not in system_prompt, "system_prompt 不应含原始 JSON 键"
    assert "营收 → 企业总营收（万元）" in system_prompt


@pytest.mark.asyncio
async def test_tc10_passthrough_query_no_knowledge_in_system_prompt() -> None:
    """TC-10 对照组：透传查询（无 knowledge）→ system_prompt 不含知识增强段落。"""
    from datacloud_analysis.orchestration.execution.node import execution_node
    from datacloud_analysis.orchestration.intend.node import intend_node

    query = "帮我查看最新进展"
    state = _make_state(query)
    config = _make_config()

    intend_updates = await intend_node(state, config, knowledge_enhancer=_passthrough_enhancer)

    merged_state = {
        **state,
        **intend_updates,
        "confirmed_terms": None,
        "react_rounds": None,
        "react_checkpoint": None,
        "react_final": None,
        "execution_status": "execution",
    }
    merged_state["user_query"] = merged_state.get("user_query") or query

    captured_prompts: list[str] = []

    async def _mock_react_loop(state, tools_list, system_prompt, max_rounds, gateway_context=None):
        captured_prompts.append(system_prompt)
        return {
            "react_rounds": 0,
            "react_final": {"answer": "", "result_type": "text"},
            "messages": [],
        }

    with patch(
        "datacloud_analysis.orchestration.execution.node.run_react_loop",
        side_effect=_mock_react_loop,
    ):
        await execution_node(merged_state, config)

    assert captured_prompts
    assert "数据查询知识增强" not in captured_prompts[0], "透传查询 system_prompt 不应含增强段落"


# ---------------------------------------------------------------------------
# TC-36: v2 设计 — ambiguous_params 控制澄清触发
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tc36_empty_ambiguous_params_skips_query_clarification() -> None:
    """TC-36 v2：ambiguous_params=[] → 插件直接跳过，_call_query_clarification 不触发。

    这是 v2 设计的核心行为：工具调用时 LLM 若无歧义（ambiguous_params=[]），
    插件不调用澄清接口，直接放行。
    """
    from datacloud_analysis.orchestration.execution.tool_wrapper import dispatch_tool
    from datacloud_analysis.tool_hook_plugins.manager import get_tool_hook_plugin_manager
    from langchain_core.tools import StructuredTool
    from pydantic import BaseModel, ConfigDict, Field

    class _Schema(BaseModel):
        model_config = ConfigDict(populate_by_name=True)

        query: str
        context_knowledge: str = Field(default="", alias="contextKnowledge")

    tool = StructuredTool(
        name="data_query_grid",
        description="test",
        args_schema=_Schema,
        coroutine=AsyncMock(return_value={"records": [], "meta": {}}),
    )
    tools_map = {"data_query_grid": tool}
    # ambiguous_params=[] → 插件 skip
    tool_call = {
        "id": "tc36-call",
        "name": "data_query_grid",
        "args": {
            "query": "营收",
            "ambiguous_params": [],  # 空：无歧义，跳过澄清
        },
    }

    state = {
        "agent_id": "tc36-agent",
        "user_query": "高效益网格的营收",
        "workspace_dir": None,
        "knowledge_snippets": None,
        "confirmed_terms": None,
    }

    clarification_spy = AsyncMock(
        return_value=MagicMock(needs_clarification=False, form="", knowledge="")
    )

    with patch(
        "datacloud_analysis.tool_hook_plugins.builtin.query_clarification_plugin._call_query_clarification",
        new=clarification_spy,
    ):
        get_tool_hook_plugin_manager.cache_clear()
        try:
            await dispatch_tool(
                tool_call=tool_call,
                tools_map=tools_map,
                state=state,
                gateway_context=None,
            )
        finally:
            get_tool_hook_plugin_manager.cache_clear()

    # ambiguous_params=[] → 插件跳过，_call_query_clarification 不应被调用
    clarification_spy.assert_not_called()


@pytest.mark.asyncio
async def test_tc36_multiple_tool_calls_no_ambiguity_skip_clarification() -> None:
    """TC-36 v2：同一请求多次工具调用，ambiguous_params=[] → 均跳过澄清接口。"""
    from datacloud_analysis.orchestration.execution.tool_wrapper import dispatch_tool
    from datacloud_analysis.tool_hook_plugins.manager import get_tool_hook_plugin_manager
    from langchain_core.tools import StructuredTool
    from pydantic import BaseModel, ConfigDict, Field

    class _Schema(BaseModel):
        model_config = ConfigDict(populate_by_name=True)

        query: str
        context_knowledge: str = Field(default="", alias="contextKnowledge")

    tool = StructuredTool(
        name="data_query_grid",
        description="test",
        args_schema=_Schema,
        coroutine=AsyncMock(return_value={"records": [], "meta": {}}),
    )
    tools_map = {"data_query_grid": tool}

    state = {
        "agent_id": "tc36b",
        "user_query": "营收利润查询",
        "workspace_dir": None,
        "knowledge_snippets": None,
        "confirmed_terms": None,
    }

    clarification_spy = AsyncMock(
        return_value=MagicMock(needs_clarification=False, form="", knowledge="")
    )

    with patch(
        "datacloud_analysis.tool_hook_plugins.builtin.query_clarification_plugin._call_query_clarification",
        new=clarification_spy,
    ):
        get_tool_hook_plugin_manager.cache_clear()
        try:
            # 第一次工具调用（ambiguous_params=[]）
            await dispatch_tool(
                tool_call={
                    "id": "c1",
                    "name": "data_query_grid",
                    "args": {"query": "营收", "ambiguous_params": []},
                },
                tools_map=tools_map,
                state=state,
                gateway_context=None,
            )
            # 第二次工具调用（同样无歧义）
            await dispatch_tool(
                tool_call={
                    "id": "c2",
                    "name": "data_query_grid",
                    "args": {"query": "利润", "ambiguous_params": []},
                },
                tools_map=tools_map,
                state=state,
                gateway_context=None,
            )
        finally:
            get_tool_hook_plugin_manager.cache_clear()

    # 两次工具调用均不触发澄清接口
    clarification_spy.assert_not_called()


@pytest.mark.asyncio
async def test_tc36_non_empty_ambiguous_params_triggers_query_clarification(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """TC-36 v2 对照组：ambiguous_params 非空 → analyze_query_clarification 被触发。

    使用 _patch_analyze_query_clarification 直接 patch sys.modules 里的函数，
    绕过 ToolHookPluginManager 动态加载导致正式模块 patch 无效的问题。
    """

    from datacloud_analysis.orchestration.execution.tool_wrapper import dispatch_tool
    from datacloud_analysis.tool_hook_plugins.manager import get_tool_hook_plugin_manager
    from langchain_core.tools import StructuredTool
    from pydantic import BaseModel, ConfigDict, Field

    class _Schema(BaseModel):
        model_config = ConfigDict(populate_by_name=True)

        query: str
        context_knowledge: str = Field(default="", alias="contextKnowledge")

    tool = StructuredTool(
        name="data_query_grid",
        description="test",
        args_schema=_Schema,
        coroutine=AsyncMock(return_value={"records": [], "meta": {}}),
    )
    tools_map = {"data_query_grid": tool}

    state = {
        "agent_id": "tc36c",
        "user_query": "营收",
        "workspace_dir": None,
        "knowledge_snippets": None,
        "confirmed_terms": None,
    }

    mock_result = MagicMock(needs_clarification=False, form="", knowledge="")

    with _patch_analyze_query_clarification(mock_result) as call_count:
        get_tool_hook_plugin_manager.cache_clear()
        try:
            await dispatch_tool(
                tool_call={
                    "id": "tc36c-call",
                    "name": "data_query_grid",
                    "args": {
                        "query": "营收",
                        "ambiguous_params": ["metric_field"],  # 非空 → 触发澄清
                    },
                },
                tools_map=tools_map,
                state=state,
                gateway_context=None,
            )
        finally:
            get_tool_hook_plugin_manager.cache_clear()

    # ambiguous_params 非空 → analyze_query_clarification 应被调用一次
    assert call_count[0] == 1, f"ambiguous_params 非空应触发澄清接口，实际调用次数：{call_count[0]}"
