"""请求级上下文，基于 contextvars 实现线程/协程安全。"""

from __future__ import annotations

import contextvars
from dataclasses import dataclass
from types import TracebackType

from datacloud_data.exceptions import DatacloudError


@dataclass
class RequestContext:
    """请求上下文数据。"""

    tenant_id: str = ""
    user_id: str = ""
    session_id: str = ""
    token: str = ""
    system_code: str = ""
    tool_list_mode: str = "unified"  # unified | per_object，控制 MCP/Skills 返回的工具列表


_ctx_var: contextvars.ContextVar[RequestContext | None] = contextvars.ContextVar(
    "invocation_context", default=None
)


class InvocationContext:
    """上下文管理器，在 with 块内设置请求上下文。

    Example::

        with InvocationContext(tenant_id="t1", token="xxx"):
            ctx = get_current_context()
            print(ctx.tenant_id)  # "t1"
    """

    def __init__(self, **kwargs: str) -> None:
        tool_mode = kwargs.get("tool_list_mode", "unified")
        if tool_mode not in ("unified", "per_object"):
            tool_mode = "unified"
        self._ctx = RequestContext(
            tenant_id=kwargs.get("tenant_id", ""),
            user_id=kwargs.get("user_id", ""),
            session_id=kwargs.get("session_id", ""),
            token=kwargs.get("token", ""),
            system_code=kwargs.get("system_code", ""),
            tool_list_mode=tool_mode,
        )
        self._token: contextvars.Token[RequestContext | None] | None = None

    def __enter__(self) -> InvocationContext:
        self._token = _ctx_var.set(self._ctx)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if self._token is not None:
            _ctx_var.reset(self._token)


def get_current_context() -> RequestContext:
    """获取当前请求上下文，未设置时抛出异常。"""
    ctx = _ctx_var.get()
    if ctx is None:
        raise DatacloudError("InvocationContext not set. Use `with InvocationContext(...):`")
    return ctx


def get_tool_list_mode() -> str:
    """获取当前 tool_list_mode，未设置上下文时返回 unified。"""
    ctx = _ctx_var.get()
    if ctx is None:
        return "unified"
    return ctx.tool_list_mode if ctx.tool_list_mode in ("unified", "per_object") else "unified"
