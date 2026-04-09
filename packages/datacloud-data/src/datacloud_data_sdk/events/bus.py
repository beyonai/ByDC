"""
事件总线模块

本模块提供内存同步事件总线实现，支持事件的发布-订阅模式。
用于在系统内部进行松耦合的事件通信。

核心功能：
- 事件订阅：注册事件处理器
- 事件发布：触发所有订阅的处理器

使用示例：
    bus = EventBus()
    bus.subscribe(QueryRequestReceived, handle_query)
    await bus.publish(QueryRequestReceived(request_id="123", trace_id="456"))
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Awaitable, Callable

from datacloud_data_sdk.events.events import BaseEvent

HandlerType = Callable[[Any], Awaitable[None]]


class EventBus:
    """
    内存同步事件总线

    实现发布-订阅模式，支持异步事件处理。

    Attributes:
        _handlers: 事件类型到处理器列表的映射

    Example:
        bus = EventBus()
        bus.subscribe(QueryRequestReceived, async_handler)
        await bus.publish(event)
    """

    def __init__(self) -> None:
        """初始化事件总线"""
        self._handlers: dict[type, list[HandlerType]] = defaultdict(list)

    def subscribe(self, event_type: type, handler: HandlerType) -> None:
        """
        订阅事件

        注册一个异步处理器到指定事件类型。

        Args:
            event_type: 事件类型
            handler: 异步处理器函数
        """
        self._handlers[event_type].append(handler)

    async def publish(self, event: BaseEvent) -> None:
        """
        发布事件

        触发所有订阅该事件类型的处理器。

        Args:
            event: 事件实例
        """
        for handler in self._handlers.get(type(event), []):
            await handler(event)
