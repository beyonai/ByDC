"""TermMixin — 术语库原子操作编排（薄封装层）。

每个方法直接委托到 TermBackend，不做编排。
"""

from __future__ import annotations

from typing import Any

from datacloud_knowledge.sync import TermSyncHandler

from datacloud_platform.backends._contracts import _HasTermBackend


class TermMixin(TermSyncHandler):
    """Mixin for term-level atomic operations.

    Thin wrapper over TermBackend — 每个方法 = 一次 backend 调用，不做编排。
    同时实现 TermSyncHandler 协议，可作为 term_sync_worker 的 handler。
    """

    # ── Term ───────────────────────────────────────────────────────

    def search_terms(
        self: _HasTermBackend, base_id: str, **kwargs: Any
    ) -> dict[str, Any]:
        return self._term_for(base_id).search_terms(**kwargs)

    def get_term_detail(
        self: _HasTermBackend, base_id: str, *, library_id: str, term_id: str
    ) -> dict[str, Any] | None:
        return self._term_for(base_id).get_term_detail(
            library_id=library_id, term_id=term_id
        )

    def list_terms(
        self: _HasTermBackend, base_id: str, **kwargs: Any
    ) -> dict[str, Any]:
        return self._term_for(base_id).list_terms(**kwargs)

    def create_term(
        self: _HasTermBackend, base_id: str, *, term: dict[str, Any]
    ) -> dict[str, Any]:
        return self._term_for(base_id).create_term(term=term)

    def import_terms(
        self: _HasTermBackend,
        base_id: str,
        *,
        library_id: str,
        terms: list[dict[str, Any]],
        backfill: bool = False,
    ) -> dict[str, Any]:
        return self._term_for(base_id).import_terms(
            library_id=library_id, terms=terms, backfill=backfill
        )

    def update_term(
        self: _HasTermBackend,
        base_id: str,
        *,
        term_id: str,
        updates: dict[str, Any],
    ) -> None:
        self._term_for(base_id).update_term(term_id=term_id, updates=updates)

    def delete_term(self: _HasTermBackend, base_id: str, *, term_id: str) -> None:
        self._term_for(base_id).delete_term(term_id=term_id)

    def query_term_relations(
        self: _HasTermBackend, base_id: str, **kwargs: Any
    ) -> dict[str, Any]:
        return self._term_for(base_id).query_term_relations(**kwargs)

    # ── TermRelation ───────────────────────────────────────────────

    def list_term_relations(
        self: _HasTermBackend, base_id: str, **kwargs: Any
    ) -> dict[str, Any]:
        return self._term_for(base_id).list_term_relations(**kwargs)

    def get_term_relation(
        self: _HasTermBackend, base_id: str, *, relation_id: str
    ) -> dict[str, Any] | None:
        return self._term_for(base_id).get_term_relation(relation_id=relation_id)

    def create_term_relation(
        self: _HasTermBackend, base_id: str, *, relation: dict[str, Any]
    ) -> dict[str, Any]:
        return self._term_for(base_id).create_term_relation(relation=relation)

    def update_term_relation(
        self: _HasTermBackend,
        base_id: str,
        *,
        relation_id: str,
        updates: dict[str, Any],
    ) -> None:
        self._term_for(base_id).update_term_relation(
            relation_id=relation_id, updates=updates
        )

    def delete_term_relation(
        self: _HasTermBackend, base_id: str, *, relation_id: str
    ) -> None:
        self._term_for(base_id).delete_term_relation(relation_id=relation_id)

    # ── TermName ───────────────────────────────────────────────────

    def list_term_names(
        self: _HasTermBackend, base_id: str, **kwargs: Any
    ) -> list[dict[str, Any]]:
        return self._term_for(base_id).list_term_names(**kwargs)

    def get_term_name(
        self: _HasTermBackend, base_id: str, *, name_id: str
    ) -> dict[str, Any] | None:
        return self._term_for(base_id).get_term_name(name_id=name_id)

    def create_term_name(
        self: _HasTermBackend, base_id: str, *, name: dict[str, Any]
    ) -> dict[str, Any]:
        return self._term_for(base_id).create_term_name(name=name)

    def update_term_name(
        self: _HasTermBackend, base_id: str, *, name_id: str, updates: dict[str, Any]
    ) -> None:
        self._term_for(base_id).update_term_name(name_id=name_id, updates=updates)

    def delete_term_name(self: _HasTermBackend, base_id: str, *, name_id: str) -> None:
        self._term_for(base_id).delete_term_name(name_id=name_id)

    # ── TermKnowledge ──────────────────────────────────────────────

    def list_term_knowledges(
        self: _HasTermBackend, base_id: str, **kwargs: Any
    ) -> list[dict[str, Any]]:
        return self._term_for(base_id).list_term_knowledges(**kwargs)

    def get_term_knowledge(
        self: _HasTermBackend, base_id: str, *, knowledge_id: str
    ) -> dict[str, Any] | None:
        return self._term_for(base_id).get_term_knowledge(knowledge_id=knowledge_id)

    def create_term_knowledge(
        self: _HasTermBackend, base_id: str, *, knowledge: dict[str, Any]
    ) -> dict[str, Any]:
        return self._term_for(base_id).create_term_knowledge(knowledge=knowledge)

    def update_term_knowledge(
        self: _HasTermBackend,
        base_id: str,
        *,
        knowledge_id: str,
        updates: dict[str, Any],
    ) -> None:
        self._term_for(base_id).update_term_knowledge(
            knowledge_id=knowledge_id, updates=updates
        )

    def delete_term_knowledge(
        self: _HasTermBackend, base_id: str, *, knowledge_id: str
    ) -> None:
        self._term_for(base_id).delete_term_knowledge(knowledge_id=knowledge_id)

    # ── TermLibrary ────────────────────────────────────────────────

    def list_term_libraries(
        self: _HasTermBackend, base_id: str, **kwargs: Any
    ) -> list[dict[str, Any]]:
        return self._term_for(base_id).list_term_libraries(**kwargs)

    def get_term_library(
        self: _HasTermBackend, base_id: str, *, library_id: str
    ) -> dict[str, Any] | None:
        return self._term_for(base_id).get_term_library(library_id=library_id)

    def create_term_library(
        self: _HasTermBackend, base_id: str, *, library: dict[str, Any]
    ) -> dict[str, Any]:
        return self._term_for(base_id).create_term_library(library=library)

    def update_term_library(
        self: _HasTermBackend, base_id: str, *, library_id: str, updates: dict[str, Any]
    ) -> None:
        self._term_for(base_id).update_term_library(
            library_id=library_id, updates=updates
        )

    def delete_term_library(
        self: _HasTermBackend, base_id: str, *, library_id: str
    ) -> None:
        self._term_for(base_id).delete_term_library(library_id=library_id)

    # ── TermType ───────────────────────────────────────────────────

    def list_term_types(
        self: _HasTermBackend, base_id: str, **kwargs: Any
    ) -> dict[str, Any]:
        return self._term_for(base_id).list_term_types(**kwargs)

    def get_term_type(
        self: _HasTermBackend, base_id: str, *, library_id: str, type_code: str
    ) -> dict[str, Any] | None:
        return self._term_for(base_id).get_term_type(
            library_id=library_id, type_code=type_code
        )

    def list_term_type_relations(
        self: _HasTermBackend, base_id: str, **kwargs: Any
    ) -> dict[str, Any]:
        return self._term_for(base_id).list_term_type_relations(**kwargs)

    def create_term_type(
        self: _HasTermBackend, base_id: str, *, term_type: dict[str, Any]
    ) -> dict[str, Any]:
        return self._term_for(base_id).create_term_type(term_type=term_type)

    def update_term_type(
        self: _HasTermBackend,
        base_id: str,
        *,
        library_id: str,
        type_code: str,
        updates: dict[str, Any],
    ) -> None:
        self._term_for(base_id).update_term_type(
            library_id=library_id, type_code=type_code, updates=updates
        )

    def delete_term_type(
        self: _HasTermBackend, base_id: str, *, library_id: str, type_code: str
    ) -> None:
        self._term_for(base_id).delete_term_type(
            library_id=library_id, type_code=type_code
        )

    # ── Domain ─────────────────────────────────────────────────────

    def list_domains(
        self: _HasTermBackend, base_id: str, *, library_id: str, **kwargs: Any
    ) -> list[dict[str, Any]]:
        return self._term_for(base_id).list_domains(library_id=library_id, **kwargs)

    def get_domain(
        self: _HasTermBackend, base_id: str, *, library_id: str, domain_code: str
    ) -> dict[str, Any] | None:
        return self._term_for(base_id).get_domain(
            library_id=library_id, domain_code=domain_code
        )

    def create_domain(
        self: _HasTermBackend, base_id: str, *, domain: dict[str, Any]
    ) -> dict[str, Any]:
        return self._term_for(base_id).create_domain(domain=domain)

    def update_domain(
        self: _HasTermBackend,
        base_id: str,
        *,
        library_id: str,
        domain_code: str,
        updates: dict[str, Any],
    ) -> None:
        self._term_for(base_id).update_domain(
            library_id=library_id, domain_code=domain_code, updates=updates
        )

    def delete_domain(
        self: _HasTermBackend, base_id: str, *, library_id: str, domain_code: str
    ) -> None:
        self._term_for(base_id).delete_domain(
            library_id=library_id, domain_code=domain_code
        )

    # ── Vector ─────────────────────────────────────────────────────

    def embed(self: _HasTermBackend, base_id: str, text: str) -> list[float]:
        return self._term_for(base_id).embed(text)

    def embed_batch(
        self: _HasTermBackend, base_id: str, texts: list[str]
    ) -> list[list[float]]:
        return self._term_for(base_id).embed_batch(texts)

    # ── Sync ───────────────────────────────────────────────────────

    def sync_terms(
        self: _HasTermBackend,
        base_id: str,
        entity_code: str,
        entity_name: str,
        entity_source: str,
        fields: list[dict[str, Any]],
        *,
        backfill_vectors: bool = True,
    ) -> None:
        self._term_for(base_id).sync_terms(
            entity_code,
            entity_name,
            entity_source,
            fields,
            backfill_vectors=backfill_vectors,
        )

    def remove_terms(self: _HasTermBackend, base_id: str, entity_code: str) -> None:
        self._term_for(base_id).remove_terms(entity_code)

    # ── TermSyncHandler 实现 ────────────────────────────────────────

    def ensure_term_type(
        self: _HasTermBackend, *, base_id: str, type_code: str, type_name: str
    ) -> None:
        self._term_for(base_id).ensure_term_type(
            base_id=base_id, type_code=type_code, type_name=type_name
        )

    def upsert_terms(
        self: _HasTermBackend, *, base_id: str, terms: list[dict[str, Any]]
    ) -> list[str]:
        return self._term_for(base_id).upsert_terms(base_id=base_id, terms=terms)

    def delete_terms(
        self: _HasTermBackend,
        *,
        base_id: str,
        term_ids: list[str] | None = None,
        terms: list[dict[str, Any]] | None = None,
    ) -> None:
        self._term_for(base_id).delete_terms(
            base_id=base_id, term_ids=term_ids, terms=terms
        )
