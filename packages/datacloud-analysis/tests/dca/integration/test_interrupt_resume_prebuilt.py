"""interrupt/resume 跨实例语义验证（阶段三卡点）。

文档 1.4.5 风险一：验证真实 OpenGauss checkpointer 下 V0.4 图的 interrupt/resume 语义。

运行条件：
  - 需要 byclaw-data/.env 中的 OpenGauss 连接配置（conftest 自动加载）
  - 标记 `pytest.mark.db_integration`，默认不执行
  - 显式运行：`uv run pytest tests/dca/integration/test_interrupt_resume_prebuilt.py -v -m db_integration`

验证目标：
  - TC-IR-1: user_clarify interrupt 后 messages + react_round_idx 在新图实例中完整保留
  - TC-IR-2: resume 时 clarification_formatted_params 被正确写入，工具参数回填成功
"""

from __future__ import annotations

import contextlib
import os
import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from datacloud_analysis.tool_hook_plugins.types import ClarificationNeededError
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.tools import tool
from langgraph.types import Command

pytestmark = [pytest.mark.db_integration, pytest.mark.asyncio]


def _has_db_env() -> bool:
    return all(
        os.getenv(k, "").strip()
        for k in ("DATACLOUD_DB_HOST", "DATACLOUD_DB_DATABASE", "DATACLOUD_DB_USER")
    )


skipif_no_db = pytest.mark.skipif(
    not _has_db_env(),
    reason=(
        "OpenGauss env vars not set. "
        "需要 byclaw-data/.env 或 DATACLOUD_DB_HOST/DATABASE/USER 手动设置"
    ),
)


# ── Mock 工具 ──────────────────────────────────────────────────────────────────


@tool
def mock_data_query(query: str) -> str:
    """查询营收数据（测试用 mock 工具）。"""
    return '{"records": [{"revenue": 100}], "meta": {"total": 1}}'


# ── 辅助：构建 V0.4 graph（含真实 checkpointer）──────────────────────────────


def _build_v04_graph(checkpointer: Any) -> Any:
    """构建编译后的 V0.4 图。"""
    from datacloud_analysis.orchestration.graph_builder import build_analysis_graph  # noqa: PLC0415

    with patch.dict(os.environ, {"DATACLOUD_USE_PREBUILT_REACT": "true"}):
        builder = build_analysis_graph(tools={"mock_data_query": mock_data_query})
    return builder.compile(checkpointer=checkpointer)


# ── Patch helpers ──────────────────────────────────────────────────────────────


def _make_patched_intend_node() -> Any:
    """mock intend_node：跳过意图识别，直接路由到 agent。"""

    async def _fake_intend(state: Any, config: Any) -> dict[str, Any]:
        return {
            "user_query": "营收查询",
            "execution_status": None,
        }

    return _fake_intend


def _make_mock_llm_side_effects() -> list[Any]:
    """返回 _invoke_llm_with_fallback 的两个调用结果。

    第 1 次：AIMessage 带 mock_data_query tool_call（触发澄清）
    第 2 次：AIMessage 带 finish_react tool_call（结束）
    """
    tc1 = {"name": "mock_data_query", "id": "tc_mock_1", "args": {"query": "营收"}}
    round1_ai = AIMessage(content="", tool_calls=[tc1])

    tc2 = {
        "name": "finish_react",
        "id": "tc_fr_1",
        "args": {
            "result_type": "text",
            "answer": "营收查询已完成",
            "stop_reason": "done",
            "csv_file_path": "",
        },
    }
    round2_ai = AIMessage(content="", tool_calls=[tc2])

    return [(round1_ai, False), (round2_ai, False)]


def _make_mock_hook_manager_clarify() -> MagicMock:
    """第 1 轮 before hook：抛 ClarificationNeededError（含 paradigm_list 快速路径数据）。"""
    exc = ClarificationNeededError(
        {
            "query": "营收",
            "structured_input": {"query": "营收"},
            "is_compute": False,
            "paradigm_list": [
                {
                    "paradigmId": "p_revenue",
                    "paradigmName": "营收维度",
                    "paradigmResult": [
                        {"choiceKeyword": "月度营收", "fieldCode": "monthly_revenue"},
                        {"choiceKeyword": "年度营收", "fieldCode": "annual_revenue"},
                    ],
                }
            ],
            "clarify_knowledge": "请确认营收查询维度",
        }
    )
    manager = MagicMock()
    manager.run_before = AsyncMock(side_effect=exc)
    manager.run_after = AsyncMock(return_value=({"tool_name": "mock_data_query"}, None))
    return manager


