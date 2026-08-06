"""Read-only cascade candidate discovery using existing loader and term APIs."""

from __future__ import annotations

import hashlib
import json
from collections import deque
from typing import Any

from datacloud_data_sdk.constants import DEFAULT_BASE_ID
from datacloud_data_sdk.executor.kb_cascade_delete.models import (
    CascadeDeleteContext,
    CascadeDeleteItem,
    CascadeDeleteRoot,
)
from datacloud_data_sdk.executor.kb_search_backend import KnowledgeFileMetadata


class CascadeDiscoveryError(RuntimeError):
    """Raised when candidate discovery cannot produce a safe complete plan."""


def _fingerprint(detail: KnowledgeFileMetadata) -> str:
    value = {
        "filePath": detail.file_path,
        "exists": detail.exists,
        "labels": detail.labels,
    }
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode()
    ).hexdigest()


def _item_value(item: Any, field: str, default: Any = "") -> Any:
    if isinstance(item, dict):
        return item.get(field, default)
    return getattr(item, field, default)


def _relation_value(relation: dict[str, Any], field: str) -> Any:
    return relation.get(field)


async def discover_cascade_context(
    *,
    loader: Any,
    root_object_code: str,
    root_source_paths: list[str],
    max_depth: int = 2,
    max_items: int = 200,
) -> CascadeDeleteContext | None:
    """Discover incoming dependents up to max_depth without probing deeper levels."""
    from datacloud_data_sdk.executor.kb_search_executor import KbSearchExecutor

    executor = KbSearchExecutor(loader)
    platform = getattr(getattr(loader, "_config", None), "platform", None)
    if platform is None:
        return None

    root_class = loader.get_ontology_class(root_object_code)
    root_backend = executor._resolve_backend(
        root_class,
        getattr(loader._config, "kb_source_configs", None),
        getattr(loader._config, "kb_search_backend", None),
    )
    root_datasource_alias = executor._get_datasource_alias(root_class)
    root_kb_resource_id = executor._get_kb_resource_id(root_class)
    root_kb_directory = executor._get_kb_directory(root_class)
    if not root_kb_resource_id:
        raise CascadeDiscoveryError("CASCADE_CONTEXT_INVALID: Root 缺少 kb_resource_id")

    roots: list[CascadeDeleteRoot] = []
    queue: deque[tuple[str, str, str | None, int]] = deque()
    for source_path in root_source_paths:
        detail = await executor._get_file_metadata(
            root_backend,
            root_class,
            root_datasource_alias,
            root_kb_resource_id,
            root_kb_directory,
            source_path,
        )
        if detail is None or not detail.exists:
            raise CascadeDiscoveryError(f"CASCADE_CONTEXT_STALE: 文件不存在 {source_path}")
        term_ids = await executor._resolve_kb_term_ids(root_class, detail)
        if term_ids is None or len(term_ids) != 1:
            raise CascadeDiscoveryError(
                f"CASCADE_CONTEXT_INVALID: Root 文件必须精确对应一个术语 {source_path}"
            )
        root = CascadeDeleteRoot(
            object_code=root_object_code,
            source_path=source_path,
            term_id=term_ids[0],
            file_fingerprint=_fingerprint(detail),
        )
        roots.append(root)
        queue.append((term_ids[0], root_object_code, None, 0))

    cascade_relations_by_target: dict[str, list[Any]] = {}
    for relation in loader.get_ontology_relations():
        if getattr(relation, "cascade_delete", False) is not True:
            continue
        target_class = str(getattr(relation, "target_class", "") or "")
        cascade_relations_by_target.setdefault(target_class, []).append(relation)
    if not any(root_object_code in cascade_relations_by_target for _ in roots):
        return None

    items: list[CascadeDeleteItem] = []
    seen_terms = {root.term_id for root in roots}
    owner_by_source_relation: dict[tuple[str, str], str] = {}
    while queue:
        owner_term_id, owner_object_code, parent_item_id, owner_depth = queue.popleft()
        if owner_depth >= max_depth:
            continue
        for relation in cascade_relations_by_target.get(owner_object_code, []):
            relation_code = str(getattr(relation, "relation_code", "") or "")
            source_object_code = str(getattr(relation, "source_class", "") or "")
            if not relation_code or not source_object_code:
                raise CascadeDiscoveryError("CASCADE_CONTEXT_INVALID: 级联关系缺少编码或对象")
            try:
                source_class = loader.get_ontology_class(source_object_code)
            except Exception as exc:
                raise CascadeDiscoveryError(
                    f"CASCADE_RELATED_OBJECT_NOT_LOADED: {source_object_code}"
                ) from exc

            page_index = 1
            relation_rows: list[dict[str, Any]] = []
            while True:
                page = platform.list_term_relations(
                    DEFAULT_BASE_ID,
                    target_term_id=owner_term_id,
                    relation_code=relation_code,
                    page_index=page_index,
                    page_size=100,
                    strict=True,
                )
                rows = page.get("data") or []
                relation_rows.extend(row for row in rows if isinstance(row, dict))
                total_pages = int(page.get("totalPages") or 0)
                if page_index >= total_pages:
                    break
                page_index += 1

            for relation_row in relation_rows:
                row_ext_attrs = relation_row.get("ext_attrs") or {}
                if str(row_ext_attrs.get("relation_code") or "") != relation_code:
                    raise CascadeDiscoveryError("CASCADE_CONTEXT_INVALID: 实例边缺少 relation_code")
                source_term_id = str(relation_row.get("source_term_id") or "")
                relation_id = str(relation_row.get("relation_id") or "")
                if not source_term_id or not relation_id:
                    raise CascadeDiscoveryError("CASCADE_CONTEXT_INVALID: 实例边身份不完整")
                owner_key = (source_term_id, relation_code)
                previous_owner = owner_by_source_relation.get(owner_key)
                if previous_owner is not None and previous_owner != owner_term_id:
                    raise CascadeDiscoveryError("CASCADE_MULTIPLE_OWNERS")
                owner_by_source_relation[owner_key] = owner_term_id
                if source_term_id in seen_terms:
                    raise CascadeDiscoveryError("CASCADE_RELATION_CYCLE")

                term_result = platform.search_terms(
                    base_id=DEFAULT_BASE_ID,
                    dataset_ids=[DEFAULT_BASE_ID],
                    term_ids=[source_term_id],
                    top_k=2,
                )
                term_items = getattr(term_result, "items", None)
                if term_items is None and isinstance(term_result, dict):
                    term_items = term_result.get("items")
                term_items = list(term_items or [])
                if len(term_items) != 1:
                    raise CascadeDiscoveryError(
                        f"CASCADE_CONTEXT_INVALID: 无法精确定位 Dependent 术语 {source_term_id}"
                    )
                term_item = term_items[0]
                term_type = str(_item_value(term_item, "term_type") or "")
                if term_type and term_type != source_object_code:
                    raise CascadeDiscoveryError("CASCADE_CONTEXT_INVALID: 术语对象类型不匹配")
                ext_attrs = _item_value(term_item, "ext_attrs", {}) or {}
                source_path = str(
                    ext_attrs.get("kb_file_path")
                    or ext_attrs.get("file_path")
                    or ext_attrs.get("source_path")
                    or ""
                )
                if not source_path.startswith("/"):
                    raise CascadeDiscoveryError(
                        f"CASCADE_CONTEXT_INVALID: Dependent 缺少文件路径 {source_term_id}"
                    )

                depth = owner_depth + 1
                if len(items) >= max_items:
                    raise CascadeDiscoveryError("CASCADE_MAX_ITEMS_EXCEEDED")

                dependent_backend = executor._resolve_backend(
                    source_class,
                    getattr(loader._config, "kb_source_configs", None),
                    getattr(loader._config, "kb_search_backend", None),
                )
                dependent_kb_resource_id = executor._get_kb_resource_id(source_class)
                if not dependent_kb_resource_id:
                    raise CascadeDiscoveryError(
                        f"CASCADE_CONTEXT_INVALID: {source_object_code} 缺少 kb_resource_id"
                    )
                detail = await executor._get_file_metadata(
                    dependent_backend,
                    source_class,
                    executor._get_datasource_alias(source_class),
                    dependent_kb_resource_id,
                    executor._get_kb_directory(source_class),
                    source_path,
                )
                if detail is None or not detail.exists:
                    raise CascadeDiscoveryError(
                        f"CASCADE_CONTEXT_STALE: Dependent 文件不存在 {source_path}"
                    )

                item_id = (
                    "cascade_item_"
                    + hashlib.sha256(
                        f"{relation_id}:{source_term_id}:{source_path}".encode()
                    ).hexdigest()[:16]
                )
                item = CascadeDeleteItem(
                    item_id=item_id,
                    parent_item_id=parent_item_id,
                    depth=depth,
                    object_code=source_object_code,
                    object_name=str(getattr(source_class, "object_name", "") or ""),
                    source_path=source_path,
                    term_id=source_term_id,
                    relation_id=relation_id,
                    relation_code=relation_code,
                    owner_term_id=owner_term_id,
                    file_fingerprint=_fingerprint(detail),
                    join_keys=tuple(
                        dict(key)
                        for key in getattr(relation, "join_keys", []) or []
                        if isinstance(key, dict)
                    ),
                )
                items.append(item)
                seen_terms.add(source_term_id)
                queue.append((source_term_id, source_object_code, item_id, depth))

    if not items:
        return None
    revision = str(
        getattr(loader, "ontology_revision", "") or getattr(loader, "fingerprint", "") or ""
    )
    return CascadeDeleteContext.create(
        roots=roots,
        items=items,
        ontology_revision=revision,
    )
