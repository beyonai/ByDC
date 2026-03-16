"""内存同步事件总线。"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Awaitable, Callable

from datacloud_data.events.events import BaseEvent

HandlerType = Callable[[Any], Awaitable[None]]


class EventBus:
    def __init__(self) -> None:
        self._handlers: dict[type, list[HandlerType]] = defaultdict(list)

    def subscribe(self, event_type: type, handler: HandlerType) -> None:
        self._handlers[event_type].append(handler)

    async def publish(self, event: BaseEvent) -> None:
        for handler in self._handlers.get(type(event), []):
            await handler(event)
