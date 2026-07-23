"""OntologyDocFragment DB adapter — SQLAlchemy ORM model + raw DB operations.

Table: ontology_doc_fragment
Responsibilities: batch insert, list by instance_ids, bulk status update by ids.
Term-name enrichment and ext_attrs extraction are handled at the Mixin layer.
"""

from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    SmallInteger,
    String,
    Text,
    update,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Session

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════════════
# ORM model
# ═══════════════════════════════════════════════════════════════════════════════


class _FragmentBase(DeclarativeBase):
    pass


class OntologyDocFragmentRow(_FragmentBase):
    __tablename__ = "ontology_doc_fragment"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    instance_id = Column(String(128), nullable=False)
    instance_name = Column(String(512), nullable=False)
    object_code = Column(String(128), nullable=True)
    content = Column(Text, nullable=False)
    status = Column(SmallInteger, nullable=False, default=0)
    origin_instance_id = Column(String(128), nullable=True)
    origin_file = Column(JSONB, nullable=False, default=dict)
    created_time = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    created_by = Column(String(64), nullable=False)
    updated_time = Column(DateTime(timezone=True), nullable=True)
    updated_by = Column(String(64), nullable=True)


# ═══════════════════════════════════════════════════════════════════════════════
# Engine singleton (reuses datacloud_knowledge connection config)
# ═══════════════════════════════════════════════════════════════════════════════

_engine_cache: dict[str, Any] = {}
_engine_lock = threading.Lock()


def _get_fragment_engine(schema: str | None = None) -> Any:
    """Return a cached SQLAlchemy Engine, creating the fragment table on first access."""
    from datacloud_knowledge.adapters.opengauss._db.connection import (  # noqa: PLC0415
        _get_engine,
    )
    from datacloud_knowledge.adapters.opengauss._db.url import (  # noqa: PLC0415
        resolve_knowledge_schema,
    )

    key = schema or "__default__"
    with _engine_lock:
        if key not in _engine_cache:
            resolved = resolve_knowledge_schema(schema)
            engine = _get_engine(resolved)
            _FragmentBase.metadata.create_all(engine, checkfirst=True)
            _engine_cache[key] = engine
        return _engine_cache[key]


# ═══════════════════════════════════════════════════════════════════════════════
# Adapter
# ═══════════════════════════════════════════════════════════════════════════════


class OntologyDocFragmentAdapter:
    """DB operations for ontology_doc_fragment table."""

    def __init__(self, schema: str | None = None) -> None:
        self._schema = schema

    def _engine(self) -> Any:
        return _get_fragment_engine(self._schema)

    def batch_create(self, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Batch insert fragment records, return full row dicts in insertion order.

        Args:
            records: Each dict must have: instance_id, instance_name, content,
                     origin_instance_id (optional), origin_file (dict), created_by.
                     status defaults to 0 (未融合).

        Returns:
            List of inserted row dicts (all columns) in the same order as records.
        """
        if not records:
            return []

        engine = self._engine()
        rows_out: list[dict[str, Any]] = []
        with Session(engine) as session:
            now = datetime.now(timezone.utc)
            for rec in records:
                row = OntologyDocFragmentRow(
                    instance_id=rec["instance_id"],
                    instance_name=rec["instance_name"],
                    object_code=rec.get("object_code") or "",
                    content=rec["content"],
                    status=rec.get("status", 0),
                    origin_instance_id=rec.get("origin_instance_id"),
                    origin_file=rec.get("origin_file") or {},
                    created_time=now,
                    created_by=rec["created_by"],
                )
                session.add(row)
                session.flush()  # populate row.id before commit
                rows_out.append(_row_to_dict(row))
            session.commit()

        logger.info(
            "OntologyDocFragmentAdapter.batch_create: inserted %d rows", len(rows_out)
        )
        return rows_out

    def list_by_instance_ids(
        self,
        instance_ids: list[str],
        *,
        page_index: int = 1,
        page_size: int = 20,
        status: int | None = None,
    ) -> dict[str, Any]:
        """Query fragments by instance_id list, paginated.

        Args:
            instance_ids: List of instance_id values to filter by.
            page_index: 1-based page number.
            page_size: Page size (max records per page).
            status: Optional status filter — 0=未融合, 1=已融合. None means no filter.

        Returns:
            {"total": int, "data": [row_dict, ...]}
        """
        if not instance_ids:
            return {"total": 0, "data": []}

        engine = self._engine()
        with Session(engine) as session:
            query = session.query(OntologyDocFragmentRow).filter(
                OntologyDocFragmentRow.instance_id.in_(instance_ids)
            )
            if status is not None:
                query = query.filter(OntologyDocFragmentRow.status == status)
            total: int = query.count()
            offset = (page_index - 1) * page_size
            rows = (
                query.order_by(OntologyDocFragmentRow.id)
                .offset(offset)
                .limit(page_size)
                .all()
            )

        return {"total": total, "data": [_row_to_dict(r) for r in rows]}

    def list_for_build(
        self,
        *,
        instance_ids: list[str],
        page_index: int = 1,
        page_size: int = 20,
        status: int = 0,
    ) -> dict[str, Any]:
        """Query fragments for object instance build tasks.

        Empty instance_ids means all unbuilt fragments under the requested status.
        """
        engine = self._engine()
        with Session(engine) as session:
            query = session.query(OntologyDocFragmentRow).filter(
                OntologyDocFragmentRow.status == status
            )
            if instance_ids:
                query = query.filter(
                    OntologyDocFragmentRow.instance_id.in_(instance_ids)
                )
            total: int = query.count()
            offset = (page_index - 1) * page_size
            rows = (
                query.order_by(OntologyDocFragmentRow.id)
                .offset(offset)
                .limit(page_size)
                .all()
            )

        return {"total": total, "data": [_row_to_dict(row) for row in rows]}

    def update_status_by_ids(
        self,
        ids: list[int],
        *,
        status: int,
        updated_by: str,
    ) -> int:
        """Bulk update status for a list of primary-key ids.

        Args:
            ids: List of primary-key id values.
            status: New status value (0=未融合, 1=已融合).
            updated_by: Operator identifier.

        Returns:
            Number of rows updated.
        """
        if not ids:
            return 0

        engine = self._engine()
        now = datetime.now(timezone.utc)
        with Session(engine) as session:
            result = session.execute(
                update(OntologyDocFragmentRow)
                .where(OntologyDocFragmentRow.id.in_(ids))
                .values(status=status, updated_time=now, updated_by=updated_by)
            )
            session.commit()
            updated: int = result.rowcount  # type: ignore[attr-defined]

        logger.info(
            "OntologyDocFragmentAdapter.update_status_by_ids: updated %d rows to status=%d",
            updated,
            status,
        )
        return updated


# ═══════════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════════


def _row_to_dict(row: OntologyDocFragmentRow) -> dict[str, Any]:
    """Convert ORM row to serialisable dict."""
    origin_file = row.origin_file
    if isinstance(origin_file, str):
        try:
            origin_file = json.loads(origin_file)
        except (json.JSONDecodeError, TypeError):
            origin_file = {}

    return {
        "id": row.id,
        "instance_id": row.instance_id,
        "instance_name": row.instance_name,
        "object_code": row.object_code or "",
        "content": row.content,
        "status": row.status,
        "origin_instance_id": row.origin_instance_id,
        "origin_file": origin_file or {},
        "created_time": row.created_time.isoformat() if row.created_time else None,
        "created_by": row.created_by,
        "updated_time": row.updated_time.isoformat() if row.updated_time else None,
        "updated_by": row.updated_by,
    }
