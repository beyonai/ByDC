"""Document-domain orchestration across ontology, term, and document-library backends."""

from __future__ import annotations

import inspect
from collections.abc import Mapping
from dataclasses import asdict, is_dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from datacloud_platform.models.document import (
    DocumentContentResult,
    DocumentFragmentItem,
    DocumentFragmentResult,
    DocumentObjectItem,
    DocumentObjectPage,
    DocumentProcessingStatus,
    MetadataSearchPage,
    Pagination,
    QueryDocumentObjectsRequest,
    QueryRelatedDocumentObjectsRequest,
    RelatedDocumentRelationItem,
    RelatedDocumentRelationPage,
    RelatedTermInfo,
    SearchDocumentFragmentsRequest,
)


class _DocumentPlatform(Protocol):
    def search_terms(self, base_id: str, **kwargs: Any) -> Any: ...
    def query_term_relations(self, base_id: str, **kwargs: Any) -> Any: ...
    def get_object_detail(
        self, base_id: str, object_code: str
    ) -> dict[str, Any] | None: ...
    async def search_knowledge_item_metadata(
        self, base_id: str, *, payload: dict[str, Any]
    ) -> MetadataSearchPage: ...
    async def read_knowledge_document(
        self, base_id: str, *, resource_id: str, file_path: str
    ) -> str: ...
    async def search_knowledge_items(
        self, base_id: str, *, payload: dict[str, Any]
    ) -> tuple[dict[str, Any], ...]: ...


