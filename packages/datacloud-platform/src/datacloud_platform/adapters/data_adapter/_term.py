"""TermBackend + TermRelation + TermName."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Any

from datacloud_platform.adapters.data_adapter._base import DataCloudDataBackendBase
from datacloud_platform.models.shared import (
    ObjectInstanceListItem,
    ObjectInstanceListPage,
)
from datacloud_knowledge.adapters import create_reader, create_writer
from datacloud_knowledge.contracts.term_provider_types import (
    LabelCondition,
    LabelFilter,
    QueryResult,
    QueryType,
    TermCreate,
    TermUpdate,
)
from datacloud_knowledge.contracts.types import SearchTermsResult, TagFilter

logger = logging.getLogger(__name__)


class TermBackendMixin(DataCloudDataBackendBase):
    """TermBackend + TermRelation + TermName."""

    # ── TermBackend ─────────────────────────────────────────────────────────

    def search_terms(
        self,
        *,
        dataset_ids: list[str] | None = None,
        keyword: str | None = None,
        term_name: str | None = None,
        term_type: str | None = None,
        query_type: QueryType = "fulltext",
        parent_term_code: str | None = None,
        label_filters: list[LabelFilter] | None = None,
        label_condition: LabelCondition = "and",
        term_ids: list[str] | None = None,
        ext_attrs: dict[str, Any] | None = None,
        top_k: int = 20,
        offset: int = 0,
        query_vector: list[float] | None = None,
    ) -> QueryResult:
        """检索术语。

        支持按关键词、术语名称、类型、标签等多维度检索，返回分页结果。
        当 query_type 为 mixed/embedding 且未提供 query_vector 时，
        内部自动计算 embedding 向量。

        Args:
            dataset_ids:      术语库 ID 列表。None/空 = 不限制。
            keyword:          检索关键词（模糊匹配 term_name/term_code）。
            term_name:        术语名称精确匹配。与 keyword 互斥。
            term_type:        术语类型编码。None = 不限制类型。
            query_type:       检索策略（fulltext/exact/embedding/mixed）。
            parent_term_code: 父术语编码过滤。None = 不限制。
            label_filters:    标签过滤条件列表。
            label_condition:  多标签组合方式（and/or）。
            term_ids:         按 ID 列表精确查询。传入时忽略 keyword/query_type。
            query_vector:     查询向量。None 时 mixed/embedding 自动计算。
            top_k:            返回条数（1..200）。
            offset:           分页偏移（>=0）。

        Returns:
            QueryResult，包含 total 和 items（TermItem 列表）。
        """
        # Auto-compute vector for mixed/embedding when not provided
        effective_vector = query_vector
        if (
            effective_vector is None
            and query_type in ("mixed", "embedding")
            and keyword
        ):
            svc = self._get_embedding()
            effective_vector = svc.get_text_embedding(keyword)

        reader = create_reader()
        return reader.query_terms(
            dataset_ids=dataset_ids,
            keyword=keyword,
            term_name=term_name,
            term_type=term_type,
            query_type=query_type,
            parent_term_code=parent_term_code,
            label_filters=label_filters,
            label_condition=label_condition,
            term_ids=term_ids,
            ext_attrs=ext_attrs,
            query_vector=effective_vector,
            top_k=top_k,
            offset=offset,
        )

    def search_terms_exact(
        self,
        *,
        term_type_code: str,
        keyword: str | None = None,
        tags: Sequence[TagFilter] | None = None,
        limit: int = 20,
        offset: int = 0,
        order_by: str = "relevance",
    ) -> SearchTermsResult:
        """按术语类型精确检索术语列表（原子查询，无 BM25 兜底）。

        委托 knowledge reader.search_terms_exact——仅 term_name/term_code
        精确匹配（term_code 命中即可定位对象术语行），强制 term_type_code
        过滤（如 ``"object"`` 匹配对象行）。无匹配返回 total=0 空结果，
        降级编排由调用方负责。

        Args:
            term_type_code: 术语类型编码（支持驼峰简写映射，如 OBJ→object）。
            keyword: 可选关键词（精确匹配 term_name/term_code）。
            tags: 可选标签过滤条件列表。
            limit: 返回条数（1..200）。
            offset: 分页偏移（>=0）。
            order_by: 排序方式（relevance/updated_time/created_time/term_name）。

        Returns:
            SearchTermsResult，无精确匹配时 total=0、items=[]。
        """
        reader = create_reader()
        return reader.search_terms_exact(
            term_type_code=term_type_code,
            keyword=keyword,
            tags=tags,
            limit=limit,
            offset=offset,
            order_by=order_by,
        )

    def search_terms_batch(
        self,
        *,
        keywords: list[str],
        dataset_ids: list[str] | None = None,
        term_type_codes: list[str] | None = None,
        query_type: QueryType = "mixed",
        parent_term_code: str | None = None,
        label_filters: list[LabelFilter] | None = None,
        label_condition: LabelCondition = "and",
        ext_attrs: dict[str, Any] | None = None,
        top_k: int = 20,
        offset: int = 0,
    ) -> dict[str, QueryResult]:
        """批量检索术语 — 内部批量 embedding + UNION ALL SQL。

        Args:
            keywords:         搜索关键词列表。
            dataset_ids:      术语库 ID 列表。
            term_type_codes:  术语类型编码列表（IN 过滤）。None=不限类型。
            query_type:       检索策略（fulltext/exact/embedding/mixed）。
            parent_term_code: 父术语编码过滤。
            label_filters:    标签过滤条件列表。
            label_condition:  多标签组合方式（and/or）。
            ext_attrs:        扩展属性键值过滤。
            top_k:            返回条数。
            offset:           分页偏移。

        Returns:
            ``{keyword: QueryResult, ...}``，与 keywords 一一对应。
        """
        if not keywords:
            return {}

        # Auto-compute batch vectors for mixed/embedding
        query_vectors: list[list[float]] | None = None
        if query_type in ("mixed", "embedding"):
            svc = self._get_embedding()
            query_vectors = svc.get_text_embedding_batch(keywords)

        reader = create_reader()
        batch_results = reader.query_terms_batch(
            keywords=keywords,
            dataset_ids=dataset_ids,
            term_type_codes=term_type_codes,
            query_type=query_type,
            parent_term_code=parent_term_code,
            label_filters=label_filters,
            label_condition=label_condition,
            ext_attrs=ext_attrs,
            query_vectors=query_vectors,
            top_k=top_k,
            offset=offset,
        )

        # Zip results with keywords
        result: dict[str, QueryResult] = {}
        for keyword, qr in zip(keywords, batch_results):
            result[keyword] = qr
        return result

    def enumerate_object_instances(
        self,
        *,
        object_codes: list[str] | None,
        kb_resource_ids: list[str] | None,
        filters: list[dict[str, Any]] | None = None,
        sort: dict[str, Any] | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> ObjectInstanceListPage:
        """枚举带度数的对象实例 — 委托 knowledge provider（filters/sort 原样透传）。

        Args:
            object_codes:   对象类型编码范围（与 kb_resource_ids AND）。
            kb_resource_ids: 知识库资源 ID 范围（ext_attrs->>'kb_resource_id'）。
            filters:        条件数组，**原样透传不解析**——非法 type/params 由
                            knowledge 层 validate 抛 ValueError（RPC 层映射 400）。
            sort:           排序规格，**原样透传不解析**（同 filters 约定）——
                            非法 by/params 由 knowledge 层 validate 抛 ValueError（400）。
            page:           页码（>=1）。
            page_size:      每页条数（>=1）。

        Returns:
            ObjectInstanceListPage：knowledge 层 ObjectInstanceItem（6 字段）
            映射为 platform 层 ObjectInstanceListItem（9 字段）。
            file_name/kb_resource_id/kb_id 枚举接口不返回，恒 None。
        """
        from datacloud_knowledge.provider import (  # noqa: PLC0415
            enumerate_object_instances as sdk_enumerate_object_instances,
        )

        result = sdk_enumerate_object_instances(
            object_codes=object_codes or [],
            kb_resource_ids=kb_resource_ids or [],
            filters=filters,
            sort=sort,
            page=page,
            page_size=page_size,
        )
        items = [
            ObjectInstanceListItem(
                instance_id=item.term_id,
                instance_code=item.term_code,
                instance_name=item.term_name,
                object_code=item.term_type_code,
                file_name=None,
                kb_resource_id=None,
                kb_id=None,
                out_degree=item.out_degree,
                in_degree=item.in_degree,
            )
            for item in result.items
        ]
        return ObjectInstanceListPage(
            items=items,
            total=result.total,
            page=page,
            page_size=page_size,
        )

    def search_terms_by_labels(
        self,
        *,
        label_filters: list[LabelFilter] | None = None,
        label_condition: LabelCondition = "or",
        term_type_codes: list[str] | None = None,
        filters: list[dict[str, Any]] | None = None,
        top_k: int = 200,
    ) -> list[dict[str, Any]]:
        """纯标签过滤检索 — 不需要关键词。

        直接使用 reader.query_terms_by_labels() 做纯 WHERE 过滤。
        label_filters 为 None/[] 时跳过 _LF 构建（透传空，依赖 reader 跳过维度语义）；
        filters 原样透传，不做任何空值改写（保持透明；结构契约由 reader 入口校验
        抛 ValueError → 调用方早暴露）。
        返回 term dict 列表。
        """
        from datacloud_knowledge.contracts.term_provider_types import LabelFilter as _LF

        reader = create_reader()
        cfgs: list[Any] = []
        for lf in label_filters or []:
            if isinstance(lf, dict):
                cfgs.append(
                    _LF(
                        field_code=lf["field_code"],
                        filter_value=str(lf["filter_value"]),
                    )
                )
            else:
                cfgs.append(lf)

        items = reader.query_terms_by_labels(
            label_filters=cfgs,
            label_condition=label_condition,
            term_type_codes=term_type_codes,
            filters=filters,
            top_k=top_k,
        )
        return [_term_item_to_dict(item) for item in items]

    def get_term_detail(
        self, *, library_id: str, term_id: str
    ) -> dict[str, Any] | None:
        """Get single term detail via datacloud_knowledge provider."""
        from datacloud_knowledge.provider import (  # noqa: PLC0415
            get_term_detail as sdk_get_term_detail,
        )

        return sdk_get_term_detail(dataset_id=library_id, term_id=term_id)  # type: ignore[return-value]

    def list_terms(
        self,
        *,
        library_id: str,
        term_type: str | None = None,
        domain_code: str | None = None,
        keyword: str | None = None,
        page_index: int = 1,
        page_size: int = 20,
    ) -> dict[str, Any]:
        """Paginated term listing via datacloud_knowledge provider."""
        from datacloud_knowledge.provider import (  # noqa: PLC0415
            list_terms as sdk_list_terms,
        )

        return sdk_list_terms(  # type: ignore[return-value]
            dataset_id=library_id,
            term_type=term_type,
            domain_code=domain_code,
            keyword=keyword,
            page_index=page_index,
            page_size=page_size,
        )

    def create_term(self, *, term: dict[str, Any]) -> dict[str, Any]:
        """Create a single term — wraps import_terms.

        支持 camelCase 和 snake_case 两种 dict 格式：
        - termName / term_name
        - termCode / term_code
        - termTypeCode / term_type_code
        - parentTermCode / parent_term_code
        ``dataset_id`` 优先从 dict 中取，缺省时使用 ``""``（provider 层有 fallback）。
        """
        library_id = term.get("datasetId") or term.get("dataset_id") or "default_term"
        return self.import_terms(library_id=library_id, terms=[term])

    def import_terms(
        self,
        *,
        library_id: str,
        terms: list[dict[str, Any]],
        backfill: bool = False,
    ) -> dict[str, Any]:
        """Batch import terms via datacloud_knowledge provider.

        ``terms`` 为 dict 列表，支持 camelCase 和 snake_case 两种 key 格式。
        内部自动转换为 ``TermCreate`` 对象再传给 sdk。
        """
        from datacloud_knowledge.provider import (  # noqa: PLC0415
            import_terms as sdk_import_terms,
        )

        term_creates = [_dict_to_term_create(t) for t in terms]
        result = sdk_import_terms(
            dataset_id=library_id, terms=term_creates, backfill=backfill
        )
        return {
            "created": result.created,
            "updated": result.updated,
            "skipped": result.skipped,
            "term_ids": result.term_ids,
            "errors": result.errors,
        }

    def update_term(
        self, *, library_id: str = "", term_id: str, updates: dict[str, Any]
    ) -> None:
        """Update a term via datacloud_knowledge provider."""
        from datacloud_knowledge.provider import (  # noqa: PLC0415
            update_term as sdk_update_term,
        )

        sdk_update_term(
            dataset_id=library_id,
            term_id=term_id,
            updates=TermUpdate(**{k: v for k, v in updates.items() if v is not None}),
        )

    def delete_term(self, *, term_id: str) -> None:
        """Delete a term via datacloud_knowledge writer."""

        with create_writer() as writer:
            writer.delete_term(term_id=term_id)

    # ── TermSyncHandler 协议实现 ────────────────────────────────────────────
    # 供 term_sync_worker 注入使用，不依赖 BulkImportAdapter。

    def ensure_term_type(self, *, base_id: str, type_code: str, type_name: str) -> None:
        """确保术语类型存在（幂等）。实现 TermSyncHandler.ensure_term_type。"""
        try:
            self.create_term_type(  # type: ignore[attr-defined]
                library_id=base_id,
                term_type={
                    "typeCode": type_code,
                    "typeName": type_name,
                    "typeDesc": "",
                    "typeCategory": 1,
                },
            )
        except Exception:
            logger.debug(
                "ensure_term_type: type_code=%s already exists or failed", type_code
            )

    def upsert_terms(self, *, base_id: str, terms: list[dict[str, Any]]) -> list[str]:
        """批量 upsert 术语，返回 term_id 列表。实现 TermSyncHandler.upsert_terms。

        ``terms`` 每条包含：term_code, term_name, term_desc,
        term_type_code, library_code, domain_code。
        使用 writer.upsert_term 实现真正的 INSERT-or-UPDATE 语义，
        避免 import_terms（纯 INSERT）在 update 事件时静默失败。
        """

        if not terms:
            return []
        term_ids: list[str] = []
        with create_writer() as writer:
            for t in terms:
                term_code = t.get("term_code") or ""
                term_name = t.get("term_name") or ""
                term_type_code = t.get("term_type_code") or ""
                library_id = t.get("library_code") or t.get("library_id") or None
                if not term_code or not term_name or not term_type_code:
                    continue
                try:
                    term_id = writer.upsert_term(
                        term_code=term_code,
                        term_name=term_name,
                        term_type_code=term_type_code,
                        library_id=library_id,
                        backfill_vectors=False,  # 批量时关闭单条向量回填，避免阻塞
                    )
                    term_ids.append(term_id)
                except Exception:
                    logger.warning(
                        "upsert_terms: failed term_code=%s type=%s",
                        term_code,
                        term_type_code,
                        exc_info=True,
                    )
        return term_ids

    def delete_terms(
        self,
        *,
        base_id: str,
        term_ids: list[str] | None = None,
        terms: list[dict[str, Any]] | None = None,
    ) -> None:
        """批量删除术语，支持两种入参，均有值时全部执行。

        Args:
            term_ids: 数据库 UUID 列表，直接按主键删除。
            terms:    业务三元组 dict 列表（term_code, term_type_code, library_code），
                      先通过 reader.get_term_by_ids 反查 UUID 再删除。
        """
        from datacloud_knowledge.adapters import create_reader  # noqa: PLC0415

        ids_to_delete: list[str] = list(term_ids) if term_ids else []

        # ── 业务三元组 → UUID ────────────────────────────────────────────
        if terms:
            keys: list[tuple[str, str, str]] = []
            for t in terms:
                library_id = t.get("library_code") or t.get("library_id") or ""
                term_type_code = t.get("term_type_code") or ""
                term_code = t.get("term_code") or ""
                if library_id and term_type_code and term_code:
                    keys.append((library_id, term_type_code, term_code))
                else:
                    logger.warning("delete_terms: 缺少必要字段，跳过 term=%s", t)

            if keys:
                try:
                    reader = create_reader()
                    id_map: dict[tuple[str, str, str], str] = reader.get_term_by_ids(
                        keys=keys
                    )
                    ids_to_delete.extend(id_map.values())
                except Exception:
                    logger.warning("delete_terms: 查询 term_id 失败", exc_info=True)

        if not ids_to_delete:
            logger.debug("delete_terms: 无需删除")
            return

        with create_writer() as writer:
            for db_id in ids_to_delete:
                try:
                    writer.delete_term(term_id=db_id)
                except Exception:
                    logger.warning(
                        "delete_terms: failed db_term_id=%s", db_id, exc_info=True
                    )

    def query_term_relations(
        self,
        *,
        term_id: str,
        relation_category: str | None = None,
        direction: str = "both",
        depth: int = 1,
        keyword: str | None = None,
        term_type_codes: list[str] | None = None,
        page_index: int = 1,
        page_size: int = 20,
    ) -> dict[str, Any]:
        """Query term relations via knowledge reader."""
        reader = self._get_knowledge_reader()
        try:
            return reader.query_term_relations(  # type: ignore[no-any-return]
                term_id=term_id,
                relation_category=relation_category,
                direction=direction,
                depth=depth,
                keyword=keyword,
                term_type_codes=term_type_codes,
                page_index=page_index,
                page_size=page_size,
            )
        except Exception:
            logger.exception("query_term_relations failed term_id=%s", term_id)
            return {"data": [], "totalCount": 0}

    def query_term_relations_tree(
        self,
        *,
        term_id: str,
        max_depth: int = 3,
        relation_category: str | None = None,
        direction: str = "both",
    ) -> dict[str, Any]:
        """Query entire relation tree via recursive CTE (single DB call)."""
        reader = self._get_knowledge_reader()
        try:
            return reader.query_term_relations_tree(  # type: ignore[no-any-return]
                term_id=term_id,
                max_depth=max_depth,
                relation_category=relation_category,
                direction=direction,
            )
        except Exception:
            logger.exception("query_term_relations_tree failed term_id=%s", term_id)
            return {"data": [], "totalCount": 0}

    def query_term_relations_tree_batch(
        self,
        *,
        term_ids: list[str],
        max_depth: int = 3,
        direction: str = "both",
        relation_category: str | None = None,
    ) -> dict[str, Any]:
        """Multi-root recursive CTE — one query for all seeds."""
        reader = self._get_knowledge_reader()
        try:
            return reader.query_term_relations_tree_batch(  # type: ignore[no-any-return]
                term_ids=term_ids,
                max_depth=max_depth,
                direction=direction,
                relation_category=relation_category,
            )
        except Exception:
            logger.exception(
                "query_term_relations_tree_batch failed term_ids=%s", term_ids
            )
            return {"data": [], "totalCount": 0}

    def query_edges_by_kb_id(
        self,
        *,
        kb_ids: list[str],
        limit: int = 2000,
        relation_category: str | None = None,
    ) -> dict[str, Any]:
        """Flat query: load all edges by kb_id filter."""
        reader = self._get_knowledge_reader()
        try:
            return reader.query_edges_by_kb_id(  # type: ignore[no-any-return]
                kb_ids=kb_ids,
                limit=limit,
                relation_category=relation_category,
            )
        except Exception:
            logger.exception("query_edges_by_kb_id failed kb_ids=%s", kb_ids)
            return {"data": []}

    # ── TermRelation ────────────────────────────────────────────────────

    def list_term_relations(
        self,
        *,
        source_term_id: str | None = None,
        target_term_id: str | None = None,
        relation_category: str | None = None,
        relation_code: str | None = None,
        keyword: str | None = None,
        page_index: int = 1,
        page_size: int = 20,
        strict: bool = False,
    ) -> dict[str, Any]:
        reader = self._get_knowledge_reader()
        try:
            return reader.list_term_relations(  # type: ignore[no-any-return]
                source_term_id=source_term_id,
                target_term_id=target_term_id,
                relation_category=relation_category,
                relation_code=relation_code,
                keyword=keyword,
                page_index=page_index,
                page_size=page_size,
            )
        except Exception:
            logger.exception("list_term_relations failed")
            if strict:
                raise
            return {"data": [], "totalCount": 0}

    def get_term_relation(
        self,
        *,
        relation_id: str,
        strict: bool = False,
    ) -> dict[str, Any] | None:
        reader = self._get_knowledge_reader()
        try:
            return reader.get_term_relation(relation_id=relation_id)  # type: ignore[no-any-return]
        except Exception:
            logger.exception("get_term_relation failed relation_id=%s", relation_id)
            if strict:
                raise
            return None

    def create_term_relation(self, *, relation: dict[str, Any]) -> dict[str, Any]:
        with create_writer() as writer:
            return writer.create_term_relation(relation=relation)

    def update_term_relation(
        self, *, relation_id: str, updates: dict[str, Any]
    ) -> None:
        with create_writer() as writer:
            writer.update_term_relation(relation_id=relation_id, updates=updates)

    def delete_term_relation(self, *, relation_id: str) -> None:
        with create_writer() as writer:
            writer.delete_term_relation(relation_id=relation_id)

    # ── TermName ────────────────────────────────────────────────────────

    def list_term_names(
        self, *, term_id: str | None = None, name_text: str | None = None
    ) -> list[dict[str, Any]]:
        reader = self._get_knowledge_reader()
        try:
            return reader.list_term_names(term_id=term_id, name_text=name_text)  # type: ignore[no-any-return]
        except Exception:
            logger.exception("list_term_names failed")
            return []

    def get_term_name(self, *, name_id: str) -> dict[str, Any] | None:
        reader = self._get_knowledge_reader()
        try:
            return reader.get_term_name(name_id=name_id)  # type: ignore[no-any-return]
        except Exception:
            logger.exception("get_term_name failed name_id=%s", name_id)
            return None

    def create_term_name(self, *, name: dict[str, Any]) -> dict[str, Any]:
        with create_writer() as writer:
            return writer.create_term_name_wrapper(name=name)

    def update_term_name(self, *, name_id: str, updates: dict[str, Any]) -> None:
        with create_writer() as writer:
            writer.update_term_name(name_id=name_id, updates=updates)

    def delete_term_name(self, *, name_id: str) -> None:
        with create_writer() as writer:
            writer.delete_term_name(name_id=name_id)

    # ── TermVocabulary ────────────────────────────────────────────────────

    def list_vocabulary(self) -> list[str]:
        """读取 term_vocabulary 全量去重词表（AC 锚定词典数据源）。

        经 knowledge 侧 TermReader 协议代理转发。
        """
        reader = create_reader()
        return reader.list_vocabulary()

    def batch_create_vocabulary(self, *, words: Sequence[str]) -> None:
        """批量写入分词词典（幂等去重），抽取词表回填通道。

        Args:
            words: 词汇文本列表。
        """
        with create_writer() as writer:
            writer.batch_create_vocabulary(words=list(words))

    def update_term_co_occurrence(self, *, term_id: str, patch: dict[str, int]) -> None:
        """更新 term_tags.co_occurrence（Top-50 计数伙伴集合），独立新写路径。

        **禁止经 update_term**（其 ext_attrs 拼入 desc_summary 的遗留怪癖）：
        经 knowledge 侧独立 SQL 写路径转发。

        Args:
            term_id: 归属 term_id。
            patch: ``{partner_term_id: count}`` 增量。
        """
        with create_writer() as writer:
            writer.update_term_co_occurrence(term_id=term_id, patch=patch)


# ── 模块级辅助函数 ──────────────────────────────────────────────────────────────


def _term_item_to_dict(item: Any) -> dict[str, Any]:
    if isinstance(item, dict):
        return {
            "term_id": item.get("term_id", ""),
            "term_code": item.get("term_code", ""),
            "term_name": item.get("term_name", ""),
            "term_type": item.get("term_type", ""),
            "ext_attrs": item.get("ext_attrs", {}),
            "term_tags": item.get("term_tags") or item.get("labels", {}),
            "score": item.get("score", 1.0),
        }
    return {
        "term_id": item.term_id,
        "term_code": item.term_code,
        "term_name": item.term_name,
        "term_type": item.term_type,
        "ext_attrs": item.ext_attrs,
        "term_tags": item.labels,
        "score": item.score if item.score is not None else 1.0,
    }


def _dict_to_term_create(term: dict[str, Any]) -> "TermCreate":
    """将 camelCase 或 snake_case dict 转换为 TermCreate dataclass。

    支持的 key 格式（优先 camelCase）：
        termName / term_name
        termCode / term_code
        termTypeCode / term_type_code
        parentTermCode / parent_term_code
        termDesc / term_desc / desc
    """
    from datacloud_knowledge.contracts.term_provider_types import TermCreate  # noqa: PLC0415

    relations = (
        term.get("relations") or term.get("relatedTo") or term.get("related_to", [])
    )

    return TermCreate(
        term_name=term.get("termName") or term.get("term_name", ""),
        term_code=term.get("termCode") or term.get("term_code", ""),
        term_type=term.get("termTypeCode")
        or term.get("term_type_code")
        or term.get("term_type", ""),
        parent_term_code=term.get("parentTermCode") or term.get("parent_term_code", ""),
        desc=term.get("termDesc") or term.get("term_desc") or term.get("desc", ""),
        labels=term.get("labels", {}),
        ext_attrs=term.get("extAttrs") or term.get("ext_attrs", {}),
        synonyms=term.get("synonyms", []),
        relations=relations,
    )
