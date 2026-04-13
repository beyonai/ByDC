"""test_llm_integration.py — 集成测试：模拟真实的主模型失败/降级/checkpoint 场景。

这里测的是"行为"，不是"代码行"：
  场景 1 - 主模型全部失败 → 自动降级到备用模型，正常返回结果
  场景 2 - 主+备用全部失败 → Checkpoint 保存 → 下次请求自动恢复
  场景 3 - run_react_loop 端到端：主模型失败，全程切换到备用模型完成请求
"""
from __future__ import annotations

import contextvars
import json
import sys
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage

# ── 测试环境：mock 未安装的 SDK 依赖 ─────────────────────────────────────────────
# datacloud_data_sdk 在 datacloud-analysis 单包测试环境中未安装，提前注入 mock 模块
# 必须在任何 datacloud_analysis 导入之前完成，否则 import chain 会报 ModuleNotFoundError
import types

def _inject_sdk_mocks() -> None:
    """把 datacloud_data_sdk 及其所有子模块注入 sys.modules。"""
    import types

    _VAR: contextvars.ContextVar[str] = contextvars.ContextVar("datacloud_trace_id", default="")

    def _make_mod(name: str) -> types.ModuleType:
        m = types.ModuleType(name)
        sys.modules[name] = m
        return m

    if "datacloud_data_sdk" not in sys.modules:
        sdk = _make_mod("datacloud_data_sdk")

        # trace_context
        tc = _make_mod("datacloud_data_sdk.trace_context")
        tc.current_trace_id = _VAR  # type: ignore[attr-defined]
        sdk.trace_context = tc  # type: ignore[attr-defined]

        # stream_text
        st = _make_mod("datacloud_data_sdk.stream_text")
        st.coerce_stream_chunk_text = lambda x: x  # type: ignore[attr-defined]
        sdk.stream_text = st  # type: ignore[attr-defined]

        # 其他懒加载子包（tool_wrapper / eval_context 等会用到）
        for sub in ("exceptions", "sql_executor", "ontology"):
            _make_mod(f"datacloud_data_sdk.{sub}")

_inject_sdk_mocks()

import datacloud_analysis.orchestration.execution.react_loop as rl_module  # noqa: E402
from datacloud_analysis.orchestration.execution.react_loop import (  # noqa: E402
    _LlmUnavailableError,
    _invoke_llm_with_fallback,
    run_react_loop,
)
from datacloud_analysis.orchestration.execution.llm_checkpoint import (  # noqa: E402
    CHECKPOINT_REPLY,
    load_llm_failure_checkpoint,
)


# ─── 共用工具 ──────────────────────────────────────────────────────────────────

class _FakeRedis:
    """进程内内存 Redis stub，供多次调用间共享状态。"""

    def __init__(self) -> None:
        self._store: dict[str, bytes] = {}

    async def setex(self, key: str, ttl: int, value: str) -> None:
        self._store[key] = value.encode() if isinstance(value, str) else value

    async def get(self, key: str) -> bytes | None:
        return self._store.get(key)

    async def delete(self, key: str) -> int:
        return 1 if self._store.pop(key, None) is not None else 0


class _FakeGatewayContext:
    """最小化 gateway_context stub。"""

    def __init__(self, session_id: str = "sess-integration", redis: Any = None) -> None:
        self.session_id = session_id
        self.redis = redis
        self.emitted: list[str] = []

    async def emit_chunk(self, event: Any, **_kwargs: Any) -> None:
        content = getattr(event, "content", str(event))
        self.emitted.append(content)

    def emitted_text(self) -> str:
        return "".join(self.emitted)


# ─── 场景 1：主模型全部重试失败 → 自动切换备用模型 ─────────────────────────────────

