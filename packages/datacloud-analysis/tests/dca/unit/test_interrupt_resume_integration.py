"""TC-18, TC-19, TC-20, TC-21: 查询澄清中断/恢复集成测试（dispatch_tool 层，无需 LLM）。

测试层级：dispatch_tool + ToolHookPluginManager + query_clarification_plugin
不需要 LangGraph 图级别的 checkpoint/resume（因此不需要真实 LLM）。

关键技巧：
- 将 langgraph.types.interrupt 打补丁为 return_value=resume_value，
  使 before_call_back 中的 interrupt() 调用直接返回用户选择的 paradigmList，
  而不是抛出 GraphBubbleUp。
- 通过 dispatch_tool 直接驱动 hook → 工具调用链，验证 _apply_resume_to_params 输出。

测试覆盖：
- TC-18: query_* 工具 → resume → OQL 结构化参数（select/where/group_by/order_by）
- TC-19: data_query_* 工具 → resume → query + contextKnowledge（中文字段映射）
- TC-20: compute_* 工具 → resume → dimensions/metrics
- TC-21: data_query_* 工具既有 knowledge 又有 needs_clarification → 选择 interrupt 路径（clarification 优先）

TC-27 的两阶段中断行为（GraphBubbleUp raise → resume return）在此文件的配套测试中也覆盖：
- test_tc27_interrupt_first_call_raises_graph_bubble_up
- test_tc27_interrupt_resume_second_call_returns_value
"""
from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from datacloud_analysis.tool_hook_plugins.manager import get_tool_hook_plugin_manager


# ---------------------------------------------------------------------------
# autouse fixture：确保 datacloud_data_sdk.context 在每个测试前可用
# ---------------------------------------------------------------------------
# test_llm_integration.py 在 pytest 收集阶段（collection）被 import，
# 此时会向 sys.modules 注入一个缺少 .context 子模块的 datacloud_data_sdk mock。
# 由于 collection 在所有测试执行之前完成，本文件的模块级注入代码已失效。
# 改为 autouse fixture，在每个测试用例执行前动态补充 .context。


@pytest.fixture(autouse=True)
def _ensure_sdk_context_mock() -> None:  # type: ignore[return]
    """在每次测试执行前确保 datacloud_data_sdk.context 存在。"""
    import sys
    import types

    if "datacloud_data_sdk" in sys.modules:
        _sdk = sys.modules["datacloud_data_sdk"]
        if "datacloud_data_sdk.context" not in sys.modules:
            _ctx_mod = types.ModuleType("datacloud_data_sdk.context")

            class _FakeInvocationContext:
                def __init__(self, **kwargs: object) -> None:
                    self._kwargs = kwargs

                def __enter__(self) -> "_FakeInvocationContext":
                    return self

                def __exit__(self, *args: object) -> None:
                    pass

            _ctx_mod.InvocationContext = _FakeInvocationContext  # type: ignore[attr-defined]
            sys.modules["datacloud_data_sdk.context"] = _ctx_mod
            _sdk.context = _ctx_mod  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# 辅助：工具 schema & factory
# ---------------------------------------------------------------------------

class _DataQuerySchema(BaseModel):
    query: str = Field(description="查询语句")
    contextKnowledge: str = Field(default="", description="上下文知识")


class _QueryGridSchema(BaseModel):
    select: list[str] = Field(default_factory=list)
    where: list[Any] = Field(default_factory=list)
    group_by: list[Any] = Field(default_factory=list)
    order_by: list[Any] = Field(default_factory=list)


class _ComputeGridSchema(BaseModel):
    dimensions: list[dict] = Field(default_factory=list)
    metrics: list[dict] = Field(default_factory=list)


