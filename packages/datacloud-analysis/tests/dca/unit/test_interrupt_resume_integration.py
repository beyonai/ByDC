"""TC-18, TC-19, TC-20, TC-21: 查询澄清中断/恢复集成测试（dispatch_tool 层，无需 LLM）。

测试层级：dispatch_tool + ToolHookPluginManager + query_clarification_plugin
不需要 LangGraph 图级别的 checkpoint/resume（因此不需要真实 LLM）。

关键技巧（v2 设计）：
- 插件从 tool_params 读取 ambiguous_params 元字段来决定是否触发澄清
- 插件通过 ToolHookPluginManager 动态加载（模块名为随机 hash，与正式注册模块不同），
  因此 patch 正式模块路径的 _call_query_clarification 无效。
  正确做法是 patch 底层延迟导入目标：datacloud_knowledge.intent.analyze_query_clarification
- 将 langgraph.types.interrupt 打补丁为 return_value=resume_value，
  使 before_call_back 中的 interrupt() 调用直接返回用户选择的 paradigmList

测试覆盖：
- TC-18: query_* 工具 → resume → OQL 结构化参数（select/where/group_by/order_by）
- TC-19: data_query_* 工具 → resume → query + contextKnowledge（中文字段映射）
- TC-20: compute_* 工具 → resume → dimensions/metrics
- TC-21: data_query_* 工具既有 knowledge 又有 needs_clarification → interrupt 路径（clarification 优先）

TC-27 的两阶段中断行为（GraphBubbleUp raise → resume return）在此文件的配套测试中也覆盖：
- test_tc27_interrupt_first_call_raises_graph_bubble_up
- test_tc27_interrupt_resume_second_call_returns_value
"""

from __future__ import annotations

import json
import sys
import types
from contextlib import contextmanager, suppress
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from datacloud_analysis.tool_hook_plugins.manager import get_tool_hook_plugin_manager
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# autouse fixture：确保 datacloud_data_sdk.context 在每个测试前可用
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _ensure_sdk_context_mock() -> None:  # type: ignore[return]
    """在每次测试执行前确保 datacloud_data_sdk.context 存在。"""
    if "datacloud_data_sdk" in sys.modules:
        _sdk = sys.modules["datacloud_data_sdk"]
        if "datacloud_data_sdk.context" not in sys.modules:
            _ctx_mod = types.ModuleType("datacloud_data_sdk.context")

            class _FakeInvocationContext:
                def __init__(self, **kwargs: object) -> None:
                    self._kwargs = kwargs

                def __enter__(self) -> _FakeInvocationContext:
                    return self

                def __exit__(self, *args: object) -> None:
                    pass

            _ctx_mod.InvocationContext = _FakeInvocationContext  # type: ignore[attr-defined]
            sys.modules["datacloud_data_sdk.context"] = _ctx_mod
            _sdk.context = _ctx_mod  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# 辅助：patch datacloud_knowledge.intent.analyze_query_clarification
#
# 插件的 _call_query_clarification 内部做了延迟导入：
#   from datacloud_knowledge.intent import analyze_query_clarification
# 无论插件被正式加载还是动态加载（hash 模块名），最终都从
# sys.modules["datacloud_knowledge.intent"] 取 analyze_query_clarification。
# 因此 patch 这个路径能同时覆盖两种加载场景。
# ---------------------------------------------------------------------------


