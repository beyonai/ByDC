"""
OQL 数据模型

定义 OQL 请求/响应的数据结构和错误模型。
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Optional
from enum import Enum
import sys

if sys.version_info >= (3, 8):
    from typing import Literal
else:
    from typing_extensions import Literal


class OQLErrorCode(str, Enum):
    """OQL 错误代码"""
    # 对象/字段不存在
    OQL_ERR_UNKNOWN_OBJECT = "OQL_ERR_UNKNOWN_OBJECT"
    OQL_ERR_UNKNOWN_FIELD = "OQL_ERR_UNKNOWN_FIELD"
    OQL_ERR_UNKNOWN_RELATION = "OQL_ERR_UNKNOWN_RELATION"

    # 不支持的操作
    OQL_ERR_UNSUPPORTED_OPERATION = "OQL_ERR_UNSUPPORTED_OPERATION"
    OQL_ERR_UNSUPPORTED_SOURCE_TYPE = "OQL_ERR_UNSUPPORTED_SOURCE_TYPE"

    # 操作符/语法错误
    OQL_ERR_INVALID_OPERATOR = "OQL_ERR_INVALID_OPERATOR"
    OQL_ERR_INVALID_REF = "OQL_ERR_INVALID_REF"
    OQL_ERR_INVALID_SCHEMA = "OQL_ERR_INVALID_SCHEMA"

    # 执行错误
    OQL_ERR_EXECUTION_FAILED = "OQL_ERR_EXECUTION_FAILED"
    OQL_ERR_STEP_LIMIT_EXCEEDED = "OQL_ERR_STEP_LIMIT_EXCEEDED"

    # 术语解析错误
    OQL_ERR_TERM_RESOLUTION_FAILED = "OQL_ERR_TERM_RESOLUTION_FAILED"


class OQLError(Exception):
    """OQL 执行异常"""

    def __init__(
        self,
        code: OQLErrorCode | str,
        message: str,
        details: Optional[dict[str, Any]] = None
    ):
        self.code = code
        self.message = message
        self.details = details or {}
        super().__init__(f"[{code}] {message}")


@dataclass
class OQLField:
    """OQL 字段定义"""
    field_code: str
    field_name: str
    data_type: str


@dataclass
class OQLObject:
    """OQL 对象定义"""
    object_code: str
    object_name: str
    source_type: Literal["DB", "API"]
    datasource_alias: Optional[str] = None
    table_name: Optional[str] = None
    fields: list[OQLField] = field(default_factory=list)


@dataclass
class OQLRelation:
    """OQL 关系定义"""
    relation_code: str
    source_object: str
    target_object: str
    join_keys: dict[str, str]  # {source_key: target_key}


@dataclass
class OQLCondition:
    """OQL WHERE 条件"""
    field: str
    operator: str  # in, nin, eq, neq, gt, gte, lt, lte, like, between, relativeDate
    value: Any
    logic: Optional[Literal["and", "or"]] = None


@dataclass
class OQLIncludeLink:
    """OQL include_links 中的单条关系"""
    relation_code: str
    fields: list[str] = field(default_factory=list)


@dataclass
class OQLMetric:
    """OQL 聚合指标"""
    field: str
    aggregation: str  # sum, avg, count, max, min, count_distinct


@dataclass
class OQLRequest:
    """OQL 查询请求"""
    object: str
    fields: list[str]
    where: Optional[list[OQLCondition]] = None
    include_links: Optional[list[OQLIncludeLink]] = None
    metrics: Optional[list[OQLMetric]] = None
    group_by: Optional[list[str]] = None
    having: Optional[list[OQLCondition]] = None
    order_by: Optional[list[dict[str, str]]] = None  # [{field: str, direction: "asc"|"desc"}]
    limit: int = 100
    offset: int = 0
    execution_strategy: Optional[Literal["auto", "single_source", "cross_source", "pipeline"]] = "auto"


@dataclass
class OQLPagination:
    """分页信息"""
    limit: int
    offset: int
    has_next: bool


@dataclass
class OQLResponse:
    """OQL 查询响应"""
    code: int  # 0 = success, non-zero = error
    message: str
    data: Optional[list[dict[str, Any]]] = None
    pagination: Optional[OQLPagination] = None
    error_code: Optional[str] = None
    error_details: Optional[dict[str, Any]] = None


@dataclass
class PipelineStep:
    """Pipeline 执行步骤"""
    step_id: str
    object: str
    fields: list[str]
    where: Optional[list[OQLCondition]] = None
    include_links: Optional[list[OQLIncludeLink]] = None
    metrics: Optional[list[OQLMetric]] = None
    group_by: Optional[list[str]] = None
    limit: int = 100
    offset: int = 0


@dataclass
class OQLPipelineRequest:
    """OQL Pipeline 请求"""
    steps: list[PipelineStep]
    max_steps: int = 10
