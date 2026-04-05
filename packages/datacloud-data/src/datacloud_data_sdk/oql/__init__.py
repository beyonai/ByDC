"""
OQL 模块

提供 OQL 结构化翻译层，将 OQL JSON 100% 转化为可执行的 SQL / API 调用。
"""

from datacloud_data_sdk.oql.router import OqlRouter
from datacloud_data_sdk.oql.adapter import OqlAdapter
from datacloud_data_sdk.oql.cross_source_executor import CrossSourceExecutor, classify_include_links
from datacloud_data_sdk.oql.pipeline_executor import PipelineExecutor, RefResolver
from datacloud_data_sdk.oql.memory_merger import MemoryMerger
from datacloud_data_sdk.oql.models import (
    OQLError, OQLErrorCode, OQLRequest, OQLResponse, OQLPagination,
    OQLField, OQLObject, OQLRelation, OQLCondition, OQLIncludeLink,
    OQLMetric, OQLPipelineRequest, PipelineStep
)

__all__ = [
    "OqlRouter",
    "OqlAdapter",
    "CrossSourceExecutor",
    "PipelineExecutor",
    "RefResolver",
    "MemoryMerger",
    "classify_include_links",
    "OQLError",
    "OQLErrorCode",
    "OQLRequest",
    "OQLResponse",
    "OQLPagination",
    "OQLField",
    "OQLObject",
    "OQLRelation",
    "OQLCondition",
    "OQLIncludeLink",
    "OQLMetric",
    "OQLPipelineRequest",
    "PipelineStep",
]

