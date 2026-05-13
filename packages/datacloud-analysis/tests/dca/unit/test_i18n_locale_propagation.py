"""国际化适配：locale 传递链路单元测试（先红后绿）。

覆盖范围：
- TC-I18N-01: graph_builder._build_legacy_graph 从 prompts_overwrite["locale"] 读取 locale
- TC-I18N-02: graph_builder._build_prebuilt_graph 从 prompts_overwrite["locale"] 读取 locale
- TC-I18N-03: graph_builder 无 prompts_overwrite 时回退到环境变量
- TC-I18N-04: execution_node 从 state prompts_overwrite["locale"] 读取 locale
- TC-I18N-05: execution_node 无 prompts_overwrite 时回退到环境变量
- TC-I18N-06: execution_node locale=en_US 时运行时会话信息输出英文
- TC-I18N-07: execution_node locale=zh_CN 时运行时会话信息输出中文
- TC-I18N-08: tool_wrapper dispatch_tool 构建 InvocationContext 时传入 language
"""

from __future__ import annotations

import os
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import HumanMessage

# ── 辅助 ──────────────────────────────────────────────────────────────────────


def _make_execution_state(
    locale: str | None = None,
    user_name: str = "",
    user_code: str = "",
    knowledge_snippets: list | None = None,
) -> dict[str, Any]:
    state: dict[str, Any] = {
        "messages": [HumanMessage(content="test query")],
        "agent_id": "test-agent",
        "workspace_dir": None,
        "user_query": "test query",
        "knowledge_payload": None,
        "knowledge_snippets": knowledge_snippets,
        "confirmed_terms": None,
        "react_rounds": None,
        "react_checkpoint": None,
        "react_final": None,
        "execution_status": "execution",
        "prompts_overwrite": {"locale": locale} if locale else {},
    }
    return state


def _make_execution_config(user_name: str = "", user_code: str = "") -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    if user_name:
        metadata["user_name"] = user_name
    if user_code:
        metadata["user_code"] = user_code

    class _FakeHeader:
        def __init__(self) -> None:
            self.metadata = metadata

    class _FakeCommand:
        def __init__(self) -> None:
            self.header = _FakeHeader()

    class _FakeGateway:
        def __init__(self) -> None:
            self.current_command = _FakeCommand()

    return {"configurable": {"gateway_context": _FakeGateway()}}


