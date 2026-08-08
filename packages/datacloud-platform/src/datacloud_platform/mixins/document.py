"""文档领域的跨后端业务编排。

职责边界
--------
本模块只负责组合 Platform 已提供的术语、关系、对象定义、文档库和服务发现能力，
不直接拼装知识库 HTTP 请求。外部协议由 ``backends`` 定义、由 ``adapters`` 实现，
本模块使用的 Pydantic 入出参统一位于 ``datacloud_platform.models.document``。

对外能力
--------
* ``query_document_objects``：按知识库、处理状态和对象编码分页查询文档对象。
* ``query_related_document_objects``：查询某术语的直接关系及两端文档信息。
* ``get_document_content_by_term_id``：由术语定位知识库文件并读取全文。
* ``search_knowledge_fragments``：按对象目录检索知识片段并回填术语信息。
* ``process_document_discovery``：异步发现对象实例并维护文档处理状态。
* ``process_document_enrichment``：异步富化文档、写回知识库并维护处理状态。

状态流转
--------
发现流程为 ``待发现/发现失败-待重试 -> 发现中 -> 已完成``；发现返回的 Document
实例登记为 ``待整理``。富化流程为 ``待整理/整理失败-待重试 -> 整理中 -> 已完成``。
单文档异常分别落为 ``发现失败-待重试`` 或 ``整理失败-待重试``，不会中断同批次
其他文档。
"""

from __future__ import annotations

import inspect
import json
import logging
import re
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from dataclasses import asdict, is_dataclass
from datetime import UTC, datetime, timedelta
from pathlib import PurePosixPath
from typing import Any, Protocol

from yaml import safe_dump, safe_load