def _make_state(
    tool_name: str,
    knowledge_payload: dict | None = None,
    extra_payload: dict | None = None,
) -> dict:
    """构造含 knowledge_payload 的测试 state。"""
    return {
        "agent_id": "test-interrupt",
        "user_query": "营收利润汇总",
        "workspace_dir": None,
        "knowledge_snippets": None,
        "confirmed_terms": None,
        "knowledge_payload": knowledge_payload or {},
        **(extra_payload or {}),
    }


def _paradigm_revenue() -> dict:
    return {"name": "营收", "fieldName": "企业总营收（万元）"}


def _paradigm_profit() -> dict:
    return {"name": "利润", "fieldName": "企业总利润（万元）"}


def _paradigm_dim() -> dict:
    return {"dimensionName": "企业经济效益等级"}


def _paradigm_metric() -> dict:
    return {"metricName": "企业总营收（万元）", "agg": "sum"}


# ---------------------------------------------------------------------------
# TC-27 两阶段中断行为（GraphBubbleUp raise → resume return）
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_tc27_interrupt_first_call_raises_graph_bubble_up() -> None:
    """TC-27: before_hook 中 interrupt() 抛 GraphBubbleUp → dispatch_tool 向上透传（不被 except Exception 吞掉）。

    注：在测试环境（非 LangGraph 执行上下文）中 interrupt() 本身不会抛 GraphBubbleUp，
    因此用 patch 将 interrupt 替换为直接抛 GraphBubbleUp 的 mock，
    从而验证「dispatch_tool 正确透传 GraphBubbleUp」这一核心特性。
    """
    from langgraph.errors import GraphBubbleUp
    from datacloud_analysis.orchestration.execution.tool_wrapper import dispatch_tool

    payload = {
        "needs_clarification": True,
        "form": json.dumps({"paradigmList": [_paradigm_revenue()]}),
        "knowledge": "",
        "query": "营收汇总",
    }
    state = _make_state("data_query_grid", knowledge_payload=payload)

    tool = StructuredTool(
        name="data_query_grid",
        description="test",
        args_schema=_DataQuerySchema,
        coroutine=AsyncMock(return_value={"records": [], "meta": {}}),
    )
    tools_map = {"data_query_grid": tool}
    tool_call = {"id": "tc27a", "name": "data_query_grid", "args": {"query": "营收"}}

    def _raising_interrupt(value: Any) -> Any:
        raise GraphBubbleUp("interrupt signal")

    get_tool_hook_plugin_manager.cache_clear()
    try:
        with patch("langgraph.types.interrupt", side_effect=_raising_interrupt):
            with pytest.raises(GraphBubbleUp):
                await dispatch_tool(
                    tool_call=tool_call, tools_map=tools_map, state=state, gateway_context=None
                )
    finally:
        get_tool_hook_plugin_manager.cache_clear()


@pytest.mark.asyncio
async def test_tc27_interrupt_resume_second_call_returns_value_and_tool_receives_params() -> None:
    """TC-27: interrupt() 被 mock 返回 resume_value → _apply_resume_to_params 运行 → tool 以正确参数被调用。

    模拟 LangGraph resume 语义：interrupt() 在 resume 路径上直接返回用户选择的值。
    """
    from datacloud_analysis.orchestration.execution.tool_wrapper import dispatch_tool

    resume_value = {"paradigmList": [_paradigm_revenue(), _paradigm_profit()]}
    payload = {
        "needs_clarification": True,
        "form": json.dumps({"paradigmList": [_paradigm_revenue(), _paradigm_profit()]}),
        "knowledge": "",
        "query": "高效益网格营收利润",
    }
    state = _make_state("data_query_grid", knowledge_payload=payload)

    captured_calls: list[dict] = []

    async def _tool_coroutine(query: str, contextKnowledge: str = "", **kwargs: Any) -> dict:
        captured_calls.append({"query": query, "contextKnowledge": contextKnowledge})
        return {"records": [], "meta": {}}

    tool = StructuredTool(
        name="data_query_grid",
        description="test",
        args_schema=_DataQuerySchema,
        coroutine=_tool_coroutine,
    )
    tools_map = {"data_query_grid": tool}
    tool_call = {"id": "tc27b", "name": "data_query_grid", "args": {"query": "营收"}}

    get_tool_hook_plugin_manager.cache_clear()
    try:
        with patch("langgraph.types.interrupt", return_value=resume_value):
            await dispatch_tool(tool_call=tool_call, tools_map=tools_map, state=state, gateway_context=None)
    finally:
        get_tool_hook_plugin_manager.cache_clear()

    assert len(captured_calls) == 1, f"工具应被调用一次，实际：{len(captured_calls)}"
    call = captured_calls[0]
    assert call["query"] == "高效益网格营收利润", f"query 应来自 payload.query，实际：{call['query']!r}"
    assert "营收 → 企业总营收（万元）" in call["contextKnowledge"], (
        f"contextKnowledge 应含字段映射，实际：{call['contextKnowledge']!r}"
    )
    assert "利润 → 企业总利润（万元）" in call["contextKnowledge"]


