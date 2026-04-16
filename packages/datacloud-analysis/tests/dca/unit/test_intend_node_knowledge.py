"""TC-01 ~ TC-05: intend_node 知识增强集成测试。"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from datacloud_analysis.orchestration.intend.node import intend_node
from langchain_core.messages import HumanMessage


def _make_state(query: str) -> dict:
    return {
        "messages": [HumanMessage(content=query)],
        "agent_id": "test-agent",
        "workspace_dir": None,
        "user_query": None,
        "knowledge_payload": None,
        "knowledge_snippets": None,
    }


def _make_config() -> dict:
    return {"configurable": {}}


def _make_result(
    *,
    query: str = "营收",
    needs_clarification: bool = False,
    form: str = "",
    knowledge: str = "",
) -> MagicMock:
    r = MagicMock()
    r.query = query
    r.needs_clarification = needs_clarification
    r.form = form
    r.knowledge = knowledge
    return r


# ---------------------------------------------------------------------------
# TC-01: 有知识、无歧义 → knowledge_snippets + knowledge_payload 均写入
# ---------------------------------------------------------------------------
async def test_tc01_knowledge_no_clarification_writes_both_state_fields() -> None:
    enhancer = AsyncMock(
        return_value=_make_result(
            query="高效益网格的营收",
            needs_clarification=False,
            knowledge='{"paradigmList":[{"name":"营收","fieldName":"企业总营收（万元）"}]}',
        )
    )
    result = await intend_node(
        _make_state("高效益网格的营收"), _make_config(), knowledge_enhancer=enhancer
    )

    enhancer.assert_awaited_once_with("高效益网格的营收", None, "")
    assert "knowledge_payload" in result
    assert result["knowledge_payload"]["needs_clarification"] is False
    assert result["knowledge_payload"]["knowledge"] != ""
    # knowledge_snippets 应写入，且格式为可读文本，不是原始 JSON
    assert "knowledge_snippets" in result
    snippets = result["knowledge_snippets"]
    assert isinstance(snippets, list)
    assert len(snippets) >= 1
    first = snippets[0]
    assert isinstance(first, str)
    assert "paradigmList" not in first, "knowledge_snippets 不应包含原始 JSON 结构"
    assert "→" in first, "knowledge_snippets 应为可读的字段映射格式"


# ---------------------------------------------------------------------------
# TC-02: 有歧义、knowledge 为空 → knowledge_snippets 不写，knowledge_payload 写入
# ---------------------------------------------------------------------------
async def test_tc02_needs_clarification_no_knowledge_skips_snippets() -> None:
    enhancer = AsyncMock(
        return_value=_make_result(
            query="信息技术各链上下游企业数",
            needs_clarification=True,
            form='{"paradigmList":[{"type":"chain"}]}',
            knowledge="",
        )
    )
    result = await intend_node(
        _make_state("信息技术各链上下游企业数"), _make_config(), knowledge_enhancer=enhancer
    )

    payload = result.get("knowledge_payload")
    assert payload is not None
    assert payload["needs_clarification"] is True
    assert payload["form"] != ""
    # knowledge_snippets 不应写入（knowledge 为空）
    assert result.get("knowledge_snippets") is None or result.get("knowledge_snippets") == []


# ---------------------------------------------------------------------------
# TC-03: needs_clarification=True 且 knowledge 非空 → 两者均写入（不互斥）
# ---------------------------------------------------------------------------
async def test_tc03_needs_clarification_and_knowledge_both_written() -> None:
    enhancer = AsyncMock(
        return_value=_make_result(
            query="上游龙头企业数",
            needs_clarification=True,
            form='{"paradigmList":[]}',
            knowledge='{"paradigmList":[{"name":"营收","fieldName":"总营收"}]}',
        )
    )
    result = await intend_node(
        _make_state("上游龙头企业数"), _make_config(), knowledge_enhancer=enhancer
    )

    # 两者均写入
    assert result.get("knowledge_snippets"), "知识非空时 knowledge_snippets 应写入"
    assert result.get("knowledge_payload", {}).get("needs_clarification") is True
    assert result.get("knowledge_payload", {}).get("form") != ""


# ---------------------------------------------------------------------------
# TC-04: 透传（knowledge="", needs_clarification=False）→ knowledge_snippets 不写
# ---------------------------------------------------------------------------
async def test_tc04_passthrough_no_snippets_written() -> None:
    enhancer = AsyncMock(
        return_value=_make_result(
            query="查询所有客户",
            needs_clarification=False,
            knowledge="",
        )
    )
    result = await intend_node(
        _make_state("查询所有客户"), _make_config(), knowledge_enhancer=enhancer
    )

    # knowledge_payload 写入（记录透传状态），但 knowledge_snippets 不写
    assert result.get("knowledge_payload") is not None
    snippets = result.get("knowledge_snippets")
    assert not snippets, f"透传时不应写入 knowledge_snippets，实际：{snippets}"


# ---------------------------------------------------------------------------
# TC-05: knowledge_enhancer=None → API 不被调用，state 无 knowledge_payload
# ---------------------------------------------------------------------------
async def test_tc05_no_enhancer_api_not_called() -> None:
    result = await intend_node(
        _make_state("帮我订一张机票"), _make_config(), knowledge_enhancer=None
    )

    # knowledge_payload 不应出现在结果中
    assert "knowledge_payload" not in result or result["knowledge_payload"] is None
    assert "knowledge_snippets" not in result or result["knowledge_snippets"] is None
    # intent 正常设置
    assert result.get("intent") == "react"
