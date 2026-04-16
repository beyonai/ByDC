"""链路追踪中间件。"""

from __future__ import annotations

import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from datacloud_data_sdk.events.bus import EventBus
from datacloud_data_sdk.events.events import (
    AggregationCompleted,
    BaseEvent,
    ExecutionTasksReady,
    ObjectViewBuilt,
    PlanRewritten,
    PlanValidated,
    PlanValidationFailed,
    QueryPlanGenerated,
    QueryRequestReceived,
    StepsExecuted,
)


def _event_to_input_summary(event: BaseEvent) -> dict:
    """从事件 payload 生成统计摘要，供 EventSpan.input_summary。"""
    if isinstance(event, QueryRequestReceived):
        return {
            "question_len": len(getattr(event, "question", "") or ""),
            "object_ids": getattr(event, "object_ids", []) or [],
        }
    if isinstance(event, ObjectViewBuilt):
        ov = getattr(event, "object_view", {}) or {}
        objs = ov.get("objects", []) if isinstance(ov, dict) else []
        return {"object_count": len(objs)}
    if isinstance(event, QueryPlanGenerated):
        plan = getattr(event, "plan", {}) or {}
        steps = plan.get("steps", []) if isinstance(plan, dict) else []
        return {
            "step_count": len(steps),
            "can_answer": plan.get("can_answer", True) if isinstance(plan, dict) else True,
        }
    if isinstance(event, PlanValidated):
        return {
            "valid": getattr(event, "valid", False),
            "error_count": len(getattr(event, "errors", []) or []),
        }
    if isinstance(event, PlanRewritten):
        rp = getattr(event, "rewritten_plan", {}) or {}
        steps = rp.get("steps", []) if isinstance(rp, dict) else []
        return {"step_count": len(steps)}
    if isinstance(event, ExecutionTasksReady):
        tasks = getattr(event, "tasks", []) or []
        return {"task_count": len(tasks)}
    if isinstance(event, StepsExecuted):
        sr = getattr(event, "step_results", {}) or {}
        return {"step_count": len(sr)}
    if isinstance(event, AggregationCompleted):
        records = getattr(event, "records", []) or []
        columns = getattr(event, "columns", []) or []
        return {"record_count": len(records), "column_count": len(columns)}
    if isinstance(event, PlanValidationFailed):
        errors = getattr(event, "errors", []) or []
        return {"error_count": len(errors)}
    return {}


SpanCallback = Callable[["EventSpan"], None]


@dataclass
class EventSpan:
    trace_id: str
    request_id: str
    span_id: str
    parent_span_id: str | None
    module: str
    event_in: str
    event_out: str | None
    started_at: float
    finished_at: float
    duration_ms: float
    status: str
    error_message: str | None = None
    input_summary: dict | None = None
    output_summary: dict | None = None


class TracingMiddleware:
    def __init__(self, bus: EventBus) -> None:
        self._bus = bus
        self._callbacks: list[SpanCallback] = []

    def on_span_complete(self, callback: SpanCallback) -> None:
        self._callbacks.append(callback)

    def subscribe(
        self,
        event_type: type,
        handler: Callable[[Any], Awaitable[None]],
        module_name: str,
    ) -> None:
        async def traced_handler(event: BaseEvent) -> None:
            span_id = str(uuid.uuid4())[:8]
            started_at = time.monotonic()
            status = "ok"
            error_msg = None
            try:
                await handler(event)
            except Exception as e:
                status = "error"
                error_msg = str(e)
                raise
            finally:
                finished_at = time.monotonic()
                span = EventSpan(
                    trace_id=getattr(event, "trace_id", ""),
                    request_id=getattr(event, "request_id", ""),
                    span_id=span_id,
                    parent_span_id=None,
                    module=module_name,
                    event_in=type(event).__name__,
                    event_out=None,
                    started_at=started_at,
                    finished_at=finished_at,
                    duration_ms=(finished_at - started_at) * 1000,
                    status=status,
                    error_message=error_msg,
                    input_summary=_event_to_input_summary(event),
                )
                for cb in self._callbacks:
                    cb(span)

        self._bus.subscribe(event_type, traced_handler)