# ---------------------------------------------------------------------------
# TC-18: query_* 工具 → resume → OQL 结构化参数
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_tc18_query_star_resume_produces_oql_params() -> None:
    """TC-18: data_query_grid（query_* 类型）resume 后收到 select/where/group_by/order_by。

    注：工具前缀为 query_（非 data_query_）时走 OQL 分支。
    """
    from datacloud_analysis.orchestration.execution.tool_wrapper import dispatch_tool

    resume_value = {
        "paradigmList": [
            {"fieldName": "企业总营收（万元）"},
            {"fieldName": "企业总利润（万元）"},
        ]
    }
    payload = {
        "needs_clarification": True,
        "form": json.dumps(resume_value),
        "knowledge": "",
        "query": "营收利润查询",
    }
    state = _make_state("query_grid", knowledge_payload=payload)

    captured_calls: list[dict] = []

    async def _tool_coroutine(**kwargs: Any) -> dict:
        captured_calls.append(kwargs)
        return {"records": [], "meta": {}}

    tool = StructuredTool(
        name="query_grid",
        description="test",
        args_schema=_QueryGridSchema,
        coroutine=_tool_coroutine,
    )
    tools_map = {"query_grid": tool}
    tool_call = {"id": "tc18", "name": "query_grid", "args": {"select": []}}

    get_tool_hook_plugin_manager.cache_clear()
    try:
        with patch("langgraph.types.interrupt", return_value=resume_value):
            await dispatch_tool(tool_call=tool_call, tools_map=tools_map, state=state, gateway_context=None)
    finally:
        get_tool_hook_plugin_manager.cache_clear()

    assert len(captured_calls) == 1
    call = captured_calls[0]
    # _apply_resume_to_params → query_* 分支 → select/where/group_by/order_by
    assert "select" in call, f"OQL 参数应含 select，实际：{call}"
    assert "企业总营收（万元）" in call["select"]
    assert "企业总利润（万元）" in call["select"]
    assert "where" in call
    assert "group_by" in call
    assert "order_by" in call
    assert "query" not in call, "query_* 工具参数不应含 query 字段（已被 OQL 替换）"


