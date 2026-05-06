"""T3+T6：OntologyAgent 公开 API 及进程级图缓存单元测试（红阶段）。

验收目标：
- TC-T3-1: ask() 返回 AsyncGenerator
- TC-T3-2: ask() 在正常流程下 yield AnswerEvent（无中断）
- TC-T3-3: ask() 在中断场景下 yield InterruptEvent
- TC-T3-4: resume() 在恢复后 yield AnswerEvent
- TC-T3-5: InterruptEvent.thread_id 与 ask() 传入的 thread_id 一致
- TC-T3-6: ErrorEvent 在图执行抛异常时被 yield
- TC-T6-1: 相同 (view_codes, object_codes) 第二次调用时图不重新构建（缓存命中）
- TC-T6-2: 不同 (view_codes, object_codes) 时图独立构建（缓存未命中）
- TC-T6-3: _make_cache_key 对 view/object 名字空间隔离（相同字符串不碰撞）
- TC-T6-4: LRU 超限时淘汰最旧条目
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from datacloud_analysis.ontology_agent import (
    AnswerEvent,
    ErrorEvent,
    InterruptEvent,
    OntologyAgent,
    OntologyAgentConfig,
    OntologyAgentEvent,
    ParadigmAnswer,
    ParadigmGroupSelection,
    ParadigmOption,
    ThinkingEvent,
    _make_cache_key,
)

# ── 辅助常量 ──────────────────────────────────────────────────────────────────

_CONFIG = OntologyAgentConfig(
    api_key="sk-test",
    model="test-model",
    resource_path="/fake/resource",
)

_VIEW_CODES = ["scene_sales"]
_OBJ_CODES = ["by_customer"]
_THREAD_ID = str(uuid.uuid4())


# ── 辅助：mock 一个 compiled graph ───────────────────────────────────────────


def _make_mock_compiled(
    *,
    interrupts: list[Any] | None = None,
    final_answer: str = "42 万元",
    events: list[dict[str, Any]] | None = None,
) -> MagicMock:
    """构造一个 mock 编译图，用于替换 OntologyAgent._get_or_build_graph 的返回值。"""
    compiled = MagicMock()

    # astream_events 返回空异步迭代器（思考过程 token）
    raw_events: list[dict[str, Any]] = events or []

    async def _astream_events(*args: Any, **kwargs: Any) -> AsyncGenerator[dict[str, Any], None]:
        for ev in raw_events:
            yield ev

    compiled.astream_events = _astream_events

    # aget_state 返回包含 interrupts 的快照
    snap = MagicMock()
    snap.interrupts = interrupts or []
    snap.values = {"final_answer": final_answer}
    compiled.aget_state = AsyncMock(return_value=snap)

    return compiled


# ── TC-T3-1: ask() 返回 AsyncGenerator ───────────────────────────────────────


def test_ask_returns_async_generator() -> None:
    agent = OntologyAgent(_CONFIG)
    with patch.object(agent, "_get_or_build_graph", return_value=_make_mock_compiled()):
        result = agent.ask(question="Q?", view_codes=_VIEW_CODES, thread_id=_THREAD_ID)
    assert isinstance(result, AsyncGenerator)


# ── TC-T3-2: ask() 正常流程 yield AnswerEvent ────────────────────────────────


async def test_ask_yields_answer_event_on_normal_flow() -> None:
    agent = OntologyAgent(_CONFIG)
    compiled = _make_mock_compiled(final_answer="销售额为 100 万元")

    with patch.object(agent, "_get_or_build_graph", return_value=compiled):
        events: list[OntologyAgentEvent] = []
        async for ev in agent.ask(
            question="各部门本月销售额？",
            view_codes=_VIEW_CODES,
            thread_id=_THREAD_ID,
        ):
            events.append(ev)

    answer_events = [e for e in events if isinstance(e, AnswerEvent)]
    assert len(answer_events) == 1
    assert answer_events[0].content == "销售额为 100 万元"


# ── TC-T3-3: ask() 在中断时 yield InterruptEvent ─────────────────────────────


async def test_ask_yields_interrupt_event_on_paradigm_clarification() -> None:
    interrupt_value = {
        "reason_code": "PARADIGM_CLARIFICATION",
        "prompt": "请确认查询维度",
        "ask_user_payload": {
            "paradigmList": [
                {
                    "paradigmId": "P001",
                    "paradigmName": "部门",
                    "paradigmResult": [
                        {"choiceKeyword": "华东", "recall": "east"},
                        {"choiceKeyword": "华南", "recall": "south"},
                    ],
                }
            ],
            "query": "Q",
        },
    }

    mock_interrupt = MagicMock()
    mock_interrupt.value = interrupt_value

    compiled = _make_mock_compiled(interrupts=[mock_interrupt])

    agent = OntologyAgent(_CONFIG)
    with patch.object(agent, "_get_or_build_graph", return_value=compiled):
        events: list[OntologyAgentEvent] = []
        async for ev in agent.ask(
            question="华东销售额",
            view_codes=_VIEW_CODES,
            thread_id=_THREAD_ID,
        ):
            events.append(ev)

    interrupt_events = [e for e in events if isinstance(e, InterruptEvent)]
    assert len(interrupt_events) == 1
    ie = interrupt_events[0]
    assert ie.thread_id == _THREAD_ID
    assert ie.reason == "PARADIGM_CLARIFICATION"
    assert ie.prompt == "请确认查询维度"
    assert ie.paradigm_list is not None
    assert len(ie.paradigm_list) == 1
    assert ie.paradigm_list[0].paradigm_name == "部门"


# ── TC-T3-4: resume() 在恢复后 yield AnswerEvent ────────────────────────────


async def test_resume_yields_answer_event() -> None:
    compiled = _make_mock_compiled(final_answer="恢复后答案")

    agent = OntologyAgent(_CONFIG)
    with patch.object(agent, "_get_or_build_graph", return_value=compiled):
        events: list[OntologyAgentEvent] = []
        answer = ParadigmAnswer(
            selections=[
                ParadigmGroupSelection(
                    paradigm_id="P001",
                    paradigm_name="部门",
                    chosen_options=[ParadigmOption(choice_keyword="华东", recall="east")],
                )
            ]
        )
        async for ev in agent.resume(
            thread_id=_THREAD_ID,
            user_input=answer,
            view_codes=_VIEW_CODES,
        ):
            events.append(ev)

    answer_events = [e for e in events if isinstance(e, AnswerEvent)]
    assert len(answer_events) == 1
    assert answer_events[0].content == "恢复后答案"


# ── TC-T3-5: InterruptEvent.thread_id 与 ask() 传入一致 ─────────────────────


async def test_interrupt_event_thread_id_matches_ask_thread_id() -> None:
    custom_tid = "my-thread-abc"
    mock_interrupt = MagicMock()
    mock_interrupt.value = {
        "reason_code": "ASK_USER",
        "prompt": "请输入",
        "ask_user_payload": {},
    }
    compiled = _make_mock_compiled(interrupts=[mock_interrupt])

    agent = OntologyAgent(_CONFIG)
    with patch.object(agent, "_get_or_build_graph", return_value=compiled):
        events: list[OntologyAgentEvent] = []
        async for ev in agent.ask(question="Q", view_codes=_VIEW_CODES, thread_id=custom_tid):
            events.append(ev)

    interrupt_events = [e for e in events if isinstance(e, InterruptEvent)]
    assert interrupt_events[0].thread_id == custom_tid


# ── TC-T3-6: ErrorEvent 在图抛异常时被 yield ─────────────────────────────────


async def test_ask_yields_error_event_on_exception() -> None:
    compiled = MagicMock()

    async def _fail(*args: Any, **kwargs: Any) -> AsyncGenerator[dict, None]:
        raise RuntimeError("graph exploded")
        yield  # make it a generator

    compiled.astream_events = _fail

    agent = OntologyAgent(_CONFIG)
    with patch.object(agent, "_get_or_build_graph", return_value=compiled):
        events: list[OntologyAgentEvent] = []
        async for ev in agent.ask(question="Q", view_codes=_VIEW_CODES, thread_id=_THREAD_ID):
            events.append(ev)

    error_events = [e for e in events if isinstance(e, ErrorEvent)]
    assert len(error_events) == 1
    assert "graph exploded" in error_events[0].message


# ── TC-T3: resume() with str user_input ──────────────────────────────────────


async def test_resume_with_str_user_input() -> None:
    compiled = _make_mock_compiled(final_answer="文本回复答案")
    agent = OntologyAgent(_CONFIG)

    with patch.object(agent, "_get_or_build_graph", return_value=compiled):
        events: list[OntologyAgentEvent] = []
        async for ev in agent.resume(
            thread_id=_THREAD_ID,
            user_input="华东",
            view_codes=_VIEW_CODES,
        ):
            events.append(ev)

    assert any(isinstance(e, AnswerEvent) for e in events)


# ── TC-T6-1: 图缓存命中时不重新构建 ─────────────────────────────────────────


async def test_graph_cache_hit_skips_rebuild() -> None:
    agent = OntologyAgent(_CONFIG)

    build_count = 0

    def _fake_build(vc: Any, oc: Any) -> MagicMock:
        nonlocal build_count
        build_count += 1
        return _make_mock_compiled()

    with patch.object(agent, "_build_and_compile", side_effect=_fake_build):
        async for _ in agent.ask(question="Q1", view_codes=_VIEW_CODES, thread_id=_THREAD_ID):
            pass
        async for _ in agent.ask(question="Q2", view_codes=_VIEW_CODES, thread_id=_THREAD_ID):
            pass

    assert build_count == 1, f"期望只构建 1 次，实际 {build_count} 次"


# ── TC-T6-2: 不同 codes 组合各自构建 ────────────────────────────────────────


async def test_graph_cache_miss_on_different_codes() -> None:
    agent = OntologyAgent(_CONFIG)

    build_count = 0

    def _fake_build(vc: Any, oc: Any) -> MagicMock:
        nonlocal build_count
        build_count += 1
        return _make_mock_compiled()

    with patch.object(agent, "_build_and_compile", side_effect=_fake_build):
        async for _ in agent.ask(question="Q1", view_codes=["scene_sales"], thread_id=_THREAD_ID):
            pass
        async for _ in agent.ask(question="Q2", view_codes=["scene_crm"], thread_id=_THREAD_ID):
            pass

    assert build_count == 2


# ── TC-T6-3: cache key 隔离 view/object 命名空间 ────────────────────────────


def test_make_cache_key_view_object_namespace_isolation() -> None:
    """view_code="x" 和 object_code="x" 应产生不同的 cache key。"""
    key_view = _make_cache_key(["x"], [])
    key_obj = _make_cache_key([], ["x"])
    assert key_view != key_obj


def test_make_cache_key_order_independent() -> None:
    """codes 顺序不同但集合相同时 key 相同。"""
    k1 = _make_cache_key(["a", "b"], ["c"])
    k2 = _make_cache_key(["b", "a"], ["c"])
    assert k1 == k2


def test_make_cache_key_none_codes() -> None:
    """None 和空列表等价。"""
    k1 = _make_cache_key(None, None)
    k2 = _make_cache_key([], [])
    assert k1 == k2


# ── TC-T6-4: LRU 超限淘汰 ───────────────────────────────────────────────────


async def test_graph_cache_lru_eviction() -> None:
    """当缓存超过 CACHE_MAX 时，最旧的条目被淘汰。"""
    agent = OntologyAgent(_CONFIG)

    build_count = 0

    def _fake_build(vc: Any, oc: Any) -> MagicMock:
        nonlocal build_count
        build_count += 1
        return _make_mock_compiled()

    with (
        patch("datacloud_analysis.ontology_agent._CACHE_MAX", 2),
        patch.object(agent, "_build_and_compile", side_effect=_fake_build),
    ):
        # 填满缓存 (2 个条目)
        async for _ in agent.ask(question="Q", view_codes=["v1"], thread_id="t1"):
            pass
        async for _ in agent.ask(question="Q", view_codes=["v2"], thread_id="t2"):
            pass

        # 第三个不同 key → 淘汰最旧 (v1)，重建
        async for _ in agent.ask(question="Q", view_codes=["v3"], thread_id="t3"):
            pass

        # v1 已被淘汰，再访问 v1 时重建
        async for _ in agent.ask(question="Q", view_codes=["v1"], thread_id="t1"):
            pass

    # 共构建：v1(1次) + v2(1次) + v3(1次) + v1再次(1次) = 4次
    assert build_count == 4


# ── TC-T3: ThinkingEvent 过滤 (非 respond 节点) ──────────────────────────────


async def test_ask_yields_thinking_events_from_non_respond_node() -> None:
    """on_chat_model_stream 来自非 respond 节点时 yield ThinkingEvent。"""
    fake_events = [
        {
            "event": "on_chat_model_stream",
            "metadata": {"langgraph_node": "agent"},
            "data": {"chunk": MagicMock(content="思考中...")},
        },
        {
            "event": "on_chat_model_stream",
            "metadata": {"langgraph_node": "respond"},
            "data": {"chunk": MagicMock(content="最终答案")},
        },
    ]

    compiled = _make_mock_compiled(events=fake_events, final_answer="done")
    agent = OntologyAgent(_CONFIG)

    with patch.object(agent, "_get_or_build_graph", return_value=compiled):
        events: list[OntologyAgentEvent] = []
        async for ev in agent.ask(question="Q", view_codes=_VIEW_CODES, thread_id=_THREAD_ID):
            events.append(ev)

    thinking_events = [e for e in events if isinstance(e, ThinkingEvent)]
    # 只有来自非 "respond" 节点的 chunk 应被 yield
    assert len(thinking_events) == 1
    assert thinking_events[0].content == "思考中..."


# ── 方案 A 红测试：result_file_storage 透传 ─────────────────────────────────


def test_config_accepts_result_file_storage_field() -> None:
    """OntologyAgentConfig 需要新增 result_file_storage 字段，默认 None。"""
    cfg = OntologyAgentConfig(api_key="k", model="m", resource_path="/x")
    assert hasattr(cfg, "result_file_storage")
    assert cfg.result_file_storage is None
    sentinel = object()
    cfg2 = OntologyAgentConfig(
        api_key="k",
        model="m",
        resource_path="/x",
        result_file_storage=sentinel,
    )
    assert cfg2.result_file_storage is sentinel


def test_build_loader_passes_result_file_storage_to_configure_loader() -> None:
    """_build_loader 应把 config.result_file_storage 透传给 configure_loader。"""
    sentinel = object()
    cfg = OntologyAgentConfig(
        api_key="k",
        model="m",
        resource_path="/x",
        result_file_storage=sentinel,
    )
    agent = OntologyAgent(cfg)
    with (
        patch("datacloud_data_sdk.ontology.loader.OntologyLoader") as m_loader_cls,
        patch(
            "datacloud_data_service.tools.virtual_action_injector.inject_virtual_actions"
        ) as _m_inject,
        patch(
            "datacloud_analysis.tools.ontology_tool_loader.configure_loader"
        ) as m_configure,
    ):
        m_loader_cls.return_value = MagicMock()
        agent._build_loader(view_codes=["v"], object_codes=["o"])

    assert m_configure.called, "configure_loader 应被调用"
    kwargs = m_configure.call_args.kwargs
    assert kwargs.get("result_file_storage") is sentinel


# ── 方案 A 红测试：gateway_context 透传 ─────────────────────────────────────


async def test_ask_injects_gateway_context_into_configurable() -> None:
    """ask(gateway_context=...) 应把它写入 run_config["configurable"]["gateway_context"]。"""
    agent = OntologyAgent(_CONFIG)
    captured: dict[str, Any] = {}

    async def _capture(
        graph_input: Any, *, config: dict[str, Any], version: str
    ) -> AsyncGenerator[dict[str, Any], None]:
        captured["config"] = config
        if False:  # pragma: no cover - generator with no yields
            yield  # type: ignore[unreachable]

    compiled = _make_mock_compiled()
    compiled.astream_events = _capture
    sentinel_ctx = MagicMock(name="gateway_context")

    with patch.object(agent, "_get_or_build_graph", return_value=compiled):
        async for _ in agent.ask(
            question="Q?",
            view_codes=_VIEW_CODES,
            thread_id=_THREAD_ID,
            gateway_context=sentinel_ctx,
        ):
            pass

    configurable = captured["config"]["configurable"]
    assert configurable.get("gateway_context") is sentinel_ctx


async def test_resume_injects_gateway_context_into_configurable() -> None:
    """resume(gateway_context=...) 应把它写入 run_config["configurable"]["gateway_context"]。"""
    agent = OntologyAgent(_CONFIG)
    captured: dict[str, Any] = {}

    async def _capture(
        graph_input: Any, *, config: dict[str, Any], version: str
    ) -> AsyncGenerator[dict[str, Any], None]:
        captured["config"] = config
        if False:  # pragma: no cover - generator with no yields
            yield  # type: ignore[unreachable]

    compiled = _make_mock_compiled()
    compiled.astream_events = _capture
    sentinel_ctx = MagicMock(name="gateway_context")

    with patch.object(agent, "_get_or_build_graph", return_value=compiled):
        async for _ in agent.resume(
            thread_id=_THREAD_ID,
            user_input="hi",
            view_codes=_VIEW_CODES,
            gateway_context=sentinel_ctx,
        ):
            pass

    configurable = captured["config"]["configurable"]
    assert configurable.get("gateway_context") is sentinel_ctx
