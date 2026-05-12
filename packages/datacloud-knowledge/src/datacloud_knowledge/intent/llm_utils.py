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
            from .types import StreamEvent

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
    def step(self, title: str, tool: str, args: Any = None):
        """推送 title + tool_name + tool_args，yield 后由调用方推 result/error。"""
        self._emit("step_begin", title)
        self.title(title)
        self.tool_name(tool)
        if args is not None:
            self.tool_args(args)
        try:
            yield self
        finally:
            self._emit("step_end", title)


def _to_json(obj: Any) -> str:
    """安全序列化为 JSON 字符串，已经是 str 则原样返回。"""
    if isinstance(obj, str):
        return obj
    return json.dumps(obj, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Thinking 关键字本地化 — 将 SQL/schema 英文关键字替换为中文
# ---------------------------------------------------------------------------

# 完整关键字 → 中文（长词优先匹配）
_KW_TABLE: dict[str, str] = {
    "group_by": "分组",
    "order_by": "排序",
    "field_alias": "字段别名",
    "select": "查询字段",
    "where": "筛选条件",
    "limit": "行数限制",
    "query": "查询",
    "expr": "表达式",
    "alias": "别名",
    "field": "字段",
    "value": "值",
    "op": "运算符",
}

# 所有关键字集合（小写），用于判断尾部 token
_KW_SET: set[str] = {k.lower() for k in _KW_TABLE}

# 可能变成更长关键字的 token（含完整短关键字，如 field → field_alias）
_KW_GROWABLE: set[str] = set()
for _kw in _KW_TABLE:
    for _i in range(1, len(_kw)):
        prefix = _kw[:_i].lower()
        # 这个前缀可以长成更长的关键字
        _KW_GROWABLE.add(prefix)

# 单次正则：匹配所有关键字（长词优先）
# 使用 ASCII 词边界（(?<![A-Za-z_]) / (?![A-Za-z_])）而非 \b，
# 因为 Python re 的 \b 将中文字符视为 \w，导致 "where里" 中 \bwhere\b 不匹配。
_ASCII_LB = r"(?<![A-Za-z_])"  # ASCII left boundary
_ASCII_RB = r"(?![A-Za-z_])"  # ASCII right boundary
_KW_PATTERN = re.compile(
    _ASCII_LB
    + "("
    + "|".join(re.escape(k) for k in sorted(_KW_TABLE, key=len, reverse=True))
    + ")"
    + _ASCII_RB,
    re.IGNORECASE,
)

# 尾部英文 token（含下划线）：可能是未完成的关键字
_TRAILING_TOKEN_RE = re.compile(r"[A-Za-z_]+$")


def _localize_thinking(text: str, *, language: str = "zh_CN") -> tuple[str, str]:
    """将 thinking 文本中的 SQL/schema 英文关键字替换为中文。

    当 ``language`` 不为 ``"zh_CN"`` 时，不做翻译，直接返回原文。

    Returns:
        (safe, pending): safe 是可以安全输出的部分，pending 是尾部可能未完成的 token。
    """
    if language != "zh_CN":
        return text, ""

    # 检查尾部是否有未完成的英文 token，且它是某个关键字的严格前缀
    m = _TRAILING_TOKEN_RE.search(text)
    if m:
        tail = m.group().lower()
        # pending 条件：tail 是某个关键字的严格前缀，后续 chunk 可能让它变成完整关键字
        # 包括 tail 本身是完整短关键字但也是更长关键字前缀的情况（如 field → field_alias）
        if tail in _KW_GROWABLE:
            safe_text = text[: m.start()]
            pending = text[m.start() :]
        else:
            safe_text = text
            pending = ""
    else:
        safe_text = text
        pending = ""

    replaced = _KW_PATTERN.sub(
        lambda match: _KW_TABLE.get(match.group().lower(), match.group()), safe_text
    )
    return replaced, pending


def stream_invoke_with_thinking(
    llm_with_tool: Any,
    messages: list[dict[str, str]],
    on_event: Callable[[Any], None] | None = None,
    *,
    language: str = "zh_CN",
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

    from .types import StreamEvent, StreamEventKind

    full = None
    thinking_acc = ""  # 累积原始 thinking，统一两种格式为累积式
    prev_emitted = ""  # 上次 emit 的安全文本，用于累积式 content
    for chunk in llm_with_tool.stream(messages):
        raw_delta = ""
        # Anthropic 格式: content 是 list，含 thinking block
        if isinstance(chunk.content, list):
            for block in chunk.content:
                if isinstance(block, dict) and block.get("type") == "thinking":
                    raw = block.get("thinking", "")
                    if raw:
                        # 判断是累积式还是增量式：如果 raw 以 thinking_acc 开头，则是累积式
                        if raw.startswith(thinking_acc) and len(raw) > len(thinking_acc):
                            raw_delta = raw[len(thinking_acc) :]
                            thinking_acc = raw
                        else:
                            # 增量式：直接追加
                            raw_delta = raw
                            thinking_acc += raw
                    break
        else:
            # OpenAI 格式: reasoning_content 是增量的，手动累积
            raw_delta = chunk.additional_kwargs.get("reasoning_content", "")
            if raw_delta:
                thinking_acc += raw_delta

        if thinking_acc:
            safe, _pending = _localize_thinking(thinking_acc, language=language)
            if safe != prev_emitted:
                on_event(
                    StreamEvent(
                        kind=StreamEventKind.THINKING,
                        content=safe,
                    )
                )
                prev_emitted = safe

        full = chunk if full is None else full + chunk

    # 流结束，flush 尾部 pending（不再有后续 chunk，直接替换输出）
    if thinking_acc:
        final = _KW_PATTERN.sub(lambda m: _KW_TABLE.get(m.group().lower(), m.group()), thinking_acc)
        if final != prev_emitted:
            on_event(StreamEvent(kind=StreamEventKind.THINKING, content=final))

    return full


def extract_json_from_text(text: str | list[Any]) -> dict[str, Any] | None:
    """从 LLM 文本输出中兜底提取 JSON 对象。

    解析策略（按优先级）：
    1. 提取 ```json ... ``` 代码块
    2. 查找最后一个含 select/query/decisions 关键字的 {...} 对象

    Args:
        text: LLM 输出文本。MiniMax reasoning 模式下 content 可能是 list，
              此处自动拼接为字符串。
    """
    if isinstance(text, list):
        text = "\n".join(str(part) for part in text)
    if not isinstance(text, str):
        text = str(text)
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
    from langchain.chat_models import init_chat_model

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
