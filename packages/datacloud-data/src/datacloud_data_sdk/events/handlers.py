"""事件处理链注册：将查询管线各阶段事件串联到 EventBus。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable

from datacloud_data_sdk.events.bus import EventBus

if TYPE_CHECKING:
    from datacloud_data_sdk.events.tracing import TracingMiddleware


async def _async_noop(event: Any) -> None:
    """无操作处理器，用于 TracingMiddleware 仅记录 span 的场景。"""
    pass


def register_query_handlers(
    bus: EventBus,
    on_event: Callable[[Any], None] | None = None,
    tracing: TracingMiddleware | None = None,
) -> None:
    """注册查询管线所有事件类型的处理器。

    on_event 回调在每个事件被发布时触发，用于日志、追踪等可观测性用途。
    tracing 非空时，通过 tracing.subscribe 注册（记录 EventSpan）；否则通过 bus.subscribe 注册。
    """
    from datacloud_data_sdk.events.events import (
        AggregationCompleted,
        ExecutionTasksReady,
        ObjectViewBuilt,
        PlanRewritten,
        PlanValidated,
        PlanValidationFailed,
        QueryPlanGenerated,
        QueryRequestReceived,
        StepsExecuted,
    )

    all_event_types = [
        QueryRequestReceived,
        ObjectViewBuilt,
        QueryPlanGenerated,
        PlanValidated,
        PlanRewritten,
        ExecutionTasksReady,
        StepsExecuted,
        AggregationCompleted,
        PlanValidationFailed,
    ]

    if tracing is not None:
        for event_cls in all_event_types:
            tracing.subscribe(event_cls, _async_noop, "query")
    elif on_event:

        async def _async_on_event(event: Any) -> None:
            on_event(event)

        for event_cls in all_event_types:
            bus.subscribe(event_cls, _async_on_event)