# ---------------------------------------------------------------------------
# TC-19: data_query_* 工具 → resume → query + contextKnowledge
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_tc19_data_query_star_resume_produces_query_and_context_knowledge() -> None:
    """TC-19: data_query_* 工具 resume 后收到 query（来自 payload.query）和 contextKnowledge（字段映射）。"""
    from datacloud_analysis.orchestration.execution.tool_wrapper import dispatch_tool

    resume_value = {
        "paradigmList": [_paradigm_revenue(), _paradigm_profit()]
    }
    payload = {
        "needs_clarification": True,
        "form": json.dumps(resume_value),
        "knowledge": "",
        "query": "高效益网格的营收利润汇总",
    }
    state = _make_state("data_query_enterprise", knowledge_payload=payload)

    captured_calls: list[dict] = []

    async def _tool_coroutine(query: str, contextKnowledge: str = "", **kwargs: Any) -> dict:
        captured_calls.append({"query": query, "contextKnowledge": contextKnowledge})
        return {"records": [], "meta": {}}

    tool = StructuredTool(
        name="data_query_enterprise",
        description="test",
        args_schema=_DataQuerySchema,
        coroutine=_tool_coroutine,
    )
    tools_map = {"data_query_enterprise": tool}
    tool_call = {
        "id": "tc19",
        "name": "data_query_enterprise",
        "args": {"query": "营收利润（含歧义原始参数）"},
    }

    get_tool_hook_plugin_manager.cache_clear()
    try:
        with patch("langgraph.types.interrupt", return_value=resume_value):
            await dispatch_tool(tool_call=tool_call, tools_map=tools_map, state=state, gateway_context=None)
    finally:
        get_tool_hook_plugin_manager.cache_clear()

    assert len(captured_calls) == 1
    call = captured_calls[0]
    assert call["query"] == "高效益网格的营收利润汇总", (
        f"query 应取自 payload.query（规范化结果），实际：{call['query']!r}"
    )
    assert "营收 → 企业总营收（万元）" in call["contextKnowledge"]
    assert "利润 → 企业总利润（万元）" in call["contextKnowledge"]


@pytest.mark.asyncio
async def test_tc19_original_llm_params_are_discarded_on_resume() -> None:
    """TC-19: resume 后 tool_params 整体替换，含歧义的 LLM 原始参数被完全丢弃。"""
    from datacloud_analysis.orchestration.execution.tool_wrapper import dispatch_tool

    resume_value = {"paradigmList": [_paradigm_revenue()]}
    payload = {
        "needs_clarification": True,
        "form": json.dumps(resume_value),
        "knowledge": "",
        "query": "规范化后的营收查询",
    }
    state = _make_state("data_query_grid", knowledge_payload=payload)

    captured_kwargs: list[dict] = []

    async def _tool_coroutine(**kwargs: Any) -> dict:
        captured_kwargs.append(kwargs)
        return {"records": [], "meta": {}}

    tool = StructuredTool(
        name="data_query_grid",
        description="test",
        args_schema=_DataQuerySchema,
        coroutine=_tool_coroutine,
    )
    tools_map = {"data_query_grid": tool}
    # LLM 原始参数（含含歧义字段）
    tool_call = {
        "id": "tc19b",
        "name": "data_query_grid",
        "args": {
            "query": "含歧义的原始参数",
            "contextKnowledge": "LLM 自己填写的旧值",
        },
    }

    get_tool_hook_plugin_manager.cache_clear()
    try:
        with patch("langgraph.types.interrupt", return_value=resume_value):
            await dispatch_tool(tool_call=tool_call, tools_map=tools_map, state=state, gateway_context=None)
    finally:
        get_tool_hook_plugin_manager.cache_clear()

    assert captured_kwargs, "工具应被调用"
    call = captured_kwargs[0]
    assert call.get("query") == "规范化后的营收查询", (
        f"LLM 含歧义 query 应被 payload.query 替换，实际：{call.get('query')!r}"
    )
    assert call.get("contextKnowledge") != "LLM 自己填写的旧值", (
        "LLM 填写的旧 contextKnowledge 应被系统值替换"
    )


