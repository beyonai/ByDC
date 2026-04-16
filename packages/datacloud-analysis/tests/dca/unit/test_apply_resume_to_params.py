"""TC-27（部分）: _apply_resume_to_params 参数重建逻辑单元测试。

覆盖范围：
  - data_query_* 分支：query 取自 payload["query"]，contextKnowledge 从 paradigmList 提取
  - query_* 分支：构造 select/where/group_by/order_by（OQL 结构化参数）
  - compute_* 分支：构造 dimensions/metrics（中文字段名）
  - 辅助函数：_extract_knowledge_from_paradigm、_build_oql_params_from_paradigm、_build_compute_params_from_paradigm

注：interrupt() 的两阶段行为（首次 raise / resume 后返回）需要 LangGraph 图集成测试环境，
    本文件仅验证 resume 之后 _apply_resume_to_params 的参数构造逻辑（纯函数，无外部依赖）。
"""

from __future__ import annotations

from datacloud_analysis.tool_hook_plugins.builtin.query_clarification_plugin import (
    _apply_resume_to_params,
    _build_compute_params_from_paradigm,
    _build_oql_params_from_paradigm,
    _extract_knowledge_from_paradigm,
)
from datacloud_analysis.tool_hook_plugins.types import HookContext

# ---------------------------------------------------------------------------
# 辅助工厂
# ---------------------------------------------------------------------------


def _make_ctx(
    tool_name: str = "data_query_grid",
    tool_params: dict | None = None,
    user_query: str = "查询营收",
) -> HookContext:
    return {
        "tool_name": tool_name,
        "tool_params": dict(tool_params or {"query": user_query}),
        "user_query": user_query,
        "knowledge_snippets": [],
        "term_context": [],
        "knowledge_payload": {},
    }


_PARADIGM_ITEM_REVENUE = {"name": "营收", "fieldName": "企业总营收（万元）"}
_PARADIGM_ITEM_PROFIT = {"name": "利润", "fieldName": "企业总利润（万元）"}
_PARADIGM_ITEM_DIM = {"dimensionName": "企业经济效益等级"}
_PARADIGM_ITEM_METRIC = {"metricName": "企业总营收（万元）", "agg": "sum"}


# ===========================================================================
# TC-27a: data_query_* — contextKnowledge 从 paradigmList 条目提取
# ===========================================================================


def test_tc27a_data_query_resume_extracts_context_knowledge() -> None:
    """resume 后 data_query_* 工具的 contextKnowledge 由 paradigmList 条目提取。"""
    ctx = _make_ctx(tool_name="data_query_grid")
    resume_value = {"paradigmList": [_PARADIGM_ITEM_REVENUE, _PARADIGM_ITEM_PROFIT]}
    payload = {"query": "高效益网格的营收利润", "knowledge": "", "needs_clarification": True}

    _apply_resume_to_params(ctx, "data_query_grid", resume_value, payload)

    params = ctx["tool_params"]
    assert "query" in params
    assert "contextKnowledge" in params
    assert "营收 → 企业总营收（万元）" in params["contextKnowledge"]
    assert "利润 → 企业总利润（万元）" in params["contextKnowledge"]


# ===========================================================================
# TC-27b: data_query_* — query 取自 payload["query"]（规范化后的自然语言）
# ===========================================================================


def test_tc27b_data_query_query_comes_from_payload() -> None:
    """data_query_* 的 query 字段取自 payload['query']（analyze_query_clarification 规范化结果）。"""
    ctx = _make_ctx(tool_name="data_query_enterprise", user_query="原始问题")
    resume_value = {"paradigmList": [_PARADIGM_ITEM_REVENUE]}
    payload = {"query": "高效益网格的营收汇总", "knowledge": "", "needs_clarification": True}

    _apply_resume_to_params(ctx, "data_query_enterprise", resume_value, payload)

    assert ctx["tool_params"]["query"] == "高效益网格的营收汇总"


# ===========================================================================
# TC-27c: data_query_* — payload["query"] 为空时 fallback 到 user_query
# ===========================================================================


