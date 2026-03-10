"""计划层数据模型。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ObjectViewSource:
    source_id: str
    source_type: str  # DB / API / KNOWLEDGE_BASE
    datasource_alias: str = ""


@dataclass
class ObjectViewField:
    name: str
    type: str
    description: str = ""
    aliases: list[str] = field(default_factory=list)
    term_set: str | None = None
    term_type: str | None = None
    dataset_id: int | None = None
    source_column: str | None = None  # DB 物理列名，SQL 中必须使用此列名


@dataclass
class ObjectViewFunctionParam:
    param_code: str
    param_name: str
    param_type: str
    direction: str  # IN / OUT
    required: bool = False
    mapping_path: str = ""
    default_value: Any = None
    term_set: str | None = None
    term_type: str | None = None
    dataset_id: int | None = None


@dataclass
class ObjectViewFunction:
    function_code: str
    description: str = ""
    params: list[ObjectViewFunctionParam] = field(default_factory=list)


@dataclass
class ObjectViewAction:
    """对象动作，供 LLM 选择 (objectId, actionCode)。"""

    action_code: str
    input_params: list[ObjectViewFunctionParam] = field(default_factory=list)
    output_params: list[ObjectViewFunctionParam] = field(default_factory=list)
    implementation_type: str = "API"  # API | SCRIPT
    function_code: str | None = None  # 仅 API 类有


@dataclass
class ObjectViewObject:
    object_id: str
    object_name: str
    source_id: str
    table: str = ""
    description: str = ""
    fields: list[ObjectViewField] = field(default_factory=list)
    functions: list[ObjectViewFunction] = field(default_factory=list)
    actions: list[ObjectViewAction] = field(default_factory=list)


@dataclass
class ObjectViewRelation:
    from_object: str
    to_object: str
    join_keys: list[dict[str, str]] = field(default_factory=list)
    cardinality: str = "ONE_TO_MANY"
    description: str = ""


@dataclass
class ObjectViewPayload:
    view_id: str
    view_name: str = ""
    description: str = ""
    sources: list[ObjectViewSource] = field(default_factory=list)
    objects: list[ObjectViewObject] = field(default_factory=list)
    relations: list[ObjectViewRelation] = field(default_factory=list)


@dataclass
class PlanStep:
    step_id: str
    type: str  # SQL / API / KB
    source_id: str = ""
    datasource_alias: str = ""
    sql_template: str = ""
    object_id: str = ""  # type=API 时必填，用于定位 action
    function_id: str = ""  # type=API 时表示 actionCode
    params: dict[str, Any] = field(default_factory=dict)
    output_ref: str = ""
    csv_table_name: str = ""
    bind_from_step: str = ""
    bind_key: str = ""
    query: str = ""
    tags: dict[str, Any] = field(default_factory=dict)


@dataclass
class PlanAggregation:
    strategy: str  # DIRECT / SQLITE_MEM
    final_step_id: str | None = None
    sqlite_sql: str = ""
    columns: list[dict[str, str]] = field(default_factory=list)
    csv_table_names: dict[str, str] = field(default_factory=dict)


@dataclass
class QueryExecutionPlan:
    question: str = ""
    can_answer: bool = True
    clarification: str = ""
    steps: list[PlanStep] = field(default_factory=list)
    aggregation: PlanAggregation | None = None
