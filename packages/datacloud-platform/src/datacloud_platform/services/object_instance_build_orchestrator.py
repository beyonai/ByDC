"""Platform orchestration for object instance build tasks."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict, dataclass, field, is_dataclass
from time import perf_counter
from typing import TYPE_CHECKING, Any, Protocol

from datacloud_knowledge.object_instance_build import (
    ObjectInstanceBuildRequest,
    ObjectInstanceBuildResult,
    ObjectInstanceFragment,
    build_object_instance as knowledge_build_object_instance,
)
from datacloud_platform import platform_file_storage
from datacloud_platform.config import get_settings
from datacloud_platform.constants import DEFAULT_BASE_ID
from datacloud_platform.services.kb_document_reader import (
    KbDocumentReadError,
    KbDocumentReader,
    build_default_kb_document_reader,
)
from datacloud_platform.services.object_action import invoke_object_write_action
from datacloud_platform.services.object_instance_build_task_service import (
    ObjectInstanceBuildRunRequest,
)

if TYPE_CHECKING:
    from datacloud_platform.platform import DatacloudPlatform

logger = logging.getLogger(__name__)

DEFAULT_ENUM_LIBRARY_ID = "default_term"
ENUM_PAGE_SIZE = 200
TERM_RELATION_PAGE_SIZE = 200
PRODUCT_OBJECT_CODE = "product"
PRODUCT_CODE_FIELD = "product_code"
PRODUCT_RELATION_PREFERRED_NAMES = (
    "product_code",
    "belongs-to-product",
    "belongs_to_product",
    "\u6240\u5c5e\u4ea7\u54c1",
)
PRODUCT_RELATION_FALLBACK_NAMES = (
    "product",
    "\u5f52\u5c5e\u4ea7\u54c1",
)
PROTECTED_LABEL_FIELDS = frozenset({"relations"})
RELATED_DOCS_BOUNDARY = "--- related_docs ---"
RELATED_DOCS_RELATION = "part-of"
_RELATED_DOCS_BLOCK_PATTERN = re.compile(
    rf"\n?{re.escape(RELATED_DOCS_BOUNDARY)}\n(?P<body>.*?)\n{re.escape(RELATED_DOCS_BOUNDARY)}\n?",
    re.DOTALL,
)
_INSTANCE_TEMPLATE_HEADING_PATTERN = re.compile(
    r"(?m)^##\s*5[.．、]?\s*实例卡片模板\s*$"
)
_NEXT_NUMBERED_HEADING_PATTERN = re.compile(r"(?m)^##\s+\d+[.．、]?\s+")
_MARKDOWN_FENCE_PATTERN = re.compile(
    r"```(?:markdown|md)?\s*\n(?P<body>.*?)\n```",
    re.DOTALL | re.IGNORECASE,
)


class ObjectInstanceBuildKnowledgeClient(Protocol):
    """Knowledge SDK facade used by the Platform orchestrator."""

    async def build_object_instance(
        self,
        request: ObjectInstanceBuildRequest,
    ) -> ObjectInstanceBuildResult: ...


class DefaultObjectInstanceBuildKnowledgeClient:
    """Default Knowledge SDK client."""

    async def build_object_instance(
        self,
        request: ObjectInstanceBuildRequest,
    ) -> ObjectInstanceBuildResult:
        return await knowledge_build_object_instance(request)


@dataclass(frozen=True)
class _FragmentGroup:
    instance_id: str
    origin_instance_id: str | None
    fragments: list[dict[str, Any]]


@dataclass(frozen=True)
class _ProtectedObjectMetadata:
    product_code: str = ""
    relations: dict[str, dict[str, list[str]]] = field(default_factory=dict)

    def has_values(self) -> bool:
        return bool(self.product_code or self.relations)

    def relation_count(self) -> int:
        return sum(
            len(target_names)
            for targets_by_type in self.relations.values()
            for target_names in targets_by_type.values()
        )


class ObjectInstanceBuildOrchestrator:
    """Coordinate fragment retrieval, Knowledge build, and datacloud-data write."""

    def __init__(
        self,
        *,
        platform: DatacloudPlatform,
        knowledge_client: ObjectInstanceBuildKnowledgeClient | None = None,
        base_id: str = DEFAULT_BASE_ID,
    ) -> None:
        self._platform = platform
        self._knowledge_client = (
            knowledge_client or DefaultObjectInstanceBuildKnowledgeClient()
        )
        self._base_id = base_id

    async def run(self, request: ObjectInstanceBuildRunRequest) -> None:
        """Run one object instance build request to a terminal log status."""
        request_id = request.request_id
        _log_task_stage(
            task_id=request_id,
            stage="run_start",
            status="started",
            input_data={
                "instance_ids": request.instance_ids,
                "batch_size": request.batch_size,
                "operator": request.operator,
            },
        )

        errors: list[dict[str, Any]] = []
        success_count = 0
        failed_count = 0
        stage_started = perf_counter()
        groups = self._load_fragment_groups(
            instance_ids=request.instance_ids,
            batch_size=request.batch_size,
        )
        _log_task_stage(
            task_id=request_id,
            stage="load_fragment_groups",
            status="succeeded",
            input_data={
                "instance_ids": request.instance_ids,
                "batch_size": request.batch_size,
                "status": 0,
            },
            output_data={
                "group_count": len(groups),
                "fragment_count": sum(len(group.fragments) for group in groups),
                "group_instance_ids": [group.instance_id for group in groups],
            },
            elapsed_ms=_elapsed_ms(stage_started),
        )

        for group in groups:
            group_started = perf_counter()
            _log_task_stage(
                task_id=request_id,
                stage="process_group",
                status="started",
                instance_id=group.instance_id,
                input_data={
                    "origin_instance_id": group.origin_instance_id or "",
                    "fragment_ids": _fragment_ids(group.fragments),
                },
            )
            try:
                await self._process_group(
                    group,
                    operator=request.operator,
                    task_id=request_id,
                )
            except Exception as exc:
                failed_count += 1
                errors.append(
                    {
                        "instance_id": group.instance_id,
                        "origin_instance_id": group.origin_instance_id or "",
                        "fragment_ids": _fragment_ids(group.fragments),
                        "stage": "process_group",
                        "message": str(exc),
                    }
                )
                logger.warning(
                    "object instance build group failed: instance_id=%s",
                    group.instance_id,
                    exc_info=True,
                )
                _log_task_stage(
                    task_id=request_id,
                    stage="process_group",
                    status="failed",
                    instance_id=group.instance_id,
                    message=str(exc),
                    output_data={
                        "success_count": success_count,
                        "failed_count": failed_count,
                    },
                    elapsed_ms=_elapsed_ms(group_started),
                )
            else:
                success_count += 1
                _log_task_stage(
                    task_id=request_id,
                    stage="process_group",
                    status="succeeded",
                    instance_id=group.instance_id,
                    output_data={
                        "success_count": success_count,
                        "failed_count": failed_count,
                    },
                    elapsed_ms=_elapsed_ms(group_started),
                )

        final_status = _final_status(
            success_count=success_count, failed_count=failed_count
        )
        _log_task_stage(
            task_id=request_id,
            stage="run_finish",
            status=final_status,
            output_data={
                "total_count": len(groups),
                "success_count": success_count,
                "failed_count": failed_count,
                "error_count": len(errors),
                "errors": errors,
            },
        )

    def _load_fragment_groups(
        self,
        *,
        instance_ids: list[str],
        batch_size: int,
    ) -> list[_FragmentGroup]:
        rows: list[dict[str, Any]] = []
        page_index = 1
        while True:
            page = (
                self._platform.list_fragments_by_instance_ids(
                    self._base_id,
                    instance_ids=instance_ids,
                    page_index=page_index,
                    page_size=batch_size,
                    status=0,
                )
                if instance_ids
                else self._platform.list_fragments_for_build(
                    self._base_id,
                    instance_ids=instance_ids,
                    page_index=page_index,
                    page_size=batch_size,
                    status=0,
                )
            )
            data = _extract_items(page)
            rows.extend(data)
            total = int(page.get("total") or page.get("totalCount") or len(rows))
            if page_index * batch_size >= total or not data:
                break
            page_index += 1
        return _group_fragments(rows)

    async def _process_group(
        self,
        group: _FragmentGroup,
        *,
        operator: str,
        task_id: str,
    ) -> None:
        stage_started = perf_counter()
        term_detail = self._load_term_detail(group.instance_id)
        object_code = _object_code_from_term(term_detail)
        _log_task_stage(
            task_id=task_id,
            stage="load_term_detail",
            status="succeeded",
            instance_id=group.instance_id,
            input_data={"instance_id": group.instance_id},
            output_data={
                "term_id": _pick_str(term_detail, "term_id", "termId", "id"),
                "term_code": _pick_str(term_detail, "term_code", "termCode"),
                "term_name": _pick_str(term_detail, "term_name", "termName"),
                "object_code": object_code,
            },
            elapsed_ms=_elapsed_ms(stage_started),
        )
        if not object_code:
            raise ValueError(
                f"object code not found for instance_id={group.instance_id}"
            )

        stage_started = perf_counter()
        object_schema = self._platform.get_object_detail(self._base_id, object_code)
        if not object_schema:
            raise ValueError(f"object schema not found: {object_code}")
        object_schema_dict = _to_dict(object_schema)
        _log_task_stage(
            task_id=task_id,
            stage="load_object_schema",
            status="succeeded",
            instance_id=group.instance_id,
            input_data={"object_code": object_code},
            output_data={
                "object_code": object_code,
                "property_count": len(_extract_properties(object_schema_dict)),
                "template_present": bool(
                    _pick_str(
                        _to_dict(
                            object_schema_dict.get("extProperty")
                            or object_schema_dict.get("ext_property")
                            or {}
                        ),
                        "template",
                    )
                ),
            },
            elapsed_ms=_elapsed_ms(stage_started),
        )

        stage_started = perf_counter()
        label_schema = self._build_label_schema(object_schema)
        _log_task_stage(
            task_id=task_id,
            stage="build_label_schema",
            status="succeeded",
            instance_id=group.instance_id,
            input_data={"object_code": object_code},
            output_data={
                "field_count": len(label_schema),
                "enum_fields": [
                    field_code
                    for field_code, field_schema in label_schema.items()
                    if field_schema.get("value_kind") == "enum"
                ],
            },
            elapsed_ms=_elapsed_ms(stage_started),
        )
        stage_started = perf_counter()
        protected_metadata = _load_protected_object_metadata(
            platform=self._platform,
            base_id=self._base_id,
            term_detail=term_detail,
        )
        _log_task_stage(
            task_id=task_id,
            stage="load_protected_metadata",
            status="succeeded",
            instance_id=group.instance_id,
            input_data={
                "term_id": _pick_str(term_detail, "term_id", "termId", "id"),
            },
            output_data={
                "product_code": protected_metadata.product_code,
                "relation_count": protected_metadata.relation_count(),
                "relation_names": sorted(protected_metadata.relations),
            },
            elapsed_ms=_elapsed_ms(stage_started),
        )
        stage_started = perf_counter()
        term_file_ref = _term_file_reference(term_detail)
        existing_content = self._read_existing_content(term_detail)
        _log_task_stage(
            task_id=task_id,
            stage="read_existing_content",
            status="succeeded",
            instance_id=group.instance_id,
            input_data=term_file_ref,
            output_data=_text_summary(existing_content),
            elapsed_ms=_elapsed_ms(stage_started),
        )
        if _has_kb_document_reference(term_file_ref) and not existing_content.strip():
            raise ValueError(
                f"existing object content not found for instance_id={group.instance_id}"
            )
        stage_started = perf_counter()
        source_content = self._read_source_content(group)
        _log_task_stage(
            task_id=task_id,
            stage="read_source_content",
            status="succeeded",
            instance_id=group.instance_id,
            input_data={
                "origin_instance_id": group.origin_instance_id or "",
                "fragment_ids": _fragment_ids(group.fragments),
            },
            output_data=_text_summary(source_content),
            elapsed_ms=_elapsed_ms(stage_started),
        )
        stage_started = perf_counter()
        related_docs = _build_related_docs_from_group(
            group=group,
            term_detail=term_detail,
        )
        _log_task_stage(
            task_id=task_id,
            stage="build_related_docs",
            status="succeeded",
            instance_id=group.instance_id,
            input_data={
                "fragment_ids": _fragment_ids(group.fragments),
            },
            output_data={
                "doc_id": related_docs.get("doc_id") or "",
                "related_doc_count": len(_related_doc_items(related_docs)),
            },
            elapsed_ms=_elapsed_ms(stage_started),
        )
        stage_started = perf_counter()
        object_template, template_constraints = _object_template_parts_from_schema(
            object_schema
        )
        request_object_template = "" if existing_content.strip() else object_template
        _log_task_stage(
            task_id=task_id,
            stage="split_object_template",
            status="succeeded",
            instance_id=group.instance_id,
            input_data={"object_code": object_code},
            output_data={
                "template_present": bool(object_template),
                "template_length": len(request_object_template),
                "constraints_length": len(template_constraints),
            },
            elapsed_ms=_elapsed_ms(stage_started),
        )
        request = ObjectInstanceBuildRequest(
            instance_id=group.instance_id,
            origin_instance_id=group.origin_instance_id,
            term_detail=term_detail,
            object_schema=object_schema_dict,
            label_schema=label_schema,
            object_template=request_object_template,
            template_constraints=template_constraints,
            related_docs=related_docs,
            existing_content=existing_content,
            source_content=source_content,
            fragments=[
                ObjectInstanceFragment(
                    fragment_id=str(fragment.get("id") or ""),
                    content=str(fragment.get("content") or ""),
                    origin_file=_origin_file(fragment),
                    sort_key=fragment.get("id"),
                )
                for fragment in _sort_fragments(group.fragments)
            ],
        )
        stage_started = perf_counter()
        result = await self._knowledge_client.build_object_instance(request)
        _log_task_stage(
            task_id=task_id,
            stage="knowledge_build",
            status="succeeded",
            instance_id=group.instance_id,
            input_data={
                "object_code": object_code,
                "fragment_count": len(request.fragments),
                "fragment_ids": _fragment_ids(group.fragments),
                "label_fields": sorted(label_schema),
                "existing_content_length": len(existing_content),
                "source_content_length": len(source_content),
                "template_present": bool(request_object_template),
            },
            output_data={
                **_text_summary(result.content),
                "labels": result.labels,
                "file_description": result.file_description,
                "confidence": result.confidence,
            },
            elapsed_ms=_elapsed_ms(stage_started),
        )
        if protected_metadata.has_values():
            stage_started = perf_counter()
            result = _apply_protected_object_metadata(
                result=result,
                metadata=protected_metadata,
                label_schema=label_schema,
            )
            _log_task_stage(
                task_id=task_id,
                stage="protect_object_metadata",
                status="succeeded",
                instance_id=group.instance_id,
                input_data={
                    "product_code": protected_metadata.product_code,
                    "relation_count": protected_metadata.relation_count(),
                },
                output_data={
                    **_text_summary(result.content),
                    "labels": result.labels,
                },
                elapsed_ms=_elapsed_ms(stage_started),
            )
        stage_started = perf_counter()
        result = _apply_related_docs_to_build_result(
            result=result,
            related_docs=related_docs,
        )
        _log_task_stage(
            task_id=task_id,
            stage="merge_related_docs",
            status="succeeded",
            instance_id=group.instance_id,
            input_data={
                "doc_id": related_docs.get("doc_id") or "",
                "related_doc_count": len(_related_doc_items(related_docs)),
            },
            output_data=_text_summary(result.content),
            elapsed_ms=_elapsed_ms(stage_started),
        )
        stage_started = perf_counter()
        _validate_build_result(result, label_schema)
        _log_task_stage(
            task_id=task_id,
            stage="validate_build_result",
            status="succeeded",
            instance_id=group.instance_id,
            input_data={
                "label_fields": sorted(result.labels),
                "allowed_label_fields": sorted(label_schema),
            },
            output_data={"label_count": len(result.labels)},
            elapsed_ms=_elapsed_ms(stage_started),
        )

        source_path = _source_path(group, object_code, term_detail)
        stage_started = perf_counter()
        write_result = await invoke_object_write_action(
            platform=self._platform,
            base_id=self._base_id,
            object_code=object_code,
            content=result.content,
            labels=result.labels,
            file_description=result.file_description,
            source_path=source_path,
        )
        _log_task_stage(
            task_id=task_id,
            stage="write_object_action",
            status="succeeded",
            instance_id=group.instance_id,
            input_data={
                "object_code": object_code,
                "action_code": f"write_{object_code}",
                "source_path": source_path,
                "content_length": len(result.content),
                "label_fields": sorted(result.labels),
            },
            output_data=_action_result_summary(write_result),
            elapsed_ms=_elapsed_ms(stage_started),
        )
        stage_started = perf_counter()
        updated = self._platform.update_fragment_status_by_ids(
            self._base_id,
            ids=[int(fragment["id"]) for fragment in group.fragments],
            status=1,
            updated_by=operator,
        )
        _log_task_stage(
            task_id=task_id,
            stage="update_fragment_status",
            status="succeeded",
            instance_id=group.instance_id,
            input_data={
                "fragment_ids": _fragment_ids(group.fragments),
                "status": 1,
                "updated_by": operator,
            },
            output_data={"updated": updated},
            elapsed_ms=_elapsed_ms(stage_started),
        )

    def _load_term_detail(self, instance_id: str) -> dict[str, Any]:
        detail = self._platform.get_term_detail(
            self._base_id,
            library_id=self._base_id,
            term_id=instance_id,
        )
        if detail is None:
            raise ValueError(f"term not found: {instance_id}")
        return _to_dict(detail)

    def _build_label_schema(self, object_schema: Any) -> dict[str, Any]:
        schema = _to_dict(object_schema)
        label_schema: dict[str, Any] = {}
        for prop in _extract_properties(schema):
            field_code = _pick_str(
                prop, "property_code", "propertyCode", "field_code", "fieldCode", "code"
            )
            if not field_code:
                continue
            terminology = _to_dict(prop.get("terminology") or {})
            term_type_code = _pick_str(terminology, "term_type_code", "termTypeCode")
            term_master_type = _pick_str(
                terminology, "term_master_type", "termMasterType"
            )
            field_schema: dict[str, Any] = {
                "field_code": field_code,
                "field_name": _pick_str(
                    prop,
                    "property_name",
                    "propertyName",
                    "field_name",
                    "fieldName",
                    "name",
                ),
                "data_type": _pick_str(prop, "data_type", "dataType", "type"),
                "required": bool(
                    prop.get("required")
                    or prop.get("is_required")
                    or prop.get("isRequired")
                ),
                "value_kind": "string",
            }
            if _is_multiple_property(prop):
                field_schema["multiple"] = True
            if terminology:
                field_schema["terminology"] = {
                    "term_field": _pick_str(terminology, "term_field", "termField")
                    or field_code,
                    "term_type_code": term_type_code,
                    "term_master_type": term_master_type,
                }
            if term_type_code and term_master_type == "DICT_TERM":
                field_schema["value_kind"] = "enum"
                field_schema["enum_values"] = self._load_enum_values(term_type_code)
            label_schema[field_code] = field_schema
        return label_schema

    def _load_enum_values(self, term_type_code: str) -> list[dict[str, Any]]:
        for library_id in (self._base_id, DEFAULT_ENUM_LIBRARY_ID):
            enum_values = self._load_enum_values_from_library(
                library_id=library_id,
                term_type_code=term_type_code,
            )
            if enum_values:
                return enum_values
        return []

    def _load_enum_values_from_library(
        self,
        *,
        library_id: str,
        term_type_code: str,
    ) -> list[dict[str, Any]]:
        enum_values: list[dict[str, Any]] = []
        page_index = 1
        while True:
            result = self._platform.list_terms(
                self._base_id,
                library_id=library_id,
                term_type=term_type_code,
                page_index=page_index,
                page_size=ENUM_PAGE_SIZE,
            )
            items = _extract_items(result)
            enum_values.extend(_normalize_enum_term(item) for item in items)
            total = int(
                result.get("total") or result.get("totalCount") or len(enum_values)
            )
            if page_index * ENUM_PAGE_SIZE >= total or not items:
                break
            page_index += 1
        return enum_values

    def _read_source_content(self, group: _FragmentGroup) -> str:
        origin_file = _origin_file(group.fragments[0]) if group.fragments else {}
        content = self._read_content_from_file_reference(
            origin_file,
            missing_log_template=(
                "source file not found, fallback to fragment content: file_id=%s"
            ),
        )
        if content.strip():
            return content

        return "\n\n".join(
            str(fragment.get("content") or "") for fragment in group.fragments
        )

    def _read_existing_content(self, term_detail: dict[str, Any]) -> str:
        file_ref = _term_file_reference(term_detail)
        if not _has_kb_document_reference(file_ref):
            return ""
        return _read_kb_document_from_reference(file_ref)

    def _read_content_from_file_reference(
        self,
        file_ref: dict[str, Any],
        *,
        missing_log_template: str,
    ) -> str:
        if not file_ref:
            return ""
        kb_content = _read_kb_document_from_reference(file_ref)
        if kb_content.strip():
            return kb_content

        reader = getattr(self._platform, "read_source_document", None)
        if callable(reader):
            try:
                content = reader(self._base_id, file_ref)
            except TypeError:
                content = reader(file_ref)
            except FileNotFoundError:
                content = ""
            if str(content or "").strip():
                logger.info(
                    "object_instance_build file read succeeded via platform reader: "
                    "file_ref=%s content_length=%d",
                    _json_for_log(file_ref),
                    len(str(content)),
                )
                return str(content)

        file_path = _pick_str(
            file_ref, "kb_file_path", "kbFilePath", "file_path", "filePath"
        )
        runtime_content = _read_runtime_result_file_storage(file_path)
        if runtime_content.strip():
            return runtime_content

        file_id = _pick_str(
            file_ref, "kb_resource_id", "kbResourceId", "file_id", "fileId"
        )
        get_result = getattr(self._platform, "get_result", None)
        if file_id and callable(get_result):
            try:
                raw_content = get_result(self._base_id, file_id)
            except FileNotFoundError:
                logger.warning(
                    missing_log_template,
                    file_id,
                )
            else:
                if isinstance(raw_content, bytes):
                    return raw_content.decode("utf-8")
                if str(raw_content or "").strip():
                    return str(raw_content)

        return ""


def _load_protected_object_metadata(
    *,
    platform: Any,
    base_id: str,
    term_detail: dict[str, Any],
) -> _ProtectedObjectMetadata:
    relation_rows = _load_source_term_relation_rows(
        platform=platform,
        base_id=base_id,
        term_detail=term_detail,
    )
    enriched_rows = _enrich_relation_target_terms(
        platform=platform,
        base_id=base_id,
        rows=relation_rows,
    )
    return _ProtectedObjectMetadata(
        product_code=_select_product_code_from_relations(enriched_rows),
        relations=_build_relation_frontmatter_from_rows(enriched_rows),
    )


def _load_source_term_relation_rows(
    *,
    platform: Any,
    base_id: str,
    term_detail: dict[str, Any],
) -> list[dict[str, Any]]:
    term_id = _pick_str(term_detail, "term_id", "termId", "id")
    if not term_id:
        return []

    reader = getattr(platform, "list_term_relations", None)
    if not callable(reader):
        return []

    rows: list[dict[str, Any]] = []
    page_index = 1
    while True:
        try:
            page = reader(
                base_id,
                source_term_id=term_id,
                page_index=page_index,
                page_size=TERM_RELATION_PAGE_SIZE,
            )
        except Exception:
            logger.warning(
                "object_instance_build term relation read failed: term_id=%s",
                term_id,
                exc_info=True,
            )
            return rows

        items = _extract_items(page)
        rows.extend(items)
        total = len(rows)
        if isinstance(page, dict):
            total = int(page.get("total") or page.get("totalCount") or total)
        if page_index * TERM_RELATION_PAGE_SIZE >= total or not items:
            break
        page_index += 1

    return rows


def _enrich_relation_target_terms(
    *,
    platform: Any,
    base_id: str,
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    enriched_rows: list[dict[str, Any]] = []
    target_cache: dict[str, dict[str, Any]] = {}
    for row in rows:
        enriched = dict(row)
        target_id = _pick_str(
            row, "target_term_id", "targetTermId", "target_id", "targetId"
        )
        if target_id and _relation_row_needs_target_detail(row):
            target_detail = target_cache.get(target_id)
            if target_detail is None:
                target_detail = _load_relation_target_detail(
                    platform=platform,
                    base_id=base_id,
                    target_id=target_id,
                )
                target_cache[target_id] = target_detail
            _merge_relation_target_detail(enriched, target_detail)
        enriched_rows.append(enriched)
    return enriched_rows


def _relation_row_needs_target_detail(row: dict[str, Any]) -> bool:
    return not (
        _pick_str(
            row, "target_term_code", "targetTermCode", "target_code", "targetCode"
        )
        and _pick_str(
            row, "target_term_name", "targetTermName", "target_name", "targetName"
        )
        and _pick_str(
            row,
            "target_term_type_code",
            "targetTermTypeCode",
            "target_term_type",
            "targetTermType",
            "target_type_code",
            "targetTypeCode",
            "target_type",
            "targetType",
        )
    )


def _load_relation_target_detail(
    *,
    platform: Any,
    base_id: str,
    target_id: str,
) -> dict[str, Any]:
    reader = getattr(platform, "get_term_detail", None)
    if not callable(reader):
        return {}
    try:
        detail = reader(base_id, library_id=base_id, term_id=target_id)
    except Exception:
        logger.warning(
            "object_instance_build relation target detail read failed: target_id=%s",
            target_id,
            exc_info=True,
        )
        return {}
    return _to_dict(detail)


def _merge_relation_target_detail(
    row: dict[str, Any],
    target_detail: dict[str, Any],
) -> None:
    if not target_detail:
        return
    field_pairs = (
        ("target_term_code", ("term_code", "termCode", "code")),
        ("target_term_name", ("term_name", "termName", "name")),
        (
            "target_term_type_code",
            ("term_type_code", "termTypeCode", "term_type", "termType"),
        ),
    )
    for target_key, source_keys in field_pairs:
        if _pick_str(row, target_key):
            continue
        value = _pick_str(target_detail, *source_keys)
        if value:
            row[target_key] = value


def _select_product_code_from_relations(rows: list[dict[str, Any]]) -> str:
    candidates: list[tuple[int, int, str]] = []
    for index, row in enumerate(rows):
        priority = _product_relation_priority(row)
        if priority is None:
            continue
        product_code = _pick_str(
            row,
            "target_term_code",
            "targetTermCode",
            "target_code",
            "targetCode",
            "target_term_name",
            "targetTermName",
            "target_name",
            "targetName",
        )
        if product_code:
            candidates.append((priority, index, product_code))

    if not candidates:
        return ""
    return sorted(candidates)[0][2]


def _build_relation_frontmatter_from_rows(
    rows: list[dict[str, Any]],
) -> dict[str, dict[str, list[str]]]:
    relations: dict[str, dict[str, list[str]]] = {}
    for row in rows:
        if _product_relation_priority(row) is not None:
            continue

        relation_name = _pick_str(
            row,
            "relation_name",
            "relationName",
            "relation_code",
            "relationCode",
            "relation_type",
            "relationType",
        )
        target_type = _pick_str(
            row,
            "target_term_type_code",
            "targetTermTypeCode",
            "target_term_type",
            "targetTermType",
            "target_type_code",
            "targetTypeCode",
            "target_type",
            "targetType",
        )
        target_name = _pick_str(
            row,
            "target_term_name",
            "targetTermName",
            "target_name",
            "targetName",
            "target_term_code",
            "targetTermCode",
            "target_code",
            "targetCode",
        )
        if not relation_name or not target_type or not target_name:
            continue

        target_names = relations.setdefault(relation_name, {}).setdefault(
            target_type,
            [],
        )
        if target_name not in target_names:
            target_names.append(target_name)

    return relations


def _product_relation_priority(row: dict[str, Any]) -> int | None:
    relation_name = _pick_str(
        row,
        "relation_name",
        "relationName",
        "relation_code",
        "relationCode",
        "relation_type",
        "relationType",
    )
    relation_key = relation_name.casefold()
    preferred_names = {name.casefold() for name in PRODUCT_RELATION_PREFERRED_NAMES}
    fallback_names = {name.casefold() for name in PRODUCT_RELATION_FALLBACK_NAMES}
    if relation_key in preferred_names:
        return 0
    if relation_key in fallback_names:
        return 20

    target_type = _pick_str(
        row,
        "target_term_type_code",
        "targetTermTypeCode",
        "target_term_type",
        "targetTermType",
        "target_type_code",
        "targetTypeCode",
        "target_type",
        "targetType",
    )
    if target_type.casefold() == PRODUCT_OBJECT_CODE:
        return 10
    return None


def _apply_protected_object_metadata(
    *,
    result: ObjectInstanceBuildResult,
    metadata: _ProtectedObjectMetadata,
    label_schema: dict[str, Any],
) -> ObjectInstanceBuildResult:
    labels = dict(result.labels)
    include_product_code = PRODUCT_CODE_FIELD in label_schema
    if include_product_code and metadata.product_code:
        labels[PRODUCT_CODE_FIELD] = metadata.product_code
    if metadata.relations:
        labels["relations"] = metadata.relations

    diagnostics = dict(result.diagnostics)
    diagnostics["protected_metadata"] = {
        "product_code": metadata.product_code if include_product_code else "",
        "relation_count": metadata.relation_count(),
    }
    return ObjectInstanceBuildResult(
        content=_merge_protected_frontmatter(
            content=result.content,
            metadata=metadata,
            include_product_code=include_product_code,
        ),
        labels=labels,
        file_description=result.file_description,
        confidence=result.confidence,
        model_name=result.model_name,
        diagnostics=diagnostics,
    )


def _merge_protected_frontmatter(
    *,
    content: str,
    metadata: _ProtectedObjectMetadata,
    include_product_code: bool,
) -> str:
    protected_keys: set[str] = set()
    if include_product_code and metadata.product_code:
        protected_keys.add(PRODUCT_CODE_FIELD)
    if metadata.relations:
        protected_keys.add("relations")
    if not protected_keys:
        return content

    frontmatter_lines, body = _split_frontmatter(content)
    retained_lines = _strip_frontmatter_keys(frontmatter_lines, protected_keys)
    protected_lines = _render_protected_frontmatter(
        metadata=metadata,
        include_product_code=include_product_code,
    )
    rendered_lines = [*retained_lines, *protected_lines]
    rendered_frontmatter = "\n".join(rendered_lines)
    rendered_body = body.lstrip("\r\n")
    if not rendered_frontmatter:
        return rendered_body
    return f"---\n{rendered_frontmatter}\n---\n\n{rendered_body}"


def _split_frontmatter(content: str) -> tuple[list[str], str]:
    normalized = content.replace("\r\n", "\n")
    if not normalized.startswith("---\n"):
        return [], normalized

    lines = normalized.split("\n")
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            return lines[1:index], "\n".join(lines[index + 1 :])
    return [], normalized


def _strip_frontmatter_keys(lines: list[str], keys: set[str]) -> list[str]:
    retained: list[str] = []
    skipping = False
    for line in lines:
        key = _frontmatter_top_level_key(line)
        if key:
            skipping = key in keys
        if not skipping:
            retained.append(line)
    return _trim_blank_lines(retained)


def _frontmatter_top_level_key(line: str) -> str:
    if line.startswith((" ", "\t")):
        return ""
    match = re.match(r"^([A-Za-z_][A-Za-z0-9_-]*)\s*:", line)
    return match.group(1) if match else ""


def _trim_blank_lines(lines: list[str]) -> list[str]:
    start = 0
    end = len(lines)
    while start < end and not lines[start].strip():
        start += 1
    while end > start and not lines[end - 1].strip():
        end -= 1
    return lines[start:end]


def _render_protected_frontmatter(
    *,
    metadata: _ProtectedObjectMetadata,
    include_product_code: bool,
) -> list[str]:
    lines: list[str] = []
    if include_product_code and metadata.product_code:
        lines.append(f"{PRODUCT_CODE_FIELD}: {_yaml_scalar(metadata.product_code)}")
    if metadata.relations:
        lines.append("relations:")
        for relation_name, targets_by_type in metadata.relations.items():
            lines.append(f"  {_yaml_scalar(relation_name)}:")
            for target_type, target_names in targets_by_type.items():
                lines.append(f"  - {_yaml_scalar(target_type)}:")
                lines.extend(
                    f"    - {_yaml_scalar(target_name)}" for target_name in target_names
                )
    return lines


def _yaml_scalar(value: str) -> str:
    text = str(value).strip()
    if not text:
        return '""'
    if re.search(r"[:\r\n]|^\s|\s$|^[\[\]{},&*#?!|>'\"%@`-]", text):
        return json.dumps(text, ensure_ascii=False)
    return text


def _final_status(*, success_count: int, failed_count: int) -> str:
    if failed_count == 0:
        return "succeeded"
    if success_count == 0:
        return "failed"
    return "partial_failed"


def _elapsed_ms(started_at: float) -> int:
    return int((perf_counter() - started_at) * 1000)


def _log_task_stage(
    *,
    task_id: str,
    stage: str,
    status: str,
    instance_id: str = "",
    message: str = "",
    input_data: dict[str, Any] | None = None,
    output_data: dict[str, Any] | None = None,
    elapsed_ms: int | None = None,
) -> None:
    logger.info(
        "object_instance_build request_id=%s stage=%s status=%s instance_id=%s "
        "message=%s elapsed_ms=%s input=%s output=%s",
        task_id,
        stage,
        status,
        instance_id,
        message,
        "" if elapsed_ms is None else elapsed_ms,
        _json_for_log(input_data or {}),
        _json_for_log(output_data or {}),
    )


def _json_for_log(data: dict[str, Any]) -> str:
    try:
        return json.dumps(data, ensure_ascii=False, sort_keys=True, default=str)
    except (TypeError, ValueError):
        return json.dumps({"repr": repr(data)}, ensure_ascii=False, sort_keys=True)


def _read_kb_document_from_reference(file_ref: dict[str, Any]) -> str:
    kn_code = _pick_str(file_ref, "kb_id", "kbId", "knCode")
    file_path = _pick_str(
        file_ref, "kb_file_path", "kbFilePath", "file_path", "filePath"
    )
    if not kn_code or not file_path:
        return ""

    try:
        content = _build_kb_document_reader().read_text(
            kn_code=kn_code,
            file_path=file_path,
        )
    except KbDocumentReadError as exc:
        logger.warning(
            "object_instance_build KB document read failed: knCode=%s filePath=%s "
            "error=%s",
            kn_code,
            file_path,
            exc,
        )
        return ""

    logger.info(
        "object_instance_build KB document read succeeded: knCode=%s filePath=%s "
        "content_length=%d",
        kn_code,
        file_path,
        len(content),
    )
    return content


def _build_kb_document_reader() -> KbDocumentReader:
    return build_default_kb_document_reader()


def _read_runtime_result_file_storage(file_path: str) -> str:
    if not file_path:
        return ""
    storage = _build_runtime_result_file_storage()
    if storage is None:
        logger.info(
            "object_instance_build runtime result file storage unavailable: "
            "file_path=%s",
            file_path,
        )
        return ""

    storage_type = str(getattr(storage, "storage_type", storage.__class__.__name__))
    reader = getattr(storage, "read_text", None)
    if not callable(reader):
        logger.info(
            "object_instance_build runtime result file storage has no read_text: "
            "file_path=%s storage_type=%s",
            file_path,
            storage_type,
        )
        return ""

    try:
        content = reader(file_path, 0, -1)
    except Exception:
        logger.warning(
            "object_instance_build runtime result file storage read failed: "
            "file_path=%s storage_type=%s",
            file_path,
            storage_type,
            exc_info=True,
        )
        return ""

    text = str(content or "")
    if text.strip():
        logger.info(
            "object_instance_build runtime result file storage read succeeded: "
            "file_path=%s storage_type=%s content_length=%d",
            file_path,
            storage_type,
            len(text),
        )
        return text

    logger.info(
        "object_instance_build runtime result file storage read empty: "
        "file_path=%s storage_type=%s",
        file_path,
        storage_type,
    )
    return ""


def _build_runtime_result_file_storage() -> Any | None:
    try:
        return platform_file_storage.build_result_file_storage(get_settings())
    except Exception:
        logger.warning(
            "object_instance_build runtime result file storage build failed",
            exc_info=True,
        )
        return None


def _text_summary(content: str, *, preview_chars: int = 160) -> dict[str, Any]:
    preview = " ".join(content.strip().split())
    if len(preview) > preview_chars:
        preview = f"{preview[:preview_chars]}..."
    return {
        "content_length": len(content),
        "content_preview": preview,
    }


def _action_result_summary(result: dict[str, Any]) -> dict[str, Any]:
    records = result.get("records")
    meta = result.get("meta")
    return {
        "record_count": len(records) if isinstance(records, list) else 0,
        "total": result.get("total") or 0,
        "meta_keys": sorted(meta) if isinstance(meta, dict) else [],
    }


def _extract_items(result: Any) -> list[dict[str, Any]]:
    if isinstance(result, dict):
        raw_items = (
            result.get("data") or result.get("items") or result.get("records") or []
        )
    else:
        raw_items = (
            getattr(result, "data", None) or getattr(result, "items", None) or []
        )
    if not isinstance(raw_items, list):
        return []
    return [_to_dict(item) for item in raw_items]


def _group_fragments(rows: list[dict[str, Any]]) -> list[_FragmentGroup]:
    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in rows:
        instance_id = str(row.get("instance_id") or row.get("instanceId") or "").strip()
        if not instance_id:
            continue
        origin_instance_id = str(
            row.get("origin_instance_id") or row.get("originInstanceId") or ""
        ).strip()
        groups.setdefault((instance_id, origin_instance_id), []).append(row)
    return [
        _FragmentGroup(
            instance_id=instance_id,
            origin_instance_id=origin_instance_id or None,
            fragments=fragments,
        )
        for (instance_id, origin_instance_id), fragments in groups.items()
    ]


def _extract_properties(schema: dict[str, Any]) -> list[dict[str, Any]]:
    raw_properties = schema.get("properties") or schema.get("fields") or []
    if not isinstance(raw_properties, list):
        return []
    return [_to_dict(prop) for prop in raw_properties]


def _normalize_enum_term(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "term_id": _pick_str(item, "term_id", "termId", "id"),
        "code": _pick_str(item, "code", "term_code", "termCode"),
        "name": _pick_str(item, "name", "term_name", "termName"),
        "aliases": _extract_aliases(item),
    }


def _extract_aliases(item: dict[str, Any]) -> list[str]:
    raw_aliases = (
        item.get("aliases") or item.get("alias") or item.get("term_names") or []
    )
    if isinstance(raw_aliases, str):
        return [raw_aliases]
    if not isinstance(raw_aliases, list):
        return []
    aliases: list[str] = []
    for alias in raw_aliases:
        if isinstance(alias, dict):
            value = _pick_str(alias, "name", "term_name", "termName")
        else:
            value = str(alias or "").strip()
        if value:
            aliases.append(value)
    return aliases


def _is_multiple_property(prop: dict[str, Any]) -> bool:
    if bool(prop.get("multiple") or prop.get("is_multiple") or prop.get("isMultiple")):
        return True
    data_type = _pick_str(prop, "data_type", "dataType", "field_type", "fieldType")
    return data_type.upper() in {"ARRAY", "LIST", "MULTI_ENUM"}


def _sort_fragments(fragments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(fragments, key=lambda item: str(item.get("id") or ""))


def _fragment_ids(fragments: list[dict[str, Any]]) -> list[int]:
    result: list[int] = []
    for fragment in fragments:
        raw_id = fragment.get("id")
        if raw_id is None:
            continue
        result.append(int(raw_id))
    return result


def _validate_build_result(
    result: ObjectInstanceBuildResult,
    label_schema: dict[str, Any],
) -> None:
    if not result.content.strip():
        raise ValueError("build result content is required")
    if not isinstance(result.labels, dict):
        raise ValueError("build result labels must be a dict")
    unsupported = sorted(
        set(result.labels) - set(label_schema) - PROTECTED_LABEL_FIELDS
    )
    if unsupported:
        raise ValueError(
            f"unsupported build result label fields: {', '.join(unsupported)}"
        )


def _apply_related_docs_to_build_result(
    *,
    result: ObjectInstanceBuildResult,
    related_docs: dict[str, Any],
) -> ObjectInstanceBuildResult:
    entries = _related_doc_items(related_docs)
    if not entries:
        return result

    diagnostics = dict(result.diagnostics)
    diagnostics["related_docs"] = {
        "doc_id": _pick_str(related_docs, "doc_id", "docId"),
        "related_doc_count": len(entries),
    }
    return ObjectInstanceBuildResult(
        content=_merge_related_docs_block(result.content, related_docs),
        labels=result.labels,
        file_description=result.file_description,
        confidence=result.confidence,
        model_name=result.model_name,
        diagnostics=diagnostics,
    )


def _origin_file(fragment: dict[str, Any]) -> dict[str, Any]:
    origin_file = fragment.get("origin_file") or fragment.get("originFile") or {}
    return _to_dict(origin_file)


def _build_related_docs_from_group(
    *,
    group: _FragmentGroup,
    term_detail: dict[str, Any],
) -> dict[str, Any]:
    entries: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for fragment in _sort_fragments(group.fragments):
        origin_file = _origin_file(fragment)
        target_doc_id = _pick_str(
            origin_file,
            "kb_file_path",
            "kbFilePath",
            "file_path",
            "filePath",
        )
        fragment_id = str(fragment.get("id") or "").strip()
        if not target_doc_id:
            logger.info(
                "object_instance_build related_doc skipped: instance_id=%s "
                "fragment_id=%s reason=missing_origin_file_path origin_file=%s",
                group.instance_id,
                fragment_id,
                _json_for_log(origin_file),
            )
            continue

        kb_resource_id = _pick_str(
            origin_file,
            "kb_resource_id",
            "kbResourceId",
            "resource_id",
            "resourceId",
            "file_id",
            "fileId",
        )
        entry = {
            "target_doc_id": target_doc_id,
            "relation": RELATED_DOCS_RELATION,
            "kb_resource_id": kb_resource_id,
        }
        key = _related_doc_key(entry)
        if key in seen:
            continue
        seen.add(key)
        entries.append(entry)

    return {
        "doc_id": _related_docs_doc_id(group=group, term_detail=term_detail),
        "related_docs": entries,
    }


def _related_docs_doc_id(
    *,
    group: _FragmentGroup,
    term_detail: dict[str, Any],
) -> str:
    for fragment in _sort_fragments(group.fragments):
        doc_id = _pick_str(fragment, "instance_name", "instanceName")
        if doc_id:
            return doc_id
    return (
        _pick_str(term_detail, "term_name", "termName")
        or _pick_str(term_detail, "term_code", "termCode")
        or group.instance_id
    )


def _merge_related_docs_block(
    content: str,
    related_docs: dict[str, Any],
) -> str:
    normalized = content.replace("\r\n", "\n").replace("\r", "\n")
    existing_doc_id = ""
    existing_entries: list[dict[str, str]] = []
    for match in _RELATED_DOCS_BLOCK_PATTERN.finditer(normalized):
        block_doc_id, block_entries = _parse_related_docs_block(match.group("body"))
        if block_doc_id and not existing_doc_id:
            existing_doc_id = block_doc_id
        existing_entries.extend(block_entries)

    merged_entries = _dedupe_related_doc_entries(
        [*existing_entries, *_related_doc_items(related_docs)]
    )
    without_blocks = _RELATED_DOCS_BLOCK_PATTERN.sub("\n", normalized)
    without_blocks = re.sub(r"\n{3,}", "\n\n", without_blocks).strip()
    if not merged_entries:
        return without_blocks

    doc_id = _pick_str(related_docs, "doc_id", "docId") or existing_doc_id
    rendered_block = _render_related_docs_block(
        doc_id=doc_id,
        entries=merged_entries,
    )
    if not without_blocks:
        return rendered_block
    return f"{without_blocks}\n\n{rendered_block}"


def _parse_related_docs_block(body: str) -> tuple[str, list[dict[str, str]]]:
    doc_id = ""
    entries: list[dict[str, str]] = []
    current_entry: dict[str, str] = {}
    for raw_line in body.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("doc_id:"):
            doc_id = _parse_related_doc_scalar(line)
            continue
        if line.startswith("- target_doc_id:"):
            if current_entry:
                normalized = _normalize_related_doc_entry(current_entry)
                if normalized is not None:
                    entries.append(normalized)
            current_entry = {"target_doc_id": _parse_related_doc_scalar(line)}
            continue
        if line.startswith("relation:") and current_entry:
            current_entry["relation"] = _parse_related_doc_scalar(line)
            continue
        if line.startswith("kb_resource_id:") and current_entry:
            current_entry["kb_resource_id"] = _parse_related_doc_scalar(line)

    if current_entry:
        normalized = _normalize_related_doc_entry(current_entry)
        if normalized is not None:
            entries.append(normalized)
    return doc_id, entries


def _parse_related_doc_scalar(line: str) -> str:
    value = line.split(":", 1)[1].strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def _related_doc_items(related_docs: dict[str, Any]) -> list[dict[str, str]]:
    raw_items = related_docs.get("related_docs") or related_docs.get("relatedDocs")
    if not isinstance(raw_items, list):
        return []
    items: list[dict[str, str]] = []
    for raw_item in raw_items:
        normalized = _normalize_related_doc_entry(_to_dict(raw_item))
        if normalized is not None:
            items.append(normalized)
    return items


def _normalize_related_doc_entry(entry: dict[str, Any]) -> dict[str, str] | None:
    target_doc_id = _pick_str(
        entry,
        "target_doc_id",
        "targetDocId",
        "kb_file_path",
        "kbFilePath",
        "file_path",
        "filePath",
    )
    if not target_doc_id:
        return None

    return {
        "target_doc_id": target_doc_id,
        "relation": _pick_str(entry, "relation") or RELATED_DOCS_RELATION,
        "kb_resource_id": _pick_str(
            entry,
            "kb_resource_id",
            "kbResourceId",
            "resource_id",
            "resourceId",
            "file_id",
            "fileId",
        ),
    }


def _dedupe_related_doc_entries(
    entries: list[dict[str, str]],
) -> list[dict[str, str]]:
    deduped: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for entry in entries:
        key = _related_doc_key(entry)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(entry)
    return deduped


def _related_doc_key(entry: dict[str, str]) -> tuple[str, str, str]:
    return (
        entry.get("target_doc_id", ""),
        entry.get("relation", ""),
        entry.get("kb_resource_id", ""),
    )


def _render_related_docs_block(
    *,
    doc_id: str,
    entries: list[dict[str, str]],
) -> str:
    lines = [
        RELATED_DOCS_BOUNDARY,
        "",
        f"doc_id: {_yaml_scalar(doc_id)}",
        "related_docs:",
        "",
    ]
    for entry in entries:
        lines.append(f"- target_doc_id: {_yaml_scalar(entry['target_doc_id'])}")
        lines.append(f"  relation: {_yaml_scalar(entry['relation'])}")
        kb_resource_id = entry.get("kb_resource_id", "")
        if kb_resource_id:
            lines.append(f"  kb_resource_id: {_yaml_scalar(kb_resource_id)}")
    lines.extend(["", RELATED_DOCS_BOUNDARY])
    return "\n".join(lines)


def _term_file_reference(term_detail: dict[str, Any]) -> dict[str, Any]:
    ext_attrs = _to_dict(
        term_detail.get("ext_attrs") or term_detail.get("extAttrs") or {}
    )
    result: dict[str, Any] = {}
    for key in ("kb_resource_id", "kbResourceId", "file_id", "fileId", "kb_id", "kbId"):
        value = ext_attrs.get(key)
        if value is not None:
            result[key] = value

    file_path = _pick_str(
        ext_attrs, "file_path", "filePath", "kb_file_path", "kbFilePath"
    )
    if file_path:
        result["file_path"] = file_path
        result["kb_file_path"] = file_path
    return result


def _has_kb_document_reference(file_ref: dict[str, Any]) -> bool:
    return bool(
        _pick_str(file_ref, "kb_id", "kbId", "knCode")
        and _pick_str(file_ref, "kb_file_path", "kbFilePath", "file_path", "filePath")
    )


def _source_path(
    group: _FragmentGroup,
    object_code: str,
    term_detail: dict[str, Any],
) -> str:
    term_file = _term_file_reference(term_detail)
    term_file_path = _pick_str(
        term_file, "kb_file_path", "kbFilePath", "file_path", "filePath"
    )
    if term_file_path:
        return (
            term_file_path if term_file_path.startswith("/") else f"/{term_file_path}"
        )

    origin_file = _origin_file(group.fragments[0]) if group.fragments else {}
    file_path = _pick_str(
        origin_file, "file_path", "filePath", "kb_file_path", "kbFilePath"
    )
    if file_path:
        return file_path if file_path.startswith("/") else f"/{file_path}"
    term_code = _pick_str(term_detail, "term_code", "termCode") or group.instance_id
    return f"/{object_code}/{term_code}.md"


def _object_code_from_term(term_detail: dict[str, Any]) -> str:
    return _pick_str(
        term_detail, "term_type_code", "termTypeCode", "term_type", "termType"
    )


def _object_template_parts_from_schema(object_schema: Any) -> tuple[str, str]:
    schema = _to_dict(object_schema)
    ext_property = schema.get("extProperty") or schema.get("ext_property") or {}
    if not isinstance(ext_property, dict):
        return "", ""
    raw_template = _pick_str(ext_property, "template")
    if not raw_template:
        return "", ""

    section_match = _INSTANCE_TEMPLATE_HEADING_PATTERN.search(raw_template)
    if section_match is None:
        return raw_template.strip(), ""

    section_start = section_match.start()
    section_body_start = section_match.end()
    next_heading = _NEXT_NUMBERED_HEADING_PATTERN.search(
        raw_template,
        section_body_start,
    )
    section_end = (
        next_heading.start() if next_heading is not None else len(raw_template)
    )
    section_body = raw_template[section_body_start:section_end].strip()
    constraints = f"{raw_template[:section_start].strip()}\n\n{raw_template[section_end:].strip()}".strip()

    fence_match = _MARKDOWN_FENCE_PATTERN.search(section_body)
    output_template = (
        fence_match.group("body").strip() if fence_match is not None else section_body
    )
    return output_template, constraints


def _pick_str(data: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = data.get(key)
        if value is not None:
            return str(value).strip()
    return ""


def _to_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if is_dataclass(value) and not isinstance(value, type):
        return asdict(value)
    if hasattr(value, "model_dump"):
        dumped = value.model_dump()
        return dumped if isinstance(dumped, dict) else {}
    if hasattr(value, "__dict__"):
        return dict(vars(value))
    return {}