def _make_react_loop_capture(captured: list[str]) -> Any:
    async def _mock(
        *,
        state: Any,
        tools_list: Any,
        system_prompt: str,
        stable_system_prompt: str | None = None,
        dynamic_prompt: str | None = None,
        max_rounds: int | None = None,
        gateway_context: Any = None,
        loader: Any = None,
        redirect_tools_map: Any = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        captured.append(system_prompt)
        return {"react_rounds": 0, "react_final": {}, "messages": [], "results": []}

    return _mock


# ── TC-I18N-01 / 02 / 03: graph_builder locale 读取 ──────────────────────────


def test_tc_i18n_01_legacy_graph_reads_locale_from_prompts_overwrite() -> None:
    """_build_legacy_graph 应从 prompts_overwrite["locale"] 读取 locale，而非环境变量。"""
    from datacloud_analysis.i18n.prompts import get_system_prompt

    captured_locale: list[str] = []
    original_get_system_prompt = get_system_prompt

    def _spy_get_system_prompt(locale: str | None = None) -> str:
        captured_locale.append(locale or "")
        return original_get_system_prompt(locale)

    with (
        patch.dict(os.environ, {"DATACLOUD_AGENT_LOCALE": "zh_CN"}),
        patch(
            "datacloud_analysis.orchestration.graph_builder.get_system_prompt",
            side_effect=_spy_get_system_prompt,
        ),
        patch(
            "datacloud_analysis.orchestration.graph_builder.get_execution_prompt",
            return_value="",
        ),
        patch(
            "datacloud_analysis.orchestration.graph_builder._build_tools_list",
            return_value=[],
        ),
        patch(
            "datacloud_analysis.orchestration.graph_builder.make_llm_call_node",
            return_value=AsyncMock(),
        ),
        patch(
            "datacloud_analysis.orchestration.graph_builder.make_tool_dispatcher_node",
            return_value=AsyncMock(),
        ),
    ):
        from datacloud_analysis.orchestration.graph_builder import _build_legacy_graph

        _build_legacy_graph(prompts_overwrite={"locale": "en_US"})

    assert captured_locale, "get_system_prompt was not called"
    assert captured_locale[0] == "en_US", (
        f"Expected locale 'en_US' from prompts_overwrite, got '{captured_locale[0]}'"
    )


def test_tc_i18n_02_prebuilt_graph_reads_locale_from_prompts_overwrite() -> None:
    """_build_prebuilt_graph 应从 prompts_overwrite["locale"] 读取 locale，而非环境变量。"""
    from datacloud_analysis.i18n.prompts import get_system_prompt

    captured_locale: list[str] = []
    original_get_system_prompt = get_system_prompt

    def _spy_get_system_prompt(locale: str | None = None) -> str:
        captured_locale.append(locale or "")
        return original_get_system_prompt(locale)

    with (
        patch.dict(os.environ, {"DATACLOUD_AGENT_LOCALE": "zh_CN"}),
        patch(
            "datacloud_analysis.orchestration.graph_builder.get_system_prompt",
            side_effect=_spy_get_system_prompt,
        ),
        patch(
            "datacloud_analysis.orchestration.graph_builder.get_execution_prompt",
            return_value="",
        ),
        patch(
            "datacloud_analysis.orchestration.graph_builder._build_tools_list",
            return_value=[],
        ),
        patch(
            "datacloud_analysis.orchestration.graph_builder.make_llm_call_node",
            return_value=AsyncMock(),
        ),
        patch(
            "datacloud_analysis.orchestration.execution.hook_aware_tool_node.HookAwareToolNode",
            MagicMock(),
        ),
        patch(
            "datacloud_analysis.orchestration.execution.react_loop.finish_react",
            MagicMock(),
        ),
    ):
        from datacloud_analysis.orchestration.graph_builder import _build_prebuilt_graph

        _build_prebuilt_graph(prompts_overwrite={"locale": "en_US"})

    assert captured_locale, "get_system_prompt was not called"
    assert captured_locale[0] == "en_US", (
        f"Expected locale 'en_US' from prompts_overwrite, got '{captured_locale[0]}'"
    )


def test_tc_i18n_03_graph_builder_falls_back_to_env_when_no_prompts_overwrite() -> None:
    """prompts_overwrite 为空时，graph_builder 应回退到环境变量 DATACLOUD_AGENT_LOCALE。"""
    from datacloud_analysis.i18n.prompts import get_system_prompt

    captured_locale: list[str] = []
    original_get_system_prompt = get_system_prompt

    def _spy_get_system_prompt(locale: str | None = None) -> str:
        captured_locale.append(locale or "")
        return original_get_system_prompt(locale)

    with (
        patch.dict(os.environ, {"DATACLOUD_AGENT_LOCALE": "en_US"}),
        patch(
            "datacloud_analysis.orchestration.graph_builder.get_system_prompt",
            side_effect=_spy_get_system_prompt,
        ),
        patch(
            "datacloud_analysis.orchestration.graph_builder.get_execution_prompt",
            return_value="",
        ),
        patch(
            "datacloud_analysis.orchestration.graph_builder._build_tools_list",
            return_value=[],
        ),
        patch(
            "datacloud_analysis.orchestration.graph_builder.make_llm_call_node",
            return_value=AsyncMock(),
        ),
        patch(
            "datacloud_analysis.orchestration.graph_builder.make_tool_dispatcher_node",
            return_value=AsyncMock(),
        ),
    ):
        from datacloud_analysis.orchestration.graph_builder import _build_legacy_graph

        _build_legacy_graph(prompts_overwrite=None)

    assert captured_locale, "get_system_prompt was not called"
    assert captured_locale[0] == "en_US", (
        f"Expected locale 'en_US' from env, got '{captured_locale[0]}'"
    )


# ── TC-I18N-04 / 05: execution_node locale 读取 ───────────────────────────────


@pytest.mark.asyncio
async def test_tc_i18n_04_execution_node_reads_locale_from_prompts_overwrite() -> None:
    """execution_node 应从 state prompts_overwrite["locale"] 读取 locale。"""
    from datacloud_analysis.i18n.prompts import get_system_prompt

    captured_locale: list[str] = []
    original_get_system_prompt = get_system_prompt

    def _spy(locale: str | None = None) -> str:
        captured_locale.append(locale or "")
        return original_get_system_prompt(locale)

    state = _make_execution_state(locale="en_US")
    config = _make_execution_config()
    captured_prompts: list[str] = []

    with (
        patch.dict(os.environ, {"DATACLOUD_AGENT_LOCALE": "zh_CN"}),
        patch(
            "datacloud_analysis.orchestration.execution.node.get_system_prompt",
            side_effect=_spy,
        ),
        patch(
            "datacloud_analysis.orchestration.execution.node.get_execution_prompt",
            return_value="",
        ),
        patch(
            "datacloud_analysis.orchestration.execution.node.run_react_loop",
            side_effect=_make_react_loop_capture(captured_prompts),
        ),
        patch(
            "datacloud_analysis.orchestration.execution.node.is_delegate_wait_resume_command",
            return_value=False,
        ),
    ):
        from datacloud_analysis.orchestration.execution.node import execution_node

        await execution_node(state, config)  # type: ignore[arg-type]

    assert captured_locale, "get_system_prompt was not called"
    assert captured_locale[0] == "en_US", (
        f"Expected locale 'en_US' from prompts_overwrite, got '{captured_locale[0]}'"
    )


@pytest.mark.asyncio
async def test_tc_i18n_05_execution_node_falls_back_to_env() -> None:
    """execution_node prompts_overwrite 无 locale 时应回退到环境变量。"""
    from datacloud_analysis.i18n.prompts import get_system_prompt

    captured_locale: list[str] = []
    original_get_system_prompt = get_system_prompt

    def _spy(locale: str | None = None) -> str:
        captured_locale.append(locale or "")
        return original_get_system_prompt(locale)

    state = _make_execution_state(locale=None)
    config = _make_execution_config()
    captured_prompts: list[str] = []

    with (
        patch.dict(os.environ, {"DATACLOUD_AGENT_LOCALE": "en_US"}),
        patch(
            "datacloud_analysis.orchestration.execution.node.get_system_prompt",
            side_effect=_spy,
        ),
        patch(
            "datacloud_analysis.orchestration.execution.node.get_execution_prompt",
            return_value="",
        ),
        patch(
            "datacloud_analysis.orchestration.execution.node.run_react_loop",
            side_effect=_make_react_loop_capture(captured_prompts),
        ),
        patch(
            "datacloud_analysis.orchestration.execution.node.is_delegate_wait_resume_command",
            return_value=False,
        ),
    ):
        from datacloud_analysis.orchestration.execution.node import execution_node

        await execution_node(state, config)  # type: ignore[arg-type]

    assert captured_locale, "get_system_prompt was not called"
    assert captured_locale[0] == "en_US", (
        f"Expected locale 'en_US' from env fallback, got '{captured_locale[0]}'"
    )


# ── TC-I18N-06 / 07: 运行时会话信息语言分支 ──────────────────────────────────


@pytest.mark.asyncio
async def test_tc_i18n_06_runtime_session_info_english_when_en_us() -> None:
    """locale=en_US 时，system_prompt 中的运行时会话信息应为英文。"""
    state = _make_execution_state(locale="en_US")
    config = _make_execution_config(user_name="Alice", user_code="U001")
    captured_prompts: list[str] = []

    with (
        patch.dict(os.environ, {"DATACLOUD_AGENT_LOCALE": "zh_CN"}),
        patch(
            "datacloud_analysis.orchestration.execution.node.get_system_prompt",
            return_value="",
        ),
        patch(
            "datacloud_analysis.orchestration.execution.node.get_execution_prompt",
            return_value="",
        ),
        patch(
            "datacloud_analysis.orchestration.execution.node.run_react_loop",
            side_effect=_make_react_loop_capture(captured_prompts),
        ),
        patch(
            "datacloud_analysis.orchestration.execution.node.is_delegate_wait_resume_command",
            return_value=False,
        ),
    ):
        from datacloud_analysis.orchestration.execution.node import execution_node

        await execution_node(state, config)  # type: ignore[arg-type]

    assert captured_prompts, "run_react_loop was not called"
    prompt = captured_prompts[0]
    assert "Current session" in prompt, f"Expected English header in prompt, got:\n{prompt}"
    assert "Current time" in prompt, f"Expected 'Current time' in prompt, got:\n{prompt}"
    assert "当前会话信息" not in prompt, (
        f"Chinese header should not appear for en_US, got:\n{prompt}"
    )


@pytest.mark.asyncio
async def test_tc_i18n_07_runtime_session_info_chinese_when_zh_cn() -> None:
    """locale=zh_CN 时，system_prompt 中的运行时会话信息应为中文。"""
    state = _make_execution_state(locale="zh_CN")
    config = _make_execution_config(user_name="张三", user_code="U002")
    captured_prompts: list[str] = []

    with (
        patch.dict(os.environ, {"DATACLOUD_AGENT_LOCALE": "en_US"}),
        patch(
            "datacloud_analysis.orchestration.execution.node.get_system_prompt",
            return_value="",
        ),
        patch(
            "datacloud_analysis.orchestration.execution.node.get_execution_prompt",
            return_value="",
        ),
        patch(
            "datacloud_analysis.orchestration.execution.node.run_react_loop",
            side_effect=_make_react_loop_capture(captured_prompts),
        ),
        patch(
            "datacloud_analysis.orchestration.execution.node.is_delegate_wait_resume_command",
            return_value=False,
        ),
    ):
        from datacloud_analysis.orchestration.execution.node import execution_node

        await execution_node(state, config)  # type: ignore[arg-type]

    assert captured_prompts, "run_react_loop was not called"
    prompt = captured_prompts[0]
    assert "当前会话信息" in prompt, f"Expected Chinese header in prompt, got:\n{prompt}"
    assert "当前时间" in prompt, f"Expected '当前时间' in prompt, got:\n{prompt}"
    assert "Current session" not in prompt, (
        f"English header should not appear for zh_CN, got:\n{prompt}"
    )


# ── TC-I18N-08: tool_wrapper InvocationContext language 传递 ─────────────────


@pytest.mark.asyncio
async def test_tc_i18n_08_tool_wrapper_passes_language_to_invocation_context() -> None:
    """dispatch_tool 构建 InvocationContext 时应将 state prompts_overwrite["locale"] 作为 language 传入。"""
    captured_kwargs: list[dict[str, Any]] = []

    class _FakeInvocationContext:
        def __init__(self, **kwargs: Any) -> None:
            captured_kwargs.append(dict(kwargs))

        def __enter__(self) -> _FakeInvocationContext:
            return self

        def __exit__(self, *args: Any) -> None:
            pass

    class _FakeTool:
        name = "query_test_obj"

        async def ainvoke(self, params: Any, config: Any = None) -> str:
            return '{"result_type": "text", "answer": "ok"}'

    fake_tool = _FakeTool()
    tools_map = {"query_test_obj": fake_tool}

    state: dict[str, Any] = {
        "prompts_overwrite": {"locale": "en_US"},
        "messages": [],
    }

    tool_call: dict[str, Any] = {
        "name": "query_test_obj",
        "args": {"query": "test"},
        "id": "tc-001",
    }

    with patch(
        "datacloud_data_sdk.context.InvocationContext",
        _FakeInvocationContext,
    ):
        from datacloud_analysis.orchestration.execution.tool_wrapper import dispatch_tool

        await dispatch_tool(
            tool_call,
            tools_map,
            state,
            gateway_context=None,
            loader=MagicMock(result_file_storage=None),
        )

    assert captured_kwargs, "InvocationContext was not instantiated"
    languages_passed = [kw.get("language") for kw in captured_kwargs]
    assert "en_US" in languages_passed, (
        f"Expected language='en_US' in InvocationContext kwargs, got: {captured_kwargs}"
    )
