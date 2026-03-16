import pytest
from datacloud_data_sdk.events.bus import EventBus
from datacloud_data_sdk.events.handlers import register_query_handlers


async def test_register_handlers_subscribes_to_events():
    bus = EventBus()
    received = []
    register_query_handlers(bus, on_event=lambda e: received.append(e))

    from datacloud_data_sdk.events.events import QueryRequestReceived

    await bus.publish(QueryRequestReceived(request_id="r1", trace_id="t1"))
    assert len(received) == 1
    assert received[0].request_id == "r1"


async def test_register_handlers_multiple_events():
    bus = EventBus()
    received = []
    register_query_handlers(bus, on_event=lambda e: received.append(type(e).__name__))

    from datacloud_data_sdk.events.events import QueryRequestReceived, ObjectViewBuilt

    await bus.publish(QueryRequestReceived(request_id="r1", trace_id="t1"))
    await bus.publish(ObjectViewBuilt(request_id="r1", trace_id="t1"))
    assert "QueryRequestReceived" in received
    assert "ObjectViewBuilt" in received


async def test_register_handlers_no_callback_does_not_crash():
    bus = EventBus()
    register_query_handlers(bus)
    from datacloud_data_sdk.events.events import QueryRequestReceived

    await bus.publish(QueryRequestReceived(request_id="r1", trace_id="t1"))


async def test_register_handlers_with_tracing_subscribes_via_tracing():
    """验证 tracing 传入时使用 tracing.subscribe 而非 bus.subscribe。"""
    bus = EventBus()
    from datacloud_data_sdk.events.tracing import TracingMiddleware

    tracing = TracingMiddleware(bus)

    subscribe_calls = []

    original_subscribe = tracing.subscribe

    def capture_subscribe(event_type, handler, module_name):
        subscribe_calls.append((event_type, handler, module_name))
        original_subscribe(event_type, handler, module_name)

    tracing.subscribe = capture_subscribe

    register_query_handlers(bus, tracing=tracing)

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

    expected_types = [
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
    assert len(subscribe_calls) == len(expected_types)
    for (event_cls, handler, module_name), expected_cls in zip(subscribe_calls, expected_types):
        assert event_cls is expected_cls
        assert callable(handler)
        assert module_name == "query"

    # 发布事件应能正常传播（tracing 已注册到 bus）
    await bus.publish(QueryRequestReceived(request_id="r1", trace_id="t1"))
