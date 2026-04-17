"""TC-06 ~ TC-09: execution_node 知识增强注入 system_prompt（层 A）测试。"""

from __future__ import annotations

from unittest.mock import patch

from langchain_core.messages import HumanMessage


def _make_state(knowledge_snippets: list | None = None) -> dict:
    return {
        "messages": [HumanMessage(content="查询营收")],
        "agent_id": "test-agent",
        "workspace_dir": None,
        "user_query": "查询营收",
        "knowledge_payload": None,
        "knowledge_snippets": knowledge_snippets,
        "confirmed_terms": None,
        "react_rounds": None,
        "react_checkpoint": None,
        "react_final": None,
        "execution_status": "execution",
    }


def _make_config() -> dict:
    return {"configurable": {}}


def _make_mock_react_loop(captured: list[str]):
    """返回兼容 run_react_loop 关键字参数签名的 mock。"""

    async def mock_react_loop(
        *,
        state,
        tools_list,
        system_prompt,
        stable_system_prompt=None,
        dynamic_prompt=None,
        max_rounds=None,
        gateway_context=None,
    ):
        captured.append(system_prompt)
        return {"react_rounds": 0, "react_final": {}, "messages": [], "results": []}

    return mock_react_loop


# ---------------------------------------------------------------------------
# TC-06: knowledge_snippets 非空 → system_prompt 含可读字段映射段落，不含原始 JSON
# ---------------------------------------------------------------------------
async def test_tc06_knowledge_snippets_injected_as_readable_text() -> None:
    snippets = ["营收 → 企业总营收（万元）", "利润 → 企业总利润（万元）"]
    state = _make_state(knowledge_snippets=snippets)

    captured_prompts: list[str] = []

    with patch(
        "datacloud_analysis.orchestration.execution.node.run_react_loop",
        side_effect=_make_mock_react_loop(captured_prompts),
    ):
        from datacloud_analysis.orchestration.execution.node import execution_node

        await execution_node(state, _make_config())

    assert captured_prompts, "run_react_loop 应被调用"
    prompt = captured_prompts[0]
    assert "数据查询知识增强" in prompt, "system_prompt 应包含知识增强段落标题"
    assert "营收 → 企业总营收（万元）" in prompt, "system_prompt 应包含可读字段映射"
    assert "利润 → 企业总利润（万元）" in prompt
    assert "paradigmList" not in prompt, "system_prompt 不应包含原始 JSON 结构"


# ---------------------------------------------------------------------------
# TC-07: knowledge_snippets 为空 → 无知识增强段落；runtime_section 仍存在
# ---------------------------------------------------------------------------
async def test_tc07_empty_snippets_system_prompt_unchanged() -> None:
    state_with = _make_state(knowledge_snippets=["营收 → 企业总营收（万元）"])
    state_without = _make_state(knowledge_snippets=None)

    captured: list[str] = []

    with patch(
        "datacloud_analysis.orchestration.execution.node.run_react_loop",
        side_effect=_make_mock_react_loop(captured),
    ):
        from datacloud_analysis.orchestration.execution.node import execution_node

        await execution_node(state_with, _make_config())
        await execution_node(state_without, _make_config())

    assert len(captured) == 2
    prompt_with, prompt_without = captured
    # 有 snippets 时含知识增强段落
    assert "数据查询知识增强" in prompt_with
    # 无 snippets 时不含知识增强段落
    assert "数据查询知识增强" not in prompt_without, "无 snippets 时不应有增强段落"
    # 两者都应包含 runtime_section（当前会话信息）
    assert "当前会话信息" in prompt_with
    assert "当前会话信息" in prompt_without
    assert "当前时间" in prompt_without


# ---------------------------------------------------------------------------
# TC-08: runtime_section 用户信息注入（从 gateway_context.current_command.header.metadata 取）
# ---------------------------------------------------------------------------
async def test_tc08_runtime_section_contains_user_info() -> None:
    """有 gateway_context 且 header.metadata 含 user_code/user_name 时，
    system_prompt 末尾应包含用户信息，且位于所有其他段落之后。"""
    from unittest.mock import MagicMock

    state = _make_state()

    mock_ctx = MagicMock()
    mock_ctx.current_command.header.metadata = {
        "user_code": "U001",
        "user_name": "张三",
    }

    captured: list[str] = []

    config = {"configurable": {"gateway_context": mock_ctx}}

    with patch(
        "datacloud_analysis.orchestration.execution.node.run_react_loop",
        side_effect=_make_mock_react_loop(captured),
    ):
        from datacloud_analysis.orchestration.execution.node import execution_node

        await execution_node(state, config)

    assert captured
    prompt = captured[0]
    assert "当前会话信息" in prompt
    assert "当前时间" in prompt
    assert "张三" in prompt
    assert "U001" in prompt
    # runtime_section 必须在 prompt 末尾（知识段落之后）
    runtime_idx = prompt.index("当前会话信息")
    exec_rules_idx = prompt.index("执行规则")
    assert runtime_idx > exec_rules_idx, "runtime_section 应在执行规则之后"


async def test_tc09_runtime_section_no_user_info_when_metadata_empty() -> None:
    """gateway_context 无 user_code/user_name 时，仅有时间，无用户行。"""
    from unittest.mock import MagicMock

    state = _make_state()

    mock_ctx = MagicMock()
    mock_ctx.current_command.header.metadata = {}

    captured: list[str] = []

    config = {"configurable": {"gateway_context": mock_ctx}}

    with patch(
        "datacloud_analysis.orchestration.execution.node.run_react_loop",
        side_effect=_make_mock_react_loop(captured),
    ):
        from datacloud_analysis.orchestration.execution.node import execution_node

        await execution_node(state, config)

    assert captured
    prompt = captured[0]
    assert "当前会话信息" in prompt
    assert "当前时间" in prompt
    assert "当前用户" not in prompt
