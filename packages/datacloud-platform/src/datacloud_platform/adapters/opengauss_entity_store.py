"""OpenGauss / PostgreSQL EntityStore — ORM-backed, table-driven, multi-process safe.

SQLAlchemy declarative models for 7 entity tables, version-tracked cache
invalidation via BIGSERIAL columns, and a :class:`_ScopedEntityStore` proxy
for per-base namespace isolation.

Engine lifecycle: module-level singleton (cached per schema).  Tables are
created idempotently on first access via ``checkfirst=True``.
"""

from __future__ import annotations

import json
import logging
import threading
from typing import Any

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    Engine,
    String,
    Text,
    insert,
    update,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.sql import func

from datacloud_platform.adapters.json_entity_store import _ScopedEntityStore
from datacloud_platform.constants import DEFAULT_SYSTEM_CODE

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════════════
# ORM models
# ═══════════════════════════════════════════════════════════════════════════════


class _Base(DeclarativeBase):
    pass


class _BaseRow(_Base):
    __tablename__ = "ontology_bases"
    base_id = Column(String(64), primary_key=True)
    display_name = Column(String(255))
    source_type = Column(String(64))
    source_url = Column(Text)
    data = Column(JSONB, nullable=False)
    version = Column(BigInteger, nullable=False, server_default="1")
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class _ObjectRow(_Base):
    __tablename__ = "ontology_objects"
    base_id = Column(String(64), primary_key=True)
    object_code = Column(String(256), primary_key=True)
    object_name = Column(String(512))
    data = Column(JSONB, nullable=False)
    version = Column(BigInteger, nullable=False, server_default="1")
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class _ViewRow(_Base):
    __tablename__ = "ontology_views"
    base_id = Column(String(64), primary_key=True)
    view_code = Column(String(256), primary_key=True)
    view_name = Column(String(512))
    data = Column(JSONB, nullable=False)
    version = Column(BigInteger, nullable=False, server_default="1")
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class _RelationRow(_Base):
    __tablename__ = "ontology_relations"
    base_id = Column(String(64), primary_key=True)
    relation_code = Column(String(256), primary_key=True)
    relation_name = Column(String(512))
    data = Column(JSONB, nullable=False)
    version = Column(BigInteger, nullable=False, server_default="1")
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class _ActionRow(_Base):
    __tablename__ = "ontology_actions"
    base_id = Column(String(64), primary_key=True)
    action_code = Column(String(256), primary_key=True)
    action_name = Column(String(512))
    data = Column(JSONB, nullable=False)
    version = Column(BigInteger, nullable=False, server_default="1")
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class _DatasourceRow(_Base):
    __tablename__ = "ontology_datasources"
    base_id = Column(String(64), primary_key=True)
    db_id = Column(String(256), primary_key=True)
    db_name = Column(String(512))
    data = Column(JSONB, nullable=False)
    version = Column(BigInteger, nullable=False, server_default="1")
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class _SceneRow(_Base):
    __tablename__ = "ontology_scenes"
    base_id = Column(String(64), primary_key=True)
    scene_id = Column(String(64), primary_key=True)
    scene_name = Column(String(255))
    data = Column(JSONB, nullable=False)
    version = Column(BigInteger, nullable=False, server_default="1")
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Engine singleton
# ═══════════════════════════════════════════════════════════════════════════════

_engine_cache: dict[str, Engine] = {}
_engine_lock = threading.Lock()


def _get_or_create_engine(schema: str | None = None) -> Engine:
    """Return a cached SQLAlchemy Engine, creating tables on first access.

    Schema is resolved once at creation time and never refreshed.
    """
    from datacloud_knowledge.adapters.opengauss._db.connection import _get_engine
    from datacloud_knowledge.adapters.opengauss._db.url import resolve_knowledge_schema

    key = schema or "__default__"
    with _engine_lock:
        if key not in _engine_cache:
            resolved = resolve_knowledge_schema(schema)
            engine: Engine = _get_engine(resolved)
            _Base.metadata.create_all(engine, checkfirst=True)
            _engine_cache[key] = engine
        return _engine_cache[key]


# ═══════════════════════════════════════════════════════════════════════════════
# Column name helpers
# ═══════════════════════════════════════════════════════════════════════════════

_CODE_COLUMNS: dict[str, str] = {
    "bases": "base_id",
    "scenes": "scene_id",
    "objects": "object_code",
    "views": "view_code",
    "relations": "relation_code",
    "actions": "action_code",
    "datasources": "db_id",
}

_NAME_COLUMNS: dict[str, str] = {
    "bases": "display_name",
    "scenes": "scene_name",
    "objects": "object_name",
    "views": "view_name",
    "relations": "relation_name",
    "actions": "action_name",
    "datasources": "db_name",
}

_ENTITY_TABLES: dict[str, type[_Base]] = {
    "bases": _BaseRow,
    "scenes": _SceneRow,
    "objects": _ObjectRow,
    "views": _ViewRow,
    "relations": _RelationRow,
    "actions": _ActionRow,
    "datasources": _DatasourceRow,
}


