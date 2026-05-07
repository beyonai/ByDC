"""Agent 执行上报抽象与默认实现。

将历史上隐式的 ``gateway_context`` 鸭子类型契约显式化为 ``ExecutionReporter``
协议，使 datacloud-analysis 与具体 Gateway 框架（如 byclaw-data 的
AgentContext）真正解耦：

- 静态：本模块不 import 任何 ``by_framework`` / ``gateway_sdk`` 包；
- 语义：``tool_wrapper`` 等业务代码只依赖此协议方法/属性；
- 默认：无 Gateway 的部署（demo、单测、独立调用）使用
  ``NoOpExecutionReporter``，所有上报为 no-op；
- 真实 Gateway：通过 duck-type 自然满足此协议（已有方法签名一致）。
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class ExecutionReporter(Protocol):
    """Agent 执行过程中的进度 / 事件上报契约。

    实现方需提供：

    Attributes:
        message_id: 当前节点消息 ID（用于父子节点串联）。无关心可返回空串。
        user_id: 调用方用户标识。
        session_id: 调用方会话标识。
        extras: 请求级扩展上下文（cookie / token 等任意键值）；
            ``None`` 表示未传。

    Required methods:
        mark_execution_start: 标记执行开始（用于 react_loop 心跳起点）。
        sub_step: 异步上下文管理器，包裹一次 sub_step 区间。
    """

    @property
    def message_id(self) -> str: ...

    @property
    def user_id(self) -> str: ...

    @property
    def session_id(self) -> str: ...

    @property
    def extras(self) -> dict[str, Any] | None: ...

    def mark_execution_start(self) -> None: ...

    def sub_step(self, title: str) -> Any:  # AsyncContextManager[None]
        """返回一个 ``async with`` 兼容的上下文管理器。

        类型用 ``Any`` 而非 ``AsyncContextManager[None]`` 是出于 Protocol
        在 mypy 中对 ``@asynccontextmanager`` 装饰返回值的兼容考量。
        """


class NoOpExecutionReporter:
    """``ExecutionReporter`` 的零开销默认实现。

    - 所有方法不执行任何副作用；
    - 所有属性返回构造时的字面量；
    - 用于无 Gateway 的演示 / 单测 / 独立 SDK 调用场景。

    真实部署（byclaw-data 等）继续直接传入自身 AgentContext 实例，由 duck-type
    匹配协议；本类不参与那条路径。
    """

    def __init__(
        self,
        *,
        user_id: str = "",
        session_id: str = "",
        extras: dict[str, Any] | None = None,
    ) -> None:
        self._user_id = user_id
        self._session_id = session_id
        self._extras = extras
        # message_id 为空串表示「无具体节点」，下游 emit 路径会跳过 parent_message_id 关联
        self._message_id = ""

    @property
    def message_id(self) -> str:
        return self._message_id

    @property
    def user_id(self) -> str:
        return self._user_id

    @property
    def session_id(self) -> str:
        return self._session_id

    @property
    def extras(self) -> dict[str, Any] | None:
        return self._extras

    def mark_execution_start(self) -> None:
        return None

    @asynccontextmanager
    async def sub_step(self, title: str) -> AsyncIterator[None]:  # noqa: ARG002
        yield


__all__ = ["ExecutionReporter", "NoOpExecutionReporter"]
