"""TermBackend Protocol — 术语库原子能力.

完整对应 term_design.md 的全部接口面。
只做原子操作——不做编排（编排在 TermMixin）。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from datacloud_platform.models.shared import EmbeddingHit


class TermBackend(Protocol):
    """术语库原子能力协议（32 方法）。"""

    # ── Term ───────────────────────────────────────────────────────

    def search_terms(
        self,
        *,
        dataset_ids: list[str] | None = None,
        keyword: str | None = None,
        term_name: str | None = None,
        term_type: str | None = None,
        query_type: str = "fulltext",
        parent_term_code: str | None = None,
        label_filters: list[dict[str, Any]] | None = None,
        label_condition: str = "and",
        term_ids: list[str] | None = None,
        ext_attrs: dict[str, Any] | None = None,
        top_k: int = 20,
        offset: int = 0,
        query_vector: list[float] | None = None,
    ) -> dict[str, Any]:
        """多策略术语检索（exact/BM25/vector/RRF混合）。

        当 query_type 为 mixed/embedding 且未提供 query_vector 时，
        适配器内部自动计算 embedding 向量。

        对应: POST /api/v1/knowledge/terms/search
        """
        ...

    def search_terms_batch(
        self,
        *,
        keywords: list[str],
        dataset_ids: list[str] | None = None,
        term_type_codes: list[str] | None = None,
        query_type: str = "mixed",
        parent_term_code: str | None = None,
        label_filters: list[dict[str, Any]] | None = None,
        label_condition: str = "and",
        ext_attrs: dict[str, Any] | None = None,
        top_k: int = 20,
        offset: int = 0,
    ) -> dict[str, Any]:
        """批量多策略术语检索。

        内部自动批量计算 embedding + UNION ALL SQL。
        返回 ``{keyword: query_result, ...}``。

        对应: POST /api/v1/knowledge/terms/search/batch
        """
        ...

    def get_term_detail(
        self, *, library_id: str, term_id: str
    ) -> dict[str, Any] | None:
        """术语完整详情（含 parentChain / names / knowledges / domain / counts）。

        对应: POST /api/v1/rpc/term/get
        """
        ...

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
        """分页列出术语（keyword + domain_code 过滤，含 domain 翻译）。

        对应: POST /api/v1/rpc/term/list
        """
        ...

    def create_term(self, *, term: dict[str, Any]) -> dict[str, Any]:
        """创建单条术语。

        对应: POST /api/v1/rpc/term/create
        """
        ...

    def import_terms(
        self, *, library_id: str, terms: list[dict[str, Any]], backfill: bool = False
    ) -> dict[str, Any]:
        """批量导入术语（5 阶段：预检→去重→类型→术语→关系）。

        对应: POST /api/v1/rpc/term/import
        """
        ...

    def update_term(
        self, *, library_id: str = "", term_id: str, updates: dict[str, Any]
    ) -> None:
        """更新术语（部分更新）。

        对应: POST /api/v1/rpc/term/update
        """
        ...

    def delete_term(self, *, term_id: str) -> None:
        """删除术语（级联：relation + name + knowledge）。

        对应: POST /api/v1/rpc/term/delete
        """
        ...

    def query_term_relations(
        self,
        *,
        term_id: str,
        relation_category: str | None = None,
        direction: str = "both",
        depth: int = 1,
        keyword: str | None = None,
        page_index: int = 1,
        page_size: int = 20,
    ) -> dict[str, Any]:
        """查询术语一跳关系（含 keyword + 分页）。

        对应: POST /api/v1/rpc/term/getRelations
        """
        ...

    def query_term_relations_tree(
        self,
        *,
        term_id: str,
        max_depth: int = 3,
        relation_category: str | None = None,
        direction: str = "both",
    ) -> dict[str, Any]:
        """通过递归 CTE 一次查询获取多跳关系树（含 term 详情 JOIN）。

        支持单根 (term_id) 和多根 (term_ids) 两种模式。
        返回的每条 relation 包含 source/target 的 term_name, term_code,
        term_type_code, ext_attrs，以及 depth（跳数）和 next_term_id（BFS
        中新发现的端点）。
        """
        ...

    def query_term_relations_tree_batch(
        self,
        *,
        term_ids: list[str],
        max_depth: int = 3,
        direction: str = "both",
        relation_category: str | None = None,
    ) -> dict[str, Any]:
        """多根递归 CTE — 一次查询加载所有种子节点的全子图。

        使用 text[] visited_ids 规避 varchar(1000)[] 类型推导问题。
        relation_category: ONTOLOGY / BUSINESS 过滤（metadata/instance 映射）。
        """
        ...

    def query_edges_by_kb_id(
        self,
        *,
        kb_ids: list[str],
        limit: int = 2000,
        relation_category: str | None = None,
    ) -> dict[str, Any]:
        """Flat query: 加载产品库所有边，无递归、无深度限制。

        Returns ``{"data": [{source_term_id, target_term_id, relation_name,
        source_term_name, source_term_type, source_ext_attrs, ...}, ...]}``.
        """
        ...

    # ── TermRelation ───────────────────────────────────────────────

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
    ) -> dict[str, Any]: ...

    def get_term_relation(
        self,
        *,
        relation_id: str,
        strict: bool = False,
    ) -> dict[str, Any] | None: ...

    def create_term_relation(self, *, relation: dict[str, Any]) -> dict[str, Any]: ...

    def update_term_relation(
        self, *, relation_id: str, updates: dict[str, Any]
    ) -> None: ...

    def delete_term_relation(self, *, relation_id: str) -> None: ...

    # ── TermName ───────────────────────────────────────────────────

    def list_term_names(
        self, *, term_id: str | None = None, name_text: str | None = None
    ) -> list[dict[str, Any]]: ...

    def get_term_name(self, *, name_id: str) -> dict[str, Any] | None: ...

    def create_term_name(self, *, name: dict[str, Any]) -> dict[str, Any]: ...

    def update_term_name(self, *, name_id: str, updates: dict[str, Any]) -> None: ...

    def delete_term_name(self, *, name_id: str) -> None: ...

    # ── TermKnowledge ──────────────────────────────────────────────

    def list_term_knowledges(
        self, *, term_id: str | None = None, ext_system: str | None = None
    ) -> list[dict[str, Any]]: ...

    def get_term_knowledge(self, *, knowledge_id: str) -> dict[str, Any] | None: ...

    def create_term_knowledge(self, *, knowledge: dict[str, Any]) -> dict[str, Any]: ...

    def update_term_knowledge(
        self, *, knowledge_id: str, updates: dict[str, Any]
    ) -> None: ...

    def delete_term_knowledge(self, *, knowledge_id: str) -> None: ...

    # ── TermLibrary ────────────────────────────────────────────────

    def list_term_libraries(
        self,
        *,
        library_code: str | None = None,
        library_name: str | None = None,
    ) -> list[dict[str, Any]]: ...

    def get_term_library(self, *, library_id: str) -> dict[str, Any] | None: ...

    def create_term_library(self, *, library: dict[str, Any]) -> dict[str, Any]: ...

    def update_term_library(
        self, *, library_id: str, updates: dict[str, Any]
    ) -> None: ...

    def delete_term_library(self, *, library_id: str) -> None: ...

    # ── TermType ───────────────────────────────────────────────────

    def list_term_types(
        self,
        *,
        library_id: str,
        domain_code: str | None = None,
        type_category: int | None = None,
        keyword: str | None = None,
        page_index: int = 1,
        page_size: int = 20,
    ) -> dict[str, Any]:
        """术语类型列表（keyword + domain_code + 分页 + term_count）。

        对应: POST /api/v1/rpc/termType/list
        """
        ...

    def get_term_type(
        self, *, library_id: str, type_code: str
    ) -> dict[str, Any] | None:
        """术语类型详情。

        对应: POST /api/v1/rpc/termType/get
        """
        ...

    def list_term_type_relations(
        self,
        *,
        library_id: str,
        type_code: str,
        direction: str = "both",
        relation_category: str | None = None,
        keyword: str | None = None,
        page_index: int = 1,
        page_size: int = 20,
    ) -> dict[str, Any]:
        """术语类型一跳关系（直接查 term_relation.term_type_code 列）。

        对应: POST /api/v1/rpc/termType/getRelations
        """
        ...

    def create_term_type(
        self, *, library_id: str, term_type: dict[str, Any]
    ) -> dict[str, Any]: ...

    def update_term_type(
        self, *, library_id: str, type_code: str, updates: dict[str, Any]
    ) -> None: ...

    def delete_term_type(self, *, library_id: str, type_code: str) -> None: ...

    # ── Domain ─────────────────────────────────────────────────────

    def list_domains(
        self, *, library_id: str, parent_id: str | None = None
    ) -> list[dict[str, Any]]: ...

    def get_domain(
        self, *, library_id: str, domain_code: str
    ) -> dict[str, Any] | None: ...

    def create_domain(self, *, domain: dict[str, Any]) -> dict[str, Any]: ...

    def update_domain(
        self, *, library_id: str, domain_code: str, updates: dict[str, Any]
    ) -> None: ...

    def delete_domain(self, *, library_id: str, domain_code: str) -> None: ...

    # ── Vector ─────────────────────────────────────────────────────

    def embed(self, text: str) -> list[float]:
        """文本 → 向量。"""
        ...

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """批量文本 → 向量。"""
        ...

    def search_by_embedding(
        self, vector: list[float], term_types: list[str], limit: int = 20
    ) -> list[EmbeddingHit]:
        """向量相似度搜索。"""
        ...

    # ── Sync ───────────────────────────────────────────────────────

    def sync_terms(
        self,
        entity_code: str,
        entity_name: str,
        entity_source: str,
        fields: list[dict[str, Any]],
        *,
        backfill_vectors: bool = True,
    ) -> None:
        """同步本体对象术语到知识库。"""
        ...

    def remove_terms(self, entity_code: str) -> None:
        """清除对象关联的所有术语。"""
        ...

    # ── TermSyncHandler 协议方法 ────────────────────────────────────

    def ensure_term_type(self, *, base_id: str, type_code: str, type_name: str) -> None:
        """确保术语类型存在（幂等）。"""
        ...

    def upsert_terms(self, *, base_id: str, terms: list[dict[str, Any]]) -> list[str]:
        """批量 upsert 术语，返回 term_id 列表。"""
        ...

    def delete_terms(
        self,
        *,
        base_id: str,
        term_ids: list[str] | None = None,
        terms: list[dict[str, Any]] | None = None,
    ) -> None:
        """批量删除术语。"""
        ...