# ═══════════════════════════════════════════════════════════════════════════════
# OpenGaussEntityStore
# ═══════════════════════════════════════════════════════════════════════════════


class OpenGaussEntityStore:
    """EntityStore backed by PostgreSQL / OpenGauss.

    Seven tables under one schema.  ``base_id`` provides per-base namespace
    isolation.  :meth:`sub_store` returns a lightweight ``_ScopedEntityStore``
    proxy sharing the same connection pool.
    """

    _DEFAULT_BASE_ID = DEFAULT_SYSTEM_CODE

    def __init__(
        self,
        default_base_id: str = "",
        *,
        schema: str | None = None,
    ) -> None:
        self._default_base_id = default_base_id or self._DEFAULT_BASE_ID
        self._engine = _get_or_create_engine(schema)

    # ── EntityStore Protocol ────────────────────────────────────────────

    def sub_store(self, namespace: str) -> _ScopedEntityStore:
        return _ScopedEntityStore(self, default_base_id=namespace)

    def save(
        self,
        entity_type: str,
        code: str,
        data: dict[str, Any],
        *,
        base_id: str = "",
    ) -> None:
        """UPSERT — UPDATE then INSERT if no row matched (openGauss PG 9.2 compatible)."""
        bid = base_id or self._default_base_id
        model = _ENTITY_TABLES[entity_type]
        code_col = _CODE_COLUMNS[entity_type]
        name_col = _NAME_COLUMNS[entity_type]
        name = self._extract_name(entity_type, data)

        from sqlalchemy.orm import Session

        with Session(self._engine) as session:
            result = session.execute(
                update(model)
                .where(
                    getattr(model, "base_id") == bid,
                    getattr(model, code_col) == code,
                )
                .values(
                    **{name_col: name, "data": data},
                    version=model.version + 1,  # type: ignore[attr-defined]
                    updated_at=func.now(),
                )
            )
            if result.rowcount == 0:  # type: ignore[attr-defined]
                stmt = insert(model).values(
                    base_id=bid,
                    **{code_col: code, name_col: name, "data": data},
                )
                session.execute(stmt)
            session.commit()

    def get(
        self,
        entity_type: str,
        code: str,
        *,
        base_id: str = "",
    ) -> dict[str, Any] | None:
        bid = base_id or self._default_base_id
        model = _ENTITY_TABLES[entity_type]
        code_col = _CODE_COLUMNS[entity_type]

        from sqlalchemy.orm import Session

        with Session(self._engine) as session:
            row = session.get(model, {code_col: code, "base_id": bid})
            return dict(row.data) if row else None  # type: ignore[attr-defined]

    def list_all(
        self,
        entity_type: str,
        *,
        base_id: str = "",
    ) -> list[dict[str, Any]]:
        """Return all entity data dicts for *entity_type* under *base_id* in one query."""
        bid = base_id or self._default_base_id
        model = _ENTITY_TABLES[entity_type]
        from sqlalchemy.orm import Session

        with Session(self._engine) as session:
            rows = session.query(model.data).filter(model.base_id == bid).all()  # type: ignore[attr-defined]
            return [dict(r[0]) for r in rows if r[0] is not None]

    def search(
        self,
        entity_type: str,
        *,
        base_id: str = "",
        keyword: str | None = None,
        codes: list[str] | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        """Paginated search with keyword and code-set filtering.

        Uses a single SQL query with ``COUNT(*) OVER()`` for total count
        alongside the data, avoiding a second round-trip.
        """
        bid = base_id or self._default_base_id
        model = _ENTITY_TABLES[entity_type]
        code_col_name = _CODE_COLUMNS[entity_type]
        name_col_name = _NAME_COLUMNS[entity_type]

        if codes is not None and len(codes) == 0:
            return [], 0

        from sqlalchemy import select
        from sqlalchemy.orm import Session

        with Session(self._engine) as session:
            total_col = func.count().over().label("total")
            stmt = select(model.data, total_col).where(
                getattr(model, "base_id") == bid,
            )

            if codes is not None:
                stmt = stmt.where(getattr(model, code_col_name).in_(codes))

            if keyword:
                stmt = stmt.where(getattr(model, name_col_name).ilike(f"%{keyword}%"))

            code_attr = getattr(model, code_col_name)
            stmt = stmt.order_by(code_attr)
            stmt = stmt.limit(page_size).offset((page - 1) * page_size)

            rows = session.execute(stmt).all()
            total: int = rows[0][1] if rows else 0
            items: list[dict[str, Any]] = [dict(r[0]) for r in rows if r[0] is not None]
            return items, total

    def delete(
        self,
        entity_type: str,
        code: str,
        *,
        base_id: str = "",
    ) -> None:
        bid = base_id or self._default_base_id
        model = _ENTITY_TABLES[entity_type]
        code_col = _CODE_COLUMNS[entity_type]

        from sqlalchemy.orm import Session

        with Session(self._engine) as session:
            row = session.get(model, {code_col: code, "base_id": bid})
            if row:
                session.delete(row)
                session.commit()

    def load_index(
        self,
        entity_type: str,
        *,
        base_id: str = "",
    ) -> dict[str, dict[str, Any]]:
        """Return backend-independent index: ``{code: {code, name}}``."""
        bid = base_id or self._default_base_id
        model = _ENTITY_TABLES[entity_type]
        code_col = _CODE_COLUMNS[entity_type]
        name_col = _NAME_COLUMNS[entity_type]

        from sqlalchemy import select
        from sqlalchemy.orm import Session

        with Session(self._engine) as session:
            stmt = select(model).where(model.base_id == bid)  # type: ignore[attr-defined]
            rows = session.execute(stmt).scalars().all()
        return {
            getattr(r, code_col): {
                "code": getattr(r, code_col),
                "name": getattr(r, name_col) or getattr(r, code_col),
            }
            for r in rows
        }

    def save_index(
        self,
        entity_type: str,
        entries: dict[str, dict[str, Any]],
        *,
        base_id: str = "",
    ) -> None:
        """Bump version via sentinel write to ``ontology_bases``.

        The index is derived from table data; this method only bumps the
        version counter so that ``storage_version()`` returns a new value.
        """
        bid = base_id or self._default_base_id
        from sqlalchemy.orm import Session

        with Session(self._engine) as session:
            base_row = session.get(_BaseRow, {"base_id": bid})
            if base_row:
                base_row.version = _BaseRow.version + 1  # type: ignore[assignment]
                base_row.updated_at = func.now()  # type: ignore[assignment]
            else:
                session.execute(insert(_BaseRow).values(base_id=bid, data={}))
            session.commit()

    def storage_version(
        self,
        entity_type: str,
        *,
        base_id: str = "",
    ) -> str:
        """Return ``MAX(version)`` — BIGSERIAL guarantees strict monotonicity."""
        bid = base_id or self._default_base_id
        model = _ENTITY_TABLES[entity_type]

        from sqlalchemy import select
        from sqlalchemy.orm import Session

        with Session(self._engine) as session:
            stmt = select(func.max(model.version)).where(model.base_id == bid)  # type: ignore[attr-defined]
            result = session.execute(stmt).scalar()
            return str(result) if result is not None else "0"

    def rebuild_index(
        self,
        entity_type: str,
        *,
        base_id: str = "",
    ) -> dict[str, dict[str, Any]]:
        """Equivalent to ``load_index()`` — table data is always complete."""
        return self.load_index(entity_type, base_id=base_id)

    def save_batch(
        self,
        entity_type: str,
        entities: list[tuple[str, dict[str, Any]]],
        *,
        base_id: str = "",
    ) -> None:
        """Batch UPSERT — 1 SELECT + bulk INSERT + bulk UPDATE, single transaction."""
        if not entities:
            return
        bid = base_id or self._default_base_id
        model = _ENTITY_TABLES[entity_type]
        code_col = _CODE_COLUMNS[entity_type]
        name_col = _NAME_COLUMNS[entity_type]

        from sqlalchemy.orm import Session

        codes = [c for c, _ in entities]
        with Session(self._engine) as session:
            # 1. Single SELECT to find existing rows
            existing = (
                session.query(getattr(model, code_col))
                .filter(model.base_id == bid, getattr(model, code_col).in_(codes))  # type: ignore[attr-defined]
                .all()
            )
            existing_codes = {row[0] for row in existing}

            # 2. Bulk INSERT new entities via raw cursor (fast, single round-trip)
            new_rows: list[tuple[Any, ...]] = []
            update_rows: list[tuple[Any, ...]] = []
            seen_new: set[str] = set()
            for code, data in entities:
                name = self._extract_name(entity_type, data)
                if code in existing_codes:
                    update_rows.append((name, code, data))
                elif code not in seen_new:
                    seen_new.add(code)
                    new_rows.append((bid, code, name, data))

            conn = session.connection().connection
            if new_rows:
                cur = conn.cursor()
                cur.executemany(
                    f"INSERT INTO {model.__tablename__} "
                    f"(base_id, {code_col}, {name_col}, data) VALUES (%s, %s, %s, %s)",
                    [
                        (r[0], r[1], r[2], json.dumps(r[3], ensure_ascii=False))
                        for r in new_rows
                    ],
                )

            # 3. Bulk UPDATE existing entities
            now = func.now()
            for name, code, data in update_rows:
                session.execute(
                    update(model)
                    .where(
                        getattr(model, "base_id") == bid,
                        getattr(model, code_col) == code,
                    )
                    .values(
                        **{name_col: name, "data": data},
                        version=model.version + 1,  # type: ignore[attr-defined]
                        updated_at=now,
                    )
                )

            session.commit()

    # ── Internal helpers ────────────────────────────────────────────────

    @staticmethod
    def _extract_name(entity_type: str, data: dict[str, Any]) -> str:
        """Extract human-readable name from data dict for the given entity type."""
        name_map: dict[str, str] = {
            "bases": "display_name",
            "scenes": "scene_name",
            "objects": "objectName",
            "views": "viewName",
            "relations": "relationName",
            "actions": "actionName",
            "datasources": "dbName",
        }
        key = name_map.get(entity_type, "")
        name: str = data.get(key, "") or ""
        return name
