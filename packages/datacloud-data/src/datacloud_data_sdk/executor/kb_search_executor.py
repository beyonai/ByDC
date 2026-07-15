"""KbSearchExecutor：执行 search_* 虚拟动作（知识库语义检索）。

协议格式：
{
  "query": "检索文本",
  "select": ["metadata_field", ...],
  "filters": [{"field": "...", "op": "...", "value": ...}],
  "filter_relation": "AND" | "OR",
  "order_by": [{"field": "...", "direction": "asc|desc"}],
  "limit": 20,
  "offset": 0
}
"""

from __future__ import annotations

import hashlib
import logging
import traceback
from pathlib import PurePosixPath
from typing import Any, cast

from datacloud_data_sdk.constants import DEFAULT_BASE_ID
from datacloud_data_sdk.exceptions import KbExecutionError
from datacloud_data_sdk.executor.kb_search_backend import (
    HttpKnowledgeSearchBackend,
    KnowledgeFileNameSearchRequest,
    KnowledgeSearchBackend,
    KnowledgeSearchRequest,
    KnowledgeWriteBackend,
    KnowledgeWriteRequest,
    _merge_related_docs_into_labels,
    _parse_related_docs,
    _related_doc_id_to_term,
    _render_markdown_with_front_matter,
    _strip_related_docs_blocks,
    _to_markdown_file_path,
)
from datacloud_data_sdk.ontology.loader import OntologyLoader
from datacloud_data_sdk.plan.term_resolver import TermResolver
from datacloud_data_sdk.result_term_converter import ResultTermConverter

logger = logging.getLogger(__name__)