from datacloud_platform.models.document import (
    DocumentAsyncProcessingRequest,
    DocumentContentResult,
    DocumentEnrichObjectScope,
    DocumentEnrichRelation,
    DocumentEnrichStatus,
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

logger = logging.getLogger(__name__)
# 内部分页固定使用较大的批量，先形成候选快照，再逐文档加锁处理。
_DOCUMENT_PAGE_SIZE = 200
# Redis 锁用于避免不同进程重复消费同一个知识库文档。
_DOCUMENT_LOCK_TTL_SECONDS = 3600


class _DocumentPlatform(Protocol):
    """DocumentMixin 所依赖的 Platform 最小能力协议。

    该协议只用于说明编排层的依赖方向；具体实现由 ``DatacloudPlatform`` 组合对应
    backend/adapter mixin 后提供。
    """

    def search_terms(self, base_id: str, **kwargs: Any) -> Any: ...
    def search_terms_by_labels(
        self, base_id: str, **kwargs: Any
    ) -> list[dict[str, Any]]: ...
    def query_term_relations(self, base_id: str, **kwargs: Any) -> Any: ...
    def get_object_detail(
        self, base_id: str, object_code: str
    ) -> dict[str, Any] | None: ...
    def get_term_detail(
        self, base_id: str, *, library_id: str, term_id: str
    ) -> Any: ...
    async def search_knowledge_item_metadata(
        self, base_id: str, *, payload: dict[str, Any]
    ) -> MetadataSearchPage: ...
    async def read_knowledge_document(
        self, base_id: str, *, resource_id: str, file_path: str
    ) -> str: ...
    async def search_knowledge_items(
        self, base_id: str, *, payload: dict[str, Any]
    ) -> tuple[dict[str, Any], ...]: ...
    async def discover_object_instances_unstructured(
        self,
        base_id: str,
        *,
        instance_id: str,
        object_codes: list[str],
        session_id: str,
    ) -> Any: ...
    async def save_or_update_object_files(
        self, base_id: str, *, object_files: list[dict[str, Any]]
    ) -> Any: ...


class DocumentMixin:
    """文档领域的 Platform 级业务编排入口。

    Mixin 由 ``DatacloudPlatform`` 继承。方法只负责编排，不绕过 Platform 直接访问
    知识库；文档库请求最终通过 ``DocumentLibraryBackend`` 及其 Adapter 发出。
    """

    async def process_document_discovery(
        self: Any,
        *,
        base_id: str,
        session_id: str,
        request: DocumentAsyncProcessingRequest,
    ) -> None:
        """异步处理等待发现或可自动重试的文档。

        业务流程：分页查询状态为“待发现、发现失败-待重试”的文档；逐文档获取分布式
        锁；调用 ``discover_object_instances_unstructured``；登记返回的 Document
        实例并更新源文档状态；最后把实体数量或失败原因追加到当前会话空间的进度
        文件。单个文档失败不会终止整批任务。

        Args:
            base_id: 本体库/系统空间标识，用于术语及文档对象查询。
            session_id: 请求 Header 中的会话 ID，写处理日志时随记录保存。
            request: 异步处理请求，包含知识库资源 ID、对象编码和模型配置。

        Returns:
            无返回值。该方法用于后台任务，处理结果写入会话空间。
        """
        await _process_document_pages(
            self,
            base_id=base_id,
            session_id=session_id,
            request=request,
            statuses=(
                DocumentProcessingStatus.PENDING_DISCOVERY,
                DocumentProcessingStatus.DISCOVERY_RETRY,
            ),
            operation="discovery",
        )

    async def process_document_enrichment(
        self: Any,
        *,
        base_id: str,
        session_id: str,
        request: DocumentAsyncProcessingRequest,
    ) -> None:
        """异步富化等待整理或可自动重试的文档。

        查询“待整理、整理失败-待重试”文档。更新时间间隔和关系出入差值由
        ``_process_document_pages`` 的可选参数控制，当前入口未启用这两个限制。每个
        文档持锁调用 ``enrich``，成功后通过对象 ``write_*`` 动作写回数据，并在处理
        前后通过服务发现更新对象文件状态。

        Args:
            base_id: 本体库/系统空间标识。
            session_id: 请求 Header 中的会话 ID。
            request: 知识库范围、对象范围和模型配置。

        Returns:
            无返回值。富化内容及执行结果写入会话空间。
        """
        await _process_document_pages(
            self,
            base_id=base_id,
            session_id=session_id,
            request=request,
            statuses=(
                DocumentProcessingStatus.PENDING_ORGANIZATION,
                DocumentProcessingStatus.ORGANIZATION_RETRY,
            ),
            operation="enrichment",
            # organization_interval_seconds=7200,
            # relation_in_out_difference=10,
        )

    @asynccontextmanager
    async def document_processing_lock(self, *, lock_key: str) -> AsyncIterator[bool]:
        """通过 redis-py 非阻塞获取单文档分布式锁。

        Args:
            lock_key: 锁的唯一键，由操作类型、base_id、kb_resource_id 和 term_id 组成。

        Yields:
            ``True`` 表示当前任务取得锁，可以处理文档；``False`` 表示其他节点正在
            处理同一文档，调用方应跳过。

        Notes:
            锁 TTL 为 3600 秒。退出上下文时由 redis-py 校验 token 并原子释放；如果
            业务执行超过 TTL 导致锁已失效，只记录告警，不覆盖原业务结果。
        """
        from datacloud_platform.redis_client import create_async_redis_client

        client = create_async_redis_client()
        lock = client.lock(
            lock_key,
            timeout=_DOCUMENT_LOCK_TTL_SECONDS,
            blocking_timeout=0,
        )
        acquired = bool(await lock.acquire(blocking=False))
        try:
            yield acquired
        finally:
            if acquired:
                try:
                    await lock.release()
                except Exception as exc:  # noqa: BLE001
                    if type(exc).__name__ != "LockNotOwnedError":
                        raise
                    logger.warning("Document lock expired before release: %s", lock_key)
            await client.aclose()

    async def discover_document_entities_todo(
        self,
        *,
        document: DocumentObjectItem,
        object_codes: tuple[str, ...],
        model_config: dict[str, Any] | None,
    ) -> int:
        """旧的文档发现扩展点，保留用于兼容调用方。

        当前异步发现主流程已经改用 ``discover_object_instances_unstructured``，本方法
        不再由 ``process_document_discovery`` 调用。

        Args:
            document: 待处理文档对象，包含术语、知识库和文件路径信息。
            object_codes: 允许发现的对象类型编码。
            model_config: 调用方传入的模型及推理配置，当前按原结构透传。

        Returns:
            从该文档中成功发现并写入的实体数量。

        Raises:
            NotImplementedError: 当前仅定义扩展协议，尚未接入实体发现实现。
        """
        raise NotImplementedError("document entity discovery is not implemented")

    def append_document_session_report(self, **report: Any) -> None:
        """向当前会话空间追加一条文档处理结果。

        Args:
            **report: JSON 可序列化的处理信息，通常包含 session_id、operation、
                term_id、file_path、status，以及 entity_count 或 error。

        Returns:
            无返回值。数据以 JSON Lines 格式追加到
            ``/datacloud/document-processing/progress.jsonl``。
        """
        storage = _current_result_file_storage()
        storage.append_text(
            "/datacloud/document-processing/progress.jsonl",
            json.dumps(report, ensure_ascii=False, default=str) + "\n",
        )

    async def query_document_objects(
        self: _DocumentPlatform,
        base_id: str,
        *,
        request: QueryDocumentObjectsRequest,
    ) -> DocumentObjectPage:
        """按文档元数据条件分页查询文档对象。

        业务流程：可选地根据关系出入差值解析候选术语及文件路径；当对象编码非空
        时读取对象详情中的 ``kb_resource_id`` 与 ``kb_directory``，前者和调用方指定
        的知识库范围求交，后者组装为文件路径前缀条件；随后调用
        ``metadataSearch``，按 ``knCode + filePath`` 回查术语并用对象编码过滤。
        核心 DSL 为 ``(filePath IN 候选路径 OR dc_status IN 状态) AND
        filePath PREFIX 对象目录 AND
        updatedAt < now - organizationIntervalSeconds``，其中各部分均按请求条件可选。

        Args:
            base_id: 本体库/系统空间标识。
            request: 查询条件，包含 kb_resource_ids、状态、对象编码、整理间隔、关系
                出入差值及分页参数。

        Returns:
            ``DocumentObjectPage``，包含术语 ID/名称/编码/类型、文件路径、知识库资源
            ID、处理状态、失败信息及分页信息。
        """
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

        effective_kb_resource_ids = request.kb_resource_ids
        object_directories: tuple[str, ...] = ()
        if request.object_codes:
            bound_resource_ids, object_directories = resolve_object_knowledge_scope(
                platform=self,
                base_id=base_id,
                object_codes=request.object_codes,
                allowed_kb_resource_ids=request.kb_resource_ids,
            )
            effective_kb_resource_ids = bound_resource_ids
            if not effective_kb_resource_ids:
                return _build_page([], 0, request.page_index, request.page_size)

        payload = build_metadata_search_payload(
            request=request,
            candidate_file_paths=candidate_file_paths,
            kb_resource_ids=effective_kb_resource_ids,
            object_directories=object_directories,
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
            kb_resource_ids=effective_kb_resource_ids,
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
                if str(
                    row.get("term_type")
                    or row.get("term_type_code")
                    or row.get("termTypeCode")
                    or ""
                )
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
        """查询指定术语的一层直接关系，并补全关系两端文档信息。

        Args:
            base_id: 本体库/系统空间标识。
            request: term_id、关系方向、深度和分页参数。接口用于直接关系时深度为 1。

        Returns:
            关系分页结果。每条关系包含关系属性，以及来源/目标术语的名称、编码、
            term_type_code、kb_resource_id 和 file_path。

        Raises:
            KeyError: 关系引用的来源或目标术语无法批量查询到。
        """
        raw = self.query_term_relations(
            base_id,
            term_id=request.term_id,
            direction=request.direction,
            depth=request.depth,
            term_type_codes=request.object_codes,
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
        """根据术语 ID 定位并读取完整知识库文件。

        Args:
            base_id: 本体库/系统空间标识。
            term_id: 文档术语唯一 ID。

        Returns:
            术语 ID、kb_resource_id、文件路径及完整文本内容。

        Raises:
            KeyError: 术语不存在。
            ValueError: 术语缺少 kb_resource_id 或 kb_file_path。
        """
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
        """在对象绑定的知识库和目录范围内检索文档片段。

        Args:
            base_id: 本体库/系统空间标识。
            request: 对象编码列表、查询文本、最大返回条数 top_k，以及可选的待排除
                术语 ID 列表。排除术语统一解析为文件路径并使用 ``not + in`` 过滤。

        Returns:
            ``DocumentFragmentResult``，每项包含来源知识库、文件路径、chunk 文本、
            得分、行号、图片路径及元数据。

        Raises:
            KeyError: 任一对象编码不存在。
            ValueError: 对象没有知识库绑定，或 kb_resource_id 不是整数。
        """
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
        where_conditions: list[dict[str, Any]] = []
        if directories:
            where_conditions.append(
                {
                    "or": [
                        {"prefix": {"fieldName": "filePath", "value": directory}}
                        for directory in directories
                    ]
                }
            )
        excluded_file_paths = resolve_term_file_paths(
            platform=self,
            base_id=base_id,
            term_ids=request.exclude_term_ids,
        )
        if excluded_file_paths:
            # 已知风险：这里只按 filePath 排除。如果多个知识库存在相同文件路径，
            # 下游检索会把这些知识库中的同路径文件全部排除。
            where_conditions.append(
                {
                    "not": {
                        "in": {
                            "fieldName": "filePath",
                            "value": list(excluded_file_paths),
                        }
                    }
                }
            )
        if len(where_conditions) == 1:
            payload["where"] = where_conditions[0]
        elif where_conditions:
            payload["where"] = {"and": where_conditions}
        rows = await self.search_knowledge_items(base_id, payload=payload)
        term_details = resolve_fragment_term_details(
            platform=self,
            base_id=base_id,
            fragment_rows=rows,
            object_codes=request.object_codes,
        )
        return DocumentFragmentResult(
            items=tuple(
                DocumentFragmentItem.model_validate(
                    {
                        **row,
                        **term_details.get(
                            (
                                str(row.get("resourceId") or ""),
                                str(row.get("filePath") or ""),
                            ),
                            {},
                        ),
                    }
                )
                for row in rows
            )
        )


def resolve_term_file_paths(
    *, platform: Any, base_id: str, term_ids: tuple[str, ...]
) -> tuple[str, ...]:
    """批量解析并去重待排除术语对应的文件路径。"""
    if not term_ids:
        return ()
    rows: list[dict[str, Any]] = []
    for start in range(0, len(term_ids), 200):
        batch = term_ids[start : start + 200]
        result = platform.search_terms(
            base_id,
            term_ids=list(batch),
            top_k=len(batch),
            offset=0,
        )
        rows.extend(_term_result_items(result))
    found_ids = {str(row.get("term_id") or row.get("termId") or "") for row in rows}
    missing_ids = [term_id for term_id in term_ids if term_id not in found_ids]
    if missing_ids:
        raise KeyError(f"terms not found: {', '.join(missing_ids)}")
    file_paths: list[str] = []
    for row in rows:
        metadata = _term_metadata(row)
        file_path = str(metadata.get("kb_file_path") or "")
        if not file_path:
            term_id = str(row.get("term_id") or row.get("termId") or "")
            raise ValueError(f"term file path is missing: term_id={term_id}")
        if file_path not in file_paths:
            file_paths.append(file_path)
    return tuple(file_paths)


def resolve_fragment_term_details(
    *,
    platform: Any,
    base_id: str,
    fragment_rows: tuple[dict[str, Any], ...],
    object_codes: tuple[str, ...],
) -> dict[tuple[str, str], dict[str, str]]:
    """批量回查 chunk 来源文件对应的文档术语信息。

    Args:
        platform: 提供 ``search_terms_by_labels`` 的 Platform。
        base_id: 本体库/系统空间标识。
        fragment_rows: 文档库 chunk 检索的原始命中列表。其中 ``knCode`` 是门户
            kb_resource_id，``filePath`` 是知识库内完整文件路径。
        object_codes: 调用方允许的对象编码，即术语的 term_type_code。

    Returns:
        以 ``(kb_resource_id, file_path)`` 为键的术语字段映射，字段包含 termId、
        termCode、termName 和 objectCode。未找到术语的 chunk 保留空字段。
    """
    candidate_keys: set[tuple[str, str]] = set()
    for fragment in fragment_rows:
        kb_resource_id = str(fragment.get("resourceId") or "")
        file_path = str(fragment.get("filePath") or "")
        if kb_resource_id and file_path:
            candidate_keys.add((kb_resource_id, file_path))
    if not candidate_keys:
        return {}
    file_paths = tuple(dict.fromkeys(file_path for _, file_path in candidate_keys))
    result = platform.search_terms_by_labels(
        base_id,
        label_filters=[
            {"field_code": "kb_file_path", "filter_value": file_path}
            for file_path in file_paths
        ],
        label_condition="or",
        term_type_codes=list(object_codes) or None,
        top_k=200,
    )
    allowed_object_codes = set(object_codes)
    details: dict[tuple[str, str], dict[str, str]] = {}
    for row in _term_result_items(result):
        metadata = _term_metadata(row)
        object_code = str(
            row.get("term_type_code")
            or row.get("termTypeCode")
            or row.get("term_type")
            or row.get("termType")
            or ""
        )
        if allowed_object_codes and object_code not in allowed_object_codes:
            continue
        key = (
            str(metadata.get("kb_resource_id") or ""),
            str(
                metadata.get("kb_file_path")
                or metadata.get("file_path")
                or metadata.get("filePath")
                or ""
            ),
        )
        if key not in candidate_keys:
            continue
        details[key] = {
            "termId": str(row.get("term_id") or row.get("termId") or ""),
            "termCode": str(row.get("term_code") or row.get("termCode") or ""),
            "termName": str(row.get("term_name") or row.get("termName") or ""),
            "objectCode": object_code,
        }
    return details


async def _process_document_pages(
    platform: Any,
    *,
    base_id: str,
    session_id: str,
    request: DocumentAsyncProcessingRequest,
    statuses: tuple[DocumentProcessingStatus, ...],
    operation: str,
    organization_interval_seconds: int | None = None,
    relation_in_out_difference: int | None = None,
) -> None:
    """先拉取全部候选页，再按顺序逐文档处理。

    完成分页快照后，一次性加载本次处理需要的本体对象详情，避免在逐文档状态更新时
    重复查询；发现与富化共用该流程，通过 ``operation`` 选择处理分支。

    Args:
        platform: 提供文档查询、锁、发现、富化、动作执行及会话写入能力的 Platform。
        base_id: 本体库/系统空间标识。
        session_id: 会话 ID。
        request: 异步处理范围和模型配置。
        statuses: 本次任务允许消费的文档状态。
        operation: ``discovery`` 或 ``enrichment``。
        organization_interval_seconds: 可选的更新时间间隔秒数。
        relation_in_out_difference: 可选的关系出入差值，不取绝对值。

    Returns:
        无返回值。候选文档逐项处理，结果写入对象文件状态接口和会话报告。

    Notes:
        本函数先读取完全部分页，确保处理过程中状态更新时间变化不会导致翻页遗漏；
        随后按对象编码去重加载 scope，并在整批任务中复用。
    """
    page_index = 1
    documents: list[DocumentObjectItem] = []
    while True:
        page = await platform.query_document_objects(
            base_id,
            request=QueryDocumentObjectsRequest(
                kbResourceIds=request.kb_resource_ids,
                statuses=statuses,
                objectCodes=request.object_codes,
                organizationIntervalSeconds=organization_interval_seconds,
                relationInOutDifference=relation_in_out_difference,
                pageIndex=page_index,
                pageSize=_DOCUMENT_PAGE_SIZE,
            ),
        )
        documents.extend(page.items)
        if page_index >= page.pagination.total_pages:
            break
        page_index += 1
    total_documents = len(documents)
    logger.info(
        "Document %s batch started: base_id=%s session_id=%s total_documents=%s",
        operation,
        base_id,
        session_id,
        total_documents,
    )
    # 请求对象和实际候选文档对象统一前置加载。发现结果只能使用这份明确的 scope，
    # 避免模型返回未配置对象编码时在逐项构造阶段临时扩张处理范围。
    scope_codes = list(
        dict.fromkeys(
            (
                *request.object_codes,
                *(document.term_type_code for document in documents),
            )
        )
    )
    object_scope_by_code = {
        object_code: _resolve_document_object_scope(
            platform=platform,
            base_id=base_id,
            object_code=object_code,
        )
        for object_code in scope_codes
    }
    for current, document in enumerate(documents, start=1):
        logger.info(
            "Document %s processing started: current=%s total=%s term_id=%s "
            "kb_resource_id=%s file_path=%s object_code=%s",
            operation,
            current,
            total_documents,
            document.term_id,
            document.kb_resource_id,
            document.file_path,
            document.term_type_code,
        )
        await _process_one_document(
            platform,
            base_id=base_id,
            session_id=session_id,
            request=request,
            document=document,
            operation=operation,
            object_scope_by_code=object_scope_by_code,
        )
        logger.info(
            "Document %s progress: processed=%s total=%s term_id=%s",
            operation,
            current,
            total_documents,
            document.term_id,
        )
    logger.info(
        "Document %s batch completed: base_id=%s session_id=%s "
        "processed=%s total_documents=%s",
        operation,
        base_id,
        session_id,
        total_documents,
        total_documents,
    )


async def _process_one_document(
    platform: Any,
    *,
    base_id: str,
    session_id: str,
    request: DocumentAsyncProcessingRequest,
    document: DocumentObjectItem,
    operation: str,
    object_scope_by_code: dict[str, DocumentEnrichObjectScope] | None = None,
) -> None:
    """在分布式锁保护下处理一个文档并记录结果。

    未取得锁时只写会话报告 ``skipped_locked``。取得锁后，发现和富化都先把源文档
    更新为处理中状态；成功时更新为 ``已完成``，异常时更新为对应的待重试状态。
    异常不会继续向上抛出，因此不会中断批次中其他文档。

    发现成功时，先通过源对象 ``write_*`` 动作把知识库文件标签更新为 ``已完成``；
    返回的所有对象实例都会按各自 ``object_code`` 构造成 ``待整理`` 对象文件记录，
    并与源文档的 ``已完成`` 门户状态在同一次服务调用中批量提交。富化成功时，从
    write action 返回记录中优先提取实际文件名、路径和 term_id。

    Args:
        platform: 文档处理 Platform。
        base_id: 本体库/系统空间标识，用于组成锁键。
        session_id: 写入处理报告的会话 ID。
        request: 对象范围和模型配置。
        document: 当前处理的文档对象。
        operation: ``discovery`` 或 ``enrichment``。
        object_scope_by_code: 前置加载并在本批次复用的对象编码到对象详情映射。

    Returns:
        无返回值。所有业务结果通过状态接口、知识库写动作或会话报告产生副作用。
    """
    if object_scope_by_code is None:
        object_scope_by_code = {
            object_code: _resolve_document_object_scope(
                platform=platform,
                base_id=base_id,
                object_code=object_code,
            )
            for object_code in request.object_codes
        }
    lock_key = (
        f"datacloud:document:{operation}:{base_id}:"
        f"{document.kb_resource_id}:{document.term_id}"
    )
    async with platform.document_processing_lock(lock_key=lock_key) as acquired:
        if not acquired:
            logger.info(
                "Document %s processing skipped: term_id=%s kb_resource_id=%s "
                "file_path=%s status=skipped_locked",
                operation,
                document.term_id,
                document.kb_resource_id,
                document.file_path,
            )
            platform.append_document_session_report(
                session_id=session_id,
                operation=operation,
                term_id=document.term_id,
                file_path=document.file_path,
                status="skipped_locked",
            )
            return
        operation_error_logged = False
        try:
            source_scope = _get_or_resolve_document_object_scope(
                platform=platform,
                base_id=base_id,
                object_scope_by_code=object_scope_by_code,
                object_code=document.term_type_code,
            )
            if operation == "discovery":
                # 第一次状态调用：源文档进入“发现中”。
                await _save_document_processing_status(
                    platform=platform,
                    base_id=base_id,
                    session_id=session_id,
                    document=document,
                    object_scope=source_scope,
                    status=DocumentProcessingStatus.DISCOVERING,
                )
                try:
                    discovery_result = (
                        await platform.discover_object_instances_unstructured(
                            base_id,
                            instance_id=document.term_id,
                            object_codes=list(request.object_codes),
                        )
                    )
                except Exception as exc:  # noqa: BLE001
                    operation_error_logged = True
                    logger.exception(
                        "discover_object_instances_unstructured failed: "
                        "base_id=%s term_id=%s kb_resource_id=%s file_path=%s error=%s",
                        base_id,
                        document.term_id,
                        document.kb_resource_id,
                        document.file_path,
                        exc,
                    )
                    raise
                (
                    source_labels,
                    source_action_result,
                ) = await _update_discovered_source_document(
                    platform=platform,
                    base_id=base_id,
                    document=document,
                    object_scope=source_scope,
                )
                discovered_document_files = _build_discovered_document_files(
                    session_id=session_id,
                    items=discovery_result.items,
                    object_scope_by_code=object_scope_by_code,
                )
                # 第二次状态调用：新 Document=待整理，源文档=已完成，批量提交。
                await _save_document_processing_status(
                    platform=platform,
                    base_id=base_id,
                    session_id=session_id,
                    document=document,
                    object_scope=source_scope,
                    status=DocumentProcessingStatus.COMPLETED,
                    labels=source_labels,
                    action_result=source_action_result,
                    related_object_files=discovered_document_files,
                )
                platform.append_document_session_report(
                    session_id=session_id,
                    operation=operation,
                    term_id=document.term_id,
                    file_path=document.file_path,
                    status="completed",
                    entity_count=len(discovery_result.items),
                )
                logger.info(
                    "Document discovery processing finished: term_id=%s "
                    "kb_resource_id=%s file_path=%s status=%s entity_count=%s",
                    document.term_id,
                    document.kb_resource_id,
                    document.file_path,
                    DocumentProcessingStatus.COMPLETED.value,
                    len(discovery_result.items),
                )
            else:
                from datacloud_platform.services.object_action import (
                    invoke_object_write_action,
                )

                target_object = source_scope
                # 富化开始前先抢占状态，防止其他消费者再次选中该文档。
                await _save_document_processing_status(
                    platform=platform,
                    base_id=base_id,
                    session_id=session_id,
                    document=document,
                    object_scope=target_object,
                    status=DocumentProcessingStatus.ORGANIZING,
                )
                try:
                    enrich_result = await platform.enrich(
                        base_id,
                        object_scope=list(object_scope_by_code.values()),
                        target_object=target_object,
                        term_id=document.term_id,
                    )
                except Exception as exc:  # noqa: BLE001
                    operation_error_logged = True
                    logger.exception(
                        "enrich failed: base_id=%s term_id=%s kb_resource_id=%s "
                        "file_path=%s error=%s",
                        base_id,
                        document.term_id,
                        document.kb_resource_id,
                        document.file_path,
                        exc,
                    )
                    raise
                content = enrich_result.enriched_content
                processing_status = _processing_status_for_enrich_result(
                    enrich_result.status
                )
                action_result: dict[str, Any] | None = None
                action_labels: dict[str, Any] = {}
                if content.strip():
                    # 关系块会在知识库写入层解析为关系标签，front matter 转为业务标签。
                    content = _append_related_docs_block(
                        platform=platform,
                        base_id=base_id,
                        content=content,
                        relations=enrich_result.relations,
                        object_scope_by_code=object_scope_by_code,
                    )
                    content_labels = _extract_front_matter_labels(content)
                    action_labels = {
                        **content_labels,
                        "dc_status": processing_status.value,
                        "dc_failure_reason": enrich_result.exception_info,
                        "dc_failure_count": document.failure_count
                        + int(enrich_result.status is DocumentEnrichStatus.FAILED),
                        "dc_last_organized_at": datetime.now(UTC).isoformat(),
                    }
                    action_result = await invoke_object_write_action(
                        platform=platform,
                        base_id=base_id,
                        object_code=target_object.object_code,
                        content=content,
                        labels=action_labels,
                        file_description=f"{document.term_name}富化文档",
                        source_path=document.file_path,
                    )
                elif enrich_result.status is DocumentEnrichStatus.FAILED:
                    action_labels = _build_failure_processing_labels(
                        document=document,
                        status=DocumentProcessingStatus.ORGANIZATION_RETRY,
                        failure_reason=enrich_result.exception_info,
                    )
                    action_result = await _write_source_document_labels(
                        platform=platform,
                        base_id=base_id,
                        document=document,
                        object_scope=target_object,
                        labels=action_labels,
                        file_description=f"{document.term_name}富化失败状态",
                    )
                await _save_document_processing_status(
                    platform=platform,
                    base_id=base_id,
                    session_id=session_id,
                    document=document,
                    object_scope=target_object,
                    status=processing_status,
                    labels=action_labels,
                    action_result=action_result,
                )
                logger.info(
                    "Document enrichment processing finished: term_id=%s "
                    "kb_resource_id=%s file_path=%s status=%s enrich_status=%s",
                    document.term_id,
                    document.kb_resource_id,
                    document.file_path,
                    processing_status.value,
                    enrich_result.status.value,
                )
        except Exception as exc:  # noqa: BLE001
            if not operation_error_logged:
                logger.exception(
                    "Document %s processing failed: base_id=%s term_id=%s "
                    "kb_resource_id=%s file_path=%s error=%s",
                    operation,
                    base_id,
                    document.term_id,
                    document.kb_resource_id,
                    document.file_path,
                    exc,
                )
            if operation == "discovery":
                failure_labels = _build_failure_processing_labels(
                    document=document,
                    status=DocumentProcessingStatus.DISCOVERY_RETRY,
                    failure_reason=str(exc),
                )
                failure_action_result: dict[str, Any] | None = None
                try:
                    source_scope = _get_or_resolve_document_object_scope(
                        platform=platform,
                        base_id=base_id,
                        object_scope_by_code=object_scope_by_code,
                        object_code=document.term_type_code,
                    )
                    failure_action_result = await _write_source_document_labels(
                        platform=platform,
                        base_id=base_id,
                        document=document,
                        object_scope=source_scope,
                        labels=failure_labels,
                        file_description=f"{document.term_name}对象发现失败状态",
                    )
                except Exception:  # noqa: BLE001
                    logger.exception(
                        "Failed to write discovery failure labels: %s",
                        document.term_id,
                    )
                try:
                    await _save_document_processing_status(
                        platform=platform,
                        base_id=base_id,
                        session_id=session_id,
                        document=document,
                        object_scope=source_scope,
                        status=DocumentProcessingStatus.DISCOVERY_RETRY,
                        labels=failure_labels,
                        action_result=failure_action_result,
                    )
                except Exception:  # noqa: BLE001
                    logger.exception(
                        "Failed to persist discovery failure status: %s",
                        document.term_id,
                    )
                platform.append_document_session_report(
                    session_id=session_id,
                    operation=operation,
                    term_id=document.term_id,
                    file_path=document.file_path,
                    status="failed",
                    error=str(exc),
                )
                logger.error(
                    "Document discovery processing finished: term_id=%s "
                    "kb_resource_id=%s file_path=%s status=%s error=%s",
                    document.term_id,
                    document.kb_resource_id,
                    document.file_path,
                    DocumentProcessingStatus.DISCOVERY_RETRY.value,
                    exc,
                )
            else:
                failure_labels = _build_failure_processing_labels(
                    document=document,
                    status=DocumentProcessingStatus.ORGANIZATION_RETRY,
                    failure_reason=str(exc),
                )
                failure_action_result = None
                try:
                    target_object = _get_or_resolve_document_object_scope(
                        platform=platform,
                        base_id=base_id,
                        object_scope_by_code=object_scope_by_code,
                        object_code=document.term_type_code,
                    )
                    failure_action_result = await _write_source_document_labels(
                        platform=platform,
                        base_id=base_id,
                        document=document,
                        object_scope=target_object,
                        labels=failure_labels,
                        file_description=f"{document.term_name}富化失败状态",
                    )
                except Exception:  # noqa: BLE001
                    logger.exception(
                        "Failed to write enrichment failure labels: %s",
                        document.term_id,
                    )
                try:
                    await _save_document_processing_status(
                        platform=platform,
                        base_id=base_id,
                        session_id=session_id,
                        document=document,
                        object_scope=target_object,
                        status=DocumentProcessingStatus.ORGANIZATION_RETRY,
                        labels=failure_labels,
                        action_result=failure_action_result,
                    )
                except Exception:  # noqa: BLE001
                    logger.exception(
                        "Failed to persist enrichment failure status: %s",
                        document.term_id,
                    )
                logger.error(
                    "Document enrichment processing finished: term_id=%s "
                    "kb_resource_id=%s file_path=%s status=%s error=%s",
                    document.term_id,
                    document.kb_resource_id,
                    document.file_path,
                    DocumentProcessingStatus.ORGANIZATION_RETRY.value,
                    exc,
                )


def _get_or_resolve_document_object_scope(
    *,
    platform: Any,
    base_id: str,
    object_scope_by_code: dict[str, DocumentEnrichObjectScope],
    object_code: str,
) -> DocumentEnrichObjectScope:
    """从批次缓存获取对象详情，缺失时只查询并缓存一次。

    Args:
        platform: 提供 ``get_object_detail`` 的 Platform。
        base_id: 本体库/系统空间标识。
        object_scope_by_code: 当前批次可变缓存，键为对象编码。
        object_code: 需要解析的 ``term_type_code``。

    Returns:
        包含对象名称、知识库资源 ID、知识库 ID 和目录的对象 scope。
    """
    object_scope = object_scope_by_code.get(object_code)
    if object_scope is None:
        object_scope = _resolve_document_object_scope(
            platform=platform,
            base_id=base_id,
            object_code=object_code,
        )
        object_scope_by_code[object_code] = object_scope
    return object_scope


async def _update_discovered_source_document(
    *,
    platform: Any,
    base_id: str,
    document: DocumentObjectItem,
    object_scope: DocumentEnrichObjectScope,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """通过源对象 write action 把发现完成状态写回知识库文件标签。

    源文件内容保持不变，仅把 ``dc_status`` 更新为“已完成”、清空失败原因并保留当前
    失败次数。返回的标签和动作结果继续用于 ``saveOrUpdateObjectFiles``，确保知识库
    元数据状态与门户对象文件状态一致。

    Returns:
        ``(labels, action_result)``；动作结果中实际文件路径和 term_id 优先用于最终登记。
    """
    labels = build_processing_labels(
        initial_status=DocumentProcessingStatus.COMPLETED,
        labels={
            "dc_status": DocumentProcessingStatus.COMPLETED.value,
            "dc_failure_reason": None,
            "dc_failure_count": document.failure_count,
        },
    )
    action_result = await _write_source_document_labels(
        platform=platform,
        base_id=base_id,
        document=document,
        object_scope=object_scope,
        labels=labels,
        file_description=f"{document.term_name}对象发现完成",
    )
    return labels, action_result


def _build_failure_processing_labels(
    *,
    document: DocumentObjectItem,
    status: DocumentProcessingStatus,
    failure_reason: str | None,
) -> dict[str, Any]:
    """构造可同时写入知识库与门户的失败状态标签。"""
    return build_processing_labels(
        initial_status=status,
        labels={
            "dc_status": status.value,
            "dc_failure_reason": failure_reason,
            "dc_failure_count": document.failure_count + 1,
        },
    )


async def _write_source_document_labels(
    *,
    platform: Any,
    base_id: str,
    document: DocumentObjectItem,
    object_scope: DocumentEnrichObjectScope,
    labels: dict[str, Any],
    file_description: str,
) -> dict[str, Any]:
    """保持源文档正文不变，通过对象写动作更新文件标签。"""
    from datacloud_platform.services.object_action import invoke_object_write_action

    source_content = await platform.get_document_content_by_term_id(
        base_id,
        term_id=document.term_id,
    )
    return await invoke_object_write_action(
        platform=platform,
        base_id=base_id,
        object_code=object_scope.object_code,
        content=source_content.content,
        labels=labels,
        file_description=file_description,
        source_path=source_content.file_path,
    )


async def _save_document_processing_status(
    *,
    platform: Any,
    base_id: str,
    session_id: str,
    document: DocumentObjectItem,
    object_scope: DocumentEnrichObjectScope,
    status: DocumentProcessingStatus,
    labels: Mapping[str, Any] | None = None,
    action_result: Mapping[str, Any] | None = None,
    related_object_files: list[dict[str, Any]] | None = None,
) -> None:
    """使用统一对象文件协议保存源文档及关联文件状态。

    Args:
        platform: 提供 ``save_or_update_object_files`` 的 Platform。
        base_id: 本体库/系统空间标识。
        session_id: 会话 ID，写入每条 ``objectFiles`` 记录。
        document: 需要更新状态的源文档。
        object_scope: 源文档所属对象及知识库定位信息。
        status: 源文档本次要写入的中文处理状态。
        labels: 可选写动作标签，当前用于读取 ``version``。
        action_result: 可选写动作结果，优先提供实际 fileName/filePath/term_id。
        related_object_files: 可选的关联对象文件。它们排在源文档之前，与源文档在同一
            次服务调用中批量保存。

    Returns:
        无返回值，服务返回由 adapter 消费。
    """
    source_object_file = _build_object_file_status(
        session_id=session_id,
        document=document,
        object_scope=object_scope,
        status=status,
        labels=labels,
        action_result=action_result,
    )
    await platform.save_or_update_object_files(
        base_id,
        object_files=[*(related_object_files or []), source_object_file],
    )


def _build_discovered_document_files(
    *,
    session_id: str,
    items: list[Any],
    object_scope_by_code: dict[str, DocumentEnrichObjectScope],
) -> list[dict[str, Any]]:
    """构造全部发现实例的待整理登记数据。

    每项只允许使用批次前置加载的 ``object_scope_by_code``。不在映射中的对象类型会
    被过滤，不在此处临时查询或扩大处理范围。文件路径优先使用发现结果的
    ``file_name``；缺失时按 ``/{kb_directory}/{instance_name}.md`` 生成。

    Returns:
        可直接放入 ``save_or_update_object_files.objectFiles`` 的字典列表。
    """
    object_files: list[dict[str, Any]] = []
    for item in items:
        item_scope = object_scope_by_code.get(item.object_code)
        if item_scope is None:
            continue
        file_path = str(item.file_name or "")
        if not file_path:
            file_name = item.instance_name
            if not file_name.lower().endswith(".md"):
                file_name += ".md"
            file_path = str(
                PurePosixPath("/" + item_scope.kb_directory.strip("/")) / file_name
            )
        discovered_item = DocumentObjectItem(
            termId=item.instance_id,
            termName=item.instance_name,
            termCode=item.instance_code,
            termTypeCode=item.object_code,
            filePath=file_path,
            kbResourceId=str(item.kb_resource_id or item_scope.kb_resource_id),
            status=DocumentProcessingStatus.PENDING_ORGANIZATION,
        )
        result_scope = item_scope.model_copy(
            update={
                "kb_resource_id": str(item.kb_resource_id or item_scope.kb_resource_id),
                "kb_id": str(item.kb_id or item_scope.kb_id),
            }
        )
        object_files.append(
            _build_object_file_status(
                session_id=session_id,
                document=discovered_item,
                object_scope=result_scope,
                status=DocumentProcessingStatus.PENDING_ORGANIZATION,
                action_result={
                    "records": [
                        {
                            "filePath": file_path,
                            "term_id": item.instance_id,
                        }
                    ]
                },
            )
        )
    return object_files


def _processing_status_for_enrich_result(
    status: DocumentEnrichStatus,
) -> DocumentProcessingStatus:
    """把富化执行结果映射为持久化的中文文档处理状态。"""
    return {
        DocumentEnrichStatus.SUCCESS: DocumentProcessingStatus.COMPLETED,
        DocumentEnrichStatus.FAILED: DocumentProcessingStatus.ORGANIZATION_RETRY,
        DocumentEnrichStatus.SKIPPED: DocumentProcessingStatus.PENDING_ORGANIZATION,
    }[status]


def _build_object_file_status(
    *,
    session_id: str,
    document: DocumentObjectItem,
    object_scope: DocumentEnrichObjectScope,
    status: DocumentProcessingStatus,
    labels: Mapping[str, Any] | None = None,
    action_result: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """构造 ``saveOrUpdateObjectFiles`` 的单条 objectFiles 数据。

    文件定位优先采用写动作第一条 record 的返回值；缺失时使用对象知识库目录和源
    文件名兜底。``extContent`` 固定携带 kb_resource_id、kb_id、kb_directory 和
    term_id，供会话文件列表及后续文档处理继续定位知识库对象。

    Returns:
        使用门户字段名的 objectFiles 条目，可直接交给服务发现 adapter。
    """
    labels = labels or {}
    records = action_result.get("records") if action_result else None
    first_record = (
        records[0]
        if isinstance(records, list) and records and isinstance(records[0], Mapping)
        else {}
    )
    fallback_file_name = PurePosixPath(document.file_path).name
    file_name = str(
        first_record.get("fileName")
        or first_record.get("file_name")
        or fallback_file_name
    )
    kb_directory = object_scope.kb_directory.strip()
    if kb_directory and not kb_directory.startswith("/"):
        kb_directory = f"/{kb_directory}"
    fallback_file_path = str(PurePosixPath("/" + kb_directory.strip("/")) / file_name)
    file_path = str(
        first_record.get("filePath")
        or first_record.get("file_path")
        or fallback_file_path
    )
    return {
        "sessionId": session_id,
        "objectName": object_scope.object_name,
        "objectCode": object_scope.object_code,
        "fileName": file_name,
        "filePath": file_path,
        "version": str(labels.get("version") or "1"),
        "statusCd": status.value,
        "extContent": json.dumps(
            {
                "kb_resource_id": object_scope.kb_resource_id,
                "kb_id": object_scope.kb_id,
                "kb_directory": kb_directory,
                "term_id": str(
                    first_record.get("term_id")
                    or first_record.get("termId")
                    or document.term_id
                ),
            },
            ensure_ascii=False,
        ),
    }


def _resolve_document_object_scope(
    *, platform: Any, base_id: str, object_code: str
) -> DocumentEnrichObjectScope:
    """根据术语类型编码查询本体对象的实际编码和名称。"""
    detail = platform.get_object_detail(base_id, object_code)
    if detail is None:
        raise KeyError(f"object not found: {object_code}")
    resolved_code = str(
        detail.get("objectCode") or detail.get("object_code") or object_code
    )
    object_name = str(detail.get("objectName") or detail.get("object_name") or "")
    if not object_name:
        raise KeyError(f"object name not found: {object_code}")
    ext_property = detail.get("extProperty") or detail.get("ext_property") or {}
    if not isinstance(ext_property, Mapping):
        ext_property = {}
    return DocumentEnrichObjectScope(
        objectCode=resolved_code,
        objectName=object_name,
        kbResourceId=str(
            ext_property.get("kb_resource_id") or ext_property.get("kbResourceId") or ""
        ),
        kbId=str(ext_property.get("kb_id") or ext_property.get("kbId") or ""),
        kbDirectory=str(
            ext_property.get("kb_directory") or ext_property.get("kbDirectory") or ""
        ),
    )


def _append_related_docs_block(
    *,
    platform: Any,
    base_id: str,
    content: str,
    relations: tuple[DocumentEnrichRelation, ...],
    object_scope_by_code: Mapping[str, DocumentEnrichObjectScope],
) -> str:
    """根据目标术语类型定位对象，并生成知识库可识别的 ``related_docs`` 块。"""
    if not relations:
        return content

    related_docs: list[dict[str, str]] = []
    target_type_by_term_id: dict[str, str] = {}
    resolved_scopes = dict(object_scope_by_code)
    for relation in relations:
        target_term_id = relation.target_term_id.strip()
        if not target_term_id:
            raise KeyError("target_term_id not found for enriched relation")
        target_object_code = target_type_by_term_id.get(target_term_id)
        if target_object_code is None:
            target_detail = platform.get_term_detail(
                base_id,
                library_id="",
                term_id=target_term_id,
            )
            target_object_code = _term_type_code_from_detail(
                target_detail,
                target_term_id=target_term_id,
            )
            target_type_by_term_id[target_term_id] = target_object_code

        target_scope = resolved_scopes.get(target_object_code)
        if target_scope is None:
            target_scope = _resolve_document_object_scope(
                platform=platform,
                base_id=base_id,
                object_code=target_object_code,
            )
            resolved_scopes[target_object_code] = target_scope
        if not target_scope.kb_resource_id:
            raise KeyError(
                f"kb_resource_id not found for relation target object: "
                f"{target_object_code}"
            )
        if not target_scope.kb_directory:
            raise KeyError(
                f"kb_directory not found for relation target object: "
                f"{target_object_code}"
            )
        file_name = relation.target_instance_name
        if not file_name.lower().endswith(".md"):
            file_name += ".md"
        target_doc_id = str(
            PurePosixPath("/" + target_scope.kb_directory.strip("/")) / file_name
        )
        related_docs.append(
            {
                "target_doc_id": target_doc_id,
                "relation": relation.relation_name,
                "kb_resource_id": target_scope.kb_resource_id,
            }
        )

    yaml_content = safe_dump(
        {"related_docs": related_docs},
        allow_unicode=True,
        sort_keys=False,
        default_flow_style=False,
    ).strip()
    yaml_content = yaml_content.replace("related_docs:\n-", "related_docs:\n\n-", 1)
    return (
        f"{content.rstrip()}\n\n"
        f"--- related_docs ---\n\n"
        f"{yaml_content}\n\n"
        f"--- related_docs ---"
    )


def _term_type_code_from_detail(detail: Any, *, target_term_id: str) -> str:
    """从目标术语详情中提取实际对象编码。"""
    if detail is None:
        raise KeyError(f"relation target term not found: {target_term_id}")
    if isinstance(detail, Mapping):
        raw = detail
    elif hasattr(detail, "model_dump"):
        raw = detail.model_dump()
    elif is_dataclass(detail) and not isinstance(detail, type):
        raw = asdict(detail)
    else:
        raise TypeError("term detail must be a mapping, dataclass, or Pydantic model")
    target_object_code = str(
        raw.get("term_type_code")
        or raw.get("termTypeCode")
        or raw.get("term_type")
        or raw.get("termType")
        or ""
    ).strip()
    if not target_object_code:
        raise KeyError(
            f"term type not found for relation target term: {target_term_id}"
        )
    return target_object_code


_FRONT_MATTER_PATTERN = re.compile(
    r"\A---[ \t]*\r?\n(?P<yaml>.*?)\r?\n---[ \t]*(?:\r?\n|\Z)",
    re.DOTALL,
)


def _extract_front_matter_labels(content: str) -> dict[str, Any]:
    """提取富化文档 YAML front matter，并转换为 JSON 兼容的业务标签。"""
    match = _FRONT_MATTER_PATTERN.match(content)
    if match is None:
        return {}
    parsed = safe_load(match.group("yaml"))
    if parsed is None:
        return {}
    if not isinstance(parsed, Mapping):
        raise ValueError("document front matter must be a mapping")
    normalized = json.loads(json.dumps(dict(parsed), ensure_ascii=False, default=str))
    if not isinstance(normalized, dict):
        raise ValueError("normalized document front matter must be a mapping")
    return {str(key): value for key, value in normalized.items()}


def _current_result_file_storage() -> Any:
    """取得当前请求的结果文件存储，缺失时回退到本地存储。

    Returns:
        实现 ``write_text``/``append_text`` 的 ResultFileStorage。若 InvocationContext
        已配置存储则直接复用，否则以 context.workspace_dir 或当前目录建立本地存储。
    """
    from datacloud_data_sdk.context import get_current_context
    from datacloud_data_sdk.file_storage.base import ResultFileStorage
    from datacloud_data_sdk.file_storage.local import LocalResultFileStorage

    try:
        context = get_current_context()
    except Exception:  # noqa: BLE001
        context = None
    storage = getattr(context, "result_file_storage", None)
    if isinstance(storage, ResultFileStorage):
        return storage
    workspace_dir = str(getattr(context, "workspace_dir", "") or "")
    return LocalResultFileStorage(workspace_dir or ".")


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
    """补齐并校验写入文档对象时使用的 ``dc_`` 处理标签。

    Args:
        initial_status: 调用场景的默认初始状态，通常是“待发现”或“待整理”。
        labels: 调用方已有业务标签；已有 dc_status 优先于默认值。

    Returns:
        合并后的标签，固定包含 dc_status、dc_failure_reason、dc_failure_count 和
        dc_last_organized_at，不修改其他业务标签。

    Raises:
        ValueError: 状态不在枚举中，或失败次数不是非负整数。
    """
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
    kb_resource_ids: tuple[str, ...] | None = None,
    object_directories: tuple[str, ...] = (),
    now: datetime,
) -> dict[str, Any]:
    """构造文档库 ``metadataSearch`` 的 Agent DSL 请求体。

    Args:
        request: 文档对象查询条件和分页参数。
        candidate_file_paths: 由关系出入差值计算得到的候选文件路径。
        kb_resource_ids: 对象绑定与请求范围求交后的有效知识库资源 ID。
        object_directories: 对象详情绑定的知识库目录，作为 filePath 前缀过滤。
        now: 计算更新时间截止点的当前时间，显式传入以便测试。

    Returns:
        下游请求体，条件语义为 ``(filePath IN paths OR dc_status IN statuses)
        AND filePath PREFIX object_directories
        AND updatedAt < now - organizationIntervalSeconds``；知识库资源 ID 写入
        resourceIdList，page_index/page_size 映射为 pageNum/pageSize。
    """
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
    if object_directories:
        and_conditions.append(
            {
                "or": [
                    {"prefix": {"fieldName": "filePath", "value": directory}}
                    for directory in object_directories
                ]
            }
        )
    if request.organization_interval_seconds is not None:
        cutoff = now - timedelta(seconds=request.organization_interval_seconds)
        and_conditions.append(
            {"lt": {"fieldName": "updatedAt", "value": cutoff.isoformat()}}
        )
    return {
        "resourceIdList": list(
            request.kb_resource_ids if kb_resource_ids is None else kb_resource_ids
        ),
        "where": {"and": and_conditions},
        "pageNum": request.page_index,
        "pageSize": request.page_size,
    }


def resolve_object_knowledge_scope(
    *,
    platform: Any,
    base_id: str,
    object_codes: tuple[str, ...],
    allowed_kb_resource_ids: tuple[str, ...],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """解析对象绑定知识库和目录，并限制在调用方指定的知识库范围内。"""
    allowed = set(allowed_kb_resource_ids)
    resource_ids: list[str] = []
    directories: list[str] = []
    has_binding = False
    for object_code in object_codes:
        detail = platform.get_object_detail(base_id, object_code)
        if detail is None:
            raise KeyError(f"object not found: {object_code}")
        ext = detail.get("ext_property") or detail.get("extProperty") or {}
        if not isinstance(ext, Mapping):
            continue
        resource_id = str(
            ext.get("kb_resource_id") or ext.get("kbResourceId") or ""
        ).strip()
        if not resource_id:
            continue
        has_binding = True
        if allowed and resource_id not in allowed:
            continue
        if resource_id not in resource_ids:
            resource_ids.append(resource_id)
        directory = _normalize_directory(
            str(ext.get("kb_directory") or ext.get("kbDirectory") or "")
        )
        if directory and directory not in directories:
            directories.append(directory)
    if not has_binding:
        raise ValueError("no knowledge-base binding found for objectCodes")
    return tuple(resource_ids), tuple(directories)


async def _call_platform_todo(platform: Any, method_name: str, **kwargs: Any) -> Any:
    method = getattr(platform, method_name, None)
    if not callable(method):
        raise NotImplementedError(f"TODO: platform.{method_name} is not implemented")
    result = method(**kwargs)
    return await result if inspect.isawaitable(result) else result


async def resolve_term_ids_by_relation_in_out_difference(
    *, platform: Any, base_id: str, difference: int
) -> tuple[str, ...]:
    """调用待实现能力，按有符号关系出入差值解析并去重术语 ID。"""
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
    """批量查询术语并从元数据中提取、去重 ``kb_file_path``。"""
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
    """按知识库与文件路径回查文档术语，并执行二次边界校验。

    Args:
        platform: 提供 search_terms_by_labels 的 Platform。
        base_id: 本体库/系统空间标识。
        kb_resource_ids: 调用方允许访问的门户知识库资源 ID。
        file_paths_by_kb_id: metadataSearch 返回的内部 kb_id 到文件路径集合映射。

    Returns:
        同时满足内部 kb_id、门户 kb_resource_id 和文件路径约束的原始术语列表，避免
        不同知识库存在相同路径时发生数据串库。
    """
    rows: list[dict[str, Any]] = []
    allowed_kb_resource_ids = set(kb_resource_ids)
    for kb_id, raw_file_paths in file_paths_by_kb_id.items():
        file_paths = tuple(dict.fromkeys(path for path in raw_file_paths if path))
        if not kb_id or not file_paths:
            continue
        result = platform.search_terms_by_labels(
            base_id,
            label_filters=[
                {"field_code": "kb_file_path", "filter_value": file_path}
                for file_path in file_paths
            ],
            label_condition="or",
            top_k=1000,
        )
        allowed_paths = set(file_paths)
        for row in _term_result_items(result):
            metadata = _term_metadata(row)
            result_kb_id = str(metadata.get("kb_id") or "")
            if result_kb_id != str(kb_id):
                continue
            if str(metadata.get("kb_resource_id") or "") not in allowed_kb_resource_ids:
                continue
            if str(metadata.get("kb_file_path") or "") not in allowed_paths:
                continue
            rows.append(row)
    return rows


def _term_result_items(result: Any) -> list[dict[str, Any]]:
    raw_items = (
        result
        if isinstance(result, (list, tuple))
        else result.get("items", [])
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
        termTypeCode=str(
            row.get("term_type")
            or row.get("term_type_code")
            or row.get("termTypeCode")
            or ""
        ),
        filePath=str(
            metadata.get("kb_file_path")
            or metadata.get("file_path")
            or metadata.get("filePath")
            or ""
        ),
        kbResourceId=str(
            metadata.get("kb_resource_id") or metadata.get("kbResourceId") or ""
        ),
        status=_parse_document_processing_status(metadata.get("dc_status")),
        failureReason=metadata.get("dc_failure_reason"),
        failureCount=metadata.get("dc_failure_count", 0),
    )


def _parse_document_processing_status(value: Any) -> DocumentProcessingStatus | None:
    """仅转换协议内定义的文档状态，未知或缺失状态返回空。"""
    try:
        return DocumentProcessingStatus(str(value or ""))
    except ValueError:
        return None
