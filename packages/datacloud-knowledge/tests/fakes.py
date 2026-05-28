"""测试用 Fake 实现 — 内存级 TermReader / TermWriter。

基于 _Architecture Patterns with Python_ 第 13 章「Fake 替代 Mock」原则设计。
所有写操作记录在内存列表中，所有读操作从内存字典读取。

用法:
    reader = FakeTermReader().seed(term_detail_1, term_detail_2)
    writer = FakeTermWriter()
    result = writer.import_terms(dataset_id="ds1", terms=[...])
    assert writer.imported_terms == [...]
"""

from __future__ import annotations

from typing import Any

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


class FakeTermReader:
    """内存级 Fake TermReader — 无 DB/HTTP，纯 Python。

    继承链:
        FakeTermReader → (duck typing) TermReader Protocol
    """

    def __init__(self) -> None:
        """初始化空术语存储。"""
        self._terms: dict[str, TermDetail] = {}

    # ── 测试 fixture 供给方法 ──────────────────────────────────────────

    def seed(self, *terms: TermDetail) -> FakeTermReader:
        """向内存存储批量添加术语详情。

        Args:
            *terms: 术语详情对象（可变参数）。

        Returns:
            self，支持链式调用。
        """
        for t in terms:
            self._terms[t.term_id] = t
        return self

    # ── TermReader 新增方法实现 ────────────────────────────────────────

    def query_terms(
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
        top_k: int = 20,
        offset: int = 0,
    ) -> QueryResult:
        """检索术语（内存过滤，与真实 DB 逻辑等价）。

        支持按 term_ids、term_name、keyword、term_type 过滤。
        label_filters / parent_term_code / label_condition 为简化的空实现，
        生产级 Fake 可按需扩展（第 13 章原则：只实现测试需要的路径）。
        """
        # 忽略未实现的过滤参数（Fake 只实现测试需要的路径）
        _ = (query_type, label_filters, label_condition, parent_term_code)

        items: list[TermItem] = list(self._terms.values())

        # term_ids 精确过滤
        if term_ids:
            items = [t for t in items if t.term_id in term_ids]

        # term_name 精确匹配
        if term_name:
            items = [t for t in items if t.term_name == term_name]
        elif keyword:
            # 关键词模糊匹配 term_name / term_code
            kw = keyword.lower()
            items = [t for t in items if kw in t.term_name.lower() or kw in t.term_code.lower()]

        # term_type 过滤
        if term_type:
            items = [t for t in items if t.term_type == term_type]

        # dataset_ids 过滤
        if dataset_ids:
            items = [t for t in items if t.dataset_id in dataset_ids]

        total = len(items)
        paged = items[offset : offset + top_k]
        return QueryResult(total=total, items=list(paged))

    def list_terms(
        self,
        *,
        dataset_id: str,
        term_type: str | None = None,
        term_type_no_eq: str | None = None,
        page_index: int = 1,
        page_size: int = 50,
    ) -> QueryResult:
        """分页列出术语（返回 TermDetail 含完整详情）。

        按 dataset_id 和 term_type 过滤，支持 term_type_no_eq 排除。
        返回的 items 为 TermDetail 列表。
        """
        items = [t for t in self._terms.values() if t.dataset_id == dataset_id]
        if term_type:
            items = [t for t in items if t.term_type == term_type]
        if term_type_no_eq:
            items = [t for t in items if t.term_type != term_type_no_eq]
        total = len(items)
        start = (page_index - 1) * page_size
        paged = items[start : start + page_size]
        return QueryResult(total=total, items=list(paged))

    def get_term_detail(self, *, dataset_id: str, term_id: str) -> TermDetail | None:
        """查询单条术语完整详情。

        Args:
            dataset_id: 术语库 ID（Fake 中暂不校验，仅用于接口兼容）。
            term_id: 术语 ID。

        Returns:
            TermDetail，不存在返回 None。
        """
        _ = dataset_id  # Fake 不校验 dataset_id 归属
        return self._terms.get(term_id)

    # ── 现有 TermReader 方法空实现（保持协议兼容）─────────────────────

    # 以下方法为 Fake 实现中不关心的路径，返回空值/空列表。
    # 参考书第 13 章：Fake 只实现测试需要的路径，不实现的返回安全默认值。

    def search_terms_exact(
        self,
        *,
        term_type_code: str = "",
        keyword: str | None = None,
        tags: Any = None,
        limit: int = 20,
        offset: int = 0,
        order_by: str = "relevance",
    ) -> Any:
        """空实现，返回空结果。"""
        from datacloud_knowledge.contracts.types import SearchTermsResult

        return SearchTermsResult(total=0, items=[])

    def search_terms(
        self,
        *,
        term_type_code: str = "",
        keyword: str | None = None,
        tags: Any = None,
        limit: int = 20,
        offset: int = 0,
        order_by: str = "relevance",
    ) -> Any:
        """空实现，返回空结果。"""
        from datacloud_knowledge.contracts.types import SearchTermsResult

        return SearchTermsResult(total=0, items=[])

    def get_term_by_ids(self, *, keys: Any = None) -> dict[tuple[str, str, str], str]:
        """空实现。"""
        return {}

    def get_term_names(
        self,
        *,
        term_ids: Any = None,
        scope_filter: dict[str, object] | None = None,
    ) -> dict[str, list[Any]]:
        """空实现。"""
        return {}

    def resolve_field_aliases(
        self,
        *,
        terms: Any = None,
        scope_code: str = "",
        library_id: str | None = None,
        resolve_values: bool = False,
        value_terms: Any = None,
    ) -> Any:
        """空实现。"""
        from datacloud_knowledge.contracts.types import FieldResolutionResult

        return FieldResolutionResult(unresolved=list(terms or []))

    def resolve_value_aliases(self, *, terms: Any = None, scope_code: str = "") -> Any:
        """空实现。"""
        from datacloud_knowledge.contracts.types import ValueResolutionResult

        return ValueResolutionResult(unmatched=list(terms or []))

    def get_object_props(self, *, source_term_ids: Any = None) -> dict[str, list[Any]]:
        """空实现。"""
        return {}

    def get_object_props_by_code(self, *, scope_code: str = "") -> list[Any]:
        """空实现。"""
        return []

    def get_prop_values_with_aliases(self, *, source_term_ids: Any = None) -> dict[str, list[Any]]:
        """空实现。"""
        return {}

    def get_prop_enum_values(
        self, *, scope_code: str = "", field_codes: Any = None
    ) -> dict[str, list[str]]:
        """空实现。"""
        return {}

    def get_bfs_distance(
        self,
        *,
        source_term_id: str = "",
        target_term_id: str = "",
        max_depth: int = 4,
    ) -> int | None:
        """空实现。"""
        return None

    def get_shortest_path_tree(
        self,
        *,
        target_term_id: str = "",
        source_term_type_codes: Any = None,
        max_depth: int = 6,
    ) -> Any:
        """空实现。"""
        return []

    def get_dimension_values(self) -> Any:
        """空实现。"""
        return []

    def get_user_scoped_names(self, *, user_id: str = "") -> Any:
        """空实现。"""
        return []

    def get_type_codes_by_category(self, *, categories: set[int] | None = None) -> set[str]:
        """空实现。"""
        return set()

    def get_matching_objects(
        self,
        *,
        ontology_code: str = "",
        field_codes: Any = None,
        limit: int = 2,
    ) -> Any:
        """空实现。"""
        return []

    def get_global_name_index(
        self,
    ) -> dict[str, list[tuple[str, str, str]]]:
        """空实现。"""
        return {}

    def get_name_ids_by_word(
        self,
        *,
        word: str = "",
        term_ids: Any = None,
        user_id: str | None = None,
    ) -> dict[str, str]:
        """空实现。"""
        return {}


