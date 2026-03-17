import pytest

from datacloud_data.events.bus import EventBus
from datacloud_data.events.events import ObjectViewBuilt


@pytest.mark.asyncio
async def test_bus_delivers_event_to_subscriber() -> None:
    bus = EventBus()
    received = []

    async def handler(event: ObjectViewBuilt) -> None:
        received.append(event)

    bus.subscribe(ObjectViewBuilt, handler)
    await bus.publish(
        ObjectViewBuilt(
            request_id="req1",
            trace_id="tr1",
            object_view={"viewId": "v1"},
            question="查商机",
        )
    )
    assert len(received) == 1
    assert received[0].request_id == "req1"


@pytest.mark.asyncio
async def test_bus_no_subscriber_does_not_raise() -> None:
    bus = EventBus()
    await bus.publish(
        ObjectViewBuilt(request_id="req1", trace_id="tr1", object_view={}, question="?")
    )
