"""_KnowledgeWriter — TermKnowledge write-side Mixin."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import delete, update

from datacloud_knowledge.adapters.opengauss._db.models import TermKnowledge
from datacloud_knowledge.adapters.opengauss._writers._base import _WriterBase

logger = logging.getLogger(__name__)

_CAMEL_TO_SNAKE_KNOWLEDGE: dict[str, str] = {
    "knowledgeId": "knowledge_id",
    "termId": "term_id",
    "descSummary": "desc_summary",
    "desc": "desc",
    "extSystem": "ext_system",
    "extKbId": "ext_kb_id",
    "extDocId": "ext_doc_id",
    "sortOrder": "sort_order",
    "createdTime": "created_time",
    "updatedTime": "updated_time",
}


class _KnowledgeWriter(_WriterBase):
    """Mixin providing TermKnowledge CRUD write operations."""

    def create_term_knowledge(self, *, knowledge: dict[str, Any]) -> dict[str, Any]:
        """Create a term knowledge record from dict.

        Args:
            knowledge: Dict with keys like termId/term_id, descSummary/desc_summary,
                       desc, extSystem/ext_system, extKbId/ext_kb_id,
                       extDocId/ext_doc_id, sortOrder/sort_order.
                       Supports both camelCase and snake_case.

        Returns:
            Dict with all fields of the created record.
        """
        knowledge_id = self._new_id()
        now = self._now()

        record = TermKnowledge(
            knowledge_id=knowledge_id,
            term_id=knowledge.get("termId", knowledge.get("term_id", "")),
            desc_summary=knowledge.get("descSummary", knowledge.get("desc_summary")),
            desc=knowledge.get("desc", knowledge.get("desc")),
            ext_system=knowledge.get("extSystem", knowledge.get("ext_system")),
            ext_kb_id=knowledge.get("extKbId", knowledge.get("ext_kb_id")),
            ext_doc_id=knowledge.get("extDocId", knowledge.get("ext_doc_id")),
            sort_order=knowledge.get("sortOrder", knowledge.get("sort_order", 0)),
            created_time=now,
            updated_time=now,
        )
        self.session.add(record)
        self.session.flush()

        logger.info(
            "create_term_knowledge: knowledge_id=%s term_id=%s",
            record.knowledge_id,
            record.term_id,
        )
        return {
            "knowledge_id": record.knowledge_id,
            "term_id": record.term_id,
            "desc_summary": record.desc_summary,
            "desc": record.desc,
            "ext_system": record.ext_system,
            "ext_kb_id": record.ext_kb_id,
            "ext_doc_id": record.ext_doc_id,
            "sort_order": record.sort_order,
            "created_time": record.created_time,
            "updated_time": record.updated_time,
        }

    def update_term_knowledge(self, *, knowledge_id: str, updates: dict[str, Any]) -> None:
        """Update a term knowledge record.

        Only non-None fields are updated. CamelCase keys are mapped to snake_case.

        Args:
            knowledge_id: The knowledge ID to update.
            updates: Dict of field updates (supports camelCase and snake_case keys).
        """
        mapped: dict[str, Any] = {}
        for key, value in updates.items():
            if key in _CAMEL_TO_SNAKE_KNOWLEDGE:
                mapped[_CAMEL_TO_SNAKE_KNOWLEDGE[key]] = value
            else:
                mapped[key] = value

        # Only update non-None fields (excluding knowledge_id which is PK)
        values = {k: v for k, v in mapped.items() if v is not None and k != "knowledge_id"}
        if not values:
            return

        values["updated_time"] = self._now()

        self.session.execute(
            update(TermKnowledge).where(TermKnowledge.knowledge_id == knowledge_id).values(**values)
        )
        logger.info(
            "update_term_knowledge: knowledge_id=%s fields=%s",
            knowledge_id,
            list(values.keys()),
        )

    def delete_term_knowledge(self, *, knowledge_id: str) -> None:
        """Delete a term knowledge record.

        Args:
            knowledge_id: The knowledge ID to delete.
        """
        self.session.execute(
            delete(TermKnowledge).where(TermKnowledge.knowledge_id == knowledge_id)
        )
        logger.info("delete_term_knowledge: knowledge_id=%s", knowledge_id)
