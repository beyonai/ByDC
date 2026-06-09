"""FakeTermStore — 内存级 TermStore 实现，零 IO。

基于 Fake > Mock 原则设计（ARCHITECTURE_V2.md §8.1）。
实现 TermStore Protocol 的 5 个方法，用内存 dict 存储，
支持 seed() 方法注入测试数据。

用法:
    store = FakeTermStore().seed(term_detail_1, term_detail_2)
    result = store.query_terms(keyword="销售额")
    assert result.total == 1
"""

from __future__ import annotations

from typing import Any

from datacloud_knowledge.capabilities.types import (
    ImportResult,
    LabelFilter,
    QueryResult,
    QueryType,
    TermCreate,
    TermDetail,
    TermUpdate,
)

__all__ = ["FakeTermStore"]


class FakeTermStore:
    """内存级 Fake TermStore，无 DB/HTTP，纯 Python。

    实现 TermStore Protocol（capabilities/protocol.py）全部 5 个方法。
    """

    def __init__(self) -> None:
        """初始化空术语存储。"""
        self._terms: dict[str, TermDetail] = {}
        self._imported: list[TermCreate] = []
        self._updated: dict[str, TermUpdate] = {}

    # ── 测试 fixture 供给方法 ──────────────────────────────────────────

    def seed(self, *terms: TermDetail) -> FakeTermStore:
        """向内存存储批量添加术语详情。返回 self，支持链式调用。"""
        for t in terms:
            self._terms[t.term_id] = t
        return self

    # ── 断言辅助 ────────────────────────────────────────────────────

    @property
    def imported_terms(self) -> list[TermCreate]:
        """返回所有已导入的术语创建请求列表。"""
        return list(self._imported)

    @property
    def stored_count(self) -> int:
        """返回当前存储的术语数量。"""
        return len(self._terms)

    # ── TermStore Protocol 实现 ────────────────────────────────────────

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
        label_condition: str = "and",
        term_ids: list[str] | None = None,
        top_k: int = 20,
        offset: int = 0,
    ) -> QueryResult:
        """检索术语（内存过滤）."""
        _ = (query_type, label_condition)

        items: list[Any] = list(self._terms.values())

        if term_ids:
            ids_set = set(term_ids)
            items = [t for t in items if t.term_id in ids_set]

        if term_name:
            items = [t for t in items if t.term_name == term_name]
        elif keyword:
            kw = keyword.lower()
            items = [t for t in items if kw in t.term_name.lower() or kw in t.term_code.lower()]

        if term_type:
            type_set = {term_type} if isinstance(term_type, str) else set(term_type)
            items = [t for t in items if t.term_type in type_set]

        if dataset_ids:
            ds_set = set(dataset_ids)
            items = [t for t in items if t.dataset_id in ds_set]

        if parent_term_code:
            items = [t for t in items if t.parent_term_code == parent_term_code]

        if label_filters:
            for lf in label_filters:
                if lf.filter_value is not None:
                    items = [t for t in items if t.labels.get(lf.field_code) == lf.filter_value]

        total = len(items)
        paged = items[offset : offset + top_k]
        return QueryResult(total=total, items=list(paged))

    def get_term_detail(self, *, dataset_id: str, term_id: str) -> TermDetail | None:
        """查询单条术语完整详情。"""
        _ = dataset_id
        return self._terms.get(term_id)

    def list_terms(
        self,
        *,
        dataset_id: str,
        term_type: str | None = None,
        term_type_no_eq: str | None = None,
        page_index: int = 1,
        page_size: int = 50,
    ) -> QueryResult:
        """分页列出术语。"""
        items: list[Any] = [t for t in self._terms.values() if t.dataset_id == dataset_id]
        if term_type:
            items = [t for t in items if t.term_type == term_type]
        if term_type_no_eq:
            items = [t for t in items if t.term_type != term_type_no_eq]

        total = len(items)
        start = (page_index - 1) * page_size
        paged = items[start : start + page_size]
        return QueryResult(total=total, items=list(paged))

    def import_terms(self, *, dataset_id: str, terms: list[TermCreate]) -> ImportResult:
        """批量新增术语（内存记录 + 写入内部存储）。"""
        _ = dataset_id
        self._imported.extend(terms)

        term_ids: list[str] = []
        for i, tc in enumerate(terms):
            tid = f"fake-{len(self._terms) + i}"
            term_ids.append(tid)
            detail = TermDetail(
                term_id=tid,
                term_code=tc.term_code,
                term_name=tc.term_name,
                term_type=tc.term_type,
                dataset_id=dataset_id,
                parent_term_code=tc.parent_term_code,
                desc=tc.desc,
                labels=tc.labels,
                synonyms="|".join(tc.synonyms),
                ext_attrs=tc.ext_attrs,
            )
            self._terms[tid] = detail

        return ImportResult(created=len(terms), term_ids=term_ids)

    def update_term(self, *, dataset_id: str, term_id: str, updates: TermUpdate) -> None:
        """更新术语。"""
        _ = dataset_id
        self._updated[term_id] = updates

        existing = self._terms.get(term_id)
        if existing is None:
            raise ValueError(f"术语不存在: term_id={term_id}")

        updated = TermDetail(
            term_id=term_id,
            term_code=updates.term_code if updates.term_code is not None else existing.term_code,
            term_name=updates.term_name if updates.term_name is not None else existing.term_name,
            term_type=updates.term_type if updates.term_type is not None else existing.term_type,
            dataset_id=existing.dataset_id,
            parent_term_code=(
                updates.parent_term_code
                if updates.parent_term_code is not None
                else existing.parent_term_code
            ),
            desc=updates.desc if updates.desc is not None else existing.desc,
            labels=updates.labels if updates.labels is not None else existing.labels,
            synonyms=(
                "|".join(updates.synonyms) if updates.synonyms is not None else existing.synonyms
            ),
            ext_attrs=updates.ext_attrs if updates.ext_attrs is not None else existing.ext_attrs,
        )
        self._terms[term_id] = updated
