"""interrupt/resume 跨实例语义验证（阶段三卡点）。

文档 1.4.5 风险一：需要真实 OpenGauss checkpointer 验证跨实例 resume 语义。

**卡点**：此测试不通过，阻塞阶段三完成，不进入阶段四。

运行条件：
  - 需要真实 OpenGauss/PostgreSQL 实例
  - 标记 `pytest.mark.db_integration`，默认不执行
  - `uv run pytest -m db_integration` 显式运行
"""

from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.db_integration


# ── 测试所需辅助工具 ───────────────────────────────────────────────────────────


@pytest.fixture
def pg_dsn() -> str:
    """从环境变量获取 PostgreSQL DSN。"""
    dsn = os.getenv("DATACLOUD_TEST_PG_DSN", "")
    if not dsn:
        pytest.skip("DATACLOUD_TEST_PG_DSN not set")
    return dsn


# ═══════════════════════════════════════════════════════════════════════════════
# TC-IR-1: interrupt → 序列化 checkpoint → 新实例 resume
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_ir1_interrupt_resume_across_invocations(pg_dsn: str) -> None:
    """TC-IR-1: user_clarify interrupt 后，跨实例 resume 时 messages / round_idx 完整保留。

    步骤：
    1. 构建新图（DATACLOUD_USE_PREBUILT_REACT=true），使用 OpenGauss checkpointer
    2. 注入 ClarificationNeededError，触发 analyze_clarify → user_clarify → interrupt()
    3. 从 DB 读取 checkpoint，用新图实例 resume
    4. 断言：messages 条数一致，react_round_idx 正确，resume 后工具调用成功
    """
    # TODO(阶段三): 实现步骤
    # from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
    # from datacloud_analysis.orchestration.graph_builder import build_analysis_graph
    #
    # checkpointer = AsyncPostgresSaver.from_conn_string(pg_dsn)
    # await checkpointer.setup()
    #
    # graph = build_analysis_graph(...).compile(checkpointer=checkpointer, interrupt_before=["user_clarify"])
    # thread_id = "test-ir1"
    # config = {"configurable": {"thread_id": thread_id}}
    #
    # # Step 1: 运行到 interrupt
    # state_before = await graph.ainvoke(initial_state, config)
    # messages_before = list(state_before.get("messages") or [])
    # round_idx_before = int(state_before.get("react_round_idx") or 0)
    #
    # # Step 2: 新图实例（模拟跨实例），从 checkpoint 恢复
    # new_graph = build_analysis_graph(...).compile(checkpointer=checkpointer)
    # state_after = await new_graph.ainvoke(resume_input, config)
    # messages_after = list(state_after.get("messages") or [])
    #
    # # 断言
    # assert len(messages_after) >= len(messages_before), "resume 后消息不应减少"
    # assert state_after.get("react_round_idx") == round_idx_before or ..., "round_idx 应正确保留"
    pytest.skip("TODO(阶段三): 实现 interrupt/resume 集成测试")


# ═══════════════════════════════════════════════════════════════════════════════
# TC-IR-2: resume 后工具参数回填成功
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_ir2_resume_tool_params_backfilled(pg_dsn: str) -> None:
    """TC-IR-2: resume 时用户回复的参数正确回填到 pending_clarification_context。

    步骤：
    1. 同 TC-IR-1，触发 interrupt
    2. 构造用户澄清回复
    3. resume，断言工具调用参数包含用户回填值
    """
    # TODO(阶段三): 实现步骤
    pytest.skip("TODO(阶段三): 实现工具参数回填验证")
