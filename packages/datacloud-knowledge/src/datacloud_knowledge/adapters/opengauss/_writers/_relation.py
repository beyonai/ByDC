"""_RelationWriter — Mixin providing TermRelation write operations for the OpenGauss adapter."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import delete, update

from datacloud_knowledge.adapters.opengauss._db.models import TermRelation
from datacloud_knowledge.adapters.opengauss._writers._base import _pick_key, _WriterBase

logger = logging.getLogger(__name__)


class _RelationWriter(_WriterBase):
    """Mixin that writes ``term_relation`` table rows via the shared writer base.

    Usage::

        with _RelationWriter(session=my_session) as writer:
            writer.create_term_relation(relation={
                "sourceTermId": "...", "targetTermId": "...",
                "relationName": "HAS_FIELD", ...
            })
            writer.update_term_relation(relation_id="rel_001", updates={...})
            writer.delete_term_relation(relation_id="rel_001")
    """

    def create_term_relation(self, *, relation: dict[str, Any]) -> dict[str, Any]:
        """Insert a new term relation.

        Generates ``relation_id`` via ``self._new_id()``,
        sets ``created_time``/``updated_time`` via ``self._now()``.

        Args:
            relation: Dict — supports both camelCase and snake_case keys:
                - sourceTermId / source_term_id (required)
                - targetTermId / target_term_id (required)
                - relationName / relation_name
                - relationCategory / relation_category
                - cardinality
                - actionTermId / action_term_id

        Returns:
            Echo dict with all relation fields.
        """
        source_term_id = _pick_key(relation, "sourceTermId", "source_term_id")
        target_term_id = _pick_key(relation, "targetTermId", "target_term_id")
        relation_name = _pick_key(relation, "relationName", "relation_name")
        relation_category = _pick_key(relation, "relationCategory", "relation_category")
        cardinality = _pick_key(relation, "cardinality")
        action_term_id = _pick_key(relation, "actionTermId", "action_term_id")
        ext_attrs = _pick_key(relation, "extAttrs", "ext_attrs") or {}
        if not isinstance(ext_attrs, dict):
            raise TypeError("relation ext_attrs must be an object")

        if not source_term_id:
            raise ValueError("relation dict must contain 'sourceTermId' or 'source_term_id'")
        if not target_term_id:
            raise ValueError("relation dict must contain 'targetTermId' or 'target_term_id'")

        relation_id = self._new_id()
        now = self._now()

        row = TermRelation(
            relation_id=relation_id,
            source_term_id=str(source_term_id),
            target_term_id=str(target_term_id),
            relation_name=str(relation_name) if relation_name is not None else "",
            relation_category=(str(relation_category) if relation_category is not None else ""),
            cardinality=str(cardinality) if cardinality is not None else None,
            action_term_id=str(action_term_id) if action_term_id is not None else None,
            ext_attrs=dict(ext_attrs),
            created_time=now,
            updated_time=now,
        )
        self.session.add(row)
        self.session.flush()

        logger.info(
            "create_term_relation: relation_id=%s %s -> %s (%s)",
            relation_id,
            source_term_id,
            target_term_id,
            relation_name,
        )

        return {
            "relation_id": row.relation_id,
            "source_term_id": row.source_term_id,
            "target_term_id": row.target_term_id,
            "relation_name": row.relation_name,
            "relation_category": row.relation_category,
            "cardinality": row.cardinality,
            "action_term_id": row.action_term_id,
            "ext_attrs": row.ext_attrs,
            "created_time": row.created_time,
            "updated_time": row.updated_time,
        }

    def update_term_relation(self, *, relation_id: str, updates: dict[str, Any]) -> None:
        """Update a term relation by its ID.

        Only non-None fields in ``updates`` are applied.

        Args:
            relation_id: The relation to update.
            updates: Dict — supports camelCase keys (sourceTermId,
                targetTermId, relationName, relationCategory, cardinality,
                actionTermId) or snake_case equivalents.
                Only non-None values are updated.
        """
        values: dict[str, Any] = {}
        for src_key, col_attr in (
            ("sourceTermId", "source_term_id"),
            ("source_term_id", "source_term_id"),
            ("targetTermId", "target_term_id"),
            ("target_term_id", "target_term_id"),
            ("relationName", "relation_name"),
            ("relation_name", "relation_name"),
            ("relationCategory", "relation_category"),
            ("relation_category", "relation_category"),
            ("cardinality", "cardinality"),
            ("actionTermId", "action_term_id"),
            ("action_term_id", "action_term_id"),
            ("extAttrs", "ext_attrs"),
            ("ext_attrs", "ext_attrs"),
        ):
            val = updates.get(src_key)
            if val is not None:
                values[col_attr] = val

        if not values:
            return

        values["updated_time"] = self._now()

        stmt = update(TermRelation).where(TermRelation.relation_id == relation_id).values(**values)
        result = self.session.execute(stmt)
        rowcount: int = result.rowcount  # type: ignore[attr-defined]

        if rowcount == 0:
            logger.warning("update_term_relation: relation_id=%s not found", relation_id)
        else:
            logger.info(
                "update_term_relation: relation_id=%s updated=%d fields=%s",
                relation_id,
                rowcount,
                list(values.keys()),
            )

    def delete_term_relation(self, *, relation_id: str) -> None:
        """Delete a term relation by its ID.

        Args:
            relation_id: The relation to delete.
        """
        stmt = delete(TermRelation).where(TermRelation.relation_id == relation_id)
        result = self.session.execute(stmt)
        rowcount: int = result.rowcount  # type: ignore[attr-defined]

        if rowcount == 0:
            logger.warning("delete_term_relation: relation_id=%s not found", relation_id)
        else:
            logger.info(
                "delete_term_relation: relation_id=%s deleted=%d",
                relation_id,
                rowcount,
            )
