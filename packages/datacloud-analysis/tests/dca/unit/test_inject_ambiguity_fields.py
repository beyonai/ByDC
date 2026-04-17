"""方案 A：inject_ambiguity_fields 验收用例（红 → 绿）。

A-TC-06 核心：三个元字段注入到工具 Schema，执行前被剥除，不透传给底层实现。
"""
from __future__ import annotations

import asyncio
import pytest
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field


# ── 被测目标（尚未实现，导入会失败 → 红）────────────────────────────────────
from datacloud_analysis.orchestration.execution.node import (
    inject_ambiguity_fields,
    _is_data_tool_name,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

class _SimpleSchema(BaseModel):
    query: str = Field(description="查询文本")


def _make_tool(name: str = "query_order") -> StructuredTool:
    async def _impl(query: str) -> str:
        return f"result:{query}"

    return StructuredTool(
        name=name,
        description="测试工具",
        args_schema=_SimpleSchema,
        coroutine=_impl,
    )


# ---------------------------------------------------------------------------
# _is_data_tool_name
# ---------------------------------------------------------------------------

def test_is_data_tool_name_query_prefix() -> None:
    assert _is_data_tool_name("query_order") is True
    assert _is_data_tool_name("compute_order") is True
    assert _is_data_tool_name("data_query_order") is True


def test_is_data_tool_name_non_data() -> None:
    assert _is_data_tool_name("ask_user") is False
    assert _is_data_tool_name("read_file") is False
    assert _is_data_tool_name("finish_react") is False


# ---------------------------------------------------------------------------
# inject_ambiguity_fields：字段注入到 Schema
# ---------------------------------------------------------------------------

def test_inject_ambiguity_fields_adds_three_fields() -> None:
    tool = _make_tool("query_order")
    new_tool = inject_ambiguity_fields(tool)
    schema = new_tool.args_schema
    fields = schema.model_fields

    assert "intent_reason" in fields, "应注入 intent_reason 字段"
    assert "extraction_confidence" in fields, "应注入 extraction_confidence 字段"
    assert "ambiguous_params" in fields, "应注入 ambiguous_params 字段"


def test_inject_ambiguity_fields_preserves_original_fields() -> None:
    tool = _make_tool("query_order")
    new_tool = inject_ambiguity_fields(tool)
    fields = new_tool.args_schema.model_fields

    assert "query" in fields, "原始字段 query 应保留"


def test_inject_ambiguity_fields_defaults() -> None:
    tool = _make_tool("query_order")
    new_tool = inject_ambiguity_fields(tool)
    schema_cls = new_tool.args_schema

    instance = schema_cls(query="test")
    assert instance.intent_reason == ""  # type: ignore[attr-defined]
    assert instance.extraction_confidence == 1.0  # type: ignore[attr-defined]
    assert instance.ambiguous_params == []  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# inject_ambiguity_fields：三个元字段在调用前被剥除，不透传给底层
# ---------------------------------------------------------------------------

def test_inject_ambiguity_fields_strips_meta_fields_before_invocation() -> None:
    """底层 coroutine 收到的 kwargs 不含三个元字段（A-TC-06）。"""
    received: dict = {}

    async def _impl(query: str) -> str:
        received.update({"query": query})
        return "ok"

    tool = StructuredTool(
        name="query_order",
        description="测试",
        args_schema=_SimpleSchema,
        coroutine=_impl,
    )
    new_tool = inject_ambiguity_fields(tool)

    asyncio.get_event_loop().run_until_complete(
        new_tool.coroutine(
            query="查营收",
            intent_reason="用户想查营收",
            extraction_confidence=0.9,
            ambiguous_params=["time_range"],
        )
    )

    assert "intent_reason" not in received, "intent_reason 不应透传给底层"
    assert "extraction_confidence" not in received, "extraction_confidence 不应透传给底层"
    assert "ambiguous_params" not in received, "ambiguous_params 不应透传给底层"
    assert received.get("query") == "查营收", "原始参数应正常透传"


def test_inject_ambiguity_fields_no_error_when_meta_fields_absent() -> None:
    """元字段未填时（全部使用默认值），底层调用不报错。"""
    async def _impl(query: str) -> str:
        return "ok"

    tool = StructuredTool(
        name="query_order",
        description="测试",
        args_schema=_SimpleSchema,
        coroutine=_impl,
    )
    new_tool = inject_ambiguity_fields(tool)

    # 只传原始参数，不传三个元字段
    result = asyncio.get_event_loop().run_until_complete(
        new_tool.coroutine(query="查营收")
    )
    assert result == "ok"
