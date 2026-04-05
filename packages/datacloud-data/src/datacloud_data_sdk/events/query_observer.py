"""QueryObserver: 在 Object.query() 管线中发布事件用于可观测性。"""

from __future__ import annotations

import uuid
from typing import Any

from datacloud_data_sdk.events.bus import EventBus
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


class QueryObserver:
    """观察者，从查询管线接收通知并发布事件。非阻塞，异常不影响主流程。"""

    def __init__(self, bus: EventBus, trace_id: str | None = None) -> None:
        self._bus = bus
        self.trace_id = trace_id or str(uuid.uuid4())[:8]

    async def on_query_start(self, request_id: str, question: str, object_ids: list[str]) -> None:
        try:
            await self._bus.publish(
                QueryRequestReceived(
                    request_id=request_id,
                    trace_id=self.trace_id,
                    question=question,
                    object_ids=object_ids,
                )
            )
        except Exception:
            logger.debug("observer/reporter callback failed", exc_info=True)

    async def on_view_built(self, request_id: str, payload: dict) -> None:
        try:
            await self._bus.publish(
                ObjectViewBuilt(
                    request_id=request_id,
                    trace_id=self.trace_id,
                    object_view=payload,
                    question="",
                )
            )
        except Exception:
            logger.debug("observer/reporter callback failed", exc_info=True)

    async def on_plan_generated(self, request_id: str, plan: dict) -> None:
        try:
            await self._bus.publish(
                QueryPlanGenerated(
                    request_id=request_id,
                    trace_id=self.trace_id,
                    plan=plan,
                )
            )
        except Exception:
            logger.debug("observer/reporter callback failed", exc_info=True)

    async def on_steps_executed(self, request_id: str, step_results: dict) -> None:
        try:
            await self._bus.publish(
                StepsExecuted(
                    request_id=request_id,
                    trace_id=self.trace_id,
                    step_results=step_results,
                )
            )
        except Exception:
            logger.debug("observer/reporter callback failed", exc_info=True)

    async def on_aggregation_completed(self, request_id: str, records: list, columns: list) -> None:
        try:
            await self._bus.publish(
                AggregationCompleted(
                    request_id=request_id,
                    trace_id=self.trace_id,
                    records=records,
                    columns=columns,
                )
            )
        except Exception:
            logger.debug("observer/reporter callback failed", exc_info=True)

    async def on_plan_validated(
        self,
        request_id: str,
        valid: bool,
        plan: dict,
        object_view: dict,
        question: str,
        errors: list[str],
        retry_count: int,
    ) -> None:
        try:
            await self._bus.publish(
                PlanValidated(
                    request_id=request_id,
                    trace_id=self.trace_id,
                    valid=valid,
                    plan=plan,
                    object_view=object_view,
                    question=question,
                    errors=errors,
                    retry_count=retry_count,
                )
            )
        except Exception:
            logger.debug("observer/reporter callback failed", exc_info=True)

    async def on_plan_rewritten(self, request_id: str, rewritten_plan: dict) -> None:
        try:
            await self._bus.publish(
                PlanRewritten(
                    request_id=request_id,
                    trace_id=self.trace_id,
                    rewritten_plan=rewritten_plan,
                )
            )
        except Exception:
            logger.debug("observer/reporter callback failed", exc_info=True)

    async def on_execution_tasks_ready(
        self, request_id: str, tasks: list[dict], aggregation: dict
    ) -> None:
        try:
            await self._bus.publish(
                ExecutionTasksReady(
                    request_id=request_id,
                    trace_id=self.trace_id,
                    tasks=tasks,
                    aggregation=aggregation,
                )
            )
        except Exception:
            logger.debug("observer/reporter callback failed", exc_info=True)

    async def on_plan_validation_failed(
        self, request_id: str, errors: list[str], last_plan: dict
    ) -> None:
        try:
            await self._bus.publish(
                PlanValidationFailed(
                    request_id=request_id,
                    trace_id=self.trace_id,
                    errors=errors,
                    last_plan=last_plan,
                )
            )
        except Exception:
            logger.debug("observer/reporter callback failed", exc_info=True)
