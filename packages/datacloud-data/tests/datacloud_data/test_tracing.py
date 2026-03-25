import pytest

from datacloud_data_sdk.events.bus import EventBus
from datacloud_data_sdk.events.events import ObjectViewBuilt, QueryPlanGenerated
from datacloud_data_sdk.events.tracing import EventSpan, TracingMiddleware


@pytest.mark.asyncio
async def test_tracing_middleware_records_span() -> None:
    bus = EventBus()
    tracing = TracingMiddleware(bus)
    spans: list[EventSpan] = []
    tracing.on_span_complete(spans.append)

    async def handler(event: ObjectViewBuilt) -> None:
        await bus.publish(
            QueryPlanGenerated(
                request_id=event.request_id,
                trace_id=event.trace_id,
                plan={},
                object_view=event.object_view,
                question=event.question,
            )
        )

    tracing.subscribe(ObjectViewBuilt, handler, module_name="ObjectViewBuilder")

    await bus.publish(
        ObjectViewBuilt(request_id="req1", trace_id="tr1", object_view={}, question="查商机")
    )

    assert len(spans) == 1
    span = spans[0]
    assert span.module == "ObjectViewBuilder"
    assert span.event_in == "ObjectViewBuilt"
    assert span.status == "ok"
    assert span.duration_ms >= 0
    assert span.input_summary == {"object_count": 0}


@pytest.mark.asyncio
async def test_tracing_middleware_populates_input_summary() -> None:
    """验证各事件类型的 input_summary 正确填充。"""
    from datacloud_data_sdk.events.events import QueryRequestReceived

    bus = EventBus()
    tracing = TracingMiddleware(bus)
    spans: list[EventSpan] = []
    tracing.on_span_complete(spans.append)

    async def noop(_: object) -> None:
        pass

    tracing.subscribe(QueryRequestReceived, noop, "test")

    await bus.publish(
        QueryRequestReceived(
            request_id="r1",
            trace_id="t1",
            question="查询商机",
            object_ids=["sales_bo"],
        )
    )

    assert len(spans) == 1
    assert spans[0].input_summary == {"question_len": 4, "object_ids": ["sales_bo"]}
