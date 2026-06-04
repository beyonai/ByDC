"""Langfuse 追踪回调工厂（兼容 SDK 4.x）。

通过 LANGFUSE_SECRET_KEY / LANGFUSE_PUBLIC_KEY / LANGFUSE_HOST 环境变量控制开关。
未配置时返回 None，不影响正常运行。

SDK 4.x 变更说明：
  - CallbackHandler 不再接受 user_id/session_id/trace_name/metadata 构造参数。
  - 请求级字段（user_id、session_id、trace_name 等）通过 run_config["metadata"]
    以 "langfuse_*" 前缀传入，SDK 在 on_chain_start 时自动读取并绑定到 trace。
  - 进程内共享单例，由 LangChain run_id 隔离不同请求的 trace。
"""

from __future__ import annotations

import contextvars
import logging
import os
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

# 进程级单例，避免每次请求都重复初始化
_handler_instance: Any | None = None
_handler_init_attempted: bool = False


def get_langfuse_callback() -> Any | None:
    """返回进程级 LangfuseCallbackHandler 单例，未配置时返回 None。

    请求级字段（user_id、session_id、trace_name 等）通过调用方写入
    run_config["metadata"]（以 "langfuse_" 为前缀），SDK 4.x 会在链启动时自动读取。

    Returns:
        CallbackHandler 实例，或 None（langfuse 未安装 / 未配置时）。
    """
    global _handler_instance, _handler_init_attempted  # noqa: PLW0603
    if _handler_init_attempted:
        return _handler_instance

    _handler_init_attempted = True

    if not os.getenv("LANGFUSE_SECRET_KEY"):
        logger.debug("langfuse: LANGFUSE_SECRET_KEY 未设置，跳过追踪")
        return None

    host = os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com")
    try:
        from langfuse.langchain import (  # type: ignore[import-untyped]  # noqa: PLC0415
            CallbackHandler,
        )

        _handler_instance = CallbackHandler()
        logger.info("langfuse: CallbackHandler 单例创建成功 host=%s", host)
    except ImportError:
        logger.warning("langfuse 未安装，已跳过追踪。可通过 `pip install langfuse` 启用。")
    except Exception:
        logger.warning("Langfuse CallbackHandler 初始化失败，已跳过追踪", exc_info=True)

    return _handler_instance
