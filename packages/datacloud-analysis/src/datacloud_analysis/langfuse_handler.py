"""Langfuse 追踪回调工厂（兼容 SDK 4.x）。

通过 LANGFUSE_SECRET_KEY / LANGFUSE_PUBLIC_KEY / LANGFUSE_HOST 环境变量控制开关。
未配置时返回 None，不影响正常运行。

SDK 4.x 变更说明：
  - CallbackHandler 通过 trace_context=TraceContext(trace_id=...) 关联请求级 trace。
  - 每次请求创建独立 CallbackHandler 实例，确保 session_id / user_id 正确隔离。
  - 进程级可用性检测缓存，避免每次请求都重试初始化。
"""

from __future__ import annotations

import contextvars
import logging
import os
import re
from typing import Any

logger = logging.getLogger(__name__)

# 请求级 trace_id，由 worker.py 在每次请求开始时写入，react_loop.py 读取
current_trace_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "langfuse_current_trace_id", default=None
)

# 请求级工具调用收集列表，由 worker.py 注入空列表，react_loop.py 往里追加
current_tool_spans: contextvars.ContextVar[list[dict[str, Any]] | None] = contextvars.ContextVar(
    "langfuse_current_tool_spans", default=None
)

# 进程级可用性缓存：None=未检测，True=可用，False=不可用
_langfuse_available: bool | None = None


def _check_langfuse_available() -> bool:
    """检测 Langfuse 是否可用（环境变量 + 依赖），结果进程级缓存。

    同时初始化全局 Langfuse 单例（指定 base_url），确保 LangchainCallbackHandler
    内部的 get_client() 拿到的是内网实例，而不是默认的 cloud.langfuse.com。
    """
    global _langfuse_available  # noqa: PLW0603
    if _langfuse_available is not None:
        return _langfuse_available

    secret_key = os.getenv("LANGFUSE_SECRET_KEY")
    public_key = os.getenv("LANGFUSE_PUBLIC_KEY")
    # LANGFUSE_BASE_URL 是 SDK 4.x 标准变量；LANGFUSE_HOST 为旧版兼容
    base_url = os.getenv("LANGFUSE_BASE_URL") or os.getenv("LANGFUSE_HOST")

    if not secret_key:
        logger.debug("langfuse: LANGFUSE_SECRET_KEY 未设置，跳过追踪")
        _langfuse_available = False
        return False

    try:
        from langfuse import Langfuse  # noqa: PLC0415
        from langfuse.langchain import (
            CallbackHandler,  # type: ignore[import-untyped]  # noqa: PLC0415, F401
        )

        # 显式初始化单例，指定正确的 host，避免 get_client() 默认连公网
        _init_kwargs: dict = {
            "public_key": public_key,
            "secret_key": secret_key,
        }
        if base_url:
            _init_kwargs["host"] = base_url
        Langfuse(**_init_kwargs)

        _langfuse_available = True
        logger.info("langfuse: SDK 可用，host=%s", base_url or "https://cloud.langfuse.com")
    except ImportError:
        logger.warning("langfuse 未安装，已跳过追踪。可通过 `pip install langfuse` 启用。")
        _langfuse_available = False
    except Exception:
        logger.warning("langfuse 可用性检测失败，已跳过追踪", exc_info=True)
        _langfuse_available = False

    return _langfuse_available


def make_langfuse_callback(
    lf_trace_id: str | None = None,
    parent_span_id: str | None = None,
) -> Any | None:
    """创建请求级 LangfuseCallbackHandler，未配置时返回 None。

    Args:
        lf_trace_id: Langfuse 合法 trace id（32位小写 hex）。
                     提供时 CallbackHandler 挂载到该 trace；
                     不提供时 SDK 自动生成新 trace。
        parent_span_id: 父 span id（16位小写 hex）。
                     提供时 LangGraph 根节点挂在该 span 下，实现完整层级。

    Returns:
        CallbackHandler 实例，或 None（langfuse 未安装 / 未配置时）。
    """
    if not _check_langfuse_available():
        return None

    try:
        from langfuse.langchain import (
            CallbackHandler as _BaseCallbackHandler,  # type: ignore[import-untyped]  # noqa: PLC0415
        )
        from langfuse.types import TraceContext  # noqa: PLC0415

        class _PatchedCallbackHandler(_BaseCallbackHandler):  # type: ignore[misc]
            """修复 MiniMax 等模型 total_characters=0 导致 token 计数全为0的问题。

            Langfuse 看到 token_usage 里有 total_characters 字段时会切换为字符计费模式，
            total_characters=0 会覆盖真实的 prompt_tokens / completion_tokens。
            在 on_llm_end 里把无效的 total_characters 字段移除，走标准 token 计费路径。
            """

            def on_llm_end(self, response: Any, **kwargs: Any) -> Any:  # type: ignore[override]
                # 修复 total_characters=0 覆盖 prompt_tokens 的问题
                try:
                    llm_output = getattr(response, "llm_output", None) or {}
                    if isinstance(llm_output, dict):
                        token_usage: dict = llm_output.get("token_usage") or {}
                        if (
                            isinstance(token_usage, dict)
                            and token_usage.get("total_characters") == 0
                            and (token_usage.get("prompt_tokens") or 0) > 0
                        ):
                            token_usage.pop("total_characters", None)
                            token_usage.pop("completion_tokens_details", None)
                            token_usage.pop("prompt_tokens_details", None)
                except Exception:  # noqa: BLE001
                    pass
                return super().on_llm_end(response, **kwargs)

        _is_valid = bool(lf_trace_id and re.fullmatch(r"[0-9a-f]{32}", lf_trace_id))
        if _is_valid:
            tc: dict[str, str] = {"trace_id": lf_trace_id}
            if parent_span_id and re.fullmatch(r"[0-9a-f]{1,32}", parent_span_id):
                tc["parent_span_id"] = parent_span_id
            trace_context = TraceContext(**tc)
        else:
            trace_context = None

        return _PatchedCallbackHandler(trace_context=trace_context)
    except Exception:
        logger.warning("LangfuseCallbackHandler 创建失败，已跳过追踪", exc_info=True)
        return None


# 向后兼容：旧代码调用 get_langfuse_callback() 的地方不会报错
def get_langfuse_callback() -> Any | None:
    """兼容旧调用，新代码请使用 make_langfuse_callback(lf_trace_id)。"""
    from datacloud_analysis.otel_handler import init_otel  # noqa: PLC0415

    init_otel()
    return make_langfuse_callback()
