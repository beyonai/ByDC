"""Platform orchestration for object instance build tasks."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol

from datacloud_knowledge.object_instance_build import (
    ObjectInstanceBuildRequest,
    ObjectInstanceBuildResult,
    ObjectInstanceFragment,
    build_object_instance as knowledge_build_object_instance,
)
from datacloud_platform.constants import DEFAULT_BASE_ID
from datacloud_platform.services.object_action import invoke_object_write_action
from datacloud_platform.services.object_instance_build_task_service import (
    ObjectInstanceBuildTaskRepository,
    TaskStatus,
)

if TYPE_CHECKING:
    from datacloud_platform.platform import DatacloudPlatform

logger = logging.getLogger(__name__)

DEFAULT_ENUM_LIBRARY_ID = "default_term"
ENUM_PAGE_SIZE = 200


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


class ObjectInstanceBuildOrchestrator:
    """Coordinate fragment retrieval, Knowledge build, and datacloud-data write."""

    def __init__(
        self,
        *,
        platform: DatacloudPlatform,
        task_repository: ObjectInstanceBuildTaskRepository,
        knowledge_client: ObjectInstanceBuildKnowledgeClient | None = None,
        base_id: str = DEFAULT_BASE_ID,
    ) -> None:
        self._platform = platform
        self._task_repository = task_repository
        self._knowledge_client = (
            knowledge_client or DefaultObjectInstanceBuildKnowledgeClient()
        )
        self._base_id = base_id

    async def run(self, task_id: str) -> None:
        """Run one object instance build task to a terminal status."""
        task = self._task_repository.get(task_id)
        self._task_repository.update(task_id, status="running")

        errors: list[dict[str, Any]] = []
        success_count = 0
        failed_count = 0
        groups = self._load_fragment_groups(
            instance_ids=task.instance_ids,
            batch_size=task.batch_size,
        )
        self._task_repository.update(task_id, total_count=len(groups))

        for group in groups:
            try:
                await self._process_group(group, operator=task.operator)
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
            else:
                success_count += 1

            self._task_repository.update(
                task_id,
                success_count=success_count,
                failed_count=failed_count,
                errors=errors,
            )

        final_status = _final_status(
            success_count=success_count, failed_count=failed_count
        )
        error_message = "; ".join(error["message"] for error in errors[:3])
        self._task_repository.update(
            task_id,
            status=final_status,
            error_message=error_message,
            errors=errors,
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

    async def _process_group(self, group: _FragmentGroup, *, operator: str) -> None:
        term_detail = self._load_term_detail(group.instance_id)
        object_code = _object_code_from_term(term_detail)
        if not object_code:
            raise ValueError(
                f"object code not found for instance_id={group.instance_id}"
            )

        object_schema = self._platform.get_object_detail(self._base_id, object_code)
        if not object_schema:
            raise ValueError(f"object schema not found: {object_code}")

        label_schema = self._build_label_schema(object_schema)
        source_content = self._read_source_content(group)
        request = ObjectInstanceBuildRequest(
            instance_id=group.instance_id,
            origin_instance_id=group.origin_instance_id,
            term_detail=term_detail,
            object_schema=_to_dict(object_schema),
            label_schema=label_schema,
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
        result = await self._knowledge_client.build_object_instance(request)
        _validate_build_result(result, label_schema)

        await invoke_object_write_action(
            platform=self._platform,
            base_id=self._base_id,
            object_code=object_code,
            content=result.content,
            labels=result.labels,
            file_description=result.file_description,
            source_path=_source_path(group, object_code, term_detail),
        )
        self._platform.update_fragment_status_by_ids(
            self._base_id,
            ids=[int(fragment["id"]) for fragment in group.fragments],
            status=1,
            updated_by=operator,
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
        reader = getattr(self._platform, "read_source_document", None)
        if callable(reader):
            try:
                content = reader(self._base_id, origin_file)
            except TypeError:
                content = reader(origin_file)
            if str(content or "").strip():
                return str(content)

        file_id = _pick_str(
            origin_file, "kb_resource_id", "kbResourceId", "file_id", "fileId"
        )
        get_result = getattr(self._platform, "get_result", None)
        if file_id and callable(get_result):
            raw_content = get_result(self._base_id, file_id)
            if isinstance(raw_content, bytes):
                return raw_content.decode("utf-8")
            if str(raw_content or "").strip():
                return str(raw_content)

        return "\n\n".join(
            str(fragment.get("content") or "") for fragment in group.fragments
        )


def _final_status(*, success_count: int, failed_count: int) -> TaskStatus:
    if failed_count == 0:
        return "succeeded"
    if success_count == 0:
        return "failed"
    return "partial_failed"


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
    unsupported = sorted(set(result.labels) - set(label_schema))
    if unsupported:
        raise ValueError(
            f"unsupported build result label fields: {', '.join(unsupported)}"
        )


def _origin_file(fragment: dict[str, Any]) -> dict[str, Any]:
    origin_file = fragment.get("origin_file") or fragment.get("originFile") or {}
    return _to_dict(origin_file)


def _source_path(
    group: _FragmentGroup,
    object_code: str,
    term_detail: dict[str, Any],
) -> str:
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


def _pick_str(data: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = data.get(key)
        if value is not None:
            return str(value).strip()
    return ""


def _to_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if hasattr(value, "model_dump"):
        dumped = value.model_dump()
        return dumped if isinstance(dumped, dict) else {}
    if hasattr(value, "__dict__"):
        return dict(vars(value))
    return {}
