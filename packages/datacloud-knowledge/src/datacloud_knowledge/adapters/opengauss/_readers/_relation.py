"""_RelationReader — Mixin providing TermRelation read operations for the OpenGauss adapter."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select

from datacloud_knowledge.adapters.opengauss._db.models import TermRelation
from datacloud_knowledge.adapters.opengauss._readers._base import _ReaderBase

logger = logging.getLogger(__name__)


class _RelationReader(_ReaderBase):
    """Mixin that reads ``term_relation`` table rows via the shared reader base.

    Usage::

        reader = _RelationReader()
        rels = reader.list_term_relations(source_term_id="term_001")
        rel = reader.get_term_relation(relation_id="rel_001")
    """

    def list_term_relations(
        self,
        *,
        source_term_id: str | None = None,
        target_term_id: str | None = None,
        relation_category: str | None = None,
    ) -> list[dict[str, Any]]:
        """List term relations, optionally filtered.

        Args:
            source_term_id: Filter by source term ID.
            target_term_id: Filter by target term ID.
            relation_category: Filter by relation category
                (ONTOLOGY, BUSINESS, etc.).

        Returns:
            List of dicts with keys: relation_id, source_term_id,
            target_term_id, relation_name, relation_category, cardinality,
            action_term_id, created_time, updated_time.
        """
        try:
            with self._get_session() as session:
                stmt = select(
                    TermRelation.relation_id,
                    TermRelation.source_term_id,
                    TermRelation.target_term_id,
                    TermRelation.relation_name,
                    TermRelation.relation_category,
                    TermRelation.cardinality,
                    TermRelation.action_term_id,
                    TermRelation.created_time,
                    TermRelation.updated_time,
                )
                if source_term_id is not None:
                    stmt = stmt.where(TermRelation.source_term_id == source_term_id)
                if target_term_id is not None:
                    stmt = stmt.where(TermRelation.target_term_id == target_term_id)
                if relation_category is not None:
                    stmt = stmt.where(TermRelation.relation_category == relation_category)
                stmt = stmt.order_by(TermRelation.relation_name)

                rows = session.execute(stmt).all()
        except Exception:
            logger.exception(
                "list_term_relations failed: source=%s target=%s category=%s",
                source_term_id,
                target_term_id,
                relation_category,
            )
            raise

        return [
            {
                "relation_id": str(row[0]),
                "source_term_id": str(row[1]),
                "target_term_id": str(row[2]),
                "relation_name": str(row[3]),
                "relation_category": str(row[4]),
                "cardinality": str(row[5]) if row[5] is not None else None,
                "action_term_id": str(row[6]) if row[6] is not None else None,
                "created_time": row[7],
                "updated_time": row[8],
            }
            for row in rows
        ]

    def get_term_relation(self, *, relation_id: str) -> dict[str, Any] | None:
        """Get a single term relation by its ID.

        Args:
            relation_id: The relation's primary key.

        Returns:
            Dict with keys: relation_id, source_term_id, target_term_id,
            relation_name, relation_category, cardinality, action_term_id,
            created_time, updated_time — or ``None`` if not found.
        """
        try:
            with self._get_session() as session:
                row = session.execute(
                    select(
                        TermRelation.relation_id,
                        TermRelation.source_term_id,
                        TermRelation.target_term_id,
                        TermRelation.relation_name,
                        TermRelation.relation_category,
                        TermRelation.cardinality,
                        TermRelation.action_term_id,
                        TermRelation.created_time,
                        TermRelation.updated_time,
                    ).where(TermRelation.relation_id == relation_id)
                ).first()
        except Exception:
            logger.exception("get_term_relation failed: relation_id=%s", relation_id)
            raise

        if row is None:
            return None

        return {
            "relation_id": str(row[0]),
            "source_term_id": str(row[1]),
            "target_term_id": str(row[2]),
            "relation_name": str(row[3]),
            "relation_category": str(row[4]),
            "cardinality": str(row[5]) if row[5] is not None else None,
            "action_term_id": str(row[6]) if row[6] is not None else None,
            "created_time": row[7],
            "updated_time": row[8],
        }
