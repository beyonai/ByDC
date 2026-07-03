"""TermBackend + TermRelation + TermName."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class TermBackendMixin:
    """TermBackend + TermRelation + TermName."""

    # ── TermBackend ─────────────────────────────────────────────────────────

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
        """Multi-strategy term search via datacloud_knowledge provider."""
        from datacloud_knowledge.provider import query_terms  # noqa: PLC0415

        return query_terms(  # type: ignore[no-any-return]
            dataset_ids=dataset_ids,
            keyword=keyword,
            term_name=term_name,
            term_type=term_type,
            query_type=query_type,
            parent_term_code=parent_term_code,
            label_filters=label_filters,
            label_condition=label_condition,
            term_ids=term_ids,
            top_k=top_k,
            offset=offset,
        )

    def get_term_detail(
        self, *, dataset_id: str, term_id: str
    ) -> dict[str, Any] | None:
        """Get single term detail via datacloud_knowledge provider."""
        from datacloud_knowledge.provider import (  # noqa: PLC0415
            get_term_detail as sdk_get_term_detail,
        )

        return sdk_get_term_detail(dataset_id=dataset_id, term_id=term_id)  # type: ignore[no-any-return]

    def list_terms(
        self,
        *,
        dataset_id: str,
        term_type: str | None = None,
        term_type_no_eq: str | None = None,
        page_index: int = 1,
        page_size: int = 50,
    ) -> dict[str, Any]:
        """Paginated term listing via datacloud_knowledge provider."""
        from datacloud_knowledge.provider import (  # noqa: PLC0415
            list_terms as sdk_list_terms,
        )

        return sdk_list_terms(  # type: ignore[no-any-return]
            dataset_id=dataset_id,
            term_type=term_type,
            term_type_no_eq=term_type_no_eq,
            page_index=page_index,
            page_size=page_size,
        )

    def create_term(self, *, term: dict[str, Any]) -> dict[str, Any]:
        """Create a single term — wraps import_terms."""
        return self.import_terms(
            dataset_id=term.get("datasetId", term.get("dataset_id", "")),
            terms=[term],
        )

    def import_terms(
        self, *, dataset_id: str, terms: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Batch import terms via datacloud_knowledge provider."""
        from datacloud_knowledge.provider import (  # noqa: PLC0415
            import_terms as sdk_import_terms,
        )

        return sdk_import_terms(dataset_id=dataset_id, terms=terms)  # type: ignore[no-any-return]

    def update_term(
        self, *, dataset_id: str, term_id: str, updates: dict[str, Any]
    ) -> None:
        """Update a term via datacloud_knowledge provider."""
        from datacloud_knowledge.provider import (  # noqa: PLC0415
            update_term as sdk_update_term,
        )

        sdk_update_term(dataset_id=dataset_id, term_id=term_id, updates=updates)

    def delete_term(self, *, term_id: str) -> None:
        """Delete a term via datacloud_knowledge writer."""
        from datacloud_knowledge.adapters import create_writer  # noqa: PLC0415

        writer = create_writer()
        writer.delete_term(term_id=term_id)

    def query_term_relations(
        self,
        *,
        term_id: str,
        relation_category: str | None = None,
        direction: str = "both",
        depth: int = 1,
    ) -> dict[str, Any]:
        """Query term relations via knowledge reader."""
        reader = self._get_knowledge_reader()
        try:
            return reader.query_term_relations(  # type: ignore[no-any-return]
                term_id=term_id,
                relation_category=relation_category,
                direction=direction,
                depth=depth,
            )
        except Exception:
            logger.exception("query_term_relations failed term_id=%s", term_id)
            return {"data": [], "totalCount": 0}

    # ── TermRelation ────────────────────────────────────────────────────

    def list_term_relations(
        self,
        *,
        source_term_id: str | None = None,
        target_term_id: str | None = None,
        relation_category: str | None = None,
    ) -> list[dict[str, Any]]:
        reader = self._get_knowledge_reader()
        try:
            return reader.list_term_relations(  # type: ignore[no-any-return]
                source_term_id=source_term_id,
                target_term_id=target_term_id,
                relation_category=relation_category,
            )
        except Exception:
            logger.exception("list_term_relations failed")
            return []

    def get_term_relation(self, *, relation_id: str) -> dict[str, Any] | None:
        reader = self._get_knowledge_reader()
        try:
            return reader.get_term_relation(relation_id=relation_id)  # type: ignore[no-any-return]
        except Exception:
            logger.exception("get_term_relation failed relation_id=%s", relation_id)
            return None

    def create_term_relation(self, *, relation: dict[str, Any]) -> dict[str, Any]:
        from datacloud_knowledge.adapters import create_writer  # noqa: PLC0415

        writer = create_writer()
        return writer.create_term_relation(relation=relation)  # type: ignore[no-any-return]

    def update_term_relation(
        self, *, relation_id: str, updates: dict[str, Any]
    ) -> None:
        from datacloud_knowledge.adapters import create_writer  # noqa: PLC0415

        writer = create_writer()
        writer.update_term_relation(relation_id=relation_id, updates=updates)

    def delete_term_relation(self, *, relation_id: str) -> None:
        from datacloud_knowledge.adapters import create_writer  # noqa: PLC0415

        writer = create_writer()
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
        from datacloud_knowledge.adapters import create_writer  # noqa: PLC0415

        writer = create_writer()
        return writer.create_term_name(name=name)  # type: ignore[no-any-return]

    def update_term_name(self, *, name_id: str, updates: dict[str, Any]) -> None:
        from datacloud_knowledge.adapters import create_writer  # noqa: PLC0415

        writer = create_writer()
        writer.update_term_name(name_id=name_id, updates=updates)

    def delete_term_name(self, *, name_id: str) -> None:
        from datacloud_knowledge.adapters import create_writer  # noqa: PLC0415

        writer = create_writer()
        writer.delete_term_name(name_id=name_id)
