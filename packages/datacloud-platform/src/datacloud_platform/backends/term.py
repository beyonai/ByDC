"""TermBackend Protocol — 术语库原子能力.

完整对应 docs/api/knowledge 的全部 API 面。
只做原子操作——不做编排（编排在 KnowledgeMixin）。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from datacloud_platform.models.shared import EmbeddingHit


class TermBackend(Protocol):
    """术语库原子能力协议。"""

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
        top_k: int = 20,
        offset: int = 0,
    ) -> dict[str, Any]:
        """多策略术语检索（exact/BM25/vector/RRF混合）。

        对应: POST /api/v1/knowledge/terms/search
        """
        ...

    def get_term_detail(
        self, *, dataset_id: str, term_id: str
    ) -> dict[str, Any] | None:
        """单条术语完整详情（基础属性+名称/别名+父链+关联知识）。

        对应: GET /api/v1/knowledge/terms/{termId}
        """
        ...

    def list_terms(
        self,
        *,
        dataset_id: str,
        term_type: str | None = None,
        term_type_no_eq: str | None = None,
        page_index: int = 1,
        page_size: int = 50,
    ) -> dict[str, Any]:
        """分页列出术语（每条含完整详情）。

        一次请求返回 TermDetail 列表，替代 N 次并发 get_term_detail。
        """
        ...

    def create_term(self, *, term: dict[str, Any]) -> dict[str, Any]:
        """创建单条术语。

        对应: POST /api/v1/knowledge/terms
        """
        ...

    def import_terms(
        self, *, dataset_id: str, terms: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """批量导入术语（含同义词、标签、扩展属性）。

        对应: POST /api/v1/knowledge/terms/import
        """
        ...

    def update_term(
        self, *, dataset_id: str, term_id: str, updates: dict[str, Any]
    ) -> None:
        """更新术语（仅更新非空字段，字段级部分更新）。

        对应: PUT /api/v1/knowledge/terms/{termId}
        """
        ...

    def delete_term(self, *, term_id: str) -> None:
        """删除术语。

        对应: DELETE /api/v1/knowledge/terms/{termId}
        """
        ...

    def query_term_relations(
        self,
        *,
        term_id: str,
        relation_category: str | None = None,
        direction: str = "both",
        depth: int = 1,
    ) -> dict[str, Any]:
        """查询术语的关联关系（N 跳进出关系）。

        对应: GET /api/v1/knowledge/terms/{termId}/relations
        """
        ...

    # ── TermRelation ───────────────────────────────────────────────

    def list_term_relations(
        self,
        *,
        source_term_id: str | None = None,
        target_term_id: str | None = None,
        relation_category: str | None = None,
    ) -> list[dict[str, Any]]: ...

    def get_term_relation(self, *, relation_id: str) -> dict[str, Any] | None: ...

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
        self, *, type_category: int | None = None
    ) -> list[dict[str, Any]]: ...

    def get_term_type(self, *, type_code: str) -> dict[str, Any] | None: ...

    def create_term_type(self, *, term_type: dict[str, Any]) -> dict[str, Any]: ...

    def update_term_type(self, *, type_code: str, updates: dict[str, Any]) -> None: ...

    def delete_term_type(self, *, type_code: str) -> None: ...

    # ── Domain ─────────────────────────────────────────────────────

    def list_domains(self, *, parent_id: str | None = None) -> list[dict[str, Any]]: ...

    def get_domain(self, *, domain_id: str) -> dict[str, Any] | None: ...

    def create_domain(self, *, domain: dict[str, Any]) -> dict[str, Any]: ...

    def update_domain(self, *, domain_id: str, updates: dict[str, Any]) -> None: ...

    def delete_domain(self, *, domain_id: str) -> None: ...

    def list_domain_term_types(self, *, domain_id: str) -> list[dict[str, Any]]: ...

    # ── Vector（从 KnowledgeBackend 迁入）──────────────────────────

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

    # ── Sync（从 KnowledgeBackend 迁入）────────────────────────────

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

    # ── TermSyncHandler 协议方法（供 term_sync_worker 注入使用）──────

    def ensure_term_type(self, *, base_id: str, type_code: str, type_name: str) -> None:
        """确保术语类型存在（幂等）。"""
        ...

    def upsert_terms(self, *, base_id: str, terms: list[dict[str, Any]]) -> list[str]:
        """批量 upsert 术语，返回 term_id（UUID）列表。

        terms 每条字段：term_code, term_name, term_desc,
        term_type_code, library_code, domain_code
        """
        ...

    def delete_terms(
        self,
        *,
        base_id: str,
        term_ids: list[str] | None = None,
        terms: list[dict[str, Any]] | None = None,
    ) -> None:
        """批量删除术语，支持 UUID 列表和业务三元组两种入参，均有值时全部执行。

        term_ids: 数据库 UUID 列表，直接按主键删除。
        terms:    业务三元组 dict 列表（term_code, term_type_code, library_code）。
        """
        ...