# ---------------------------------------------------------------------------
# TC-20: compute_* 工具 → resume → dimensions/metrics
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_tc20_compute_star_resume_produces_dimensions_and_metrics() -> None:
    """TC-20: compute_* 工具 resume 后收到 dimensions/metrics 结构（来自 paradigmList）。"""
    from datacloud_analysis.orchestration.execution.tool_wrapper import dispatch_tool

    resume_value = {
        "paradigmList": [
            _paradigm_dim(),                                    # dimensionName
            _paradigm_metric(),                                  # metricName + agg
            {"metricName": "企业总利润（万元）"},                 # agg 缺省 → sum
        ]
    }
    payload = {
        "needs_clarification": True,
        "form": json.dumps(resume_value),
        "knowledge": "",
        "query": "效益等级分组营收利润",
    }
    state = _make_state("compute_grid", knowledge_payload=payload)

    captured_calls: list[dict] = []

    async def _tool_coroutine(**kwargs: Any) -> dict:
        captured_calls.append(kwargs)
        return {"records": [], "meta": {}}

    tool = StructuredTool(
        name="compute_grid",
        description="test",
        args_schema=_ComputeGridSchema,
        coroutine=_tool_coroutine,
    )
    tools_map = {"compute_grid": tool}
    tool_call = {"id": "tc20", "name": "compute_grid", "args": {}}

    get_tool_hook_plugin_manager.cache_clear()
    try:
        with patch("langgraph.types.interrupt", return_value=resume_value):
            await dispatch_tool(tool_call=tool_call, tools_map=tools_map, state=state, gateway_context=None)
    finally:
        get_tool_hook_plugin_manager.cache_clear()

    assert len(captured_calls) == 1
    call = captured_calls[0]

    assert "dimensions" in call, f"compute_* 应有 dimensions，实际：{call}"
    assert "metrics" in call, f"compute_* 应有 metrics，实际：{call}"
    assert {"field": "企业经济效益等级"} in call["dimensions"]
    assert {"field": "企业总营收（万元）", "agg": "sum"} in call["metrics"]
    # agg 缺省补 sum
    assert {"field": "企业总利润（万元）", "agg": "sum"} in call["metrics"]
    assert "query" not in call, "compute_* 参数不应含 query 字段"


@pytest.mark.asyncio
async def test_tc20_compute_empty_paradigm_list_produces_empty_dims_metrics() -> None:
    """TC-20 边界：paradigmList 为空 → dimensions/metrics 均为空列表。"""
    from datacloud_analysis.orchestration.execution.tool_wrapper import dispatch_tool

    resume_value = {"paradigmList": []}
    payload = {
        "needs_clarification": True,
        "form": json.dumps(resume_value),
        "knowledge": "",
        "query": "空选择结果",
    }
    state = _make_state("compute_enterprise", knowledge_payload=payload)

    captured_calls: list[dict] = []

    async def _tool_coroutine(**kwargs: Any) -> dict:
        captured_calls.append(kwargs)
        return {"records": [], "meta": {}}

    tool = StructuredTool(
        name="compute_enterprise",
        description="test",
        args_schema=_ComputeGridSchema,
        coroutine=_tool_coroutine,
    )
    tools_map = {"compute_enterprise": tool}
    tool_call = {"id": "tc20b", "name": "compute_enterprise", "args": {}}

    get_tool_hook_plugin_manager.cache_clear()
    try:
        with patch("langgraph.types.interrupt", return_value=resume_value):
            await dispatch_tool(tool_call=tool_call, tools_map=tools_map, state=state, gateway_context=None)
    finally:
        get_tool_hook_plugin_manager.cache_clear()

    assert captured_calls
    call = captured_calls[0]
    assert call.get("dimensions") == [], f"空 paradigmList → dimensions 应为空，实际：{call}"
    assert call.get("metrics") == [], f"空 paradigmList → metrics 应为空，实际：{call}"


