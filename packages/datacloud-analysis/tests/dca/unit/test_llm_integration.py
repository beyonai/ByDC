"""test_llm_integration.py 鈥?闆嗘垚娴嬭瘯锛氭ā鎷熺湡瀹炵殑涓绘ā鍨嬪け璐?闄嶇骇/checkpoint 鍦烘櫙銆?

杩欓噷娴嬬殑鏄?琛屼负"锛屼笉鏄?浠ｇ爜琛?锛?
  鍦烘櫙 1 - 涓绘ā鍨嬪叏閮ㄥけ璐?鈫?鑷姩闄嶇骇鍒板鐢ㄦā鍨嬶紝姝ｅ父杩斿洖缁撴灉
  鍦烘櫙 2 - 涓?澶囩敤鍏ㄩ儴澶辫触 鈫?Checkpoint 淇濆瓨 鈫?涓嬫璇锋眰鑷姩鎭㈠
  鍦烘櫙 3 - run_react_loop 绔埌绔細涓绘ā鍨嬪け璐ワ紝鍏ㄧ▼鍒囨崲鍒板鐢ㄦā鍨嬪畬鎴愯姹?
"""

from __future__ import annotations

import contextvars
import json
import sys

# 鈹€鈹€ 娴嬭瘯鐜锛歮ock 鏈畨瑁呯殑 SDK 渚濊禆 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
# datacloud_data_sdk 鍦?datacloud-analysis 鍗曞寘娴嬭瘯鐜涓湭瀹夎锛屾彁鍓嶆敞鍏?mock 妯″潡
# 蹇呴』鍦ㄤ换浣?datacloud_analysis 瀵煎叆涔嬪墠瀹屾垚锛屽惁鍒?import chain 浼氭姤 ModuleNotFoundError
import types
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage


def _inject_sdk_mocks() -> None:
    """Inject datacloud_data_sdk and required submodules into sys.modules."""
    import types

    trace_var: contextvars.ContextVar[str] = contextvars.ContextVar(
        "datacloud_trace_id",
        default="",
    )

    def _make_mod(name: str) -> types.ModuleType:
        m = types.ModuleType(name)
        sys.modules[name] = m
        return m

    if "datacloud_data_sdk" not in sys.modules:
        sdk = _make_mod("datacloud_data_sdk")

        # trace_context
        tc = _make_mod("datacloud_data_sdk.trace_context")
        tc.current_trace_id = trace_var  # type: ignore[attr-defined]
        sdk.trace_context = tc  # type: ignore[attr-defined]

        # stream_text
        st = _make_mod("datacloud_data_sdk.stream_text")
        st.coerce_stream_chunk_text = lambda x: x  # type: ignore[attr-defined]
        sdk.stream_text = st  # type: ignore[attr-defined]

        # 鍏朵粬鎳掑姞杞藉瓙鍖咃紙tool_wrapper / eval_context 绛変細鐢ㄥ埌锛?
        for sub in ("exceptions", "sql_executor", "ontology"):
            _make_mod(f"datacloud_data_sdk.{sub}")


_inject_sdk_mocks()

import datacloud_analysis.orchestration.execution.react_loop as rl_module  # noqa: E402
from datacloud_analysis.orchestration.execution.react_loop import (  # noqa: E402
    _invoke_llm_with_fallback,
    _LlmUnavailableError,
    run_react_loop,
)

# 鈹€鈹€鈹€ 鍏辩敤宸ュ叿 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€


class _FakeRedis:
    """In-process Redis stub shared across calls in tests."""

    def __init__(self) -> None:
        self._store: dict[str, bytes] = {}

    async def setex(self, key: str, ttl: int, value: str) -> None:
        self._store[key] = value.encode() if isinstance(value, str) else value

    async def get(self, key: str) -> bytes | None:
        return self._store.get(key)

    async def delete(self, key: str) -> int:
        return 1 if self._store.pop(key, None) is not None else 0


class _FakeGatewayContext:
    """Minimal gateway_context stub."""

    def __init__(self, session_id: str = "sess-integration", redis: Any = None) -> None:
        self.session_id = session_id
        self.redis = redis
        self.emitted: list[str] = []

    async def emit_chunk(self, event: Any, **_kwargs: Any) -> None:
        content = getattr(event, "content", str(event))
        self.emitted.append(content)

    def emitted_text(self) -> str:
        return "".join(self.emitted)


