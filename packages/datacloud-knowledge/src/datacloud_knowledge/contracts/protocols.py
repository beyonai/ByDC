"""公共协议 — 术语读取、搜索召回、术语写入。

定义数据中心知识服务的三层协议接口：
- TermReader: 无状态纯查询操作（术语检索、别名消歧、属性查询）
- TermSearchEngine: 文本/向量多路召回策略（BM25、子串、向量）
- TermWriter: 有状态持久化操作（创建术语、名称、词汇）
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from .text import Tokenizer
from .types import (
    BM25Result,
    FieldResolutionResult,
    NameItem,
    PropItem,
    SearchTermsResult,
    SubstringResult,
    TagFilter,
    TermNameCreate,
    ValueResolutionResult,
    ValueWithAliases,
    VectorResult,
)


class TermReader(Protocol):
    """术语读取接口。所有查询操作，无副作用。

    仅依赖 DB 查询，不修改任何数据。实现方负责 DB session 管理和 SQL 组装。
    """

    def search_terms(
        self,
        *,
        term_type_code: str,
        keyword: str | None = None,
        tags: Sequence[TagFilter] | None = None,
        limit: int = 20,
        offset: int = 0,
        order_by: str = "relevance",
    ) -> SearchTermsResult:
        """按术语类型检索术语列表。

        Args:
            term_type_code: 术语类型编码（支持驼峰简写映射，如 ONTOLOGY_VIEW→view）。
            keyword: 可选关键词搜索（精确匹配 term_name/term_code，BM25 兜底）。
            tags: 可选标签过滤条件列表。
            limit: 返回条数（1..200）。
            offset: 分页偏移（>=0）。
            order_by: 排序方式（relevance/updated_time/created_time/term_name）。

        Returns:
            分页搜索结果，包含 total 和 items。
        """
        ...

    def get_term_by_ids(
        self, *, keys: Sequence[tuple[str, str, str]]
    ) -> dict[tuple[str, str, str], str]:
        """批量根据 (library_id, term_type_code, term_code) 三元组查询 term_id。

        Args:
            keys: (library_id, term_type_code, term_code) 三元组列表。

        Returns:
            {(library_id, term_type_code, term_code) → term_id} 映射。
        """
        ...

    def get_term_names(
        self,
        *,
        term_ids: Sequence[str],
        scope_filter: dict[str, object] | None = None,
    ) -> dict[str, list[NameItem]]:
        """批量查询术语的所有名称（标准名 + 别名）。

        Args:
            term_ids: 术语 ID 列表。
            scope_filter: 可选的作用域过滤条件（如 {"scope": "view", "code": "xxx"}）。

        Returns:
            {term_id → [NameItem]} 映射。
        """
        ...

    def resolve_field_aliases(
        self,
        *,
        terms: Sequence[str],
        scope_code: str,
        library_id: str | None = None,
        resolve_values: bool = False,
        value_terms: Sequence[str] | None = None,
    ) -> FieldResolutionResult:
        """轻量级字段 + 值别名精确消歧。

        在 scope_code 对应的视图/对象下查找字段别名（TermName.name_text → prop term_code）
        和可选值别名（child term 的 term_name/TermName 别名）。

        Args:
            terms: 待解析的字段中文名/别名列表。
            scope_code: 视图或对象 code（如 "scene_enterprise_analysis"）。
            library_id: 预留参数，v1 不使用。
            resolve_values: 是否对 value_terms 追加值级别消歧。
            value_terms: 待值消歧的过滤值列表（如企业名、地区名等）。

        Returns:
            FieldResolutionResult，包含 resolved/ambiguous/unresolved 三类结果。
        """
        ...

    def resolve_value_aliases(
        self, *, terms: Sequence[str], scope_code: str
    ) -> ValueResolutionResult:
        """轻量级属性值精确消歧。

        在 scope_code 对应的 view/object 下，通过关系链路查找 child term 名称和别名匹配。

        Args:
            terms: 待匹配的值列表（如企业名、地区名等）。
            scope_code: 视图或对象 code。

        Returns:
            ValueResolutionResult，包含 matched（已知值）和 unmatched（未知值）。
        """
        ...

    def get_object_props(self, *, source_term_ids: Sequence[str]) -> dict[str, list[PropItem]]:
        """批量查询对象/视图下的属性（通过 term_relation HAS_FIELD）。

        Args:
            source_term_ids: 源术语 ID 列表（view/object 的 term_id）。

        Returns:
            {source_term_id → [PropItem]} 映射。
        """
        ...

    def get_prop_values_with_aliases(
        self, *, source_term_ids: Sequence[str]
    ) -> dict[str, list[ValueWithAliases]]:
        """批量查询对象下属性的值术语及其别名。

        路径: source → (HAS_FIELD) → prop → (parent_term_id) → child term。

        Args:
            source_term_ids: 源术语 ID 列表。

        Returns:
            {source_term_id → [ValueWithAliases]} 映射。
        """
        ...

    def get_prop_enum_values(
        self, *, scope_code: str, field_codes: Sequence[str]
    ) -> dict[str, list[str]]:
        """查询指定 prop 的枚举值（child term_name + 别名）。

        路径: view/object(scope_code) → HAS_FIELD → prop(field_code) → child terms。

        Args:
            scope_code: 视图或对象 code。
            field_codes: 待查询的 prop term_code 列表。

        Returns:
            {field_code → [枚举值列表]}，去重保序。
        """
        ...


class TermSearchEngine(Protocol):
    """文本召回引擎。每种策略独立暴露，由调用方控制策略组合和 RRF 融合。

    三路核心召回策略：
    - BM25: PostgreSQL tsvector + ts_rank_cd 全文搜索
    - Substring: 双向子串匹配（术语名⊆查询 OR 查询⊆术语名）
    - Vector: pgvector HNSW 余弦相似度搜索
    """

    def search_bm25(
        self,
        *,
        query_text: str,
        top_k: int = 10,
        min_score: float = 0.01,
        tokenizer: Tokenizer,
        term_type_codes: Sequence[str] | None = None,
        partitioned: bool = False,
        per_type_limit: int = 3,
    ) -> list[BM25Result]:
        """使用 BM25 文本匹配搜索术语名称。

        Args:
            query_text: 查询文本（原始输入，由 tokenizer 分词后构建 tsquery）。
            top_k: 返回结果数量上限。
            min_score: 最小 BM25 分数阈值。
            tokenizer: 分词器实例（负责分词和 tsquery 构建）。
            term_type_codes: 可选术语类型白名单过滤。
            partitioned: 是否按 term_type_code 分区取 top-N。
            per_type_limit: 分区模式下每个类型的 top-N 数量。

        Returns:
            BM25Result 列表，按 score 降序。
        """
        ...

    def search_substring(
        self,
        *,
        query_text: str,
        top_k: int = 20,
        term_type_codes: Sequence[str] | None = None,
        partitioned: bool = False,
        per_type_limit: int = 3,
    ) -> list[SubstringResult]:
        """执行双向子串匹配召回。

        匹配逻辑：
        1. 术语名是查询文本的子串（term_name IN query_text）
        2. 查询文本是术语名的子串（query_text IN term_name）

        Args:
            query_text: 用户输入的查询文本。
            top_k: 最大返回数量。
            term_type_codes: 可选术语类型白名单过滤。
            partitioned: 是否按 term_type_code 分区取 top-N。
            per_type_limit: 分区模式下每个类型的 top-N 数量。

        Returns:
            SubstringResult 列表，按名称长度降序。
        """
        ...

    def search_vector(
        self,
        *,
        query_vector: Sequence[float],
        top_k: int = 10,
        min_similarity: float = 0.5,
    ) -> list[VectorResult]:
        """使用预计算的向量进行语义搜索。

        Args:
            query_vector: 查询文本向量。
            top_k: 返回结果数量上限。
            min_similarity: 最小余弦相似度阈值（0-1）。

        Returns:
            VectorResult 列表，按 similarity 降序。
        """
        ...


class TermWriter(Protocol):
    """术语写入接口。所有持久化操作。

    实现方负责 DB session 管理、事务控制和幂等性保证。
    """

    def create_term_name(
        self,
        *,
        term_id: str,
        name_text: str,
        search_scope: dict[str, object],
        user_id: str | None = None,
    ) -> str:
        """创建用户级术语别名。

        Args:
            term_id: 归属术语 ID。
            name_text: 别名文本。
            search_scope: 搜索作用域（JSONB 格式，含 user_id/score/use_count 等）。
            user_id: 创建用户 ID。

        Returns:
            生成的 name_id。
        """
        ...

    def batch_create_term_names(self, *, items: Sequence[TermNameCreate]) -> list[str]:
        """批量创建术语别名。

        Args:
            items: 别名创建项列表。

        Returns:
            生成的 name_id 列表，与 items 顺序对应。
        """
        ...

    def create_term_with_knowledge(
        self,
        *,
        term_name: str,
        term_type_code: str,
        library_id: str,
        domain_id: str,
        knowledge_desc: str | None = None,
        parent_term_id: str | None = None,
        term_tags: dict[str, object] | None = None,
        user_id: str | None = None,
    ) -> str:
        """创建新术语及其关联知识。

        Args:
            term_name: 术语标准名称。
            term_type_code: 术语类型编码。
            library_id: 术语库 ID。
            domain_id: 所属领域 ID。
            knowledge_desc: 关联知识描述文本。
            parent_term_id: 父术语 ID（可选，用于实例-概念关系）。
            term_tags: 术语标签属性（JSONB）。
            user_id: 创建用户 ID。

        Returns:
            创建的 term_id。
        """
        ...

    def batch_create_vocabulary(self, *, words: Sequence[str]) -> None:
        """批量写入分词词典（TermVocabulary 表）。

        用于 jieba 自定义词典数据源，将 TermName 去重后写入。

        Args:
            words: 词汇文本列表。
        """
        ...
