"""_KnowledgeReader — TermKnowledge read-side Mixin."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select

from datacloud_knowledge.adapters.opengauss._db.models import TermKnowledge
from datacloud_knowledge.adapters.opengauss._readers._base import _ReaderBase

logger = logging.getLogger(__name__)


class _KnowledgeReader(_ReaderBase):
    """Mixin providing TermKnowledge CRUD read operations."""

    def list_term_knowledges(
        self,
        *,
        term_id: str | None = None,
        ext_system: str | None = None,
    ) -> list[dict[str, Any]]:
        """List term knowledge records with optional filters.

        Args:
            term_id: Optional filter by term_id (exact match).
            ext_system: Optional filter by ext_system (exact match).

        Returns:
            List of dicts with keys: knowledge_id, term_id, desc_summary, desc,
            ext_system, ext_kb_id, ext_doc_id, sort_order, created_time, updated_time.
        """
        try:
            with self._get_session() as session:
                stmt = select(
                    TermKnowledge.knowledge_id,
                    TermKnowledge.term_id,
                    TermKnowledge.desc_summary,
                    TermKnowledge.desc,
                    TermKnowledge.ext_system,
                    TermKnowledge.ext_kb_id,
                    TermKnowledge.ext_doc_id,
                    TermKnowledge.sort_order,
                    TermKnowledge.created_time,
                    TermKnowledge.updated_time,
                )
                if term_id is not None:
                    stmt = stmt.where(TermKnowledge.term_id == term_id)
                if ext_system is not None:
                    stmt = stmt.where(TermKnowledge.ext_system == ext_system)

                rows = session.execute(stmt).all()
        except Exception:
            logger.exception(
                "list_term_knowledges failed: term_id=%s, ext_system=%s",
                term_id,
                ext_system,
            )
            raise

        return [
            {
                "knowledge_id": str(row.knowledge_id),
                "term_id": str(row.term_id),
                "desc_summary": row.desc_summary,
                "desc": row.desc,
                "ext_system": row.ext_system,
                "ext_kb_id": row.ext_kb_id,
                "ext_doc_id": row.ext_doc_id,
                "sort_order": row.sort_order,
                "created_time": row.created_time,
                "updated_time": row.updated_time,
            }
            for row in rows
        ]

    def get_term_knowledge(self, *, knowledge_id: str) -> dict[str, Any] | None:
        """Get a single term knowledge record by knowledge_id.

        Args:
            knowledge_id: The knowledge ID to look up.

        Returns:
            Dict with keys: knowledge_id, term_id, desc_summary, desc,
            ext_system, ext_kb_id, ext_doc_id, sort_order, created_time, updated_time.
            Returns None if not found.
        """
        try:
            with self._get_session() as session:
                row = session.execute(
                    select(
                        TermKnowledge.knowledge_id,
                        TermKnowledge.term_id,
                        TermKnowledge.desc_summary,
                        TermKnowledge.desc,
                        TermKnowledge.ext_system,
                        TermKnowledge.ext_kb_id,
                        TermKnowledge.ext_doc_id,
                        TermKnowledge.sort_order,
                        TermKnowledge.created_time,
                        TermKnowledge.updated_time,
                    ).where(TermKnowledge.knowledge_id == knowledge_id)
                ).one_or_none()
        except Exception:
            logger.exception("get_term_knowledge failed: knowledge_id=%s", knowledge_id)
            raise

        if row is None:
            return None

        return {
            "knowledge_id": str(row.knowledge_id),
            "term_id": str(row.term_id),
            "desc_summary": row.desc_summary,
            "desc": row.desc,
            "ext_system": row.ext_system,
            "ext_kb_id": row.ext_kb_id,
            "ext_doc_id": row.ext_doc_id,
            "sort_order": row.sort_order,
            "created_time": row.created_time,
            "updated_time": row.updated_time,
        }