def test_tc27c_data_query_fallback_to_user_query_when_payload_query_empty() -> None:
    """payload['query'] 为空时，query 字段 fallback 到 ctx['user_query']。"""
    ctx = _make_ctx(tool_name="data_query_grid", user_query="用户原始输入")
    resume_value = {"paradigmList": [_PARADIGM_ITEM_REVENUE]}
    payload = {"query": "", "knowledge": "", "needs_clarification": True}  # query 为空

    _apply_resume_to_params(ctx, "data_query_grid", resume_value, payload)

    assert ctx["tool_params"]["query"] == "用户原始输入"


# ===========================================================================
# TC-27d: query_* — 构造 OQL 结构化参数（select/where/group_by/order_by）
# ===========================================================================


def test_tc27d_query_star_resume_constructs_oql_params() -> None:
    """resume 后 query_* 工具的 tool_params 为 OQL 结构化参数。"""
    ctx = _make_ctx(
        tool_name="query_grid",
        tool_params={"query": "旧参数应被替换"},  # 原始 LLM 参数，应被整体替换
    )
    resume_value = {
        "paradigmList": [
            {"fieldName": "企业总营收（万元）"},
            {"fieldName": "物理网格亩产效益（万元/亩）"},
        ]
    }
    payload = {"query": "", "knowledge": "", "needs_clarification": True}

    _apply_resume_to_params(ctx, "query_grid", resume_value, payload)

    params = ctx["tool_params"]
    assert "select" in params
    assert "企业总营收（万元）" in params["select"]
    assert "物理网格亩产效益（万元/亩）" in params["select"]
    assert "where" in params
    assert "group_by" in params
    assert "order_by" in params
    assert "query" not in params, "OQL 参数不应含 query 字段"


# ===========================================================================
# TC-27e: compute_* — 构造 dimensions/metrics（中文字段名）
# ===========================================================================


def test_tc27e_compute_star_resume_constructs_dimensions_metrics() -> None:
    """resume 后 compute_* 工具的 tool_params 为 dimensions/metrics 结构。"""
    ctx = _make_ctx(
        tool_name="compute_grid",
        tool_params={"old": "旧参数应被替换"},
    )
    resume_value = {
        "paradigmList": [
            {"dimensionName": "企业经济效益等级"},
            {"metricName": "企业总营收（万元）", "agg": "sum"},
            {"metricName": "企业总利润（万元）"},  # agg 缺省 → "sum"
        ]
    }
    payload = {"query": "", "knowledge": "", "needs_clarification": True}

    _apply_resume_to_params(ctx, "compute_grid", resume_value, payload)

    params = ctx["tool_params"]
    assert "dimensions" in params
    assert "metrics" in params
    assert {"field": "企业经济效益等级"} in params["dimensions"]
    assert {"field": "企业总营收（万元）", "agg": "sum"} in params["metrics"]
    assert {"field": "企业总利润（万元）", "agg": "sum"} in params["metrics"]


# ===========================================================================
# TC-27f: 未知工具类型 — tool_params 不被修改
# ===========================================================================


def test_tc27f_unknown_tool_type_does_not_modify_tool_params() -> None:
    """未知工具类型（非 data_query_*/query_*/compute_* 前缀）不修改 tool_params。"""
    original_params = {"some": "param"}
    ctx = _make_ctx(tool_name="send_email", tool_params=dict(original_params))
    resume_value = {"paradigmList": [_PARADIGM_ITEM_REVENUE]}
    payload = {"query": "x", "knowledge": "", "needs_clarification": True}

    _apply_resume_to_params(ctx, "send_email", resume_value, payload)

    assert ctx["tool_params"] == original_params, "未知工具类型不应修改 tool_params"


# ===========================================================================
# TC-27g: paradigmList 为空 — contextKnowledge 为空字符串，select 为空列表
# ===========================================================================


def test_tc27g_empty_paradigm_list_produces_empty_context_knowledge() -> None:
    """paradigmList 为空时，data_query_* 的 contextKnowledge 为空字符串。"""
    ctx = _make_ctx(tool_name="data_query_grid")
    resume_value = {"paradigmList": []}
    payload = {"query": "查询营收", "knowledge": "", "needs_clarification": True}

    _apply_resume_to_params(ctx, "data_query_grid", resume_value, payload)

    assert ctx["tool_params"]["contextKnowledge"] == ""


