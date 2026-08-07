"""Term knowledge entity CRUD — TermKnowledge, TermLibrary, TermType, Domain."""

from __future__ import annotations

import logging
from typing import Any

from datacloud_platform.adapters.data_adapter._base import DataCloudDataBackendBase

logger = logging.getLogger(__name__)


class TermEntityMixin(DataCloudDataBackendBase):
    """Term knowledge entity CRUD — TermKnowledge, TermLibrary, TermType, Domain."""

    # ── TermKnowledge ───────────────────────────────────────────────────

    def list_term_knowledges(
        self, *, term_id: str | None = None, ext_system: str | None = None
    ) -> list[dict[str, Any]]:
        reader = self._get_knowledge_reader()
        try:
            return reader.list_term_knowledges(term_id=term_id, ext_system=ext_system)  # type: ignore[no-any-return]
        except Exception:
            logger.exception("list_term_knowledges failed")
            return []

    def get_term_knowledge(self, *, knowledge_id: str) -> dict[str, Any] | None:
        reader = self._get_knowledge_reader()
        try:
            return reader.get_term_knowledge(knowledge_id=knowledge_id)  # type: ignore[no-any-return]
        except Exception:
            logger.exception("get_term_knowledge failed knowledge_id=%s", knowledge_id)
            return None

    def create_term_knowledge(self, *, knowledge: dict[str, Any]) -> dict[str, Any]:
        from datacloud_knowledge.adapters import create_writer  # noqa: PLC0415

        with create_writer() as writer:
            return writer.create_term_knowledge(knowledge=knowledge)

    def update_term_knowledge(
        self, *, knowledge_id: str, updates: dict[str, Any]
    ) -> None:
        from datacloud_knowledge.adapters import create_writer  # noqa: PLC0415

        with create_writer() as writer:
            writer.update_term_knowledge(knowledge_id=knowledge_id, updates=updates)

    def delete_term_knowledge(self, *, knowledge_id: str) -> None:
        from datacloud_knowledge.adapters import create_writer  # noqa: PLC0415

        with create_writer() as writer:
            writer.delete_term_knowledge(knowledge_id=knowledge_id)

    # ── TermLibrary ─────────────────────────────────────────────────────

    def list_term_libraries(
        self,
        *,
        library_code: str | None = None,
        library_name: str | None = None,
    ) -> list[dict[str, Any]]:
        reader = self._get_knowledge_reader()
        try:
            return reader.list_term_libraries(  # type: ignore[no-any-return]
                library_code=library_code, library_name=library_name
            )
        except Exception:
            logger.exception("list_term_libraries failed")
            return []

    def get_term_library(self, *, library_id: str) -> dict[str, Any] | None:
        reader = self._get_knowledge_reader()
        try:
            return reader.get_term_library(library_id=library_id)  # type: ignore[no-any-return]
        except Exception:
            logger.exception("get_term_library failed library_id=%s", library_id)
            return None

    def create_term_library(self, *, library: dict[str, Any]) -> dict[str, Any]:
        from datacloud_knowledge.adapters import create_writer  # noqa: PLC0415

        with create_writer() as writer:
            return writer.create_term_library(library=library)

    def update_term_library(self, *, library_id: str, updates: dict[str, Any]) -> None:
        from datacloud_knowledge.adapters import create_writer  # noqa: PLC0415

        with create_writer() as writer:
            writer.update_term_library(library_id=library_id, updates=updates)

    def delete_term_library(self, *, library_id: str) -> None:
        from datacloud_knowledge.adapters import create_writer  # noqa: PLC0415

        with create_writer() as writer:
            writer.delete_term_library(library_id=library_id)

    # ── TermType ────────────────────────────────────────────────────────

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
        reader = self._get_knowledge_reader()
        try:
            return reader.list_term_types(  # type: ignore[no-any-return]
                library_id=library_id,
                domain_code=domain_code,
                type_category=type_category,
                keyword=keyword,
                page_index=page_index,
                page_size=page_size,
            )
        except Exception:
            logger.exception("list_term_types failed")
            return {"items": [], "total": 0}

    def get_term_type(
        self, *, library_id: str, type_code: str
    ) -> dict[str, Any] | None:
        reader = self._get_knowledge_reader()
        try:
            return reader.get_term_type(library_id=library_id, type_code=type_code)  # type: ignore[no-any-return]
        except Exception:
            logger.exception("get_term_type failed type_code=%s", type_code)
            return None

    def list_term_type_relations(
        self,
        *,
        library_id: str,
        type_code: str,
        direction: str = "both",
        relation_category: str | None = None,
        relation_code: str | None = None,
        keyword: str | None = None,
        page_index: int = 1,
        page_size: int = 20,
    ) -> dict[str, Any]:
        reader = self._get_knowledge_reader()
        try:
            return reader.list_term_type_relations(  # type: ignore[no-any-return]
                library_id=library_id,
                type_code=type_code,
                direction=direction,
                relation_category=relation_category,
                relation_code=relation_code,
                keyword=keyword,
                page_index=page_index,
                page_size=page_size,
            )
        except Exception:
            logger.exception("list_term_type_relations failed type_code=%s", type_code)
            return {"items": [], "total": 0}

    def create_term_type(
        self, *, library_id: str, term_type: dict[str, Any]
    ) -> dict[str, Any]:
        from datacloud_knowledge.adapters import create_writer  # noqa: PLC0415

        with create_writer() as writer:
            return writer.create_term_type(library_id=library_id, term_type=term_type)

    def update_term_type(
        self, *, library_id: str, type_code: str, updates: dict[str, Any]
    ) -> None:
        from datacloud_knowledge.adapters import create_writer  # noqa: PLC0415

        with create_writer() as writer:
            writer.update_term_type(
                library_id=library_id, type_code=type_code, updates=updates
            )

    def delete_term_type(self, *, library_id: str, type_code: str) -> None:
        from datacloud_knowledge.adapters import create_writer  # noqa: PLC0415

        with create_writer() as writer:
            writer.delete_term_type(library_id=library_id, type_code=type_code)

    # ── Domain ──────────────────────────────────────────────────────────

    def list_domains(
        self, *, library_id: str, parent_id: str | None = None
    ) -> list[dict[str, Any]]:
        reader = self._get_knowledge_reader()
        try:
            return reader.list_domains(library_id=library_id, parent_id=parent_id)  # type: ignore[no-any-return]
        except Exception:
            logger.exception("list_domains failed")
            return []

    def get_domain(self, *, library_id: str, domain_code: str) -> dict[str, Any] | None:
        reader = self._get_knowledge_reader()
        try:
            return reader.get_domain(library_id=library_id, domain_code=domain_code)  # type: ignore[no-any-return]
        except Exception:
            logger.exception("get_domain failed domain_code=%s", domain_code)
            return None

    def create_domain(self, *, domain: dict[str, Any]) -> dict[str, Any]:
        from datacloud_knowledge.adapters import create_writer  # noqa: PLC0415

        with create_writer() as writer:
            return writer.create_domain(domain=domain)

    def update_domain(
        self, *, library_id: str, domain_code: str, updates: dict[str, Any]
    ) -> None:
        from datacloud_knowledge.adapters import create_writer  # noqa: PLC0415

        with create_writer() as writer:
            writer.update_domain(
                library_id=library_id, domain_code=domain_code, updates=updates
            )

    def delete_domain(self, *, library_id: str, domain_code: str) -> None:
        from datacloud_knowledge.adapters import create_writer  # noqa: PLC0415

        with create_writer() as writer:
            writer.delete_domain(library_id=library_id, domain_code=domain_code)

    def list_domain_term_types(self, *, domain_id: str) -> list[dict[str, Any]]:
        reader = self._get_knowledge_reader()
        try:
            return reader.list_domain_term_types(domain_id=domain_id)  # type: ignore[no-any-return]
        except Exception:
            logger.exception("list_domain_term_types failed domain_id=%s", domain_id)
            return []