# ---------------------------------------------------------------------------
# TC-21: data_query_* 同时有 knowledge 且 needs_clarification → 走 interrupt（优先）
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_tc21_needs_clarification_takes_priority_over_knowledge_injection() -> None:
    """TC-21: needs_clarification=True 且 knowledge 非空 → interrupt 路径优先（不走层 B 直接注入）。

    即：两者并存时 _apply_resume_to_params 路径胜出，contextKnowledge 由 paradigmList 生成。
    """
    from datacloud_analysis.orchestration.execution.tool_wrapper import dispatch_tool

    raw_knowledge = '{"paradigmList":[{"name":"亩产","fieldName":"物理网格亩产效益（万元/亩）"}]}'
    resume_paradigm = [_paradigm_revenue()]  # 用户最终选了"营收"
    resume_value = {"paradigmList": resume_paradigm}

    payload = {
        "needs_clarification": True,          # ← 有歧义
        "form": json.dumps(resume_value),
        "knowledge": raw_knowledge,           # ← 且有 knowledge（两者并存）
        "query": "高效益网格的营收汇总",
    }
    state = _make_state("data_query_grid", knowledge_payload=payload)

    captured_calls: list[dict] = []

    async def _tool_coroutine(query: str, contextKnowledge: str = "", **kwargs: Any) -> dict:
        captured_calls.append({"query": query, "contextKnowledge": contextKnowledge})
        return {"records": [], "meta": {}}

    tool = StructuredTool(
        name="data_query_grid",
        description="test",
        args_schema=_DataQuerySchema,
        coroutine=_tool_coroutine,
    )
    tools_map = {"data_query_grid": tool}
    tool_call = {"id": "tc21", "name": "data_query_grid", "args": {"query": "原始参数"}}

    get_tool_hook_plugin_manager.cache_clear()
    try:
        with patch("langgraph.types.interrupt", return_value=resume_value):
            await dispatch_tool(tool_call=tool_call, tools_map=tools_map, state=state, gateway_context=None)
    finally:
        get_tool_hook_plugin_manager.cache_clear()

    assert captured_calls, "工具应被调用"
    call = captured_calls[0]

    # query 取自 payload.query（由 _apply_resume_to_params 设置）
    assert call["query"] == "高效益网格的营收汇总"

    # contextKnowledge 由用户最终选择的 paradigmList 生成（营收），而非直接取 knowledge
    assert "营收 → 企业总营收（万元）" in call["contextKnowledge"], (
        f"contextKnowledge 应由用户选择的 paradigmList 生成，实际：{call['contextKnowledge']!r}"
    )
    # 原始 knowledge 中的亩产不应出现（已被用户选择替换）
    assert "亩产" not in call["contextKnowledge"], (
        f"用户未选亩产，contextKnowledge 不应含亩产，实际：{call['contextKnowledge']!r}"
    )


# ---------------------------------------------------------------------------
# TC-21 追加：非数据工具在 needs_clarification=True 时不触发 interrupt
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_tc21_non_data_tool_not_affected_by_clarification_flag() -> None:
    """TC-21 补充：非数据工具（send_email）即使 knowledge_payload.needs_clarification=True 也不触发 interrupt。"""
    from datacloud_analysis.orchestration.execution.tool_wrapper import dispatch_tool
    from langgraph.errors import GraphBubbleUp

    payload = {
        "needs_clarification": True,
        "form": json.dumps({"paradigmList": [_paradigm_revenue()]}),
        "knowledge": "",
        "query": "发送邮件",
    }
    state = _make_state("send_email", knowledge_payload=payload)

    class _SendEmailSchema(BaseModel):
        to: str
        subject: str = ""

    tool = StructuredTool(
        name="send_email",
        description="test",
        args_schema=_SendEmailSchema,
        coroutine=AsyncMock(return_value="sent"),
    )
    tools_map = {"send_email": tool}
    tool_call = {"id": "tc21b", "name": "send_email", "args": {"to": "test@example.com"}}

    get_tool_hook_plugin_manager.cache_clear()
    try:
        # 不应抛 GraphBubbleUp（send_email 不是数据工具，插件直接跳过）
        tool_call_id, result = await dispatch_tool(
            tool_call=tool_call,
            tools_map=tools_map,
            state=state,
            gateway_context=None,
        )
    finally:
        get_tool_hook_plugin_manager.cache_clear()

    # 工具正常调用并返回
    assert result is not None
