"""意图理解公共工具函数。"""

from __future__ import annotations

import json
import logging
import os
import re
from collections.abc import Callable
from contextlib import contextmanager
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# EventEmitter — 封装 StreamEvent 推送模式
# ---------------------------------------------------------------------------


class EventEmitter:
    """轻量事件推送器，封装 title → tool_name → tool_args → result/error 模式。

    用法::

        emit = EventEmitter(on_event)
        with emit.step("问题理解", "expand_query", {"query": q}):
            result = expand_query(q, on_event=on_event)
            if result is None:
                emit.error("LLM 展开失败")
                return ...
            emit.result(result.model_dump())
    """

    def __init__(self, on_event: Callable[[Any], None] | None) -> None:
        self._on_event = on_event

    def _emit(self, kind: str, content: str) -> None:
        if self._on_event:
            from .types import StreamEvent  # noqa: PLC0415

            self._on_event(StreamEvent(kind=kind, content=content))

    @property
    def active(self) -> bool:
        return self._on_event is not None

    # --- 原子事件 ---

    def title(self, text: str) -> None:
        self._emit("title", text)

    def tool_name(self, name: str) -> None:
        self._emit("tool_name", name)

    def tool_args(self, args: Any) -> None:
        self._emit("tool_args", _to_json(args))

    def result(self, data: Any) -> None:
        self._emit("tool_result", _to_json(data))

    def error(self, msg: str) -> None:
        self._emit("error", msg)

    # --- 组合：step 上下文管理器 ---

    @contextmanager
    def step(self, title: str, tool: str, args: Any = None):  # noqa: ANN204
        """推送 title + tool_name + tool_args，yield 后由调用方推 result/error。"""
        self.title(title)
        self.tool_name(tool)
        if args is not None:
            self.tool_args(args)
        yield self


def _to_json(obj: Any) -> str:
    """安全序列化为 JSON 字符串，已经是 str 则原样返回。"""
    if isinstance(obj, str):
        return obj
    return json.dumps(obj, ensure_ascii=False)


def stream_invoke_with_thinking(
    llm_with_tool: Any,
    messages: list[dict[str, str]],
    on_event: Callable[[Any], None] | None = None,
) -> Any:
    """用 stream() 替代 invoke()，同时通过回调推送 thinking 内容。

    支持两种 thinking 格式：
    - Anthropic provider: chunk.content 是 list，含 {'type': 'thinking', 'thinking': '...'} 块
    - OpenAI provider: chunk.additional_kwargs.get('reasoning_content')

    Args:
        llm_with_tool: 已 bind_tools 的 LLM 实例（RunnableBinding）。
        messages: 消息列表。
        on_event: 可选回调，接收 StreamEvent 实例。

    Returns:
        累积后的完整 AIMessage，等价于 invoke() 的返回值。
    """
    if not on_event:
        return llm_with_tool.invoke(messages)

    from .types import StreamEvent  # noqa: PLC0415

    full = None
    for chunk in llm_with_tool.stream(messages):
        thinking = ""

        # Anthropic 格式: content 是 list，含 thinking block
        if isinstance(chunk.content, list):
            for block in chunk.content:
                if isinstance(block, dict) and block.get("type") == "thinking":
                    thinking = block.get("thinking", "")
                    break

        # OpenAI 格式: additional_kwargs 里的 reasoning_content
        if not thinking:
            thinking = chunk.additional_kwargs.get("reasoning_content", "")

        if thinking:
            on_event(StreamEvent(kind=StreamEvent.THINKING, content=thinking))

        full = chunk if full is None else full + chunk
    return full


def extract_json_from_text(text: str) -> dict[str, Any] | None:
    """从 LLM 文本输出中兜底提取 JSON 对象。

    解析策略（按优先级）：
    1. 提取 ```json ... ``` 代码块
    2. 查找最后一个含 select/query/decisions 关键字的 {...} 对象
    """
    # 策略 1：```json ... ``` 块
    m = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if m:
        raw = m.group(1).strip()
        try:
            obj = json.loads(raw)
            if isinstance(obj, dict):
                return obj
        except (json.JSONDecodeError, ValueError):
            pass

    # 策略 2：最后一个含关键字段的 {...}
    matches = re.findall(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", text, re.DOTALL)
    for candidate in reversed(matches):
        try:
            obj = json.loads(candidate)
            if isinstance(obj, dict) and ("select" in obj or "query" in obj or "decisions" in obj):
                return obj
        except (json.JSONDecodeError, ValueError):
            continue
    return None


def build_llm() -> Any:
    """构建 LLM 实例（懒导入 langchain，不增加硬依赖）。

    按优先级读取环境变量：DATACLOUD_LLM → OPENAI 兜底。
    通过 DATACLOUD_LLM_MODEL_PROVIDER 指定协议（openai 默认，或 anthropic）。
    请使用此变量指定协议，不要在 DATACLOUD_LLM_MODEL 中使用前缀写法。
    支持 MODEL_KWARGS（JSON 字符串）透传额外参数。
    """
    from langchain.chat_models import init_chat_model  # noqa: PLC0415

    for env_prefix in ("DATACLOUD_LLM", "OPENAI"):
        api_base = os.getenv(f"{env_prefix}_API_BASE", "")
        api_key = os.getenv(f"{env_prefix}_API_KEY", "")
        model = os.getenv(f"{env_prefix}_MODEL", "")
        if api_key and model:
            provider = os.getenv(f"{env_prefix}_MODEL_PROVIDER", "openai").strip().lower()
            temperature = float(os.getenv(f"{env_prefix}_TEMPERATURE", "0.0"))
            # 读取可选的 MODEL_KWARGS（JSON 字符串）
            model_kwargs: dict[str, Any] = {}
            raw_kwargs = os.getenv(f"{env_prefix}_MODEL_KWARGS", "")
            if raw_kwargs:
                try:
                    model_kwargs = json.loads(raw_kwargs)
                except (json.JSONDecodeError, ValueError):
                    logger.warning(
                        "[build_llm] 无法解析 %s_MODEL_KWARGS: %s", env_prefix, raw_kwargs
                    )
            kwargs: dict[str, Any] = dict(
                model=model,
                model_provider=provider,
                api_key=api_key,
                temperature=temperature,
                **model_kwargs,
            )
            if api_base:
                kwargs["base_url"] = api_base
            return init_chat_model(**kwargs)
    # 兜底
    api_key = os.getenv("OPENAI_API_KEY", "")
    base_url = os.getenv("OPENAI_BASE_URL", "")
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    return init_chat_model(
        model=model,
        model_provider="openai",
        api_key=api_key,
        base_url=base_url,
        temperature=0.0,
    )
