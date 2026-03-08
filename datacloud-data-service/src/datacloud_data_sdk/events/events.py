"""事件类型定义。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class BaseEvent:
    request_id: str
    trace_id: str


@dataclass
class QueryRequestReceived(BaseEvent):
    question: str = ""
    view_ids: list[str] = field(default_factory=list)
    object_ids: list[str] = field(default_factory=list)
    tenant_id: str = ""


@dataclass
class ObjectViewBuilt(BaseEvent):
    object_view: dict = field(default_factory=dict)
    question: str = ""


@dataclass
class QueryPlanGenerated(BaseEvent):
    plan: dict = field(default_factory=dict)
    object_view: dict = field(default_factory=dict)
    question: str = ""


@dataclass
class PlanValidated(BaseEvent):
    valid: bool = False
    plan: dict = field(default_factory=dict)
    object_view: dict = field(default_factory=dict)
    question: str = ""
    errors: list[str] = field(default_factory=list)
    retry_count: int = 0


@dataclass
class PlanRetryRequested(BaseEvent):
    object_view: dict = field(default_factory=dict)
    question: str = ""
    validation_errors: list[str] = field(default_factory=list)
    retry_count: int = 0


@dataclass
class PlanValidationFailed(BaseEvent):
    errors: list[str] = field(default_factory=list)
    last_plan: dict = field(default_factory=dict)


@dataclass
class PlanRewritten(BaseEvent):
    rewritten_plan: dict = field(default_factory=dict)


@dataclass
class ExecutionTasksReady(BaseEvent):
    tasks: list[dict] = field(default_factory=list)
    aggregation: dict = field(default_factory=dict)


@dataclass
class StepsExecuted(BaseEvent):
    step_results: dict[str, str] = field(default_factory=dict)
    aggregation: dict = field(default_factory=dict)
    csv_table_names: dict[str, str] = field(default_factory=dict)


@dataclass
class AggregationCompleted(BaseEvent):
    records: list[dict] = field(default_factory=list)
    columns: list[dict] = field(default_factory=list)
    meta: dict = field(default_factory=dict)
