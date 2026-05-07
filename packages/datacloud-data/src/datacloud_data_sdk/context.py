"""
请求级上下文模块

本模块基于 Python 的 contextvars 实现线程/协程安全的请求上下文管理。
主要用于在请求处理过程中传递租户ID、用户ID、会话ID、认证令牌等上下文信息。

核心组件：
- RequestContext: 请求上下文数据类，存储请求级别的元数据
- InvocationContext: 上下文管理器，用于设置和清理请求上下文
- get_current_context(): 获取当前请求上下文的工具函数

使用示例：
    with InvocationContext(tenant_id="t1", user_id="u1", token="xxx"):
        ctx = get_current_context()
        print(ctx.tenant_id)  # 输出: "t1"
"""

from __future__ import annotations

import contextvars
from dataclasses import dataclass, field
from types import TracebackType
from typing import Any

from datacloud_data_sdk.exceptions import DatacloudError


@dataclass
class RequestContext:
    """
    请求上下文数据类

    存储单个请求的所有上下文信息，包括租户、用户、会话等标识。
    所有字段都有默认值，支持部分设置。

    Attributes:
        tenant_id: 租户ID，用于多租户隔离
        user_id: 用户ID，标识当前操作用户
        session_id: 会话ID，用于追踪用户会话
        token: 认证令牌，用于API调用时的身份验证
        system_code: 系统代码，标识调用来源系统
        cookie: Cookie 字符串，用于 HTTP 请求认证
        tool_list_mode: 工具列表模式，控制 MCP/Skills 返回的工具列表格式
            - "unified": 统一模式，返回所有工具的合并列表
            - "per_object": 按对象模式，按对象分组返回工具列表
        gateway_context: Gateway AgentContext 实例，用于向前端推送执行进度事件。
            类型声明为 Any 以避免 datacloud-data 依赖 gateway_sdk。
        result_file_storage: 结果文件存储后端实例（实现 ResultFileStorage 抽象），
            用于工具/SDK 内的文件读写。类型声明为 Any 以避免 datacloud-data 与
            落地项目（如 byclaw-data 的 ByclawResultFileStorage）形成静态依赖。
            由调用方在构造 InvocationContext 时注入。
    """

    tenant_id: str = ""
    user_id: str = ""
    session_id: str = ""
    token: str = ""
    system_code: str = ""
    cookie: str = ""
    tool_list_mode: str = "unified"
    view_id: str = ""
    object_ids: list[str] | None = None
    tool_call_detail: bool = False
    gateway_context: Any = field(default=None, repr=False)
    workspace_dir: str = ""
    result_file_storage: Any = field(default=None, repr=False)


_ctx_var: contextvars.ContextVar[RequestContext | None] = contextvars.ContextVar(
    "invocation_context", default=None
)


class InvocationContext:
    """
    请求上下文管理器

    实现 Python 上下文管理器协议，在 with 块内自动设置请求上下文，
    退出 with 块时自动清理，确保上下文不会泄漏到其他请求。

    使用 contextvars 实现线程和协程安全，支持异步环境。

    Args:
        **kwargs: 上下文字段，支持 tenant_id, user_id, session_id, token, system_code,
            tool_list_mode, view_id, object_ids

    Example:
        基本用法::

            with InvocationContext(tenant_id="t1", token="xxx"):
                ctx = get_current_context()
                print(ctx.tenant_id)  # 输出: "t1"

        异步环境使用::

            async def handle_request():
                with InvocationContext(tenant_id="t1", user_id="u1"):
                    # 在异步函数中也能正确获取上下文
                    ctx = get_current_context()
                    await process_with_context(ctx)
    """

    def __init__(self, **kwargs: Any) -> None:
        tool_mode = kwargs.get("tool_list_mode", "unified")
        if tool_mode not in ("unified", "per_object"):
            tool_mode = "unified"
        self._ctx = RequestContext(
            tenant_id=kwargs.get("tenant_id", ""),
            user_id=kwargs.get("user_id", ""),
            session_id=kwargs.get("session_id", ""),
            token=kwargs.get("token", ""),
            system_code=kwargs.get("system_code", ""),
            cookie=kwargs.get("cookie", ""),
            tool_list_mode=tool_mode,
            view_id=kwargs.get("view_id", ""),
            object_ids=kwargs.get("object_ids"),
            tool_call_detail=bool(kwargs.get("tool_call_detail", False)),
            gateway_context=kwargs.get("gateway_context"),
            workspace_dir=kwargs.get("workspace_dir", ""),
            result_file_storage=kwargs.get("result_file_storage"),
        )
        self._token: contextvars.Token[RequestContext | None] | None = None

    def __enter__(self) -> InvocationContext:
        """进入上下文，设置请求上下文变量"""
        self._token = _ctx_var.set(self._ctx)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """退出上下文，恢复之前的上下文状态"""
        if self._token is not None:
            _ctx_var.reset(self._token)


def get_current_context() -> RequestContext:
    """
    获取当前请求上下文

    从 contextvars 中获取当前请求的上下文信息。
    必须在 InvocationContext 上下文管理器内部调用，
    否则抛出 DatacloudError 异常。

    Returns:
        RequestContext: 当前请求的上下文对象

    Raises:
        DatacloudError: 未设置上下文时抛出

    Example:
        with InvocationContext(tenant_id="t1"):
            ctx = get_current_context()
            print(ctx.tenant_id)  # 输出: "t1"
    """
    ctx = _ctx_var.get()
    if ctx is None:
        raise DatacloudError("InvocationContext not set. Use `with InvocationContext(...):`")
    return ctx


def get_tool_list_mode() -> str:
    """
    获取当前工具列表模式

    安全地获取当前的 tool_list_mode 设置。
    如果未设置上下文或模式值无效，返回默认值 "unified"。

    Returns:
        str: 工具列表模式，"unified" 或 "per_object"
    """
    ctx = _ctx_var.get()
    if ctx is None:
        return "unified"
    return ctx.tool_list_mode if ctx.tool_list_mode in ("unified", "per_object") else "unified"


def get_tool_call_detail() -> bool:
    """
    获取当前请求是否需要输出 tool_call 详细信息。

    未设置上下文时返回 False，避免 SDK 层直接调用时报错。

    Returns:
        bool: 是否输出 tool_call 详细信息
    """
    ctx = _ctx_var.get()
    if ctx is None:
        return False
    return bool(ctx.tool_call_detail)


def get_gateway_context() -> Any | None:
    """
    获取当前请求中的 Gateway AgentContext

    从 contextvars 中安全地获取 gateway_context。
    未设置上下文或未传入 gateway_context 时返回 None，不抛异常。

    Returns:
        AgentContext 实例，或 None
    """
    ctx = _ctx_var.get()
    if ctx is None:
        return None
    return ctx.gateway_context
