"""PostgresTermStore — 术语存储聚合层。

将 PostgresTermReader 和 PostgresTermWriter 聚合为一个统一入口，
提供多路召回 + RRF 融合的 query_terms 实现，
其余方法委托给 reader/writer。

满足 TermStore + TermStoreExtended 两条协议（duck typing，无显式继承）。
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import AbstractContextManager
from typing import TYPE_CHECKING, Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from datacloud_knowledge.adapters.opengauss._db.connection import get_session
from datacloud_knowledge.adapters.opengauss._db.models import Term
from datacloud_knowledge.adapters.opengauss.bm25 import bm25_search_with_or
from datacloud_knowledge.adapters.opengauss.jieba_recall import jieba_recall
from datacloud_knowledge.adapters.opengauss.reader import PostgresTermReader
from datacloud_knowledge.adapters.opengauss.substring_recall import substring_recall
from datacloud_knowledge.adapters.opengauss.writer import PostgresTermWriter
from datacloud_knowledge.contracts.rrf import rrf_fuse
from datacloud_knowledge.contracts.term_provider_types import (
    ImportResult,
    LabelCondition,
    LabelFilter,
    QueryResult,
    QueryType,
    TermCreate,
    TermDetail,
    TermItem,
    TermUpdate,
)
from datacloud_knowledge.contracts.types import ShortestPathNode

if TYPE_CHECKING:
    from datacloud_knowledge.retrieval.embedding import EmbeddingService

log = logging.getLogger(__name__)

# 每路召回的默认 top_k（供 RRF 融合池）
_RECALL_TOP_K = 200


class PostgresTermStore:
    """术语存储聚合层 — 读/写统一入口 + 多路召回融合。

    Usage::

        store = PostgresTermStore()
        result = store.query_terms(keyword="客户", top_k=20)
        detail = store.get_term_detail(dataset_id="ds1", term_id="term_001")
        store.update_term(dataset_id="ds1", term_id="term_001", updates=...)
    """

    def __init__(
        self,
        session_factory: Callable[[], AbstractContextManager[Session]] | None = None,
        embedding_service: EmbeddingService | None = None,
    ) -> None:
        """初始化存储聚合层。

        Args:
            session_factory: SQLAlchemy session 工厂，默认使用 ``get_session``。
            embedding_service: 可选的向量嵌入服务，传入后启用向量召回路径。
        """
        self._session_factory = session_factory or get_session
        self._reader = PostgresTermReader(session_factory=self._session_factory)
        self._writer = PostgresTermWriter(session_factory=self._session_factory)
        self._embedding_service = embedding_service

    # ── TermStore 协议方法 ──────────────────────────────────────────────

    def query_terms(
        self,
        *,
        dataset_ids: list[str] | None = None,
        keyword: str | None = None,
        term_name: str | None = None,
        term_type: str | list[str] | None = None,
        query_type: QueryType = "fulltext",
        parent_term_code: str | None = None,
        label_filters: list[LabelFilter] | None = None,
        label_condition: LabelCondition = "and",
        term_ids: list[str] | None = None,
        top_k: int = 20,
        offset: int = 0,
    ) -> QueryResult:
        """多路召回 + RRF 融合检索术语。

        召回路径：
        - BM25 字级全文搜索
        - Jieba 分词 → 逐 token BM25 → RRF 内融合
        - 双向子串匹配
        - 向量语义搜索（需注入 ``embedding_service``）

        特例：
        - ``term_ids`` 传入时跳过召回，直接按 ID 查询。
        - ``term_name`` 传入且 keyword 为空时，执行精确匹配。

        Args:
            dataset_ids: 术语库 ID 列表过滤。
            keyword: 检索关键词（模糊匹配）。
            term_name: 精确匹配 term_name/term_code，与 keyword 互斥。
            term_type: 术语类型编码过滤。
            query_type: 检索策略（当前均为 multi-recall 融合）。
            parent_term_code: 父术语编码过滤。
            label_filters: 标签过滤（暂未实现）。
            label_condition: 标签组合方式（暂未实现）。
            term_ids: 按 ID 列表精确查询，传入时忽略 keyword。
            top_k: 返回条数。
            offset: 分页偏移。

        Returns:
            QueryResult，包含 total 和 items。
        """
        _ = (query_type, label_filters, label_condition, parent_term_code)

        # 特例 1：按 term_ids 直接查询
        if term_ids:
            return self._reader.query_terms(
                dataset_ids=dataset_ids,
                term_type=term_type,
                term_ids=term_ids,
                top_k=top_k,
                offset=offset,
            )

        # 特例 2：term_name 精确匹配
        normalized_term_name = (term_name or "").strip()
        if normalized_term_name and not (keyword or "").strip():
            return self._query_by_exact_name(
                term_name=normalized_term_name,
                dataset_ids=dataset_ids,
                term_type=term_type,
                top_k=top_k,
                offset=offset,
            )

        # 常规路径：多路召回 + RRF 融合
        query_text = (keyword or "").strip()
        if not query_text:
            return self._reader.query_terms(
                dataset_ids=dataset_ids,
                term_type=term_type,
                top_k=top_k,
                offset=offset,
            )

        # 构建类型过滤集合
        type_codes: set[str] | None = None
        if term_type:
            if isinstance(term_type, list):
                type_codes = {PostgresTermReader._normalize_type_code(t) for t in term_type}
            else:
                type_codes = {PostgresTermReader._normalize_type_code(term_type)}

        # 并行多路召回
        ranked_lists = self._multi_recall(query_text, type_codes)

        if not ranked_lists:
            return QueryResult(total=0, items=[])

        # RRF 融合
        fused = rrf_fuse(ranked_lists, k=60, top_n=top_k * 3)
        if not fused:
            return QueryResult(total=0, items=[])

        # 查询完整 TermItem 数据
        items = self._fetch_term_items([c.term_id for c in fused], fused, dataset_ids)

        # 分页
        paginated = items[offset : offset + top_k]
        return QueryResult(total=len(items), items=paginated)

    def get_term_detail(
        self,
        *,
        dataset_id: str,
        term_id: str,
    ) -> TermDetail | None:
        """查询单条术语完整详情。委托给 reader。"""
        return self._reader.get_term_detail(dataset_id=dataset_id, term_id=term_id)

    def list_terms(
        self,
        *,
        dataset_id: str,
        term_type: str | None = None,
        term_type_no_eq: str | None = None,
        page_index: int = 1,
        page_size: int = 50,
    ) -> QueryResult:
        """分页列出术语（含完整详情）。委托给 reader。"""
        return self._reader.list_terms(
            dataset_id=dataset_id,
            term_type=term_type,
            term_type_no_eq=term_type_no_eq,
            page_index=page_index,
            page_size=page_size,
        )

    def import_terms(
        self,
        *,
        dataset_id: str,
        terms: list[TermCreate],
    ) -> ImportResult:
        """批量新增术语。委托给 writer（自动管理 session 生命周期）。"""
        with self._writer:
            return self._writer.import_terms(dataset_id=dataset_id, terms=terms)

    def update_term(
        self,
        *,
        dataset_id: str,
        term_id: str,
        updates: TermUpdate,
    ) -> None:
        """更新术语。委托给 writer（自动管理 session 生命周期）。"""
        with self._writer:
            self._writer.update_term(dataset_id=dataset_id, term_id=term_id, updates=updates)

    # ── TermStoreExtended 协议方法 ──────────────────────────────────────

    def get_bfs_distance(
        self,
        *,
        source_term_id: str,
        target_term_id: str,
        max_depth: int = 4,
    ) -> int | None:
        """计算两术语在图谱中的 BFS 最短距离。委托给 reader。"""
        return self._reader.get_bfs_distance(
            source_term_id=source_term_id,
            target_term_id=target_term_id,
            max_depth=max_depth,
        )

    def get_shortest_path_tree(
        self,
        *,
        target_term_id: str,
        source_term_type_codes: Sequence[str],
        max_depth: int = 6,
    ) -> Sequence[ShortestPathNode]:
        """查询从限定类型根节点到目标术语的最短路径树。委托给 reader。"""
        return self._reader.get_shortest_path_tree(
            target_term_id=target_term_id,
            source_term_type_codes=source_term_type_codes,
            max_depth=max_depth,
        )

    def get_global_name_index(
        self,
    ) -> dict[str, list[tuple[str, str, str]]]:
        """构建全局术语名称索引。委托给 reader。"""
        return self._reader.get_global_name_index()

    def get_name_ids_by_word(
        self,
        *,
        word: str,
        term_ids: Sequence[str],
        user_id: str | None = None,
    ) -> dict[str, str]:
        """按单词+术语ID查询 name_id。委托给 reader。"""
        return self._reader.get_name_ids_by_word(
            word=word,
            term_ids=term_ids,
            user_id=user_id,
        )

    # ── 多路召回内部方法 ────────────────────────────────────────────────

    def _multi_recall(
        self, query_text: str, type_codes: set[str] | None
    ) -> list[list[tuple[str, str, str, str, str]]]:
        """并行执行 BM25 / Jieba / 子串 / 向量四路召回。

        Returns:
            非空召回列表的列表，供 RRF 融合使用。
        """
        ranked_lists: list[list[tuple[str, str, str, str, str]]] = []

        with ThreadPoolExecutor(max_workers=4) as executor:
            futures: dict[Any, str] = {}

            f_bm25 = executor.submit(self._bm25_recall, query_text, type_codes)
            futures[f_bm25] = "bm25"

            f_jieba = executor.submit(self._jieba_recall_worker, query_text, type_codes)
            futures[f_jieba] = "jieba"

            f_sub = executor.submit(self._substring_recall_worker, query_text, type_codes)
            futures[f_sub] = "substring"

            if self._embedding_service is not None:
                f_vec = executor.submit(self._vector_recall_worker, query_text)
                futures[f_vec] = "vector"

            for future in as_completed(futures):
                path_name = futures[future]
                try:
                    result = future.result()
                    if result:
                        ranked_lists.append(result)
                        log.debug("召回路径 '%s' 返回 %d 条", path_name, len(result))
                except Exception:
                    log.warning("召回路径 '%s' 失败", path_name, exc_info=True)

        return ranked_lists

    def _bm25_recall(
        self, query_text: str, type_codes: set[str] | None
    ) -> list[tuple[str, str, str, str, str]]:
        """BM25 字级 OR 召回。"""
        with self._session_factory() as session:
            results = bm25_search_with_or(
                session, query_text, top_k=_RECALL_TOP_K, term_type_codes=type_codes
            )
            return [
                (r.term_id, r.term_name, r.name_id, r.term_type_code, r.term_code) for r in results
            ]

    def _jieba_recall_worker(
        self, query_text: str, type_codes: set[str] | None
    ) -> list[tuple[str, str, str, str, str]]:
        """Jieba 分词 → 逐 token BM25 → RRF 内融合。"""
        with self._session_factory() as session:
            return jieba_recall(
                session, query_text, top_k=_RECALL_TOP_K, term_type_codes=type_codes
            )

    def _substring_recall_worker(
        self, query_text: str, type_codes: set[str] | None
    ) -> list[tuple[str, str, str, str, str]]:
        """双向子串匹配召回。"""
        with self._session_factory() as session:
            return substring_recall(
                session, query_text, top_k=_RECALL_TOP_K, term_type_codes=type_codes
            )

    def _vector_recall_worker(self, query_text: str) -> list[tuple[str, str, str, str, str]]:
        """向量语义召回。需在构造时注入 embedding_service。"""
        if self._embedding_service is None:
            return []
        from datacloud_knowledge.adapters.opengauss.vector import vector_search

        with self._session_factory() as session:
            results = vector_search(
                session,
                query_text,
                self._embedding_service,
                top_k=_RECALL_TOP_K,
            )
            return [
                (r.term_id, r.term_name, r.name_id, r.term_type_code, r.term_code) for r in results
            ]

    # ── TermItem 查询辅助 ───────────────────────────────────────────────

    def _fetch_term_items(
        self,
        fused_ids: list[str],
        fused_candidates: list[Any],  # RRFCandidate 列表
        dataset_ids: list[str] | None,
    ) -> list[TermItem]:
        """根据 RRF 融合后的 term_id 列表查询完整 TermItem 数据。

        Args:
            fused_ids: RRF 融合后的 term_id 列表（去重）。
            fused_candidates: RRF 融合候选列表，用于取 score。
            dataset_ids: 术语库 ID 过滤。

        Returns:
            按 RRF score 降序排列的 TermItem 列表。
        """
        if not fused_ids:
            return []

        # 构建 score 映射
        score_map: dict[str, float] = {}
        for c in fused_candidates:
            score_map[c.term_id] = c.rrf_score

        with self._session_factory() as session:
            stmt = select(
                Term.term_id,
                Term.term_code,
                Term.term_name,
                Term.term_type_code,
                Term.library_id,
                Term.parent_term_id,
                Term.desc_summary,
                Term.term_tags,
            ).where(Term.term_id.in_(fused_ids))

            if dataset_ids:
                stmt = stmt.where(Term.library_id.in_(dataset_ids))

            rows = session.execute(stmt).all()

        items: list[TermItem] = []
        for row in rows:
            tags: dict[str, str] = {}
            raw_tags = row[7]
            if isinstance(raw_tags, dict):
                tags = {str(k): str(v) for k, v in raw_tags.items()}

            term_id = str(row[0])
            items.append(
                TermItem(
                    term_id=term_id,
                    term_code=str(row[1]),
                    term_name=str(row[2]),
                    term_type=str(row[3]),
                    dataset_id=str(row[4]) if row[4] else "",
                    parent_term_code=str(row[5]) if row[5] else "",
                    desc=str(row[6]) if row[6] else "",
                    labels=tags,
                    synonyms="",
                    ext_attrs={},
                    created_time=0,
                    updated_time=0,
                    score=score_map.get(term_id),
                )
            )

        # 按 RRF score 降序排列
        items.sort(key=lambda x: x.score if x.score is not None else 0.0, reverse=True)
        return items

    # ── 精确名称查询 ────────────────────────────────────────────────────

    def _query_by_exact_name(
        self,
        *,
        term_name: str,
        dataset_ids: list[str] | None,
        term_type: str | list[str] | None,
        top_k: int,
        offset: int,
    ) -> QueryResult:
        """按 term_name 或 term_code 精确匹配查询。"""
        try:
            with self._session_factory() as session:
                filters: list[Any] = []
                if term_type:
                    if isinstance(term_type, list):
                        normalized = [PostgresTermReader._normalize_type_code(t) for t in term_type]
                        filters.append(Term.term_type_code.in_(normalized))
                    else:
                        canonical = PostgresTermReader._normalize_type_code(term_type)
                        filters.append(Term.term_type_code == canonical)
                if dataset_ids:
                    filters.append(Term.library_id.in_(dataset_ids))

                from sqlalchemy import and_, func, or_

                filters.append(
                    or_(
                        Term.term_name == term_name,
                        Term.term_code == term_name,
                    )
                )

                where_clause: Any = and_(*filters)

                total = int(
                    session.execute(
                        select(func.count()).select_from(Term).where(where_clause)
                    ).scalar_one()
                )

                if total == 0:
                    return QueryResult(total=0, items=[])

                rows = session.execute(
                    select(
                        Term.term_id,
                        Term.term_code,
                        Term.term_name,
                        Term.term_type_code,
                        Term.library_id,
                        Term.parent_term_id,
                        Term.desc_summary,
                        Term.term_tags,
                    )
                    .where(where_clause)
                    .limit(top_k)
                    .offset(offset)
                ).all()
        except Exception:
            log.exception("_query_by_exact_name failed: term_name=%s", term_name)
            raise

        items: list[TermItem] = []
        for row in rows:
            tags: dict[str, str] = {}
            raw_tags = row[7]
            if isinstance(raw_tags, dict):
                tags = {str(k): str(v) for k, v in raw_tags.items()}

            items.append(
                TermItem(
                    term_id=str(row[0]),
                    term_code=str(row[1]),
                    term_name=str(row[2]),
                    term_type=str(row[3]),
                    dataset_id=str(row[4]) if row[4] else "",
                    parent_term_code=str(row[5]) if row[5] else "",
                    desc=str(row[6]) if row[6] else "",
                    labels=tags,
                    synonyms="",
                    ext_attrs={},
                    created_time=0,
                    updated_time=0,
                )
            )

        return QueryResult(total=total, items=items)
