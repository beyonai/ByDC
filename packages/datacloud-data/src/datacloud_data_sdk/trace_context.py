"""轻量级请求追踪上下文。

通过 Python contextvars 在同一异步调用链内共享 trace_id，
使 USER_QUERY / tool_call 参数 / SQL 三条日志可以通过同一个 ID 关联。

用法：
    # react_loop 入口处 set
    from datacloud_data_sdk.trace_context import current_trace_id
    token = current_trace_id.set("abc123")
    try:
        ...
    finally:
        current_trace_id.reset(token)

    # 任意深层调用 get
    tid = current_trace_id.get("")
"""

from __future__ import annotations

import contextvars

current_trace_id: contextvars.ContextVar[str] = contextvars.ContextVar(
    "datacloud_trace_id", default=""
)