def test_tc27g_empty_paradigm_list_produces_empty_select() -> None:
    """paradigmList 为空时，query_* 的 select 为空列表。"""
    ctx = _make_ctx(tool_name="query_grid")
    resume_value = {"paradigmList": []}
    payload = {"query": "", "knowledge": "", "needs_clarification": True}

    _apply_resume_to_params(ctx, "query_grid", resume_value, payload)

    assert ctx["tool_params"]["select"] == []
    assert ctx["tool_params"]["where"] == []


# ===========================================================================
# TC-27h: tool_params 整体替换（原始 LLM 参数被丢弃）
# ===========================================================================


def test_tc27h_tool_params_are_wholly_replaced_not_merged() -> None:
    """resume 后 tool_params 为整体替换，原始 LLM 含歧义参数被完全丢弃。"""
    ctx = _make_ctx(
        tool_name="data_query_grid",
        tool_params={
            "query": "旧的含歧义字段名",
            "contextKnowledge": "旧的值",
            "extra_llm_field": "多余字段",
        },
    )
    resume_value = {"paradigmList": [_PARADIGM_ITEM_REVENUE]}
    payload = {"query": "规范化后的查询", "knowledge": "", "needs_clarification": True}

    _apply_resume_to_params(ctx, "data_query_grid", resume_value, payload)

    params = ctx["tool_params"]
    assert "extra_llm_field" not in params, "原始 LLM 多余字段应被丢弃"
    assert params["query"] == "规范化后的查询"


# ===========================================================================
# _extract_knowledge_from_paradigm 独立测试
# ===========================================================================


def test_extract_knowledge_uses_name_and_field_name() -> None:
    """name + fieldName → '名称 → 字段名' 格式。"""
    selected = [
        {"name": "营收", "fieldName": "企业总营收（万元）"},
        {"name": "利润", "fieldName": "企业总利润（万元）"},
    ]
    result = _extract_knowledge_from_paradigm(selected)
    assert "营收 → 企业总营收（万元）" in result
    assert "利润 → 企业总利润（万元）" in result


def test_extract_knowledge_falls_back_to_term_name_and_description() -> None:
    """缺少 name 时 fallback 到 termName；缺少 fieldName 时 fallback 到 description。"""
    selected = [{"termName": "营收", "description": "企业总营收（万元）"}]
    result = _extract_knowledge_from_paradigm(selected)
    assert "营收 → 企业总营收（万元）" in result


def test_extract_knowledge_skips_incomplete_items() -> None:
    """name 或 fieldName 任一为空时，该条目被跳过。"""
    selected = [
        {"name": "营收"},  # 缺 fieldName → 跳过
        {"fieldName": "企业总营收（万元）"},  # 缺 name → 跳过
        {"name": "利润", "fieldName": "企业总利润（万元）"},  # 完整 → 保留
    ]
    result = _extract_knowledge_from_paradigm(selected)
    lines = result.split("\n")
    assert len(lines) == 1
    assert "利润 → 企业总利润（万元）" in result


# ===========================================================================
# _build_oql_params_from_paradigm 独立测试
# ===========================================================================


def test_build_oql_params_extracts_field_names_into_select() -> None:
    selected = [
        {"fieldName": "企业总营收（万元）"},
        {"fieldName": "物理网格亩产效益（万元/亩）"},
        {"name": "仅有name无fieldName"},  # 无 fieldName，跳过
    ]
    result = _build_oql_params_from_paradigm(selected)
    assert result["select"] == ["企业总营收（万元）", "物理网格亩产效益（万元/亩）"]
    assert result["where"] == []
    assert result["group_by"] == []
    assert result["order_by"] == []


# ===========================================================================
# _build_compute_params_from_paradigm 独立测试
# ===========================================================================


def test_build_compute_params_separates_dims_and_metrics() -> None:
    selected = [
        {"dimensionName": "企业经济效益等级"},
        {"metricName": "企业总营收（万元）", "agg": "sum"},
    ]
    result = _build_compute_params_from_paradigm(selected)
    assert result["dimensions"] == [{"field": "企业经济效益等级"}]
    assert result["metrics"] == [{"field": "企业总营收（万元）", "agg": "sum"}]


def test_build_compute_params_default_agg_is_sum() -> None:
    """metricName 存在但 agg 缺省时，agg 默认为 'sum'。"""
    selected = [{"metricName": "企业总利润（万元）"}]
    result = _build_compute_params_from_paradigm(selected)
    assert result["metrics"][0]["agg"] == "sum"
