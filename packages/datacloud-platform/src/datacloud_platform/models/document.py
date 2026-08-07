"""Typed contracts for document-library orchestration and transport."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class DocumentProcessingStatus(StrEnum):
    """Allowed Chinese processing states stored in ``dc_status``."""

    PENDING_DISCOVERY = "待发现"
    DISCOVERING = "发现中"
    DISCOVERY_RETRY = "发现失败-待重试"
    DISCOVERY_MANUAL = "发现失败-待人工处理"
    PENDING_ORGANIZATION = "待整理"
    ORGANIZING = "整理中"
    ORGANIZATION_RETRY = "整理失败-待重试"
    ORGANIZATION_MANUAL = "整理失败-待人工处理"
    COMPLETED = "已完成"


class DocumentEnrichStatus(StrEnum):
    """Outcome of one document-enrichment attempt."""

    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


class _AliasedModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")


class QueryDocumentObjectsRequest(_AliasedModel):
    kb_resource_ids: tuple[str, ...] = Field(default=(), alias="kbResourceIds")
    statuses: tuple[DocumentProcessingStatus, ...] = ()
    object_codes: tuple[str, ...] = Field(default=(), alias="objectCodes")
    organization_interval_seconds: int | None = Field(
        default=None, alias="organizationIntervalSeconds", ge=0
    )
    relation_in_out_difference: int | None = Field(
        default=None, alias="relationInOutDifference"
    )
    page_index: int = Field(default=1, alias="pageIndex", ge=1)
    page_size: int = Field(default=20, alias="pageSize", ge=1, le=200)

    @field_validator("kb_resource_ids", "object_codes", mode="before")
    @classmethod
    def _normalize_strings(cls, value: object) -> tuple[str, ...]:
        if value is None:
            return ()
        if not isinstance(value, (list, tuple)):
            raise ValueError("must be an array")
        normalized = tuple(dict.fromkeys(str(item).strip() for item in value))
        if any(not item for item in normalized):
            raise ValueError("must not contain blank values")
        return normalized

    @field_validator("statuses", mode="before")
    @classmethod
    def _deduplicate_statuses(cls, value: object) -> object:
        if value is None:
            return ()
        if isinstance(value, (list, tuple)):
            return tuple(dict.fromkeys(value))
        return value


class QueryRelatedDocumentObjectsRequest(_AliasedModel):
    term_id: str = Field(alias="termId", min_length=1)
    page_index: int = Field(default=1, alias="pageIndex", ge=1)
    page_size: int = Field(default=20, alias="pageSize", ge=1, le=200)
    object_codes: list[str] = Field(default=[], alias="objectCodes")
    # direction: "outgoing", "incoming", or "both"(default).
    # depth: Recursion depth(1 = direct only).
    direction: str = Field(default="both", alias="direction")
    depth: int = Field(default=1, alias="depth")

    @field_validator("term_id")
    @classmethod
    def _strip_term_id(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("termId is required")
        return stripped


class DocumentObjectItem(_AliasedModel):
    term_id: str = Field(alias="termId")
    term_name: str = Field(alias="termName")
    term_code: str = Field(alias="termCode")
    term_type_code: str = Field(alias="termTypeCode")
    file_path: str = Field(alias="filePath")
    kb_resource_id: str = Field(alias="kbResourceId")
    status: DocumentProcessingStatus | None = None
    failure_reason: str | None = Field(default=None, alias="failureReason")
    failure_count: int = Field(default=0, alias="failureCount", ge=0)


class Pagination(_AliasedModel):
    page_index: int = Field(alias="pageIndex")
    page_size: int = Field(alias="pageSize")
    total: int = Field(ge=0)
    total_pages: int = Field(alias="totalPages", ge=0)


class DocumentObjectPage(_AliasedModel):
    items: tuple[DocumentObjectItem, ...] = ()
    pagination: Pagination


class RelatedTermInfo(_AliasedModel):
    term_id: str = Field(alias="termId")
    term_name: str = Field(alias="termName")
    term_code: str = Field(alias="termCode")
    term_type_code: str = Field(alias="termTypeCode")
    kb_resource_id: str = Field(alias="kbResourceId")
    file_path: str = Field(alias="filePath")


class RelatedDocumentRelationItem(_AliasedModel):
    relation_id: str = Field(alias="relationId")
    relation_name: str = Field(alias="relationName")
    relation_category: str = Field(alias="relationCategory")
    cardinality: str | None = None
    source: RelatedTermInfo
    target: RelatedTermInfo


class RelatedDocumentRelationPage(_AliasedModel):
    items: tuple[RelatedDocumentRelationItem, ...] = ()
    pagination: Pagination


@dataclass(frozen=True, slots=True)
class MetadataSearchPage:
    """One stable metadata-search page and its downstream pagination data."""

    data: tuple[dict[str, Any], ...]
    total: int
    page_num: int
    page_size: int


class GetDocumentContentRequest(_AliasedModel):
    term_id: str = Field(alias="termId", min_length=1)

    @field_validator("term_id")
    @classmethod
    def _strip_content_term_id(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("termId is required")
        return value


class DocumentContentResult(_AliasedModel):
    term_id: str = Field(alias="termId")
    kb_resource_id: str = Field(alias="kbResourceId")
    file_path: str = Field(alias="filePath")
    content: str


class SearchDocumentFragmentsRequest(_AliasedModel):
    """知识片段检索条件。

    ``exclude_term_ids`` 最终仅转换为 ``filePath`` 排除条件；不同知识库存在相同
    文件路径时会被同时排除，这是当前接口语义下的已知风险。
    """

    object_codes: tuple[str, ...] = Field(alias="objectCodes", min_length=1)
    exclude_term_ids: tuple[str, ...] = Field(default=(), alias="excludeTermIds")
    query: str = Field(min_length=1)
    top_k: int = Field(alias="topK", gt=0)

    @field_validator("object_codes", mode="before")
    @classmethod
    def _normalize_object_codes(cls, value: object) -> tuple[str, ...]:
        if not isinstance(value, (list, tuple)):
            raise ValueError("objectCodes must be an array")
        normalized = tuple(dict.fromkeys(str(item).strip() for item in value))
        if not normalized or any(not item for item in normalized):
            raise ValueError("objectCodes must not contain blank values")
        return normalized

    @field_validator("exclude_term_ids", mode="before")
    @classmethod
    def _normalize_exclude_term_ids(cls, value: object) -> tuple[str, ...]:
        if value is None:
            return ()
        if not isinstance(value, (list, tuple)):
            raise ValueError("excludeTermIds must be an array")
        normalized = tuple(dict.fromkeys(str(item).strip() for item in value))
        if any(not item for item in normalized):
            raise ValueError("excludeTermIds must not contain blank values")
        return normalized

    @field_validator("query")
    @classmethod
    def _strip_query(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("query is required")
        return value


class DocumentAsyncProcessingRequest(_AliasedModel):
    kb_resource_ids: tuple[str, ...] = Field(default=(), alias="kbResourceIds")
    object_codes: tuple[str, ...] = Field(alias="objectCodes", min_length=1)
    model_config_payload: dict[str, Any] | None = Field(
        default=None, alias="modelConfig"
    )

    @field_validator("kb_resource_ids", mode="before")
    @classmethod
    def _normalize_optional_kb_scope(cls, value: object) -> tuple[str, ...]:
        if value is None:
            return ()
        if not isinstance(value, (list, tuple)):
            raise ValueError("must be an array")
        normalized = tuple(dict.fromkeys(str(item).strip() for item in value))
        if any(not item for item in normalized):
            raise ValueError("must not contain blank values")
        return normalized

    @field_validator("object_codes", mode="before")
    @classmethod
    def _normalize_required_object_scope(cls, value: object) -> tuple[str, ...]:
        if not isinstance(value, (list, tuple)):
            raise ValueError("must be an array")
        normalized = tuple(dict.fromkeys(str(item).strip() for item in value))
        if not normalized or any(not item for item in normalized):
            raise ValueError("must not contain blank values")
        return normalized


class DocumentAsyncProcessingAccepted(_AliasedModel):
    session_id: str = Field(alias="sessionId")
    task_type: str = Field(alias="taskType")
    accepted: bool = True


class DocumentFragmentItem(_AliasedModel):
    term_id: str = Field(default="", alias="termId")
    term_code: str = Field(default="", alias="termCode")
    term_name: str = Field(default="", alias="termName")
    object_code: str = Field(default="", alias="objectCode")
    kb_code: str = Field(default="", alias="kbCode")
    kn_code: str = Field(default="", alias="knCode")
    file_path: str = Field(default="", alias="filePath")
    chunk_no: int | None = Field(default=None, alias="chunkNo")
    chunk_id: int | None = Field(default=None, alias="chunkId")
    chunk_text: str = Field(default="", alias="chunkText")
    score: float = 0.0
    image_path: str | None = Field(default=None, alias="imagePath")
    start_line: int | None = Field(default=None, alias="startLine")
    end_line: int | None = Field(default=None, alias="endLine")
    metadata: dict[str, Any] = Field(default_factory=dict)
    resource_id: int | None = Field(default=None, alias="resourceId")


class DocumentFragmentResult(_AliasedModel):
    items: tuple[DocumentFragmentItem, ...] = ()


class DocumentEnrichRelation(_AliasedModel):
    """One outgoing relation extracted from the generated document."""

    relation_name: str = Field(alias="relationName")
    target_object_type: str = Field(alias="targetObjectType")
    target_instance_name: str = Field(alias="targetInstanceName")
    target_term_id: str = Field(alias="targetTermId")


class DocumentEnrichResult(_AliasedModel):
    """Stable result returned by ``DocumentEnrichMixin.enrich``."""

    status: DocumentEnrichStatus
    exception_info: str | None = Field(default=None, alias="exceptionInfo")
    enriched_content: str = Field(default="", alias="enrichedContent")
    relations: tuple[DocumentEnrichRelation, ...] = ()


class DocumentEnrichObjectScope(_AliasedModel):
    """One ontology object included in document-enrichment retrieval."""

    object_code: str = Field(alias="objectCode", min_length=1)
    object_name: str = Field(alias="objectName", min_length=1)
    kb_resource_id: str = Field(default="", alias="kbResourceId")
    kb_id: str = Field(default="", alias="kbId")
    kb_directory: str = Field(default="", alias="kbDirectory")

    @field_validator("object_code", "object_name")
    @classmethod
    def _strip_scope_value(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value