@contextmanager
def _patch_analyze_query_clarification(mock_result: Any):
    """临时注入 datacloud_knowledge.intent.analyze_query_clarification 的 mock。

    插件的 _call_query_clarification 内部做延迟导入：
      from datacloud_knowledge.intent import analyze_query_clarification
    无论插件被正式加载还是动态加载，最终都从
    sys.modules["datacloud_knowledge.intent"].analyze_query_clarification 取值。

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

    async def _fake_analyze(*args: Any, **kwargs: Any) -> Any:
        return mock_result

    intent_mod.analyze_query_clarification = _fake_analyze  # type: ignore[attr-defined]
    try:
        yield
    finally:
        # 还原：先恢复属性，再清理我们创建的假模块
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
# 辅助：工具 schema & factory
# ---------------------------------------------------------------------------


class _DataQuerySchema(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    query: str = Field(description="查询语句")
    context_knowledge: str = Field(default="", alias="contextKnowledge", description="上下文知识")


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
    """构造测试 state（插件 v2 不再读取 knowledge_payload，保留为空）。"""
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


def _make_clarification_result(
    *,
    needs_clarification: bool,
    form: str = "",
    knowledge: str = "",
) -> Any:
    """构造 mock 的 analyze_query_clarification 返回值。"""
    result = MagicMock()
    result.needs_clarification = needs_clarification
    result.form = form
    result.knowledge = knowledge
    return result


# ---------------------------------------------------------------------------
# TC-27 两阶段中断行为（GraphBubbleUp raise → resume return）
# ---------------------------------------------------------------------------


@pytest.mark.skip(
    reason="V0.2->V0.3: before_call_back now raises ClarificationNeededError instead of interrupt()"
)
@pytest.mark.asyncio
async def test_tc27_interrupt_first_call_raises_graph_bubble_up() -> None:
    """TC-27: before_hook 中 interrupt() 抛 GraphBubbleUp → dispatch_tool 向上透传（不被 except Exception 吞掉）。

    新插件设计：通过 tool_call args 中的 ambiguous_params 触发澄清，
    analyze_query_clarification 返回 needs_clarification=True，
    再 patch interrupt 为 raising_interrupt 来验证 GraphBubbleUp 透传。
    """
    from datacloud_analysis.orchestration.execution.tool_wrapper import dispatch_tool
    from langgraph.errors import GraphBubbleUp

    resume_paradigm = [_paradigm_revenue()]
    mock_result = _make_clarification_result(
        needs_clarification=True,
        form=json.dumps({"paradigmList": resume_paradigm}),
    )

    state = _make_state("data_query_grid")

    tool = StructuredTool(
        name="data_query_grid",
        description="test",
        args_schema=_DataQuerySchema,
        coroutine=AsyncMock(return_value={"records": [], "meta": {}}),
    )
    tools_map = {"data_query_grid": tool}
    # ambiguous_params 在 args 中，插件剥离后触发澄清
    tool_call = {
        "id": "tc27a",
        "name": "data_query_grid",
        "args": {
            "query": "营收",
            "ambiguous_params": ["time_range"],
        },
    }

    def _raising_interrupt(value: Any) -> Any:
        raise GraphBubbleUp("interrupt signal")

    get_tool_hook_plugin_manager.cache_clear()
    try:
        with (
            _patch_analyze_query_clarification(mock_result),
            patch("langgraph.types.interrupt", side_effect=_raising_interrupt),
            pytest.raises(GraphBubbleUp),
        ):
            await dispatch_tool(
                tool_call=tool_call, tools_map=tools_map, state=state, gateway_context=None
            )
    finally:
        get_tool_hook_plugin_manager.cache_clear()


@pytest.mark.skip(
    reason="V0.2->V0.3: before_call_back now raises ClarificationNeededError instead of interrupt()"
)
@pytest.mark.asyncio
async def test_tc27_interrupt_resume_second_call_returns_value_and_tool_receives_params() -> None:
    """TC-27: interrupt() 被 mock 返回 resume_value → _apply_resume_to_params 运行 → tool 以正确参数被调用。

    新插件设计：ambiguous_params 在 tool_call args 中，analyze_query_clarification
    返回 needs_clarification=True，interrupt() mock 返回 resume_value（用户选择）。
    """
    from datacloud_analysis.orchestration.execution.tool_wrapper import dispatch_tool

    resume_value = {"paradigmList": [_paradigm_revenue(), _paradigm_profit()]}
    mock_result = _make_clarification_result(
        needs_clarification=True,
        form=json.dumps(resume_value),
    )

    # user_query 来自 state，resume 后 _apply_resume_to_params 用它填 query
    state = _make_state("data_query_grid")
    state["user_query"] = "高效益网格营收利润"

    captured_calls: list[dict] = []

    async def _tool_coroutine(query: str, context_knowledge: str = "", **kwargs: Any) -> dict:
        captured_calls.append({"query": query, "contextKnowledge": context_knowledge})
        return {"records": [], "meta": {}}

    tool = StructuredTool(
        name="data_query_grid",
        description="test",
        args_schema=_DataQuerySchema,
        coroutine=_tool_coroutine,
    )
    tools_map = {"data_query_grid": tool}
    tool_call = {
        "id": "tc27b",
        "name": "data_query_grid",
        "args": {
            "query": "营收",
            "ambiguous_params": ["time_range"],
        },
    }

    get_tool_hook_plugin_manager.cache_clear()
    try:
        with (
            _patch_analyze_query_clarification(mock_result),
            patch("langgraph.types.interrupt", return_value=resume_value),
        ):
            await dispatch_tool(
                tool_call=tool_call, tools_map=tools_map, state=state, gateway_context=None
            )
    finally:
        get_tool_hook_plugin_manager.cache_clear()

    assert len(captured_calls) == 1, f"工具应被调用一次，实际：{len(captured_calls)}"
    call = captured_calls[0]
    # resume 后 query 取自 state["user_query"]
    assert call["query"] == "高效益网格营收利润", (
        f"query 应来自 state.user_query，实际：{call['query']!r}"
    )
    assert "营收 → 企业总营收（万元）" in call["contextKnowledge"], (
        f"contextKnowledge 应含字段映射，实际：{call['contextKnowledge']!r}"
    )
    assert "利润 → 企业总利润（万元）" in call["contextKnowledge"]


# ---------------------------------------------------------------------------
# TC-18: query_* 工具 → resume → OQL 结构化参数
# ---------------------------------------------------------------------------


@pytest.mark.skip(
    reason="V0.2->V0.3: before_call_back now raises ClarificationNeededError instead of interrupt()"
)
@pytest.mark.asyncio
async def test_tc18_query_star_resume_produces_oql_params() -> None:
    """TC-18: query_* 工具 resume 后收到 select/where/group_by/order_by。

    analyze_query_clarification 返回 needs_clarification=True 并带 form（包含 paradigmList），
    interrupt() mock 返回 resume_value（用户选择）。
    """
    from datacloud_analysis.orchestration.execution.tool_wrapper import dispatch_tool

    resume_value = {
        "paradigmList": [
            {"fieldName": "企业总营收（万元）"},
            {"fieldName": "企业总利润（万元）"},
        ]
    }
    mock_result = _make_clarification_result(
        needs_clarification=True,
        form=json.dumps(resume_value),
    )

    state = _make_state("query_grid")

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
    tool_call = {
        "id": "tc18",
        "name": "query_grid",
        "args": {
            "select": [],
            "ambiguous_params": ["metric_field"],
        },
    }

    get_tool_hook_plugin_manager.cache_clear()
    try:
        with (
            _patch_analyze_query_clarification(mock_result),
            patch("langgraph.types.interrupt", return_value=resume_value),
        ):
            await dispatch_tool(
                tool_call=tool_call, tools_map=tools_map, state=state, gateway_context=None
            )
    finally:
        get_tool_hook_plugin_manager.cache_clear()

    assert len(captured_calls) == 1
    call = captured_calls[0]
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


@pytest.mark.skip(
    reason="V0.2->V0.3: before_call_back now raises ClarificationNeededError instead of interrupt()"
)
@pytest.mark.asyncio
async def test_tc19_data_query_star_resume_produces_query_and_context_knowledge() -> None:
    """TC-19: data_query_* 工具 resume 后收到 query（来自 state.user_query）和 contextKnowledge（字段映射）。"""
    from datacloud_analysis.orchestration.execution.tool_wrapper import dispatch_tool

    resume_value = {"paradigmList": [_paradigm_revenue(), _paradigm_profit()]}
    mock_result = _make_clarification_result(
        needs_clarification=True,
        form=json.dumps(resume_value),
    )

    state = _make_state("data_query_enterprise")
    state["user_query"] = "高效益网格的营收利润汇总"

    captured_calls: list[dict] = []

    async def _tool_coroutine(query: str, context_knowledge: str = "", **kwargs: Any) -> dict:
        captured_calls.append({"query": query, "contextKnowledge": context_knowledge})
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
        "args": {
            "query": "营收利润（含歧义原始参数）",
            "ambiguous_params": ["metric_field"],
        },
    }

    get_tool_hook_plugin_manager.cache_clear()
    try:
        with (
            _patch_analyze_query_clarification(mock_result),
            patch("langgraph.types.interrupt", return_value=resume_value),
        ):
            await dispatch_tool(
                tool_call=tool_call, tools_map=tools_map, state=state, gateway_context=None
            )
    finally:
        get_tool_hook_plugin_manager.cache_clear()

    assert len(captured_calls) == 1
    call = captured_calls[0]
    assert call["query"] == "高效益网格的营收利润汇总", (
        f"query 应取自 state.user_query，实际：{call['query']!r}"
    )
    assert "营收 → 企业总营收（万元）" in call["contextKnowledge"]
    assert "利润 → 企业总利润（万元）" in call["contextKnowledge"]


@pytest.mark.skip(
    reason="V0.2->V0.3: before_call_back now raises ClarificationNeededError instead of interrupt()"
)
@pytest.mark.asyncio
async def test_tc19_original_llm_params_are_discarded_on_resume() -> None:
    """TC-19: resume 后 tool_params 整体替换，含歧义的 LLM 原始参数被完全丢弃。"""
    from datacloud_analysis.orchestration.execution.tool_wrapper import dispatch_tool

    resume_value = {"paradigmList": [_paradigm_revenue()]}
    mock_result = _make_clarification_result(
        needs_clarification=True,
        form=json.dumps(resume_value),
    )

    state = _make_state("data_query_grid")
    state["user_query"] = "规范化后的营收查询"

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
    tool_call = {
        "id": "tc19b",
        "name": "data_query_grid",
        "args": {
            "query": "含歧义的原始参数",
            "contextKnowledge": "LLM 自己填写的旧值",
            "ambiguous_params": ["metric_field"],
        },
    }

    get_tool_hook_plugin_manager.cache_clear()
    try:
        with (
            _patch_analyze_query_clarification(mock_result),
            patch("langgraph.types.interrupt", return_value=resume_value),
        ):
            await dispatch_tool(
                tool_call=tool_call, tools_map=tools_map, state=state, gateway_context=None
            )
    finally:
        get_tool_hook_plugin_manager.cache_clear()

    assert captured_kwargs, "工具应被调用"
    call = captured_kwargs[0]
    assert call.get("query") == "规范化后的营收查询", (
        f"LLM 含歧义 query 应被 state.user_query 替换，实际：{call.get('query')!r}"
    )
    assert call.get("contextKnowledge") != "LLM 自己填写的旧值", (
        "LLM 填写的旧 contextKnowledge 应被系统值替换"
    )


# ---------------------------------------------------------------------------
# TC-20: compute_* 工具 → resume → dimensions/metrics
# ---------------------------------------------------------------------------


@pytest.mark.skip(
    reason="V0.2->V0.3: before_call_back now raises ClarificationNeededError instead of interrupt()"
)
@pytest.mark.asyncio
async def test_tc20_compute_star_resume_produces_dimensions_and_metrics() -> None:
    """TC-20: compute_* 工具 resume 后收到 dimensions/metrics 结构（来自 paradigmList）。"""
    from datacloud_analysis.orchestration.execution.tool_wrapper import dispatch_tool

    resume_value = {
        "paradigmList": [
            _paradigm_dim(),  # dimensionName
            _paradigm_metric(),  # metricName + agg
            {"metricName": "企业总利润（万元）"},  # agg 缺省 → sum
        ]
    }
    mock_result = _make_clarification_result(
        needs_clarification=True,
        form=json.dumps(resume_value),
    )

    state = _make_state("compute_grid")

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
    tool_call = {
        "id": "tc20",
        "name": "compute_grid",
        "args": {
            "ambiguous_params": ["dimension_field"],
        },
    }

    get_tool_hook_plugin_manager.cache_clear()
    try:
        with (
            _patch_analyze_query_clarification(mock_result),
            patch("langgraph.types.interrupt", return_value=resume_value),
        ):
            await dispatch_tool(
                tool_call=tool_call, tools_map=tools_map, state=state, gateway_context=None
            )
    finally:
        get_tool_hook_plugin_manager.cache_clear()

    assert len(captured_calls) == 1
    call = captured_calls[0]

    assert "dimensions" in call, f"compute_* 应有 dimensions，实际：{call}"
    assert "metrics" in call, f"compute_* 应有 metrics，实际：{call}"
    assert {"field": "企业经济效益等级"} in call["dimensions"]
    assert {"field": "企业总营收（万元）", "agg": "sum"} in call["metrics"]
    assert {"field": "企业总利润（万元）", "agg": "sum"} in call["metrics"]
    assert "query" not in call, "compute_* 参数不应含 query 字段"


@pytest.mark.skip(
    reason="V0.2->V0.3: before_call_back now raises ClarificationNeededError instead of interrupt()"
)
@pytest.mark.asyncio
async def test_tc20_compute_empty_paradigm_list_produces_empty_dims_metrics() -> None:
    """TC-20 边界：ambiguous_params=[] → 插件跳过，工具以原始空参数调用。"""
    from datacloud_analysis.orchestration.execution.tool_wrapper import dispatch_tool

    state = _make_state("compute_enterprise")

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
    tool_call = {
        "id": "tc20b",
        "name": "compute_enterprise",
        "args": {
            "dimensions": [],
            "metrics": [],
            "ambiguous_params": [],  # 空：跳过澄清
        },
    }

    get_tool_hook_plugin_manager.cache_clear()
    try:
        await dispatch_tool(
            tool_call=tool_call, tools_map=tools_map, state=state, gateway_context=None
        )
    finally:
        get_tool_hook_plugin_manager.cache_clear()

    assert captured_calls
    call = captured_calls[0]
    assert call.get("dimensions") == [], f"空 paradigmList → dimensions 应为空，实际：{call}"
    assert call.get("metrics") == [], f"空 paradigmList → metrics 应为空，实际：{call}"


# ---------------------------------------------------------------------------
# TC-21: data_query_* 同时有 knowledge 且 needs_clarification → 走 interrupt（优先）
# ---------------------------------------------------------------------------


@pytest.mark.skip(
    reason="V0.2->V0.3: before_call_back now raises ClarificationNeededError instead of interrupt()"
)
@pytest.mark.asyncio
async def test_tc21_needs_clarification_takes_priority_over_knowledge_injection() -> None:
    """TC-21: needs_clarification=True 且 knowledge 非空 → interrupt 路径优先。

    mock analyze_query_clarification 同时返回 knowledge 和 needs_clarification=True，
    验证 interrupt 路径被选择，contextKnowledge 由用户选择的 paradigmList 生成。
    """
    from datacloud_analysis.orchestration.execution.tool_wrapper import dispatch_tool

    raw_knowledge = '{"paradigmList":[{"name":"亩产","fieldName":"物理网格亩产效益（万元/亩）"}]}'
    resume_paradigm = [_paradigm_revenue()]
    resume_value = {"paradigmList": resume_paradigm}

    mock_result = _make_clarification_result(
        needs_clarification=True,
        form=json.dumps(resume_value),
        knowledge=raw_knowledge,
    )

    state = _make_state("data_query_grid")
    state["user_query"] = "高效益网格的营收汇总"

    captured_calls: list[dict] = []

    async def _tool_coroutine(query: str, context_knowledge: str = "", **kwargs: Any) -> dict:
        captured_calls.append({"query": query, "contextKnowledge": context_knowledge})
        return {"records": [], "meta": {}}

    tool = StructuredTool(
        name="data_query_grid",
        description="test",
        args_schema=_DataQuerySchema,
        coroutine=_tool_coroutine,
    )
    tools_map = {"data_query_grid": tool}
    tool_call = {
        "id": "tc21",
        "name": "data_query_grid",
        "args": {
            "query": "原始参数",
            "ambiguous_params": ["metric_field"],
        },
    }

    get_tool_hook_plugin_manager.cache_clear()
    try:
        with (
            _patch_analyze_query_clarification(mock_result),
            patch("langgraph.types.interrupt", return_value=resume_value),
        ):
            await dispatch_tool(
                tool_call=tool_call, tools_map=tools_map, state=state, gateway_context=None
            )
    finally:
        get_tool_hook_plugin_manager.cache_clear()

    assert captured_calls, "工具应被调用"
    call = captured_calls[0]

    assert call["query"] == "高效益网格的营收汇总"
    assert "营收 → 企业总营收（万元）" in call["contextKnowledge"], (
        f"contextKnowledge 应由用户选择的 paradigmList 生成，实际：{call['contextKnowledge']!r}"
    )
    assert "亩产" not in call["contextKnowledge"], (
        f"用户未选亩产，contextKnowledge 不应含亩产，实际：{call['contextKnowledge']!r}"
    )


# ---------------------------------------------------------------------------
# TC-21 追加：非数据工具在 needs_clarification=True 时不触发 interrupt
# ---------------------------------------------------------------------------


@pytest.mark.skip(
    reason="V0.2->V0.3: before_call_back now raises ClarificationNeededError instead of interrupt()"
)
@pytest.mark.asyncio
async def test_tc21_non_data_tool_not_affected_by_clarification_flag() -> None:
    """TC-21 补充：非数据工具（send_email）插件直接跳过，不触发 interrupt。"""
    from datacloud_analysis.orchestration.execution.tool_wrapper import dispatch_tool

    state = _make_state("send_email")

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
        tool_call_id, result = await dispatch_tool(
            tool_call=tool_call,
            tools_map=tools_map,
            state=state,
            gateway_context=None,
        )
    finally:
        get_tool_hook_plugin_manager.cache_clear()

    assert result is not None
