"""文档领域的跨后端业务编排。

本模块不直接实现知识库 HTTP 协议，而是组合 Platform 已提供的术语、关系、对象定义和
文档库能力，完成以下业务：文档对象筛选、直接关系查询、完整内容读取、知识片段检索，
以及文档发现/富化后台任务。外部接口的 Pydantic 入出参统一定义在
``datacloud_platform.models.document``。
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
_DOCUMENT_PAGE_SIZE = 200
_DOCUMENT_LOCK_TTL_SECONDS = 3600


class _DocumentPlatform(Protocol):
    """DocumentMixin 所依赖的 Platform 最小能力协议。"""

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
        锁；调用 ``discover_document_entities_todo``；最后把实体数量或失败原因追加到
        当前会话空间的进度文件。单个文档失败不会终止整批任务。

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

        查询“待整理、整理失败-待重试”文档，并固定附加两个筛选条件：更新时间早于
        当前时间 7200 秒、关系出入差值为 10。每个文档持锁调用 ``enrich``，成功后
        通过对象 ``write_*`` 动作写回数据，并在处理前后通过服务发现更新对象文件状态。

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
        """发现单个文档中的实体（待接入具体实现）。

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

    富化任务先按 ``request.object_codes`` 一次性加载本体对象详情，再完成分页快照，
    避免循环内重复查询对象；发现与富化共用该流程，通过 ``operation`` 选择处理分支。

    Args:
        platform: 提供文档查询、锁、发现、富化、动作执行及会话写入能力的 Platform。
        base_id: 本体库/系统空间标识。
        session_id: 会话 ID。
        request: 异步处理范围和模型配置。
        statuses: 本次任务允许消费的文档状态。
        operation: ``discovery`` 或 ``enrichment``。
        organization_interval_seconds: 可选的更新时间间隔秒数。
        relation_in_out_difference: 可选的关系出入差值，不取绝对值。
    """
    enrich_scope_by_code: dict[str, DocumentEnrichObjectScope] | None = None
    if operation == "enrichment":
        enrich_scope_by_code = {
            object_code: _resolve_document_object_scope(
                platform=platform,
                base_id=base_id,
                object_code=object_code,
            )
            for object_code in request.object_codes
        }
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
    for document in documents:
        await _process_one_document(
            platform,
            base_id=base_id,
            session_id=session_id,
            request=request,
            document=document,
            operation=operation,
            enrich_scope_by_code=enrich_scope_by_code,
        )


async def _process_one_document(
    platform: Any,
    *,
    base_id: str,
    session_id: str,
    request: DocumentAsyncProcessingRequest,
    document: DocumentObjectItem,
    operation: str,
    enrich_scope_by_code: Mapping[str, DocumentEnrichObjectScope] | None = None,
) -> None:
    """在分布式锁保护下处理一个文档并记录结果。

    未取得锁时写入 ``skipped_locked``；业务成功写入 ``completed``；任何单文档异常
    写入 ``failed + error``，异常不会继续向上抛出，因此不会中断批次中其他文档。

    Args:
        platform: 文档处理 Platform。
        base_id: 本体库/系统空间标识，用于组成锁键。
        session_id: 写入处理报告的会话 ID。
        request: 对象范围和模型配置。
        document: 当前处理的文档对象。
        operation: ``discovery`` 或 ``enrichment``。
        enrich_scope_by_code: 前置加载的对象编码到本体对象详情映射，仅富化使用。
    """
    lock_key = (
        f"datacloud:document:{operation}:{base_id}:"
        f"{document.kb_resource_id}:{document.term_id}"
    )
    async with platform.document_processing_lock(lock_key=lock_key) as acquired:
        if not acquired:
            platform.append_document_session_report(
                session_id=session_id,
                operation=operation,
                term_id=document.term_id,
                file_path=document.file_path,
                status="skipped_locked",
            )
            return
        try:
            if operation == "discovery":
                entity_count = await platform.discover_document_entities_todo(
                    document=document,
                    object_codes=request.object_codes,
                    model_config=request.model_config_payload,
                )
                platform.append_document_session_report(
                    session_id=session_id,
                    operation=operation,
                    term_id=document.term_id,
                    file_path=document.file_path,
                    status="completed",
                    entity_count=entity_count,
                )
            else:
                from datacloud_platform.services.object_action import (
                    invoke_object_write_action,
                )

                if enrich_scope_by_code is None:
                    enrich_scope_by_code = {
                        object_code: _resolve_document_object_scope(
                            platform=platform,
                            base_id=base_id,
                            object_code=object_code,
                        )
                        for object_code in request.object_codes
                    }
                target_object = enrich_scope_by_code.get(document.term_type_code)
                if target_object is None:
                    raise KeyError(
                        f"term_type_code is not in object_codes: "
                        f"{document.term_type_code}"
                    )
                await platform.save_or_update_object_files(
                    base_id,
                    object_files=[
                        _build_object_file_status(
                            session_id=session_id,
                            document=document,
                            object_scope=target_object,
                            status=DocumentProcessingStatus.ORGANIZING,
                        )
                    ],
                )
                enrich_result = await platform.enrich(
                    base_id,
                    object_scope=list(enrich_scope_by_code.values()),
                    target_object=target_object,
                    term_id=document.term_id,
                )
                content = enrich_result.enriched_content
                processing_status = _processing_status_for_enrich_result(
                    enrich_result.status
                )
                action_result: dict[str, Any] | None = None
                action_labels: dict[str, Any] = {}
                if content.strip():
                    content = _append_related_docs_block(
                        platform=platform,
                        base_id=base_id,
                        content=content,
                        relations=enrich_result.relations,
                        object_scope_by_code=enrich_scope_by_code,
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
                await platform.save_or_update_object_files(
                    base_id,
                    object_files=[
                        _build_object_file_status(
                            session_id=session_id,
                            document=document,
                            object_scope=target_object,
                            status=processing_status,
                            labels=action_labels,
                            action_result=action_result,
                        )
                    ],
                )
        except Exception as exc:  # noqa: BLE001
            logger.exception("Document %s failed: %s", operation, document.term_id)
            if operation == "discovery":
                platform.append_document_session_report(
                    session_id=session_id,
                    operation=operation,
                    term_id=document.term_id,
                    file_path=document.file_path,
                    status="failed",
                    error=str(exc),
                )
            else:
                try:
                    target_object = (enrich_scope_by_code or {}).get(
                        document.term_type_code
                    )
                    if target_object is None:
                        raise KeyError(
                            f"term_type_code is not in object_codes: "
                            f"{document.term_type_code}"
                        )
                    await platform.save_or_update_object_files(
                        base_id,
                        object_files=[
                            _build_object_file_status(
                                session_id=session_id,
                                document=document,
                                object_scope=target_object,
                                status=DocumentProcessingStatus.ORGANIZATION_RETRY,
                            )
                        ],
                    )
                except Exception:  # noqa: BLE001
                    logger.exception(
                        "Failed to persist enrichment failure status: %s",
                        document.term_id,
                    )


def _processing_status_for_enrich_result(
    status: DocumentEnrichStatus,
) -> DocumentProcessingStatus:
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
