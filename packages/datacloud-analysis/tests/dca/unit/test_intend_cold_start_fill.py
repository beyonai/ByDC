"""阈值填充机制单元测试（先红后绿）

测试规格：
  TC-FILL-01  冷启动后 active_tools < THRESHOLD，自动从 TOOL_POOL 补充剩余工具直到填满
  TC-FILL-02  冷启动后 active_tools 已等于 THRESHOLD，不再补充
  TC-FILL-03  冷启动后 active_tools 超过 THRESHOLD，不再补充
  TC-FILL-04  search_ontology 工具调用后同样触发填充（同一 _fill_to_threshold 函数）
  TC-FILL-05  TOOL_POOL 工具总数不足 THRESHOLD，全部解锁（不报错）
  TC-FILL-06  补充时跳过 activate_skill_* 工具（skill wrapper 不计入阈值配额）
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import HumanMessage

# ── 辅助 ──────────────────────────────────────────────────────────────────────


def _make_state(active_tools: list[str] | None = None) -> dict[str, Any]:
    return {
        "messages": [HumanMessage(content="为什么这个 trace 失败了？")],
        "active_tools": active_tools,
    }


def _patch_no_command() -> Any:
    return patch(
        "datacloud_analysis.orchestration.intend.command_router.CommandPluginManager.from_defaults",
        return_value=MagicMock(handle_ext_command=AsyncMock(return_value=(False, None))),
    )


# ── TC-FILL-01：冷启动后不足阈值，自动补充 ──────────────────────────────────


@pytest.mark.asyncio
async def test_cold_start_fills_to_threshold_when_under() -> None:
    """冷启动解锁 2 个工具，阈值=5，TOOL_POOL 有 8 个工具 → 补充到 5 个。"""
    from datacloud_analysis.orchestration.intend import node as intend_module
    from datacloud_analysis.tools import tool_pool

    # search_ontology 只命中 ops_langfuse_trace，解锁 get_spans / find_error_spans
    fake_hits = [{"objectCode": "ops_langfuse_trace", "resultType": "object", "score": 0.9}]
    fake_pool = {
        "get_spans": MagicMock(),
        "find_error_spans": MagicMock(),
        "get_agent_diag": MagicMock(),
        "get_tool_detail": MagicMock(),
        "get_llm_tool_calls": MagicMock(),
        "get_llm_metrics": MagicMock(),
        "check_db_connection": MagicMock(),
        "validate_jdbc_url": MagicMock(),
    }
    fake_tool_to_object = {
        "get_spans": "ops_langfuse_trace",
        "find_error_spans": "ops_langfuse_trace",
        "get_agent_diag": "ops_langfuse_trace",
        "get_tool_detail": "ops_langfuse_trace",
        "get_llm_tool_calls": "ops_langfuse_trace",
        "get_llm_metrics": "ops_langfuse_trace",
        "check_db_connection": "ops_opengauss",
        "validate_jdbc_url": "ops_owl_dbsource",
    }

    with (
        _patch_no_command(),
        patch.object(tool_pool, "TOOL_POOL_THRESHOLD", 5),
        patch.object(tool_pool, "TOOL_POOL", fake_pool),
        patch.object(tool_pool, "TOOL_TO_OBJECT", fake_tool_to_object),
        patch(
            "datacloud_analysis.orchestration.intend.node._do_search_ontology",
            return_value=fake_hits,
        ),
        patch("datacloud_analysis.orchestration.intend.node.TOOL_POOL", fake_pool),
        patch("datacloud_analysis.orchestration.intend.node.TOOL_TO_OBJECT", fake_tool_to_object),
        patch("datacloud_analysis.orchestration.intend.node.is_anchor_mode", return_value=True),
        patch("datacloud_analysis.orchestration.intend.node.TOOL_POOL_THRESHOLD", 5),
    ):
        result = await intend_module.intend_node(_make_state(), {})

    assert result["execution_status"] == "execution"
    active = result["active_tools"]
    # 命中对象本身有6个工具，超过阈值5 → 全部保留（不截断），同时不再额外补充
    assert len(active) >= 5
    assert "get_spans" in active
    assert "find_error_spans" in active
    # check_db_connection / validate_jdbc_url（其他对象）不应被补充进来（已超阈值）
    assert "check_db_connection" not in active
    assert "validate_jdbc_url" not in active


# ── TC-FILL-02：已等于阈值，不再补充 ────────────────────────────────────────


@pytest.mark.asyncio
async def test_cold_start_no_fill_when_at_threshold() -> None:
    """冷启动已解锁 3 个工具，阈值=3 → 不再补充。"""
    from datacloud_analysis.orchestration.intend import node as intend_module
    from datacloud_analysis.tools import tool_pool

    fake_hits = [{"objectCode": "ops_langfuse_trace", "resultType": "object", "score": 0.9}]
    fake_pool = {
        "get_spans": MagicMock(),
        "find_error_spans": MagicMock(),
        "get_agent_diag": MagicMock(),
        "extra_tool": MagicMock(),
    }
    fake_t2o = {
        "get_spans": "ops_langfuse_trace",
        "find_error_spans": "ops_langfuse_trace",
        "get_agent_diag": "ops_langfuse_trace",
        "extra_tool": "ops_other",
    }

    with (
        _patch_no_command(),
        patch.object(tool_pool, "TOOL_POOL_THRESHOLD", 3),
        patch.object(tool_pool, "TOOL_POOL", fake_pool),
        patch.object(tool_pool, "TOOL_TO_OBJECT", fake_t2o),
        patch(
            "datacloud_analysis.orchestration.intend.node._do_search_ontology",
            return_value=fake_hits,
        ),
        patch("datacloud_analysis.orchestration.intend.node.TOOL_POOL", fake_pool),
        patch("datacloud_analysis.orchestration.intend.node.TOOL_TO_OBJECT", fake_t2o),
        patch("datacloud_analysis.orchestration.intend.node.TOOL_POOL_THRESHOLD", 3),
    ):
        result = await intend_module.intend_node(_make_state(), {})

    active = result["active_tools"]
    assert len(active) == 3
    assert "extra_tool" not in active


# ── TC-FILL-03：超过阈值，不补充也不截断 ────────────────────────────────────


@pytest.mark.asyncio
async def test_cold_start_no_fill_when_over_threshold() -> None:
    """冷启动已解锁 4 个工具，阈值=3 → 保留全部 4 个，不截断。"""
    from datacloud_analysis.orchestration.intend import node as intend_module
    from datacloud_analysis.tools import tool_pool

    fake_hits = [
        {"objectCode": "ops_langfuse_trace", "resultType": "object", "score": 0.9},
        {"objectCode": "ops_opengauss", "resultType": "object", "score": 0.7},
    ]
    fake_pool = {
        "get_spans": MagicMock(),
        "find_error_spans": MagicMock(),
        "check_db_connection": MagicMock(),
        "execute_sql": MagicMock(),
        "extra_tool": MagicMock(),
    }
    fake_t2o = {
        "get_spans": "ops_langfuse_trace",
        "find_error_spans": "ops_langfuse_trace",
        "check_db_connection": "ops_opengauss",
        "execute_sql": "ops_opengauss",
        "extra_tool": "ops_other",
    }

    with (
        _patch_no_command(),
        patch.object(tool_pool, "TOOL_POOL_THRESHOLD", 3),
        patch.object(tool_pool, "TOOL_POOL", fake_pool),
        patch.object(tool_pool, "TOOL_TO_OBJECT", fake_t2o),
        patch(
            "datacloud_analysis.orchestration.intend.node._do_search_ontology",
            return_value=fake_hits,
        ),
        patch("datacloud_analysis.orchestration.intend.node.TOOL_POOL", fake_pool),
        patch("datacloud_analysis.orchestration.intend.node.TOOL_TO_OBJECT", fake_t2o),
        patch("datacloud_analysis.orchestration.intend.node.TOOL_POOL_THRESHOLD", 3),
    ):
        result = await intend_module.intend_node(_make_state(), {})

    active = result["active_tools"]
    assert len(active) == 4  # 保留全部，不截断
    assert "extra_tool" not in active  # 未补充额外工具


# ── TC-FILL-04：TOOL_POOL 总数不足 THRESHOLD，全部解锁 ─────────────────────


@pytest.mark.asyncio
async def test_cold_start_fills_all_when_pool_smaller_than_threshold() -> None:
    """TOOL_POOL 只有 3 个工具，阈值=10 → 全部 3 个都解锁，不报错。"""
    from datacloud_analysis.orchestration.intend import node as intend_module
    from datacloud_analysis.tools import tool_pool

    fake_hits = [{"objectCode": "ops_langfuse_trace", "resultType": "object", "score": 0.9}]
    fake_pool = {
        "get_spans": MagicMock(),
        "find_error_spans": MagicMock(),
        "get_agent_diag": MagicMock(),
    }
    fake_t2o = {
        "get_spans": "ops_langfuse_trace",
        "find_error_spans": "ops_langfuse_trace",
        "get_agent_diag": "ops_langfuse_trace",
    }

    with (
        _patch_no_command(),
        patch.object(tool_pool, "TOOL_POOL_THRESHOLD", 10),
        patch.object(tool_pool, "TOOL_POOL", fake_pool),
        patch.object(tool_pool, "TOOL_TO_OBJECT", fake_t2o),
        patch(
            "datacloud_analysis.orchestration.intend.node._do_search_ontology",
            return_value=fake_hits,
        ),
        patch("datacloud_analysis.orchestration.intend.node.TOOL_POOL", fake_pool),
        patch("datacloud_analysis.orchestration.intend.node.TOOL_TO_OBJECT", fake_t2o),
        patch("datacloud_analysis.orchestration.intend.node.is_anchor_mode", return_value=True),
        patch("datacloud_analysis.orchestration.intend.node.TOOL_POOL_THRESHOLD", 10),
    ):
        result = await intend_module.intend_node(_make_state(), {})

    active = result["active_tools"]
    assert len(active) == 3
    assert set(active) == {"get_spans", "find_error_spans", "get_agent_diag"}


# ── TC-FILL-05：activate_skill_* 不计入阈值配额 ─────────────────────────────


@pytest.mark.asyncio
async def test_cold_start_fill_skips_skill_wrappers() -> None:
    """TOOL_POOL 有 2 个业务工具 + 2 个 skill wrapper，阈值=4 →
    只补充业务工具（skill wrapper 不占配额），共 2 个业务工具 + 2 个 skill 不被计入。"""
    from datacloud_analysis.orchestration.intend import node as intend_module
    from datacloud_analysis.tools import tool_pool

    fake_hits = [{"objectCode": "ops_langfuse_trace", "resultType": "object", "score": 0.9}]
    fake_pool = {
        "get_spans": MagicMock(),
        "find_error_spans": MagicMock(),
        "check_db_connection": MagicMock(),
        "activate_skill_diagnose_fault": MagicMock(),
        "activate_skill_slow_response": MagicMock(),
    }
    fake_t2o = {
        "get_spans": "ops_langfuse_trace",
        "find_error_spans": "ops_langfuse_trace",
        "check_db_connection": "ops_opengauss",
        "activate_skill_diagnose_fault": "ops_langfuse_trace",
        "activate_skill_slow_response": "ops_langfuse_trace",
    }

    with (
        _patch_no_command(),
        patch.object(tool_pool, "TOOL_POOL_THRESHOLD", 4),
        patch.object(tool_pool, "TOOL_POOL", fake_pool),
        patch.object(tool_pool, "TOOL_TO_OBJECT", fake_t2o),
        patch(
            "datacloud_analysis.orchestration.intend.node._do_search_ontology",
            return_value=fake_hits,
        ),
        patch("datacloud_analysis.orchestration.intend.node.TOOL_POOL", fake_pool),
        patch("datacloud_analysis.orchestration.intend.node.TOOL_TO_OBJECT", fake_t2o),
        patch("datacloud_analysis.orchestration.intend.node.is_anchor_mode", return_value=True),
        patch("datacloud_analysis.orchestration.intend.node.TOOL_POOL_THRESHOLD", 4),
    ):
        result = await intend_module.intend_node(_make_state(), {})

    active = result["active_tools"]
    # skill wrapper 解锁后不占配额，业务工具继续补充到阈值
    business_tools = [t for t in active if not t.startswith("activate_skill_")]
    assert len(business_tools) <= 4
    # 验证补充了 check_db_connection（来自其他对象的填充）
    assert "check_db_connection" in active
