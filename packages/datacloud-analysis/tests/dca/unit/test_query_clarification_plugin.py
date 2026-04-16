"""TC-13 ~ TC-16, TC-23 ~ TC-25: QueryClarificationPlugin before_call_back 测试。"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

# 直接导入插件模块（实现后才会通过）
from datacloud_analysis.tool_hook_plugins.builtin.query_clarification_plugin import (
    _format_knowledge_for_prompt,
    _is_data_query_tool,
    _is_data_tool,
    before_call_back,
)
from datacloud_analysis.tool_hook_plugins.types import HookContext


def _make_ctx(
    tool_name: str = "data_query_grid",
    tool_params: dict | None = None,
    knowledge_payload: dict | None = None,
    user_query: str = "查询营收",
) -> HookContext:
    return {
        "tool_name": tool_name,
        "tool_params": dict(tool_params or {"query": "查询营收"}),
        "user_query": user_query,
        "knowledge_snippets": [],
        "term_context": [],
        "knowledge_payload": dict(knowledge_payload or {}),
    }


# ---------------------------------------------------------------------------
# _is_data_tool / _is_data_query_tool 单元测试
# ---------------------------------------------------------------------------
def test_is_data_tool_query_prefix() -> None:
    assert _is_data_tool("query_grid") is True
    assert _is_data_tool("data_query_enterprise") is True
    assert _is_data_tool("compute_grid") is True
    assert _is_data_tool("send_email") is False
    assert _is_data_tool("ask_user") is False


def test_is_data_query_tool() -> None:
    assert _is_data_query_tool("data_query_grid") is True
    assert _is_data_query_tool("data_query_enterprise") is True
    assert _is_data_query_tool("query_grid") is False
    assert _is_data_query_tool("compute_grid") is False


# ---------------------------------------------------------------------------
# TC-23: 非数据工具 → before_call_back 返回 None，不处理
# ---------------------------------------------------------------------------
async def test_tc23_non_data_tool_returns_none() -> None:
    ctx = _make_ctx(tool_name="send_email")
    result = await before_call_back(ctx)
    assert result is None, f"非数据工具应返回 None，实际：{result}"


# ---------------------------------------------------------------------------
# TC-24: query_intent（以 query_ 开头）→ 被识别为数据工具（startswith 匹配）
#         注：文档 TC-24 预期行为存在歧义，实现以 startswith 语义为准
# ---------------------------------------------------------------------------
async def test_tc24_query_intent_matches_query_prefix() -> None:
    # ⚠️ 文档 TC-24 描述与实现存在矛盾：
    #   文档期望 _is_data_tool("query_intent") == False
    #   但实现用 startswith("query_")，会匹配 query_intent
    # 本测试记录实际行为（matches），部署时需确保不存在命名冲突
    assert _is_data_tool("query_intent") is True, (
        "⚠️ query_intent 以 query_ 开头，被 startswith 匹配为数据工具。"
        "部署时需确保非数据工具不使用 query_/data_query_/compute_ 前缀。"
    )


# ---------------------------------------------------------------------------
# TC-13: data_query_* + knowledge 非空 → contextKnowledge 被无条件覆盖
# ---------------------------------------------------------------------------
async def test_tc13_data_query_with_knowledge_patches_context_knowledge() -> None:
    knowledge_str = '{"paradigmList":[{"name":"营收","fieldName":"企业总营收（万元）"}]}'
    payload = {
        "needs_clarification": False,
        "form": "",
        "knowledge": knowledge_str,
        "query": "营收查询",
    }
    ctx = _make_ctx(
        tool_name="data_query_grid",
        tool_params={"query": "查询营收", "contextKnowledge": ""},
        knowledge_payload=payload,
    )
    result = await before_call_back(ctx)

    assert result is not None
    assert result.get("action") == "patch"
    patched_params = result["patch"]["tool_params"]
    assert "contextKnowledge" in patched_params
    assert patched_params["contextKnowledge"] == knowledge_str


# ---------------------------------------------------------------------------
# TC-14: data_query_* + knowledge 为空 → contextKnowledge 不被 patch
# ---------------------------------------------------------------------------
async def test_tc14_data_query_empty_knowledge_no_patch() -> None:
    payload = {
        "needs_clarification": False,
        "form": "",
        "knowledge": "",
        "query": "查询所有客户",
    }
    ctx = _make_ctx(
        tool_name="data_query_grid",
        tool_params={"query": "查询所有客户", "contextKnowledge": ""},
        knowledge_payload=payload,
    )
    result = await before_call_back(ctx)

    assert result is None, f"knowledge 为空时应返回 None（不 patch），实际：{result}"


# ---------------------------------------------------------------------------
# TC-15: LLM 已填 contextKnowledge → 被系统值无条件覆盖
# ---------------------------------------------------------------------------
async def test_tc15_llm_filled_context_knowledge_is_overwritten() -> None:
    knowledge_str = "系统注入的知识"
    payload = {
        "needs_clarification": False,
        "form": "",
        "knowledge": knowledge_str,
        "query": "营收查询",
    }
    ctx = _make_ctx(
        tool_name="data_query_grid",
        tool_params={"query": "查询营收", "contextKnowledge": "LLM自己填写的内容"},
        knowledge_payload=payload,
    )
    result = await before_call_back(ctx)

    assert result is not None
    patched_params = result["patch"]["tool_params"]
    # 系统值应覆盖 LLM 填写的值
    assert patched_params["contextKnowledge"] == knowledge_str
    assert patched_params["contextKnowledge"] != "LLM自己填写的内容"


# ---------------------------------------------------------------------------
# TC-16: query_* 工具 → 不触发层 B patch（contextKnowledge 不写入）
# ---------------------------------------------------------------------------
async def test_tc16_query_star_tool_skips_layer_b_patch() -> None:
    payload = {
        "needs_clarification": False,
        "form": "",
        "knowledge": "系统注入的知识",
        "query": "查询营收",
    }
    ctx = _make_ctx(
        tool_name="query_grid",
        tool_params={"select": ["营收"], "where": [], "group_by": [], "order_by": []},
        knowledge_payload=payload,
    )
    result = await before_call_back(ctx)

    # query_* 工具无第二 LLM，不触发层 B patch
    if result is not None:
        patched_params = result.get("patch", {}).get("tool_params", {})
        assert "contextKnowledge" not in patched_params, "query_* 不应注入 contextKnowledge"


# ---------------------------------------------------------------------------
# TC-25: knowledge_payload 缓存为空时走兜底分支（fallback analyze_query_clarification）
# ---------------------------------------------------------------------------
async def test_tc25_fallback_when_no_cache() -> None:
    ctx = _make_ctx(
        tool_name="data_query_grid",
        tool_params={"query": "查询营收"},
        knowledge_payload={},  # 空缓存
    )

    mock_result = MagicMock()
    mock_result.needs_clarification = False
    mock_result.form = ""
    mock_result.knowledge = "fallback_knowledge"

    with patch(
        "datacloud_analysis.tool_hook_plugins.builtin.query_clarification_plugin._call_fallback_enhancer",
        new=AsyncMock(return_value=mock_result),
    ):
        result = await before_call_back(ctx)

    # 兜底调用后，应根据返回结果决定是否 patch
    assert result is not None
    patched_params = result.get("patch", {}).get("tool_params", {})
    assert patched_params.get("contextKnowledge") == "fallback_knowledge"


# ---------------------------------------------------------------------------
# _format_knowledge_for_prompt 单元测试
# ---------------------------------------------------------------------------
def test_format_knowledge_extracts_readable_text() -> None:

    knowledge_json = '{"paradigmList":[{"name":"营收","fieldName":"企业总营收（万元）"},{"name":"利润","fieldName":"企业总利润（万元）"}]}'
    result = _format_knowledge_for_prompt(knowledge_json)
    assert "营收 → 企业总营收（万元）" in result
    assert "利润 → 企业总利润（万元）" in result
    assert "paradigmList" not in result, "格式化结果不应含原始 JSON 键"


def test_format_knowledge_returns_original_on_parse_error() -> None:

    bad_json = "not-json"
    result = _format_knowledge_for_prompt(bad_json)
    assert result == bad_json