@pytest.mark.asyncio
async def test_scenario1_primary_fails_fallback_takes_over(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    场景：主模型连续失败（模拟服务不可用），备用模型正常工作。
    期望：_invoke_llm_with_fallback 切换到备用模型，返回备用模型的响应，
          调用方感受不到失败——只是用了备用模型。
    """
    primary_llm = MagicMock(name="primary")
    fallback_llm = MagicMock(name="fallback")
    expected_msg = AIMessage(content="fallback answer", tool_calls=[])

    call_log: list[str] = []

    async def fake_stream(llm_with_tools: Any, messages: Any, ctx: Any) -> tuple:
        if llm_with_tools is primary_llm:
            call_log.append("primary_called")
            exc = Exception("Primary 503 Service Unavailable")
            exc.status_code = 503  # type: ignore[attr-defined]
            raise exc
        call_log.append("fallback_called")
        return expected_msg, False

    # MAX_RETRIES=0：主模型失败 1 次即放弃，直接切备用
    monkeypatch.setenv("DATACLOUD_LLM_MAX_RETRIES", "0")

    with patch.object(rl_module, "_stream_llm_call", fake_stream):
        result_msg, did_stream = await _invoke_llm_with_fallback(
            primary_llm,
            fallback_llm,
            messages_window=[],
            gateway_context=None,
            state={},
            round_idx=0,
        )

    # ✅ 最终拿到备用模型的结果
    assert result_msg is expected_msg
    assert did_stream is False

    # ✅ 确认调用顺序：先试主模型，再切备用
    assert call_log == ["primary_called", "fallback_called"]


@pytest.mark.asyncio
async def test_scenario1_primary_retries_then_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    场景：主模型重试 2 次（共 3 次调用）仍失败，备用模型第一次即成功。
    期望：call_log 里有 3 次 primary + 1 次 fallback。
    """
    primary_llm = MagicMock(name="primary")
    fallback_llm = MagicMock(name="fallback")
    expected_msg = AIMessage(content="fallback saved the day", tool_calls=[])

    call_log: list[str] = []

    async def fake_stream(llm_with_tools: Any, messages: Any, ctx: Any) -> tuple:
        if llm_with_tools is primary_llm:
            call_log.append("primary")
            exc = Exception("Internal Server Error")
            exc.status_code = 500  # type: ignore[attr-defined]
            raise exc
        call_log.append("fallback")
        return expected_msg, True

    monkeypatch.setenv("DATACLOUD_LLM_MAX_RETRIES", "2")
    monkeypatch.setenv("DATACLOUD_LLM_RETRY_MIN_WAIT", "0")

    with patch.object(rl_module, "_stream_llm_call", fake_stream):
        with patch("asyncio.sleep", new_callable=AsyncMock):
            result_msg, _ = await _invoke_llm_with_fallback(
                primary_llm,
                fallback_llm,
                messages_window=[],
                gateway_context=None,
                state={},
                round_idx=1,
            )

    assert result_msg is expected_msg
    # 主模型被调用 3 次（1 首次 + 2 重试），备用模型 1 次
    assert call_log.count("primary") == 3
    assert call_log.count("fallback") == 1
    assert call_log[-1] == "fallback"  # 最后一次是备用模型成功


# ─── 场景 2：主+备用全部失败 → Checkpoint 保存 → 下次请求自动恢复 ──────────────────

@pytest.mark.asyncio
async def test_scenario2_all_models_fail_checkpoint_saved(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    第一步：主模型和备用模型全部失败。
    期望：
      - 抛出 _LlmUnavailableError
      - Redis 中保存了断点（key / session_id / completed_steps / state_snapshot）
      - 向用户推送了引导文案
    """
    primary_llm = MagicMock(name="primary")
    fallback_llm = MagicMock(name="fallback")

    async def fake_stream_fail(llm_with_tools: Any, messages: Any, ctx: Any) -> tuple:
        exc = Exception("all systems down")
        exc.status_code = 503  # type: ignore[attr-defined]
        raise exc

    fake_redis = _FakeRedis()
    ctx = _FakeGatewayContext(session_id="sess-recovery-test", redis=fake_redis)

    monkeypatch.setenv("DATACLOUD_LLM_MAX_RETRIES", "0")

    with patch.object(rl_module, "_stream_llm_call", fake_stream_fail):
        with pytest.raises(_LlmUnavailableError):
            await _invoke_llm_with_fallback(
                primary_llm,
                fallback_llm,
                messages_window=[],
                gateway_context=ctx,
                state={"user_query": "帮我查小米的营收", "confirmed_terms": ["小米"]},
                round_idx=1,
            )

    # ✅ Redis 中有断点
    raw = await fake_redis.get("llm:checkpoint:sess-recovery-test")
    assert raw is not None
    payload = json.loads(raw)
    assert payload["session_id"] == "sess-recovery-test"
    assert payload["completed_steps"] == 1
    assert payload["state_snapshot"]["user_query"] == "帮我查小米的营收"

    # ✅ 用户收到了引导文案
    assert "重新发送同样的问题" in ctx.emitted_text()


@pytest.mark.asyncio
async def test_scenario2_checkpoint_recovered_on_next_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    第二步：用户重新发送同样的问题（模型此时已恢复）。
    期望：
      - run_react_loop 检测到 Redis 断点，恢复上次保存的 state 字段
      - 断点被删除（消费后清理）
      - 请求正常完成（stop_reason != "llm_unavailable"）
    """
    # ── 预先在 Redis 中写入断点（模拟上次失败保存的断点）──────────────────────────
    fake_redis = _FakeRedis()
    await fake_redis.setex(
        "llm:checkpoint:sess-recovery",
        3600,
        json.dumps({
            "session_id": "sess-recovery",
            "completed_steps": 1,
            "state_snapshot": {"user_query": "帮我查小米的营收", "confirmed_terms": ["小米"]},
            "error_type": "Exception",
            "error_message": "all models down",
        }),
    )

    ctx = _FakeGatewayContext(session_id="sess-recovery", redis=fake_redis)

    # ── Mock LLM：本次模型已恢复，直接返回文字结果 ────────────────────────────────
    recovered_msg = AIMessage(content="小米2024年营收为3100亿元", tool_calls=[])
    mock_llm_with_tools = MagicMock()
    mock_llm_with_tools.astream = AsyncMock(return_value=aiter([recovered_msg]))
    mock_llm_with_tools.ainvoke = AsyncMock(return_value=recovered_msg)
    mock_llm = MagicMock()
    mock_llm.bind_tools.return_value = mock_llm_with_tools

    monkeypatch.setenv("DATACLOUD_LLM_MAX_RETRIES", "0")

    with patch.object(rl_module, "_build_llm", return_value=mock_llm):
        with patch("datacloud_analysis.orchestration.execution.llm_retry._build_fallback_llm", return_value=None):
            result = await run_react_loop(
                state={"user_query": "帮我查小米的营收", "messages": []},
                tools_list=[],
                system_prompt="你是数据分析助手",
                gateway_context=ctx,
                max_rounds=3,
            )

    # ✅ 请求正常完成
    assert result["react_final"]["stop_reason"] != "llm_unavailable"

    # ✅ 断点已被消费删除
    remaining = await fake_redis.get("llm:checkpoint:sess-recovery")
    assert remaining is None


# ─── 场景 3：run_react_loop 端到端，主模型失败全程使用备用模型 ─────────────────────

@pytest.mark.asyncio
async def test_scenario3_end_to_end_degradation_to_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    端到端场景：整个 run_react_loop 调用中主模型始终失败，备用模型接管，
    最终仍能正常返回结果（stop_reason 不是 llm_unavailable）。
    """
    primary_llm_tools = MagicMock(name="primary_bound")
    fallback_llm_tools = MagicMock(name="fallback_bound")

    primary_llm = MagicMock(name="primary")
    fallback_llm = MagicMock(name="fallback")
    primary_llm.bind_tools.return_value = primary_llm_tools
    fallback_llm.bind_tools.return_value = fallback_llm_tools

    # 备用模型直接返回纯文字回答（无 tool_calls → L2 停止）
    final_answer = AIMessage(content="备用模型的回答：营收数据如下…", tool_calls=[])

    async def fake_stream(llm_with_tools: Any, messages: Any, ctx: Any) -> tuple:
        if llm_with_tools is primary_llm_tools:
            exc = Exception("Primary unavailable")
            exc.status_code = 503  # type: ignore[attr-defined]
            raise exc
        # 备用模型成功返回
        return final_answer, False

    monkeypatch.setenv("DATACLOUD_LLM_MAX_RETRIES", "0")

    with patch.object(rl_module, "_build_llm", return_value=primary_llm):
        with patch("datacloud_analysis.orchestration.execution.llm_retry._build_fallback_llm", return_value=fallback_llm):
            with patch.object(rl_module, "_stream_llm_call", fake_stream):
                result = await run_react_loop(
                    state={"user_query": "查营收", "messages": []},
                    tools_list=[],
                    system_prompt="你是助手",
                    gateway_context=None,
                    max_rounds=3,
                )

    # ✅ 请求成功完成（备用模型的 L2 no_tool_call 路径）
    react_final = result["react_final"]
    assert react_final["stop_reason"] != "llm_unavailable"
    assert "备用模型" in react_final.get("answer", "")


@pytest.mark.asyncio
async def test_scenario3_both_models_fail_returns_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    端到端：主模型和备用模型都失败时，run_react_loop 返回 stop_reason=llm_unavailable，
    且向用户推送了引导文案。
    """
    primary_llm_tools = MagicMock(name="primary_bound")
    fallback_llm_tools = MagicMock(name="fallback_bound")
    primary_llm = MagicMock()
    fallback_llm = MagicMock()
    primary_llm.bind_tools.return_value = primary_llm_tools
    fallback_llm.bind_tools.return_value = fallback_llm_tools

    async def fake_stream_always_fail(llm_with_tools: Any, messages: Any, ctx: Any) -> tuple:
        exc = Exception("complete outage")
        exc.status_code = 503  # type: ignore[attr-defined]
        raise exc

    ctx = _FakeGatewayContext(session_id="sess-e2e-fail", redis=_FakeRedis())
    monkeypatch.setenv("DATACLOUD_LLM_MAX_RETRIES", "0")

    with patch.object(rl_module, "_build_llm", return_value=primary_llm):
        with patch("datacloud_analysis.orchestration.execution.llm_retry._build_fallback_llm", return_value=fallback_llm):
            with patch.object(rl_module, "_stream_llm_call", fake_stream_always_fail):
                result = await run_react_loop(
                    state={"user_query": "查营收", "messages": []},
                    tools_list=[],
                    system_prompt="你是助手",
                    gateway_context=ctx,
                    max_rounds=3,
                )

    # ✅ stop_reason 标记为 llm_unavailable
    assert result["react_final"]["stop_reason"] == "llm_unavailable"

    # ✅ 用户收到了引导文案
    assert "重新发送同样的问题" in result["react_final"]["answer"]


# ─── 辅助：async iterator helper（Python 3.10+ 有 aiter，低版本兼容） ──────────────

def aiter(items: list) -> Any:
    """把普通 list 包成 async iterator，供 mock astream 使用。"""
    async def _gen():
        for item in items:
            yield item
    return _gen()