class DocumentMixin:
    """Platform-level document query, relation, content, and chunk orchestration."""

    async def query_document_objects(
        self: _DocumentPlatform,
        base_id: str,
        *,
        request: QueryDocumentObjectsRequest,
    ) -> DocumentObjectPage:
        candidate_file_paths: tuple[str, ...] = ()
        if request.relation_in_out_difference is not None:
            term_ids = await resolve_term_ids_by_relation_in_out_difference(
                platform=self,
                base_id=base_id,
                difference=request.relation_in_out_difference,
            )
            candidate_file_paths = await resolve_file_paths_by_term_ids(
                platform=self,
                base_id=base_id,
                term_ids=term_ids,
            )

        payload = build_metadata_search_payload(
            request=request,
            candidate_file_paths=candidate_file_paths,
            now=datetime.now(UTC),
        )
        metadata_page = await self.search_knowledge_item_metadata(
            base_id, payload=payload
        )
        paths_by_kb_id: dict[str, list[str]] = {}
        for row in metadata_page.data:
            kb_id = str(row.get("knCode") or "")
            file_path = str(row.get("filePath") or "")
            if kb_id and file_path:
                paths_by_kb_id.setdefault(kb_id, []).append(file_path)
        if not paths_by_kb_id:
            return _build_page(
                [], metadata_page.total, metadata_page.page_num, metadata_page.page_size
            )
        rows = await resolve_document_objects_by_file_paths(
            platform=self,
            base_id=base_id,
            kb_resource_ids=request.kb_resource_ids,
            file_paths_by_kb_id={
                kb_id: tuple(dict.fromkeys(file_paths))
                for kb_id, file_paths in paths_by_kb_id.items()
            },
        )
        if request.object_codes:
            allowed_codes = set(request.object_codes)
            rows = [
                row
                for row in rows
                if str(row.get("term_type_code") or row.get("termTypeCode") or "")
                in allowed_codes
            ]
        return _build_page(
            rows,
            metadata_page.total,
            metadata_page.page_num,
            metadata_page.page_size,
        )

    async def query_related_document_objects(
        self: _DocumentPlatform,
        base_id: str,
        *,
        request: QueryRelatedDocumentObjectsRequest,
    ) -> RelatedDocumentRelationPage:
        raw = self.query_term_relations(
            base_id,
            term_id=request.term_id,
            direction="both",
            depth=1,
            page_index=request.page_index,
            page_size=request.page_size,
        )
        relation_result = await raw if inspect.isawaitable(raw) else raw
        relation_rows = relation_result.get("data") or []
        term_ids = {
            str(row.get(key) or "")
            for row in relation_rows
            if isinstance(row, dict)
            for key in (
                "source_term_id",
                "sourceTermId",
                "target_term_id",
                "targetTermId",
            )
            if row.get(key)
        }
        details: dict[str, RelatedTermInfo] = {}
        if term_ids:
            term_result: Any = self.search_terms(
                base_id,
                term_ids=sorted(term_ids),
                top_k=len(term_ids),
                offset=0,
            )
            raw_items = (
                term_result.get("items", [])
                if isinstance(term_result, Mapping)
                else getattr(term_result, "items", [])
            )
            for detail in raw_items:
                info = _to_related_term_info(detail, fallback_term_id="")
                details[info.term_id] = info
            missing_term_ids = term_ids - details.keys()
            if missing_term_ids:
                missing = ", ".join(sorted(missing_term_ids))
                raise KeyError(f"terms not found: {missing}")

        items = tuple(
            _to_related_relation(row, details)
            for row in relation_rows
            if isinstance(row, dict)
        )
        total = int(relation_result.get("totalCount") or len(items))
        total_pages = int(
            relation_result.get("totalPages")
            or ((total + request.page_size - 1) // request.page_size if total else 0)
        )
        return RelatedDocumentRelationPage(
            items=items,
            pagination=Pagination(
                pageIndex=int(relation_result.get("pageIndex") or request.page_index),
                pageSize=int(relation_result.get("pageSize") or request.page_size),
                total=total,
                totalPages=total_pages,
            ),
        )

    async def get_document_content_by_term_id(
        self: _DocumentPlatform, base_id: str, *, term_id: str
    ) -> DocumentContentResult:
        result = self.search_terms(base_id, term_ids=[term_id], top_k=1, offset=0)
        rows = _term_result_items(result)
        if not rows:
            raise KeyError(f"term not found: {term_id}")
        metadata = _term_metadata(rows[0])
        kb_resource_id = str(metadata.get("kb_resource_id") or "")
        file_path = str(metadata.get("kb_file_path") or "")
        if not kb_resource_id or not file_path:
            raise ValueError(
                f"term knowledge location is incomplete: term_id={term_id}"
            )
        content = await self.read_knowledge_document(
            base_id, resource_id=kb_resource_id, file_path=file_path
        )
        return DocumentContentResult(
            termId=term_id,
            kbResourceId=kb_resource_id,
            filePath=file_path,
            content=content,
        )

    async def search_knowledge_fragments(
        self: _DocumentPlatform,
        base_id: str,
        *,
        request: SearchDocumentFragmentsRequest,
    ) -> DocumentFragmentResult:
        resource_ids: list[int] = []
        directories: list[str] = []
        for object_code in request.object_codes:
            detail = self.get_object_detail(base_id, object_code)
            if detail is None:
                raise KeyError(f"object not found: {object_code}")
            ext = detail.get("ext_property") or detail.get("extProperty") or {}
            if not isinstance(ext, Mapping):
                continue
            raw_resource_id = str(
                ext.get("kb_resource_id") or ext.get("kbResourceId") or ""
            ).strip()
            if not raw_resource_id:
                continue
            try:
                resource_id = int(raw_resource_id)
            except ValueError as exc:
                raise ValueError(
                    "object kb_resource_id must be an integer: "
                    f"object_code={object_code}"
                ) from exc
            if resource_id not in resource_ids:
                resource_ids.append(resource_id)
            directory = _normalize_directory(
                str(ext.get("kb_directory") or ext.get("kbDirectory") or "")
            )
            if directory and directory not in directories:
                directories.append(directory)
        if not resource_ids:
            raise ValueError("no knowledge-base binding found for objectCodes")

        payload: dict[str, Any] = {
            "resourceIdList": resource_ids,
            "query": request.query,
            "topK": request.top_k,
            "searchMode": "mixedRecall",
        }
        if directories:
            payload["where"] = {
                "or": [
                    {"prefix": {"fieldName": "filePath", "value": directory}}
                    for directory in directories
                ]
            }
        rows = await self.search_knowledge_items(base_id, payload=payload)
        return DocumentFragmentResult(
            items=tuple(DocumentFragmentItem.model_validate(row) for row in rows)
        )


def _normalize_directory(value: str) -> str:
    value = value.strip().replace("\\", "/")
    if not value:
        return ""
    return "/" + value.strip("/") + "/"


def build_processing_labels(
    *,
    initial_status: DocumentProcessingStatus,
    labels: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return business labels with validated document-processing defaults."""
    result = dict(labels or {})
    supplied_status = result.get("dc_status", initial_status)
    result["dc_status"] = DocumentProcessingStatus(str(supplied_status)).value
    result.setdefault("dc_failure_reason", None)
    result.setdefault("dc_failure_count", 0)
    result.setdefault("dc_last_organized_at", None)
    failure_count = result["dc_failure_count"]
    if isinstance(failure_count, bool) or not isinstance(failure_count, int):
        raise ValueError("dc_failure_count must be an integer")
    if failure_count < 0:
        raise ValueError("dc_failure_count must be greater than or equal to 0")
    return result


def build_metadata_search_payload(
    *,
    request: QueryDocumentObjectsRequest,
    candidate_file_paths: tuple[str, ...],
    now: datetime,
) -> dict[str, Any]:
    """Build ``(filePath IN paths OR dc_status IN statuses) AND updateAt``."""
    or_conditions: list[dict[str, Any]] = []
    if candidate_file_paths:
        or_conditions.append(
            {
                "in": {
                    "fieldName": "filePath",
                    "value": list(candidate_file_paths),
                }
            }
        )
    if request.statuses:
        or_conditions.append(
            {
                "in": {
                    "fieldName": "dc_status",
                    "value": [status.value for status in request.statuses],
                }
            }
        )
    and_conditions: list[dict[str, Any]] = []
    if or_conditions:
        and_conditions.append({"or": or_conditions})
    if request.organization_interval_seconds is not None:
        cutoff = now - timedelta(seconds=request.organization_interval_seconds)
        and_conditions.append(
            {"lt": {"fieldName": "updateAt", "value": cutoff.isoformat()}}
        )
    return {
        "knCodeList": list(request.kb_resource_ids),
        "where": {"and": and_conditions},
        "pageNum": request.page_index,
        "pageSize": request.page_size,
    }


async def _call_platform_todo(platform: Any, method_name: str, **kwargs: Any) -> Any:
    method = getattr(platform, method_name, None)
    if not callable(method):
        raise NotImplementedError(f"TODO: platform.{method_name} is not implemented")
    result = method(**kwargs)
    return await result if inspect.isawaitable(result) else result


async def resolve_term_ids_by_relation_in_out_difference(
    *, platform: Any, base_id: str, difference: int
) -> tuple[str, ...]:
    values = await _call_platform_todo(
        platform,
        "resolve_term_ids_by_relation_in_out_difference",
        base_id=base_id,
        difference=difference,
    )
    return tuple(dict.fromkeys(str(value) for value in values if value))


async def resolve_file_paths_by_term_ids(
    *, platform: Any, base_id: str, term_ids: tuple[str, ...]
) -> tuple[str, ...]:
    if not term_ids:
        return ()
    result = platform.search_terms(
        base_id,
        term_ids=list(term_ids),
        top_k=min(len(term_ids), 200),
        offset=0,
    )
    rows = _term_result_items(result)
    paths = (_term_metadata(row).get("kb_file_path") for row in rows)
    return tuple(dict.fromkeys(str(path) for path in paths if path))


async def resolve_document_objects_by_file_paths(
    *,
    platform: Any,
    base_id: str,
    kb_resource_ids: tuple[str, ...],
    file_paths_by_kb_id: Mapping[str, tuple[str, ...]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    allowed_kb_resource_ids = set(kb_resource_ids)
    for kb_id, raw_file_paths in file_paths_by_kb_id.items():
        file_paths = tuple(dict.fromkeys(path for path in raw_file_paths if path))
        if not kb_id or not file_paths:
            continue
        result = platform.search_terms(
            base_id,
            label_filters=[
                {"field_code": "kb_file_path", "filter_value": file_path}
                for file_path in file_paths
            ],
            label_condition="or",
            ext_attrs={"kb_id": kb_id},
            top_k=200,
            offset=0,
        )
        allowed_paths = set(file_paths)
        rows.extend(
            row
            for row in _term_result_items(result)
            if _term_metadata(row).get("kb_id") == kb_id
            and _term_metadata(row).get("kb_resource_id") in allowed_kb_resource_ids
            and _term_metadata(row).get("kb_file_path") in allowed_paths
        )
    return rows


def _term_result_items(result: Any) -> list[dict[str, Any]]:
    raw_items = (
        result.get("items", [])
        if isinstance(result, Mapping)
        else getattr(result, "items", [])
    )
    items: list[dict[str, Any]] = []
    for item in raw_items:
        if isinstance(item, Mapping):
            items.append(dict(item))
        elif hasattr(item, "model_dump"):
            items.append(item.model_dump())
        elif is_dataclass(item) and not isinstance(item, type):
            items.append(asdict(item))
    return items


def _term_metadata(row: Mapping[str, Any]) -> dict[str, Any]:
    tags = row.get("term_tags") or row.get("termTags") or row.get("labels") or {}
    ext_attrs = row.get("ext_attrs") or row.get("extAttrs") or {}
    return {
        **(ext_attrs if isinstance(ext_attrs, Mapping) else {}),
        **(tags if isinstance(tags, Mapping) else {}),
    }


def _to_related_relation(
    row: dict[str, Any], details: dict[str, RelatedTermInfo]
) -> RelatedDocumentRelationItem:
    source_id = str(row.get("source_term_id") or row.get("sourceTermId") or "")
    target_id = str(row.get("target_term_id") or row.get("targetTermId") or "")
    return RelatedDocumentRelationItem(
        relationId=str(row.get("relation_id") or row.get("relationId") or ""),
        relationName=str(row.get("relation_name") or row.get("relationName") or ""),
        relationCategory=str(
            row.get("relation_category") or row.get("relationCategory") or ""
        ),
        cardinality=row.get("cardinality"),
        source=details[source_id],
        target=details[target_id],
    )


def _to_related_term_info(detail: Any, *, fallback_term_id: str) -> RelatedTermInfo:
    if isinstance(detail, Mapping):
        raw = dict(detail)
    elif hasattr(detail, "model_dump"):
        raw = detail.model_dump()
    elif is_dataclass(detail) and not isinstance(detail, type):
        raw = asdict(detail)
    else:
        raise TypeError("term detail must be a mapping, dataclass, or Pydantic model")
    tags = raw.get("term_tags") or raw.get("termTags") or raw.get("labels") or {}
    ext_attrs = raw.get("ext_attrs") or raw.get("extAttrs") or {}
    metadata = {
        **(ext_attrs if isinstance(ext_attrs, dict) else {}),
        **(tags if isinstance(tags, dict) else {}),
    }
    return RelatedTermInfo(
        termId=str(raw.get("term_id") or raw.get("termId") or fallback_term_id),
        termName=str(raw.get("term_name") or raw.get("termName") or ""),
        termCode=str(raw.get("term_code") or raw.get("termCode") or ""),
        termTypeCode=str(
            raw.get("term_type_code")
            or raw.get("termTypeCode")
            or raw.get("term_type")
            or raw.get("termType")
            or ""
        ),
        kbResourceId=str(
            metadata.get("kb_resource_id") or metadata.get("kbResourceId") or ""
        ),
        filePath=str(
            metadata.get("kb_file_path")
            or metadata.get("file_path")
            or metadata.get("filePath")
            or ""
        ),
    )


def _build_page(
    rows: list[dict[str, Any]], total: int, page_index: int, page_size: int
) -> DocumentObjectPage:
    items = tuple(_to_item(row) for row in rows)
    return DocumentObjectPage(
        items=items,
        pagination=Pagination(
            pageIndex=page_index,
            pageSize=page_size,
            total=total,
            totalPages=(total + page_size - 1) // page_size if total else 0,
        ),
    )


def _to_item(row: dict[str, Any]) -> DocumentObjectItem:
    tags = row.get("term_tags") or row.get("termTags") or {}
    ext_attrs = row.get("ext_attrs") or row.get("extAttrs") or {}
    metadata = {**ext_attrs, **tags}
    return DocumentObjectItem(
        termId=str(row.get("term_id") or row.get("termId") or ""),
        termName=str(row.get("term_name") or row.get("termName") or ""),
        termCode=str(row.get("term_code") or row.get("termCode") or ""),
        termTypeCode=str(row.get("term_type_code") or row.get("termTypeCode") or ""),
        filePath=str(
            metadata.get("kb_file_path")
            or metadata.get("file_path")
            or metadata.get("filePath")
            or ""
        ),
        kbResourceId=str(
            metadata.get("kb_resource_id") or metadata.get("kbResourceId") or ""
        ),
        status=DocumentProcessingStatus(str(metadata.get("dc_status") or "")),
        failureReason=metadata.get("dc_failure_reason"),
        failureCount=metadata.get("dc_failure_count", 0),
    )