# 鈹€鈹€鈹€ 鍦烘櫙 1锛氫富妯″瀷鍏ㄩ儴閲嶈瘯澶辫触 鈫?鑷姩鍒囨崲澶囩敤妯″瀷 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€


@pytest.mark.asyncio
async def test_scenario1_primary_fails_fallback_takes_over(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    鍦烘櫙锛氫富妯″瀷杩炵画澶辫触锛堟ā鎷熸湇鍔′笉鍙敤锛夛紝澶囩敤妯″瀷姝ｅ父宸ヤ綔銆?
    鏈熸湜锛歘invoke_llm_with_fallback 鍒囨崲鍒板鐢ㄦā鍨嬶紝杩斿洖澶囩敤妯″瀷鐨勫搷搴旓紝
          璋冪敤鏂规劅鍙椾笉鍒板け璐モ€斺€斿彧鏄敤浜嗗鐢ㄦā鍨嬨€?
    """
    primary_llm = MagicMock(name="primary")
    fallback_llm = MagicMock(name="fallback")
    expected_msg = AIMessage(content="fallback answer", tool_calls=[])

    call_log: list[str] = []

    async def fake_stream(
        llm_with_tools: Any,
        messages: Any,
        ctx: Any,
        *,
        thinking_message_id: str,
        query_received_at: float | None = None,
        round_idx: int = 0,
        config: Any = None,
    ) -> tuple:
        if llm_with_tools is primary_llm:
            call_log.append("primary_called")
            exc = Exception("Primary 503 Service Unavailable")
            exc.status_code = 503  # type: ignore[attr-defined]
            raise exc
        call_log.append("fallback_called")
        return expected_msg, False

    # 鏈€澶ч噸璇曟暟鏀逛负 0锛氫富妯″瀷澶辫触 1 娆″嵆鏀惧純锛岀洿鎺ュ垏澶囩敤
    monkeypatch.setattr(
        "datacloud_analysis.orchestration.execution.llm_retry._DEFAULT_MAX_RETRIES",
        0,
    )

    with patch.object(rl_module, "_stream_llm_call", fake_stream):
        result_msg, did_stream = await _invoke_llm_with_fallback(
            primary_llm,
            fallback_llm,
            messages_window=[],
            gateway_context=None,
            state={},
            round_idx=0,
            thinking_message_id="test_round_0",
        )

    # 鉁?鏈€缁堟嬁鍒板鐢ㄦā鍨嬬殑缁撴灉
    assert result_msg is expected_msg
    assert did_stream is False

    # 鉁?纭璋冪敤椤哄簭锛氬厛璇曚富妯″瀷锛屽啀鍒囧鐢?
    assert call_log == ["primary_called", "fallback_called"]


@pytest.mark.asyncio
async def test_scenario1_primary_retries_then_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    鍦烘櫙锛氫富妯″瀷閲嶈瘯 2 娆★紙鍏?3 娆¤皟鐢級浠嶅け璐ワ紝澶囩敤妯″瀷绗竴娆″嵆鎴愬姛銆?
    鏈熸湜锛歝all_log 閲屾湁 3 娆?primary + 1 娆?fallback銆?
    """
    primary_llm = MagicMock(name="primary")
    fallback_llm = MagicMock(name="fallback")
    expected_msg = AIMessage(content="fallback saved the day", tool_calls=[])

    call_log: list[str] = []

    async def fake_stream(
        llm_with_tools: Any,
        messages: Any,
        ctx: Any,
        *,
        thinking_message_id: str,
        query_received_at: float | None = None,
        round_idx: int = 0,
        config: Any = None,
    ) -> tuple:
        if llm_with_tools is primary_llm:
            call_log.append("primary")
            exc = Exception("Internal Server Error")
            exc.status_code = 500  # type: ignore[attr-defined]
            raise exc
        call_log.append("fallback")
        return expected_msg, True

    monkeypatch.setattr(
        "datacloud_analysis.orchestration.execution.llm_retry._DEFAULT_MAX_RETRIES",
        2,
    )
    monkeypatch.setattr(
        "datacloud_analysis.orchestration.execution.llm_retry._DEFAULT_MIN_WAIT",
        0.0,
    )

    with (
        patch.object(rl_module, "_stream_llm_call", fake_stream),
        patch("asyncio.sleep", new_callable=AsyncMock),
    ):
        result_msg, _ = await _invoke_llm_with_fallback(
            primary_llm,
            fallback_llm,
            messages_window=[],
            gateway_context=None,
            state={},
            round_idx=1,
            thinking_message_id="test_round_1",
        )

    assert result_msg is expected_msg
    # 涓绘ā鍨嬭璋冪敤 3 娆★紙1 棣栨 + 2 閲嶈瘯锛夛紝澶囩敤妯″瀷 1 娆?
    assert call_log.count("primary") == 3
    assert call_log.count("fallback") == 1
    assert call_log[-1] == "fallback"  # 鏈€鍚庝竴娆℃槸澶囩敤妯″瀷鎴愬姛


# 鈹€鈹€鈹€ 鍦烘櫙 2锛氫富+澶囩敤鍏ㄩ儴澶辫触 鈫?Checkpoint 淇濆瓨 鈫?涓嬫璇锋眰鑷姩鎭㈠ 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€


@pytest.mark.asyncio
async def test_scenario2_all_models_fail_checkpoint_saved(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    绗竴姝ワ細涓绘ā鍨嬪拰澶囩敤妯″瀷鍏ㄩ儴澶辫触銆?
    鏈熸湜锛?
      - 鎶涘嚭 _LlmUnavailableError
      - Redis 涓繚瀛樹簡鏂偣锛坘ey / session_id / completed_steps / state_snapshot锛?
      - 鍚戠敤鎴锋帹閫佷簡寮曞鏂囨
    """
    primary_llm = MagicMock(name="primary")
    fallback_llm = MagicMock(name="fallback")

    async def fake_stream_fail(
        llm_with_tools: Any,
        messages: Any,
        ctx: Any,
        *,
        thinking_message_id: str,
    ) -> tuple:
        exc = Exception("all systems down")
        exc.status_code = 503  # type: ignore[attr-defined]
        raise exc

    fake_redis = _FakeRedis()
    ctx = _FakeGatewayContext(session_id="sess-recovery-test", redis=fake_redis)

    monkeypatch.setattr(
        "datacloud_analysis.orchestration.execution.llm_retry._DEFAULT_MAX_RETRIES",
        0,
    )

    with (
        patch.object(rl_module, "_stream_llm_call", fake_stream_fail),
        pytest.raises(_LlmUnavailableError) as exc_info,
    ):
        await _invoke_llm_with_fallback(
            primary_llm,
            fallback_llm,
            messages_window=[],
            gateway_context=ctx,
            state={"user_query": "甯垜鏌ュ皬绫崇殑钀ユ敹", "confirmed_terms": ["灏忕背"]},
            round_idx=1,
            thinking_message_id="test_round_1",
        )

    # 鉁?Redis 涓湁鏂偣
    raw = await fake_redis.get("llm:checkpoint:sess-recovery-test")
    assert raw is not None
    payload = json.loads(raw)
    assert payload["session_id"] == "sess-recovery-test"
    assert payload["completed_steps"] == 1
    assert payload["state_snapshot"]["user_query"] == "甯垜鏌ュ皬绫崇殑钀ユ敹"

    # 验证引导文案通过异常返回（emit_chunk 在无 by_framework mock 时可能被静默降级）
    assert "重新发送同样的问题" in str(exc_info.value)


@pytest.mark.asyncio
async def test_scenario2_checkpoint_recovered_on_next_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    绗簩姝ワ細鐢ㄦ埛閲嶆柊鍙戦€佸悓鏍风殑闂锛堟ā鍨嬫鏃跺凡鎭㈠锛夈€?
    鏈熸湜锛?
      - run_react_loop 妫€娴嬪埌 Redis 鏂偣锛屾仮澶嶄笂娆′繚瀛樼殑 state 瀛楁
      - 鏂偣琚垹闄わ紙娑堣垂鍚庢竻鐞嗭級
      - 璇锋眰姝ｅ父瀹屾垚锛坰top_reason != "llm_unavailable"锛?
    """
    # 鈹€鈹€ 棰勫厛鍦?Redis 涓啓鍏ユ柇鐐癸紙妯℃嫙涓婃澶辫触淇濆瓨鐨勬柇鐐癸級鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
    fake_redis = _FakeRedis()
    await fake_redis.setex(
        "llm:checkpoint:sess-recovery",
        3600,
        json.dumps(
            {
                "session_id": "sess-recovery",
                "completed_steps": 1,
                "state_snapshot": {
                    "user_query": "甯垜鏌ュ皬绫崇殑钀ユ敹",
                    "confirmed_terms": ["灏忕背"],
                },
                "error_type": "Exception",
                "error_message": "all models down",
            }
        ),
    )

    ctx = _FakeGatewayContext(session_id="sess-recovery", redis=fake_redis)

    # 鈹€鈹€ Mock LLM锛氭湰娆℃ā鍨嬪凡鎭㈠锛岀洿鎺ヨ繑鍥炴枃瀛楃粨鏋?鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
    recovered_msg = AIMessage(content="灏忕背2024骞磋惀鏀朵负3100浜垮厓", tool_calls=[])
    mock_llm_with_tools = MagicMock()
    # astream should return an async iterator directly, not a coroutine.
    mock_llm_with_tools.astream = MagicMock(return_value=aiter([recovered_msg]))
    mock_llm_with_tools.ainvoke = AsyncMock(return_value=recovered_msg)
    mock_llm = MagicMock()
    mock_llm.bind_tools.return_value = mock_llm_with_tools

    monkeypatch.setattr(
        "datacloud_analysis.orchestration.execution.llm_retry._DEFAULT_MAX_RETRIES",
        0,
    )

    with (
        patch.object(rl_module, "_build_llm", return_value=mock_llm),
        patch(
            "datacloud_analysis.orchestration.execution.llm_retry._build_fallback_llm",
            return_value=None,
        ),
    ):
        result = await run_react_loop(
            state={"user_query": "甯垜鏌ュ皬绫崇殑钀ユ敹", "messages": []},
            tools_list=[],
            system_prompt="浣犳槸鏁版嵁鍒嗘瀽鍔╂墜",
            gateway_context=ctx,
            max_rounds=3,
        )

    # 鉁?璇锋眰姝ｅ父瀹屾垚
    assert result["react_final"]["stop_reason"] != "llm_unavailable"

    # 鉁?鏂偣宸茶娑堣垂鍒犻櫎
    remaining = await fake_redis.get("llm:checkpoint:sess-recovery")
    assert remaining is None


# 鈹€鈹€鈹€ 鍦烘櫙 3锛歳un_react_loop 绔埌绔紝涓绘ā鍨嬪け璐ュ叏绋嬩娇鐢ㄥ鐢ㄦā鍨?鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€


@pytest.mark.asyncio
async def test_scenario3_end_to_end_degradation_to_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    绔埌绔満鏅細鏁翠釜 run_react_loop 璋冪敤涓富妯″瀷濮嬬粓澶辫触锛屽鐢ㄦā鍨嬫帴绠★紝
    鏈€缁堜粛鑳芥甯歌繑鍥炵粨鏋滐紙stop_reason 涓嶆槸 llm_unavailable锛夈€?
    """
    primary_llm_tools = MagicMock(name="primary_bound")
    fallback_llm_tools = MagicMock(name="fallback_bound")

    primary_llm = MagicMock(name="primary")
    fallback_llm = MagicMock(name="fallback")
    primary_llm.bind_tools.return_value = primary_llm_tools
    fallback_llm.bind_tools.return_value = fallback_llm_tools

    # 澶囩敤妯″瀷鐩存帴杩斿洖绾枃瀛楀洖绛旓紙鏃?tool_calls 鈫?L2 鍋滄锛?
    final_answer = AIMessage(content="fallback model answer: revenue data below", tool_calls=[])

    async def fake_stream(
        llm_with_tools: Any,
        messages: Any,
        ctx: Any,
        *,
        thinking_message_id: str,
        query_received_at: float | None = None,
        round_idx: int = 0,
        config: Any = None,
    ) -> tuple:
        if llm_with_tools is primary_llm_tools:
            exc = Exception("Primary unavailable")
            exc.status_code = 503  # type: ignore[attr-defined]
            raise exc
        # 澶囩敤妯″瀷鎴愬姛杩斿洖
        return final_answer, False

    monkeypatch.setattr(
        "datacloud_analysis.orchestration.execution.llm_retry._DEFAULT_MAX_RETRIES",
        0,
    )

    with (
        patch.object(rl_module, "_build_llm", return_value=primary_llm),
        patch(
            "datacloud_analysis.orchestration.execution.llm_retry._build_fallback_llm",
            return_value=fallback_llm,
        ),
        patch.object(rl_module, "_stream_llm_call", fake_stream),
    ):
        result = await run_react_loop(
            state={"user_query": "查询营收", "messages": []},
            tools_list=[],
            system_prompt="浣犳槸鍔╂墜",
            gateway_context=None,
            max_rounds=3,
        )

    # 鉁?璇锋眰鎴愬姛瀹屾垚锛堝鐢ㄦā鍨嬬殑 L2 no_tool_call 璺緞锛?
    react_final = result["react_final"]
    assert react_final["stop_reason"] != "llm_unavailable"
    assert "fallback model answer" in react_final.get("answer", "")


@pytest.mark.asyncio
async def test_scenario3_both_models_fail_returns_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    绔埌绔細涓绘ā鍨嬪拰澶囩敤妯″瀷閮藉け璐ユ椂锛宺un_react_loop 杩斿洖 stop_reason=llm_unavailable锛?
    涓斿悜鐢ㄦ埛鎺ㄩ€佷簡寮曞鏂囨銆?
    """
    primary_llm_tools = MagicMock(name="primary_bound")
    fallback_llm_tools = MagicMock(name="fallback_bound")
    primary_llm = MagicMock()
    fallback_llm = MagicMock()
    primary_llm.bind_tools.return_value = primary_llm_tools
    fallback_llm.bind_tools.return_value = fallback_llm_tools

    async def fake_stream_always_fail(
        llm_with_tools: Any,
        messages: Any,
        ctx: Any,
        *,
        thinking_message_id: str,
    ) -> tuple:
        exc = Exception("complete outage")
        exc.status_code = 503  # type: ignore[attr-defined]
        raise exc

    ctx = _FakeGatewayContext(session_id="sess-e2e-fail", redis=_FakeRedis())
    monkeypatch.setattr(
        "datacloud_analysis.orchestration.execution.llm_retry._DEFAULT_MAX_RETRIES",
        0,
    )

    with (
        patch.object(rl_module, "_build_llm", return_value=primary_llm),
        patch(
            "datacloud_analysis.orchestration.execution.llm_retry._build_fallback_llm",
            return_value=fallback_llm,
        ),
        patch.object(rl_module, "_stream_llm_call", fake_stream_always_fail),
    ):
        result = await run_react_loop(
            state={"user_query": "查询营收", "messages": []},
            tools_list=[],
            system_prompt="浣犳槸鍔╂墜",
            gateway_context=ctx,
            max_rounds=3,
        )

    # 鉁?stop_reason 鏍囪涓?llm_unavailable
    assert result["react_final"]["stop_reason"] == "llm_unavailable"

    # 鉁?鐢ㄦ埛鏀跺埌浜嗗紩瀵兼枃妗?
    assert "重新发送同样的问题" in result["react_final"]["answer"]


@pytest.mark.asyncio
async def test_invoke_llm_with_fallback_requires_non_empty_thinking_message_id() -> None:
    """Contract guard: thinking_message_id 不能为空字符串。"""
    with pytest.raises(ValueError, match="thinking_message_id"):
        await _invoke_llm_with_fallback(
            primary_llm_with_tools=MagicMock(),
            fallback_llm_with_tools=None,
            messages_window=[],
            gateway_context=None,
            state={},
            round_idx=0,
            thinking_message_id="",
        )


# 鈹€鈹€鈹€ 杈呭姪锛歛sync iterator helper锛圥ython 3.10+ 鏈?aiter锛屼綆鐗堟湰鍏煎锛?鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€


def aiter(items: list) -> Any:
    """Wrap a plain list as an async iterator for mocked astream."""

    async def _gen():
        for item in items:
            yield item

    return _gen()