class FakeTermWriter:
    """内存级 Fake TermWriter — 无 DB/HTTP。

    继承链:
        FakeTermWriter → (duck typing) TermWriter Protocol
    """

    def __init__(self) -> None:
        """初始化空写入记录。"""
        self._imported: list[TermCreate] = []
        self._updated: dict[str, TermUpdate] = {}
        self._import_results: ImportResult | None = None

    # ── 测试断言辅助属性 ──────────────────────────────────────────────

    @property
    def imported_terms(self) -> list[TermCreate]:
        """返回所有已导入的术语创建请求列表。"""
        return list(self._imported)

    def get_update(self, term_id: str) -> TermUpdate | None:
        """获取指定 term_id 的更新记录。

        Args:
            term_id: 术语 ID。

        Returns:
            TermUpdate 或 None。
        """
        return self._updated.get(term_id)

    # ── 测试 fixture 供给方法 ──────────────────────────────────────────

    def set_import_result(self, result: ImportResult) -> FakeTermWriter:
        """预设 import_terms 的返回结果。

        Args:
            result: 预设返回结果。

        Returns:
            self，支持链式调用。
        """
        self._import_results = result
        return self

    # ── TermWriter 新增方法实现 ────────────────────────────────────────

    def import_terms(self, *, dataset_id: str, terms: list[TermCreate]) -> ImportResult:
        """批量新增术语（内存记录）。

        Args:
            dataset_id: 目标术语库 ID。
            terms: 待新增术语列表。

        Returns:
            ImportResult，含创建数和 term_id 列表。
        """
        _ = dataset_id  # Fake 不校验 dataset_id
        self._imported.extend(terms)

        if self._import_results is not None:
            return self._import_results

        term_ids = [f"term-{i}" for i in range(len(terms))]
        return ImportResult(created=len(terms), term_ids=term_ids)

    def update_term(
        self,
        *,
        dataset_id: str,
        term_id: str,
        updates: TermUpdate,
    ) -> None:
        """更新术语（内存记录）。

        Args:
            dataset_id: 术语库 ID（Fake 中暂不校验）。
            term_id: 术语 ID。
            updates: 更新字段（None = 不修改）。

        Raises:
            ValueError: 术语不存在（当 Fake 感知到 term 不存在时可抛出）。
        """
        _ = dataset_id  # Fake 不校验 dataset_id
        self._updated[term_id] = updates

    # ── TermWriter 上下文管理器 ────────────────────────────────────────

    def __enter__(self) -> FakeTermWriter:
        """空实现上下文管理器入口。"""
        return self

    def __exit__(
        self,
        exc_type: object,
        exc_val: object,
        exc_tb: object,
    ) -> None:
        """空实现上下文管理器出口。"""

    # ── 现有 TermWriter 方法空实现（保持协议兼容）─────────────────────

    def insert_term(
        self,
        *,
        term_name: str = "",
        term_type_code: str = "",
        library_id: str | None = None,
        domain_id: str = "",
        parent_term_id: str | None = None,
        term_tags: dict[str, object] | None = None,
        user_id: str | None = None,
    ) -> str:
        """空实现，返回 fake ID。"""
        return "fake-term-id"

    def insert_term_knowledge(
        self,
        *,
        term_id: str = "",
        desc_summary: str = "",
        desc: str = "",
    ) -> str:
        """空实现，返回 fake ID。"""
        return "fake-knowledge-id"

    def create_term_name(
        self,
        *,
        term_id: str = "",
        name_text: str = "",
        search_scope: dict[str, object] | None = None,
        user_id: str | None = None,
    ) -> str:
        """空实现，返回 fake ID。"""
        return "fake-name-id"

    def batch_create_term_names(self, *, items: Any = None) -> list[str]:
        """空实现。"""
        return ["fake-name-id" for _ in range(len(items))] if items else []

    def create_term_with_knowledge(
        self,
        *,
        term_name: str = "",
        term_type_code: str = "",
        library_id: str | None = None,
        domain_id: str = "",
        knowledge_desc: str | None = None,
        parent_term_id: str | None = None,
        term_tags: dict[str, object] | None = None,
        user_id: str | None = None,
    ) -> str:
        """空实现，返回 fake ID。"""
        return "fake-term-id"

    def batch_create_vocabulary(self, *, words: Any = None) -> None:
        """空实现。"""

    def get_name_search_scope(self, *, name_id: str = "") -> dict[str, object] | None:
        """空实现。"""
        return None

    def update_name_search_scope(
        self,
        *,
        name_id: str = "",
        search_scope: dict[str, object] | None = None,
        updated_time: object = None,
    ) -> None:
        """空实现。"""


# ═══════════════════════════════════════════════════════════════════════════════
# 公开 API 导出
# ═══════════════════════════════════════════════════════════════════════════════

__all__ = [
    "FakeTermReader",
    "FakeTermWriter",
]
