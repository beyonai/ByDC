"""请求级上下文，基于 contextvars 实现线程/协程安全。"""

from __future__ import annotations

import contextvars
from dataclasses import dataclass
from types import TracebackType

from datacloud_data_sdk.exceptions import DatacloudError


@dataclass
class RequestContext:
    """请求上下文数据。"""

    tenant_id: str = ""
    user_id: str = ""
    session_id: str = ""
    token: str = ""
    system_code: str = ""


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
        self._ctx = RequestContext(**{k: v for k, v in kwargs.items() if v})
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