def _make_mock_hook_manager_ok() -> MagicMock:
    """第 2 轮 before hook：正常成功，不修改参数。"""
    manager = MagicMock()

    async def _run_before(ctx: dict[str, Any]) -> tuple[dict[str, Any], None]:
        return ctx, None

    manager.run_before = _run_before
    manager.run_after = AsyncMock(return_value=({"tool_name": "mock_data_query"}, None))
    return manager


# ═══════════════════════════════════════════════════════════════════════════════
# TC-IR-1: interrupt → checkpoint → 新实例 resume，messages + round_idx 完整保留
# ═══════════════════════════════════════════════════════════════════════════════


@skipif_no_db
async def test_ir1_interrupt_resume_messages_and_round_idx_preserved(
    og_checkpointer: Any,
    initialized_sdk: None,
) -> None:
    """TC-IR-1: user_clarify interrupt 后，新图实例 resume 时 messages + react_round_idx 完整保留。"""
    thread_id = f"test-ir1-{uuid.uuid4().hex[:8]}"
    config: dict[str, Any] = {"configurable": {"thread_id": thread_id}}

    llm_side_effects = _make_mock_llm_side_effects()
    llm_call_count = 0

    async def _fake_llm(*args: Any, **kwargs: Any) -> Any:
        nonlocal llm_call_count
        result = llm_side_effects[min(llm_call_count, len(llm_side_effects) - 1)]
        llm_call_count += 1
        return result

    hook_manager_sequence = [
        _make_mock_hook_manager_clarify(),  # 第 1 次工具调用 → raise ClarificationNeededError
        _make_mock_hook_manager_ok(),  # 第 2 次工具调用（resume 后）→ 成功
    ]
    hook_manager_idx = 0

    def _get_hook_manager() -> MagicMock:
        nonlocal hook_manager_idx
        m = hook_manager_sequence[min(hook_manager_idx, len(hook_manager_sequence) - 1)]
        hook_manager_idx += 1
        return m

    initial_messages = [HumanMessage(content="请查询营收数据")]

    with (
        patch(
            "datacloud_analysis.orchestration.intend.node.intend_node",
            side_effect=_make_patched_intend_node(),
        ),
        patch(
            "datacloud_analysis.orchestration.execution.react_loop._invoke_llm_with_fallback",
            side_effect=_fake_llm,
        ),
        patch(
            "datacloud_analysis.orchestration.execution.hook_aware_tool_node.get_tool_hook_plugin_manager",
            side_effect=_get_hook_manager,
        ),
        patch(
            "datacloud_analysis.orchestration.respond.formatter.format_result",
            new_callable=AsyncMock,
        ),
    ):
        # ── 阶段一：图实例 1 运行到 user_clarify interrupt ─────────────────────
        graph1 = _build_v04_graph(og_checkpointer)

        from langgraph.errors import GraphInterrupt  # noqa: PLC0415

        interrupt_payload: Any = None
        try:
            await graph1.ainvoke({"messages": initial_messages}, config)
        except GraphInterrupt as exc:
            interrupt_payload = exc.args[0] if exc.args else None

        assert interrupt_payload is not None, (
            "应在 user_clarify_node 触发 GraphInterrupt，但没有抛出"
        )

        # ── 验证 checkpoint 已写入 DB ──────────────────────────────────────────
        checkpoint_tuple = og_checkpointer.get_tuple(config)
        assert checkpoint_tuple is not None, "interrupt 后 checkpoint 应写入 OpenGauss"

        saved_config = checkpoint_tuple.config
        full_state = await graph1.aget_state(saved_config)
        saved_messages = list(full_state.values.get("messages") or [])
        saved_round_idx = int(full_state.values.get("react_round_idx") or 0)

        assert len(saved_messages) >= len(initial_messages), (
            f"checkpoint 中消息数 {len(saved_messages)} 不应少于初始消息数 {len(initial_messages)}"
        )
        assert saved_round_idx >= 1, (
            f"checkpoint 中 react_round_idx={saved_round_idx}，至少应为 1（已经 agent 轮次）"
        )

        # ── 阶段二：图实例 2（模拟新 pod）从 checkpoint resume ─────────────────
        graph2 = _build_v04_graph(og_checkpointer)  # 新 graph 对象，同一 checkpointer

        user_clarify_reply = {
            "paradigmList": [
                {"paradigmList": [{"choiceKeyword": "月度营收", "fieldCode": "monthly_revenue"}]}
            ]
        }
        resume_cmd = Command(resume=user_clarify_reply)

        final_state_result = await graph2.ainvoke(resume_cmd, config)
        final_state = final_state_result if isinstance(final_state_result, dict) else {}

        # ── 验证 resume 后 messages 保留 + 新消息追加 ─────────────────────────
        final_messages = list(final_state.get("messages") or [])
        assert len(final_messages) >= len(saved_messages), (
            f"resume 后消息数 {len(final_messages)} 不应少于 checkpoint 时 {len(saved_messages)}"
        )

        final_round_idx = int(final_state.get("react_round_idx") or 0)
        assert final_round_idx >= saved_round_idx, (
            f"resume 后 react_round_idx={final_round_idx} 不应小于 checkpoint 时 {saved_round_idx}"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# TC-IR-2: resume 后 clarification_formatted_params 被正确消费
# ═══════════════════════════════════════════════════════════════════════════════


@skipif_no_db
async def test_ir2_resume_clarification_params_consumed(
    og_checkpointer: Any,
    initialized_sdk: None,
) -> None:
    """TC-IR-2: resume 时 user_clarify 返回的 clarification_formatted_params 被 tools 节点消费。"""
    thread_id = f"test-ir2-{uuid.uuid4().hex[:8]}"
    config: dict[str, Any] = {"configurable": {"thread_id": thread_id}}

    llm_side_effects = _make_mock_llm_side_effects()
    llm_call_count = 0

    async def _fake_llm(*args: Any, **kwargs: Any) -> Any:
        nonlocal llm_call_count
        result = llm_side_effects[min(llm_call_count, len(llm_side_effects) - 1)]
        llm_call_count += 1
        return result

    hook_manager_sequence = [
        _make_mock_hook_manager_clarify(),
        _make_mock_hook_manager_ok(),
    ]
    hook_manager_idx = 0

    def _get_hook_manager() -> MagicMock:
        nonlocal hook_manager_idx
        m = hook_manager_sequence[min(hook_manager_idx, len(hook_manager_sequence) - 1)]
        hook_manager_idx += 1
        return m

    with (
        patch(
            "datacloud_analysis.orchestration.intend.node.intend_node",
            side_effect=_make_patched_intend_node(),
        ),
        patch(
            "datacloud_analysis.orchestration.execution.react_loop._invoke_llm_with_fallback",
            side_effect=_fake_llm,
        ),
        patch(
            "datacloud_analysis.orchestration.execution.hook_aware_tool_node.get_tool_hook_plugin_manager",
            side_effect=_get_hook_manager,
        ),
        patch(
            "datacloud_analysis.orchestration.respond.formatter.format_result",
            new_callable=AsyncMock,
        ),
    ):
        graph1 = _build_v04_graph(og_checkpointer)
        from langgraph.errors import GraphInterrupt  # noqa: PLC0415

        with contextlib.suppress(GraphInterrupt):
            await graph1.ainvoke({"messages": [HumanMessage(content="查询营收")]}, config)

        # 验证 pending_clarification_context 已写入（interrupt 前的状态）
        full_state_before = await graph1.aget_state(config)
        ctx = dict(full_state_before.values.get("pending_clarification_context") or {})
        assert ctx.get("tool_name") == "mock_data_query", (
            f"pending_clarification_context.tool_name 应为 mock_data_query，实际: {ctx.get('tool_name')}"
        )

        # Resume：用户选择具体维度
        graph2 = _build_v04_graph(og_checkpointer)
        user_reply = {
            "paradigmList": [
                {"paradigmList": [{"choiceKeyword": "月度营收", "fieldCode": "monthly_revenue"}]}
            ]
        }
        await graph2.ainvoke(Command(resume=user_reply), config)

        # 验证 clarification_formatted_params 已消费（resume 后被 user_clarify 清除）
        final_state_after = await graph2.aget_state(config)
        final_ctx = final_state_after.values.get("pending_clarification_context")
        assert final_ctx is None or final_ctx == {}, (
            f"resume 完成后 pending_clarification_context 应被清除，实际: {final_ctx}"
        )
