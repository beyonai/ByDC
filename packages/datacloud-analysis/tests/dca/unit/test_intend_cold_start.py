"""改动四：冷启动自动锚点 — intend_node 单元测试

测试规格（先红后绿）：
  TC-4.1-01a  anchor mode + active_tools 为空 → 框架自动调 _do_search_ontology
              → active_tools 写入搜索命中的工具列表，至少 1 个工具
  TC-4.1-01b  search_ontology 返回多个 object hits → 每个 object 的工具都写入 active_tools
  TC-4.1-01c  anchor mode + active_tools 非空 → 跳过冷启动（不覆盖已有工具）
  TC-4.1-01d  非 anchor mode（工具数 ≤ 阈值）→ 跳过冷启动，active_tools 不出现在返回值
  TC-4.1-01e  _do_search_ontology 抛异常 → 静默降级，intend_node 仍正常返回 execution
  TC-4.1-01f  search_ontology 命中对象无工具（TOOL_POOL 中没注册）→ active_tools=[]，不报错
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import HumanMessage

# ── 辅助 ──────────────────────────────────────────────────────────────────────


def _make_state(active_tools: list[str] | None = None, **kwargs: Any) -> dict[str, Any]:
    state: dict[str, Any] = {
        "messages": [HumanMessage(content="为什么这个 trace 失败了？")],
        "active_tools": active_tools,
    }
    state.update(kwargs)
    return state


def _make_config() -> dict[str, Any]:
    return {"configurable": {}}


def _patch_command_router_no_match() -> Any:
    """Patch CommandRouter 总是返回 handled=False。"""
    return patch(
        "datacloud_analysis.orchestration.intend.command_router.CommandPluginManager.from_defaults",
        return_value=MagicMock(handle_ext_command=AsyncMock(return_value=(False, None))),
    )


# ── TC-4.1-01a：冷启动触发，active_tools 被写入 ───────────────────────────────


@pytest.mark.asyncio
async def test_cold_start_populates_active_tools_in_anchor_mode() -> None:
    """anchor mode + active_tools 为空 → active_tools 被写入搜索命中的工具。"""
    from datacloud_analysis.orchestration.intend import node as intend_module
    from datacloud_analysis.tools import tool_pool

    # 构造 TOOL_POOL：注册 ops_langfuse_trace 的 2 个工具
    fake_pool: dict[str, Any] = {
        "get_spans": MagicMock(),
        "find_error_spans": MagicMock(),
    }
    fake_tool_to_object: dict[str, str] = {
        "get_spans": "ops_langfuse_trace",
        "find_error_spans": "ops_langfuse_trace",
    }
    # search_ontology 返回 ops_langfuse_trace 命中
    fake_hits = [{"objectCode": "ops_langfuse_trace", "resultType": "object", "score": 0.9}]

    with (
        _patch_command_router_no_match(),
        patch.object(tool_pool, "TOOL_POOL", fake_pool),
        patch.object(tool_pool, "TOOL_TO_OBJECT", fake_tool_to_object),
        patch.object(tool_pool, "TOOL_POOL_THRESHOLD", 1),  # 2个工具 > 1 → anchor mode
        patch(
            "datacloud_analysis.orchestration.intend.node._do_search_ontology",
            return_value=fake_hits,
        ) as mock_search,
        patch("datacloud_analysis.orchestration.intend.node.TOOL_POOL", fake_pool),
        patch("datacloud_analysis.orchestration.intend.node.TOOL_TO_OBJECT", fake_tool_to_object),
        patch("datacloud_analysis.orchestration.intend.node.TOOL_POOL_THRESHOLD", 999),
    ):
        result = await intend_module.intend_node(_make_state(), _make_config())

    mock_search.assert_called_once()
    assert result["execution_status"] == "execution"
    assert "active_tools" in result
    active = result["active_tools"]
    assert isinstance(active, list)
    assert len(active) >= 1
    assert set(active) == {"get_spans", "find_error_spans"}


# ── TC-4.1-01b：多个 object hits → 所有对象的工具都写入 ──────────────────────


@pytest.mark.asyncio
async def test_cold_start_unlocks_tools_from_multiple_hits() -> None:
    """search_ontology 返回 2 个 object → 两者的工具都写入 active_tools。"""
    from datacloud_analysis.orchestration.intend import node as intend_module
    from datacloud_analysis.tools import tool_pool

    fake_pool: dict[str, Any] = {
        "get_spans": MagicMock(),
        "find_error_spans": MagicMock(),
        "check_db_connection": MagicMock(),
    }
    fake_tool_to_object: dict[str, str] = {
        "get_spans": "ops_langfuse_trace",
        "find_error_spans": "ops_langfuse_trace",
        "check_db_connection": "ops_db_config",
    }
    fake_hits = [
        {"objectCode": "ops_langfuse_trace", "resultType": "object", "score": 0.9},
        {"objectCode": "ops_db_config", "resultType": "object", "score": 0.7},
    ]

    with (
        _patch_command_router_no_match(),
        patch.object(tool_pool, "TOOL_POOL", fake_pool),
        patch.object(tool_pool, "TOOL_TO_OBJECT", fake_tool_to_object),
        patch.object(tool_pool, "TOOL_POOL_THRESHOLD", 1),
        patch(
            "datacloud_analysis.orchestration.intend.node._do_search_ontology",
            return_value=fake_hits,
        ),
        patch("datacloud_analysis.orchestration.intend.node.TOOL_POOL", fake_pool),
        patch("datacloud_analysis.orchestration.intend.node.TOOL_TO_OBJECT", fake_tool_to_object),
        patch("datacloud_analysis.orchestration.intend.node.TOOL_POOL_THRESHOLD", 999),
    ):
        result = await intend_module.intend_node(_make_state(), _make_config())

    assert set(result["active_tools"]) == {"get_spans", "find_error_spans", "check_db_connection"}


# ── TC-4.1-01c：active_tools 已有内容 → 跳过冷启动 ──────────────────────────


@pytest.mark.asyncio
async def test_cold_start_skipped_when_active_tools_not_empty() -> None:
    """active_tools 非空时，冷启动应跳过，_do_search_ontology 不被调用。"""
    from datacloud_analysis.orchestration.intend import node as intend_module
    from datacloud_analysis.tools import tool_pool

    with (
        _patch_command_router_no_match(),
        patch.object(tool_pool, "TOOL_POOL_THRESHOLD", 1),
        patch.object(tool_pool, "TOOL_POOL", {"get_spans": MagicMock()}),
        patch.object(tool_pool, "TOOL_TO_OBJECT", {"get_spans": "ops_langfuse_trace"}),
        patch(
            "datacloud_analysis.orchestration.intend.node._do_search_ontology",
        ) as mock_search,
    ):
        result = await intend_module.intend_node(
            _make_state(active_tools=["get_spans"]), _make_config()
        )

    mock_search.assert_not_called()
    # 返回值中不应覆盖已有的 active_tools
    assert "active_tools" not in result


# ── TC-4.1-01d：非 anchor mode → 跳过冷启动 ──────────────────────────────────


@pytest.mark.asyncio
async def test_cold_start_skipped_when_not_anchor_mode() -> None:
    """工具数 ≤ 阈值（非 anchor mode）时，冷启动跳过。"""
    from datacloud_analysis.orchestration.intend import node as intend_module
    from datacloud_analysis.tools import tool_pool

    with (
        _patch_command_router_no_match(),
        patch.object(tool_pool, "TOOL_POOL_THRESHOLD", 999),  # 阈值极高 → 非 anchor mode
        patch.object(tool_pool, "TOOL_POOL", {"get_spans": MagicMock()}),
        patch.object(tool_pool, "TOOL_TO_OBJECT", {"get_spans": "ops_langfuse_trace"}),
        patch(
            "datacloud_analysis.orchestration.intend.node._do_search_ontology",
        ) as mock_search,
    ):
        result = await intend_module.intend_node(_make_state(), _make_config())

    mock_search.assert_not_called()
    assert result["execution_status"] == "execution"
    assert "active_tools" not in result


# ── TC-4.1-01e：_do_search_ontology 抛异常 → 静默降级 ────────────────────────


@pytest.mark.asyncio
async def test_cold_start_silently_degrades_on_search_error() -> None:
    """_do_search_ontology 抛异常时，intend_node 仍正常返回，不 crash。"""
    from datacloud_analysis.orchestration.intend import node as intend_module
    from datacloud_analysis.tools import tool_pool

    with (
        _patch_command_router_no_match(),
        patch.object(tool_pool, "TOOL_POOL_THRESHOLD", 1),
        patch.object(tool_pool, "TOOL_POOL", {"get_spans": MagicMock()}),
        patch.object(tool_pool, "TOOL_TO_OBJECT", {"get_spans": "ops_langfuse_trace"}),
        patch(
            "datacloud_analysis.orchestration.intend.node._do_search_ontology",
            side_effect=RuntimeError("search engine unavailable"),
        ),
    ):
        result = await intend_module.intend_node(_make_state(), _make_config())

    # 不崩溃，正常路由
    assert result["execution_status"] == "execution"
    # active_tools 未被写入（降级后跳过）
    assert "active_tools" not in result


# ── TC-4.1-01f：命中对象无工具 → active_tools=[] ─────────────────────────────


@pytest.mark.asyncio
async def test_cold_start_returns_empty_list_when_hit_has_no_tools() -> None:
    """search_ontology 命中的对象在 TOOL_POOL 中没有注册工具 → active_tools=[]，不报错。"""
    from datacloud_analysis.orchestration.intend import node as intend_module
    from datacloud_analysis.tools import tool_pool

    fake_hits = [{"objectCode": "ops_unknown_object", "resultType": "object", "score": 0.8}]

    with (
        _patch_command_router_no_match(),
        patch.object(tool_pool, "TOOL_POOL_THRESHOLD", 0),  # 配额=0，不补充
        patch.object(tool_pool, "TOOL_POOL", {"get_spans": MagicMock()}),
        patch.object(tool_pool, "TOOL_TO_OBJECT", {"get_spans": "ops_langfuse_trace"}),
        patch(
            "datacloud_analysis.orchestration.intend.node._do_search_ontology",
            return_value=fake_hits,
        ),
        patch("datacloud_analysis.orchestration.intend.node.TOOL_POOL", {"get_spans": MagicMock()}),
        patch(
            "datacloud_analysis.orchestration.intend.node.TOOL_TO_OBJECT",
            {"get_spans": "ops_langfuse_trace"},
        ),
        patch("datacloud_analysis.orchestration.intend.node.TOOL_POOL_THRESHOLD", 0),
    ):
        result = await intend_module.intend_node(_make_state(), _make_config())

    assert result["execution_status"] == "execution"
    assert result["active_tools"] == []