class KbSearchExecutor:
    """执行知识库对象的 search_* 虚拟动作。"""

    def __init__(
        self,
        loader: OntologyLoader,
        search_backend: KnowledgeSearchBackend | None = None,
    ) -> None:
        self._loader = loader
        self._search_backend = search_backend

    async def execute(
        self,
        object_code: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """
        执行 search 动作。实际检索委托给 KnowledgeSearchBackend 协议实现。

        Args:
            object_code: 对象编码
            arguments: search 协议参数 {query, select, filters, filter_relation, order_by, limit}

        Returns:
            {"records": [], "total": 0, "meta": {...}}
        """
        cls = self._loader.get_ontology_class(object_code)
        kb_configs = getattr(self._loader._config, "kb_source_configs", None)
        configured_backend = getattr(self._loader._config, "kb_search_backend", None)
        datasource_alias = self._get_datasource_alias(cls)

        backend = self._resolve_backend(cls, kb_configs, configured_backend)
        query = str(arguments.get("query", "") or "")
        select = [
            str(getattr(field, "field_code", ""))
            for field in getattr(cls, "fields", [])
            if str(getattr(field, "field_code", ""))
        ]
        filters = self._normalize_filters(arguments.get("filters") or [])
        filter_relation = str(arguments.get("filter_relation") or "AND")
        order_by = self._normalize_order_by(arguments.get("order_by") or [])
        limit = int(arguments.get("limit") or 20)
        offset = int(arguments.get("offset") or 0)
        try:
            result = await backend.search(
                KnowledgeSearchRequest(
                    object_code=cls.object_code,
                    datasource_alias=datasource_alias,
                    query=query,
                    filters=filters,
                    filter_relation=filter_relation,
                    select=select,
                    order_by=order_by,
                    limit=limit,
                    offset=offset,
                    kb_id=self._get_kb_id(cls),
                    kb_directory=self._get_kb_directory(cls),
                    field_types=_metadata_field_types(list(getattr(cls, "fields", []))),
                )
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("knowledge base search failed: object_code=%s", object_code)
            return self._empty_response(
                object_code,
                arguments,
                str(exc),
                error=True,
                meta_extra=_standard_action_meta(cls, datasource_alias, query),
            )
        response = result.to_response()
        records = ResultTermConverter(
            getattr(self._loader._config, "term_loader", None)
        ).convert_by_fields(response.get("records", []), list(getattr(cls, "fields", [])))
        records = self._ensure_primary_key_in_records(records, cls)
        records = _normalize_action_records(records, cls)
        response["records"] = records
        response["meta"] = _standard_action_meta(cls, datasource_alias, query)
        return response

    async def search_by_file_name(
        self,
        object_code: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute chunk-level semantic search constrained by directory and file name."""
        cls = self._loader.get_ontology_class(object_code)
        kb_configs = getattr(self._loader._config, "kb_source_configs", None)
        configured_backend = getattr(self._loader._config, "kb_search_backend", None)
        datasource_alias = self._get_datasource_alias(cls)

        backend = self._resolve_backend(cls, kb_configs, configured_backend)
        query = str(arguments.get("query", "") or "")
        file_name = str(arguments.get("fileName") or "")
        if not file_name:
            return self._empty_response(
                object_code,
                arguments,
                "fileName is required",
                error=True,
                meta_extra=_standard_action_meta(
                    cls,
                    datasource_alias,
                    query,
                    include_content=True,
                ),
            )
        search_by_file_name = getattr(backend, "search_by_file_name", None)
        if not callable(search_by_file_name):
            return self._empty_response(
                object_code,
                arguments,
                "knowledge backend does not support search_by_file_name",
                error=True,
                meta_extra=_standard_action_meta(
                    cls,
                    datasource_alias,
                    query,
                    include_content=True,
                ),
            )

        try:
            result = await search_by_file_name(
                KnowledgeFileNameSearchRequest(
                    object_code=cls.object_code,
                    datasource_alias=datasource_alias,
                    query=query,
                    file_name=file_name,
                    kb_id=self._get_kb_id(cls),
                    kb_directory=self._get_kb_directory(cls),
                    metadata_field_list=self._with_primary_key_metadata_fields(
                        [str(getattr(field, "field_code", "")) for field in cls.fields],
                        cls,
                    ),
                )
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("knowledge base file-name search failed: object_code=%s", object_code)
            error_traceback = "".join(traceback.format_exception(exc))
            return self._empty_response(
                object_code,
                arguments,
                error_traceback,
                error=True,
                meta_extra=_standard_action_meta(
                    cls,
                    datasource_alias,
                    query,
                    include_content=True,
                ),
            )

        response = result.to_response()
        records = ResultTermConverter(
            getattr(self._loader._config, "term_loader", None)
        ).convert_by_fields(response.get("records", []), list(getattr(cls, "fields", [])))
        records = self._ensure_primary_key_in_records(records, cls)
        records = _normalize_action_records(records, cls, include_content=True)
        response["records"] = records
        response["meta"] = _standard_action_meta(
            cls,
            datasource_alias,
            query,
            include_content=True,
        )
        return response

    async def write(
        self,
        object_code: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute write_* action by delegating to a knowledge write backend."""
        cls = self._loader.get_ontology_class(object_code)
        kb_configs = getattr(self._loader._config, "kb_source_configs", None)
        configured_backend = getattr(self._loader._config, "kb_search_backend", None)
        datasource_alias = self._get_datasource_alias(cls)
        query = ""
        kb_resource_id = self._get_kb_resource_id(cls)
        kb_id = self._get_kb_id(cls)
        kb_directory = self._get_kb_directory(cls)
        if not kb_id:
            return self._empty_response(
                object_code,
                arguments,
                "knowledge base id not configured",
                meta_extra=_standard_action_meta(cls, datasource_alias, query),
            )

        backend = self._resolve_backend(cls, kb_configs, configured_backend)
        if not hasattr(backend, "write"):
            return self._empty_response(
                object_code,
                arguments,
                "knowledge backend does not support write",
                error=True,
                meta_extra=_standard_action_meta(cls, datasource_alias, query),
            )

        write_items = self._normalize_write_items(arguments)
        if not write_items:
            return self._empty_response(
                object_code,
                arguments,
                "records or source_path/content is required",
                error=True,
                meta_extra=_standard_action_meta(cls, datasource_alias, query),
            )

        write_requests: list[KnowledgeWriteRequest] = []
        for index, item in enumerate(write_items):
            file_path = str(item.get("source_path") or item.get("file_path") or "")
            content = str(item.get("content") or item.get("source_text") or "")
            if not file_path.startswith("/"):
                return self._empty_response(
                    object_code,
                    arguments,
                    f"records[{index}].source_path must start with /",
                    error=True,
                    meta_extra=_standard_action_meta(cls, datasource_alias, query),
                )
            if not content:
                return self._empty_response(
                    object_code,
                    arguments,
                    f"records[{index}].content is required",
                    error=True,
                    meta_extra=_standard_action_meta(cls, datasource_alias, query),
                )

            labels = self._resolve_label_terms(item.get("labels") or {}, cls)
            markdown_file_path = _to_markdown_file_path(file_path, self._get_kb_directory(cls))
            labels = self._inject_primary_key_label(labels, cls, markdown_file_path)
            write_requests.append(
                KnowledgeWriteRequest(
                    object_code=cls.object_code,
                    datasource_alias=datasource_alias,
                    kb_resource_id=kb_resource_id,
                    kb_id=kb_id,
                    kb_directory=kb_directory,
                    file_path=file_path,
                    labels=labels,
                    content=content,
                    file_description=str(item.get("file_description") or ""),
                    metadata_properties=_metadata_properties_from_labels(labels, cls),
                )
            )

        try:
            write_backend = cast(KnowledgeWriteBackend, backend)
            raw_records: list[dict[str, Any]] = []
            for request in write_requests:
                result = await write_backend.write(request)
                raw_records.extend(result.records)
        except Exception as exc:  # noqa: BLE001
            logger.exception("knowledge base write failed: object_code=%s", object_code)
            return self._empty_response(
                object_code,
                arguments,
                str(exc),
                error=True,
                meta_extra=_standard_action_meta(cls, datasource_alias, query),
            )

        records = ResultTermConverter(
            getattr(self._loader._config, "term_loader", None)
        ).convert_by_fields(raw_records, list(getattr(cls, "fields", [])))
        records = _normalize_action_records(records, cls)
        meta = _standard_action_meta(cls, datasource_alias, query)

        # Enqueue KB term sync for each written document.
        await self._enqueue_kb_term_sync(write_requests)

        # Collect KB file paths from write requests for the summary message.
        kb_file_paths = [
            _to_markdown_file_path(req.file_path, req.kb_directory) for req in write_requests
        ]
        meta["kb_files"] = kb_file_paths
        meta["_write_note"] = _write_summary(kb_file_paths, [])

        response: dict[str, Any] = {"records": records, "total": len(records), "meta": meta}
        _attach_session_file(response, write_requests)

        # Update _write_note to include session paths once _attach_session_file has run.
        session_paths: list[str] = (response.get("file") or {}).get("file_urls") or []
        meta["session_files"] = session_paths
        write_note = _write_summary(kb_file_paths, session_paths)
        meta["_write_note"] = write_note

        # Expose _write_note as a column so the Agent can surface it in the result table.
        columns: list[dict[str, str]] = meta.get("columns") or []
        if not any(c.get("name") == "_write_note" for c in columns):
            columns.append({"name": "_write_note", "label": "写入说明", "type": "string"})
            meta["columns"] = columns

        # Inject _write_note into every record so callers can surface it directly.
        for record in response.get("records") or []:
            record["_write_note"] = write_note

        return response

    async def _enqueue_kb_term_sync(self, write_requests: list[KnowledgeWriteRequest]) -> None:
        """非阻塞投递 KB 术语同步事件（knowledge 包不可用时静默跳过）。

        对每个写入请求：
        1. 从内容中解析 related_docs 块，构建文档级关联关系。
        2. 从 loader._relations 中获取当前对象的本体关联关系，将术语写入关联对象。
        """
        try:
            from datacloud_knowledge.sync import (  # type: ignore[import-untyped]
                TermSyncEvent,
                enqueue_sync,
            )

            from datacloud_data_sdk.constants import DEFAULT_BASE_ID
        except Exception:  # noqa: BLE001
            logger.debug("KB 术语同步跳过：knowledge 包不可用")
            return

        terms: list[dict[str, Any]] = []
        for req in write_requests:
            markdown_file_path = _to_markdown_file_path(req.file_path, req.kb_directory)
            file_stem = PurePosixPath(markdown_file_path).stem or markdown_file_path
            term_type_code = req.object_code

            # 从内容 related_docs 块中解析文档级关联关系
            related_docs = _parse_related_docs(req.content)
            relations: list[dict[str, str]] = []
            for entry in related_docs:
                _rel_type, rel_name = _related_doc_id_to_term(entry["target_doc_id"])
                kb_dir = str(PurePosixPath(entry["target_doc_id"]).parent.name)
                term_type = (
                    self._get_object_code_by_kb(entry.get("kb_resource_id", ""), kb_dir)
                    or _rel_type
                )
                if not term_type:
                    logger.warning("术语关联关系获取不到术语类型：%s", entry)
                    continue
                relations.append(
                    {
                        "term_name": rel_name,
                        "term_code": rel_name,
                        "term_type_code": term_type,
                        "relation_name": entry["relation"],
                    }
                )

            # 从 loader 本体关联关系中获取当前对象关联的目标对象，补充关联术语
            # join_keys 中的字段值即为目标术语的标识
            ontology_relations = self._loader.get_ontology_relations()
            for rel in ontology_relations:
                if rel.source_class == term_type_code:
                    related_object_code = rel.target_class
                    # 当前对象为 source，取 sourceField 对应的 label 值作为目标术语名
                    join_field_key = "sourceField"
                elif rel.target_class == term_type_code:
                    related_object_code = rel.source_class
                    # 当前对象为 target，取 targetField 对应的 label 值作为目标术语名
                    join_field_key = "targetField"
                else:
                    continue

                if not related_object_code:
                    continue

                for jk in rel.join_keys or []:
                    field_name = jk.get(join_field_key) or ""
                    if not field_name:
                        continue
                    term_value = str(req.labels.get(field_name) or "")
                    if not term_value:
                        continue
                    relations.append(
                        {
                            "term_name": term_value,
                            "term_code": term_value,
                            "term_type_code": related_object_code,
                            "relation_name": rel.relation_name or rel.relation_code,
                        }
                    )

            term: dict[str, Any] = {
                "term_name": file_stem,
                "term_code": file_stem,
                "term_type_code": term_type_code,
                "ext_attrs": {
                    "kb_id": req.kb_id,
                    "kb_file_path": markdown_file_path,
                    "kb_resource_id": req.kb_resource_id,
                },
            }
            if relations:
                term["relations"] = relations
            terms.append(term)

        if not terms:
            return

        try:
            await enqueue_sync(
                TermSyncEvent(
                    op="kb_write",
                    base_id=DEFAULT_BASE_ID,
                    object_code=write_requests[0].object_code,
                    records=terms,
                )
            )
        except Exception:  # noqa: BLE001
            logger.debug("KB 术语同步投递失败", exc_info=True)

    def _get_object_code_by_kb(self, kb_resource_id: str, kb_directory: str) -> str | None:
        if not kb_resource_id:
            return None
        cfg = self._loader._config if self._loader else None
        platform = getattr(cfg, "platform", None)
        response = platform.query_ontologies_by_scene(
            DEFAULT_BASE_ID,
            "",
            ext_property_filters={"kb_resource_id": kb_resource_id, "kb_directory": kb_directory},
            page=1,
            page_size=5,
            cross_scene=True,
        )
        if response and response.get("data") and response.get("data").get("objects"):
            return response.get("data").get("objects")[0].get("objectCode")
        return None

    def _resolve_backend(
        self,
        cls: Any,
        kb_configs: dict[str, dict[str, Any]] | None,
        configured_backend: KnowledgeSearchBackend | KnowledgeWriteBackend | None,
    ) -> KnowledgeSearchBackend:
        if self._search_backend is not None:
            return self._search_backend

        datasource_alias = str(getattr(cls, "datasource_alias", "") or "")
        backend_name = self._resolve_backend_name(cls, datasource_alias, kb_configs)
        if backend_name:
            kb_backends = getattr(self._loader._config, "kb_backends", {}) or {}
            backend = kb_backends.get(backend_name)
            if backend is None:
                raise KbExecutionError(
                    datasource_alias,
                    f"knowledge backend not registered: {backend_name}",
                )
            return cast(KnowledgeSearchBackend, backend)

        if configured_backend is not None:
            return cast(KnowledgeSearchBackend, configured_backend)

        return HttpKnowledgeSearchBackend(kb_configs or {})

    def _resolve_backend_name(
        self,
        cls: Any,
        datasource_alias: str,
        kb_configs: dict[str, dict[str, Any]] | None,
    ) -> str | None:
        ext_property = getattr(cls, "ext_property", {}) or {}
        if isinstance(ext_property, dict):
            value = ext_property.get("backend")
            if value:
                return str(value)

        config = (kb_configs or {}).get(datasource_alias, {})
        if isinstance(config, dict):
            value = config.get("backend")
            if value:
                return str(value)

        value = getattr(self._loader._config, "default_kb_backend", None)
        return str(value) if value else None

    def _has_configured_backend(self) -> bool:
        if self._search_backend is not None:
            return True
        if getattr(self._loader._config, "default_kb_backend", None):
            return True
        return bool(getattr(self._loader._config, "kb_backends", {}) or {})

    def _resolve_label_terms(self, labels: Any, cls: Any) -> dict[str, Any]:
        if not isinstance(labels, dict):
            return {}
        term_loader = getattr(self._loader._config, "term_loader", None)
        if term_loader is None:
            return dict(labels)

        field_map = {field.field_code: field for field in getattr(cls, "fields", [])}
        resolved = dict(labels)
        resolver = TermResolver(term_loader)
        for field_code, value in labels.items():
            field = field_map.get(str(field_code))
            if field is None or not getattr(field, "term_set", None):
                continue
            resolved_filter = resolver.resolve_filter_values(
                [{"field": field.field_code, "op": "eq", "value": value}],
                [field],
            )
            if isinstance(resolved_filter, list) and resolved_filter:
                resolved[field_code] = resolved_filter[0].get("value")
        return resolved

    @staticmethod
    def _normalize_write_items(arguments: dict[str, Any]) -> list[dict[str, Any]]:
        records = arguments.get("records")
        if isinstance(records, list):
            return [dict(item) for item in records if isinstance(item, dict)]
        return [arguments]

    @staticmethod
    def _with_primary_key_metadata_fields(fields: list[str], cls: Any) -> list[str]:
        primary_key = KbSearchExecutor._get_primary_key_field_code(cls)
        if not primary_key:
            return fields
        if primary_key in fields:
            return fields
        return [*fields, primary_key]

    def _inject_primary_key_label(
        self,
        labels: dict[str, Any],
        cls: Any,
        markdown_file_path: str,
    ) -> dict[str, Any]:
        primary_key = self._get_primary_key_field_code(cls)
        if not primary_key:
            return labels

        resolved = dict(labels)
        resolved[primary_key] = self._generate_primary_key_value(markdown_file_path)
        return resolved

    def _ensure_primary_key_in_records(
        self,
        records: list[dict[str, Any]],
        cls: Any,
    ) -> list[dict[str, Any]]:
        primary_key = self._get_primary_key_field_code(cls)
        if not primary_key or not records:
            return records

        normalized_records: list[dict[str, Any]] = []
        for record in records:
            if primary_key in record and record[primary_key] not in (None, ""):
                normalized_records.append(record)
                continue
            file_path = str(record.get("filePath") or "")
            if not file_path:
                normalized_records.append(record)
                continue
            updated = dict(record)
            updated[primary_key] = self._generate_primary_key_value(file_path)
            normalized_records.append(updated)
        return normalized_records

    @staticmethod
    def _get_primary_key_field_code(cls: Any) -> str | None:
        for field in getattr(cls, "fields", []):
            if getattr(field, "is_primary_key", False):
                return str(getattr(field, "field_code", "") or "")
        return None

    @staticmethod
    def _generate_primary_key_value(file_path: str) -> str:
        """Generate the KB primary key from the final Markdown file name."""
        file_name = PurePosixPath(file_path).name or "document.md"
        digest = hashlib.sha1(file_name.encode("utf-8")).hexdigest()[:12]
        return f"{digest}"

    @staticmethod
    def _get_kb_id(cls: Any) -> str | None:
        ext_property = getattr(cls, "ext_property", {}) or {}
        if isinstance(ext_property, dict):
            value = ext_property.get("kb_id") or ext_property.get("knCode")
            if value:
                return str(value)
        # fallback: submit_object 新路径将 kb_id 存入 source_config
        source_config = getattr(cls, "source_config", {}) or {}
        if isinstance(source_config, dict):
            value = source_config.get("kb_id") or source_config.get("knCode")
            if value:
                return str(value)
        return None

    @staticmethod
    def _get_kb_resource_id(cls: Any) -> str | None:
        ext_property = getattr(cls, "ext_property", {}) or {}
        if isinstance(ext_property, dict):
            value = ext_property.get("kb_resource_id")
            if value:
                return str(value)
        # fallback: submit_object 新路径将 kb_id 存入 source_config
        source_config = getattr(cls, "source_config", {}) or {}
        if isinstance(source_config, dict):
            value = source_config.get("kb_resource_id")
            if value:
                return str(value)
        return None

    @staticmethod
    def _get_kb_directory(cls: Any) -> str | None:
        ext_property = getattr(cls, "ext_property", {}) or {}
        if isinstance(ext_property, dict):
            value = ext_property.get("kb_directory")
            if value:
                return str(value)
        # fallback: submit_object 新路径将 kb_directory 存入 source_config
        source_config = getattr(cls, "source_config", {}) or {}
        if isinstance(source_config, dict):
            value = source_config.get("kb_directory")
            if value:
                return str(value)
        return None

    @staticmethod
    def _get_datasource_alias(cls: Any) -> str:
        return str(getattr(cls, "datasource_alias", "") or getattr(cls, "object_code", "") or "")

    @staticmethod
    def _normalize_filters(filters: Any) -> dict[str, Any]:
        if isinstance(filters, dict):
            normalized: dict[str, Any] = {}
            for field_code, value in filters.items():
                if isinstance(value, dict) and "op" in value:
                    normalized[str(field_code)] = value
                else:
                    normalized[str(field_code)] = {"op": "eq", "value": value}
            return normalized
        if not isinstance(filters, list):
            return {}

        normalized: dict[str, Any] = {}
        for item in filters:
            if not isinstance(item, dict):
                continue
            field_code = str(item.get("field", "") or "")
            op = str(item.get("op", "eq") or "eq")
            if not field_code:
                continue
            normalized[field_code] = {"op": op, "value": item.get("value")}
        return normalized

    @staticmethod
    def _normalize_string_list(value: Any) -> list[str]:
        if isinstance(value, list):
            return [str(item) for item in value if str(item)]
        if isinstance(value, str) and value:
            return [value]
        return []

    @staticmethod
    def _normalize_order_by(value: Any) -> list[dict[str, Any]]:
        if not isinstance(value, list):
            return []
        order_by: list[dict[str, Any]] = []
        for item in value:
            if not isinstance(item, dict):
                continue
            field = str(item.get("field", "") or "")
            if not field:
                continue
            direction = str(item.get("direction", "asc") or "asc").lower()
            if direction not in ("asc", "desc"):
                direction = "asc"
            order_by.append({"field": field, "direction": direction})
        return order_by

    @staticmethod
    def _empty_response(
        object_code: str,
        arguments: dict[str, Any],
        note: str,
        *,
        error: bool = False,
        meta_extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        meta: dict[str, Any] = {
            "object_code": object_code,
            "query": arguments.get("query", ""),
            "note": note,
        }
        if meta_extra:
            meta.update(meta_extra)
        if error:
            meta["error"] = note
        return {
            "records": [],
            "total": 0,
            "meta": meta,
        }


def _write_summary(kb_paths: list[str], session_paths: list[str]) -> str:
    """Build a human-readable summary of a KB write operation."""
    lines: list[str] = []
    if kb_paths:
        paths_str = ", ".join(kb_paths)
        lines.append(f"已成功写入知识库，文件路径：{paths_str}")
    if session_paths:
        paths_str = ", ".join(session_paths)
        lines.append(f"同时把已打标的文件写入到会话空间，路径：{paths_str}")
    return "；".join(lines) if lines else "写入完成"


def _attach_session_file(
    response: dict[str, Any],
    write_requests: list[KnowledgeWriteRequest],
) -> None:
    """Write each KB upload into the session's ResultFileStorage.

    File name mirrors the Markdown path used by the KB backend (via
    ``_to_markdown_file_path``).  Labels are rendered as YAML front matter
    (via ``_render_markdown_with_front_matter``) so metadata is embedded
    exactly as it is uploaded to the knowledge base.

    The first written logical path is attached to ``response["file"]``.
    Failures are non-fatal: a warning is logged and the caller continues.
    """
    if not write_requests:
        return

    import os

    from datacloud_data_sdk.context import get_current_context
    from datacloud_data_sdk.exceptions import DatacloudError
    from datacloud_data_sdk.file_storage.base import ResultFileStorage
    from datacloud_data_sdk.file_storage.local import LocalResultFileStorage

    try:
        try:
            ctx = get_current_context()
        except DatacloudError:
            ctx = None

        storage: ResultFileStorage = getattr(ctx, "result_file_storage", None)  # type: ignore[assignment]
        if not isinstance(storage, ResultFileStorage):
            workspace_dir = str(getattr(ctx, "workspace_dir", "") or "").strip() if ctx else ""
            storage = LocalResultFileStorage(workspace_dir or os.getcwd())

        written_paths: list[str] = []
        for req in write_requests:
            # Derive the same filename the KB backend uses when it stores the file.
            markdown_file_path = _to_markdown_file_path(req.file_path, req.kb_directory)
            file_name = PurePosixPath(markdown_file_path).name or "document.md"
            logical_path = f"/datacloud/kb/{file_name}"

            # Render content with YAML front-matter labels, identical to the KB upload.
            related_docs = _parse_related_docs(req.content)
            effective_labels = _merge_related_docs_into_labels(req.labels, related_docs)
            clean_content = _strip_related_docs_blocks(req.content)
            file_content = _render_markdown_with_front_matter(effective_labels, clean_content)

            storage.write_text(logical_path, file_content)
            written_paths.append(logical_path)
            logger.debug("kb write: saved session file %s", logical_path)

        if written_paths:
            response["file"] = {"file_url": written_paths[0], "file_urls": written_paths}
    except Exception:  # noqa: BLE001
        logger.warning("kb write: failed to save session md file", exc_info=True)


def _field_meta(fields: list[Any]) -> list[dict[str, str]]:
    return [
        {
            "name": str(getattr(field, "field_code", "")),
            "label": str(getattr(field, "field_name", "")),
            "type": str(getattr(field, "field_type", "STRING") or "STRING").lower(),
        }
        for field in fields
    ]


def _standard_action_meta(
    cls: Any,
    datasource_alias: str,
    query: str,
    *,
    include_content: bool = False,
) -> dict[str, Any]:
    return {
        "columns": _action_columns(list(getattr(cls, "fields", [])), include_content),
        "object_code": str(getattr(cls, "object_code", "")),
        "datasource_alias": datasource_alias,
        "query": query,
    }


def _action_columns(fields: list[Any], include_content: bool) -> list[dict[str, str]]:
    columns = _field_meta(fields)
    existing_names = {column["name"] for column in columns}
    for column in (
        {"name": "fileName", "label": "文件名称", "type": "string"},
        {"name": "filePath", "label": "文件路径", "type": "string"},
    ):
        if column["name"] not in existing_names:
            columns.append(column)
            existing_names.add(column["name"])
    if include_content and "content" not in existing_names:
        columns.append({"name": "content", "label": "文件内容", "type": "string"})
    return columns


def _normalize_action_records(
    records: list[dict[str, Any]],
    cls: Any,
    *,
    include_content: bool = False,
) -> list[dict[str, Any]]:
    field_codes = [
        str(getattr(field, "field_code", ""))
        for field in getattr(cls, "fields", [])
        if str(getattr(field, "field_code", ""))
    ]
    normalized: list[dict[str, Any]] = []
    for record in records:
        if not isinstance(record, dict):
            continue
        item = {field_code: record.get(field_code) for field_code in field_codes}
        file_path = str(record.get("filePath") or "")
        item["fileName"] = str(record.get("fileName") or _file_name_from_path(file_path))
        item["filePath"] = file_path
        if include_content:
            item["content"] = str(record.get("content") or "")
        normalized.append(item)
    return normalized


def _file_name_from_path(file_path: str) -> str:
    if not file_path:
        return ""
    return PurePosixPath(file_path).name


def _metadata_field_types(fields: list[Any]) -> dict[str, str]:
    return {
        str(getattr(field, "field_code", "")): _metadata_value_type(field, None)
        for field in fields
        if str(getattr(field, "field_code", ""))
    }


def _metadata_properties_from_labels(labels: dict[str, Any], cls: Any) -> list[dict[str, Any]]:
    field_map = {str(field.field_code): field for field in getattr(cls, "fields", [])}
    properties: list[dict[str, Any]] = []
    for property_name, value in labels.items():
        name = str(property_name)
        field = field_map.get(name)
        property_def: dict[str, Any] = {
            "propertyName": name,
            "valueType": _metadata_value_type(field, value),
        }
        description = (
            getattr(field, "description", None) or getattr(field, "field_name", None)
            if field is not None
            else None
        )
        if description:
            property_def["description"] = str(description)
        properties.append(property_def)
    return properties


def _metadata_value_type(field: Any | None, value: Any) -> str:
    if isinstance(value, list):
        return "stringList"

    field_type = str(getattr(field, "field_type", "") or "").upper()
    if field_type == "ARRAY":
        return "stringList"
    if field_type in {"INTEGER", "NUMBER", "FLOAT", "DOUBLE", "DECIMAL", "BIGINT"}:
        return "number"
    if field_type in {"BOOLEAN", "BOOL"}:
        return "boolean"
    if field_type in {"DATE", "DATETIME", "TIME", "TIMESTAMP"}:
        return "datetime"
    return "string"
