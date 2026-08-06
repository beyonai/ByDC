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


class _ObjectFieldRow(_Base):
    """Denormalised field metadata for fast ``_resolve_referenced_properties`` lookups.

    Populated from ``ontology_objects.data -> fields`` JSONB at write time.
    New databases get this table via ``Base.metadata.create_all(checkfirst=True)``;
    existing databases use ``db/scripts/backfill_ontology_object_fields.py``.
    """

    __tablename__ = "ontology_object_fields"
    base_id = Column(String(64), primary_key=True)
    object_code = Column(String(256), primary_key=True)
    field_code = Column(String(256), primary_key=True)
    field_name = Column(String(512))
    term_type_code = Column(String(128))


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
        owner_type: str | None = None,
        user_code: str | None = None,
        ext_property_filters: dict[str, Any] | None = None,
        ext_property_in_filters: dict[str, list[Any]] | None = None,
        top_level_or_filters: dict[str, list[Any]] | None = None,
        page: int = 1,
        page_size: int | None = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        """Paginated search with keyword, code-set, owner, and extProperty filtering.

        All filters are pushed down to SQL via JSONB operators on the ``data``
        column.  ``owner_type`` / ``user_code`` are matched at top-level as well
        as inside ``ext_property`` for backward compatibility with OWL-imported
        entities.

        ``top_level_or_filters`` matches top-level JSON keys with OR semantics:
        an entity passes if ANY (key, value) pair matches
        (e.g. ``{"source_class": [c], "target_class": [c]}``).  ``page_size``
        may be ``None`` to disable pagination and return all matches.
        """
        bid = base_id or self._default_base_id
        model = _ENTITY_TABLES[entity_type]
        code_col_name = _CODE_COLUMNS[entity_type]
        name_col_name = _NAME_COLUMNS[entity_type]

        if codes is not None and len(codes) == 0:
            return [], 0

        from sqlalchemy import or_, select
        from sqlalchemy.orm import Session

        with Session(self._engine) as session:
            # Base WHERE clause (reused for both count and data queries)
            base_where = [getattr(model, "base_id") == bid]

            if codes is not None:
                base_where.append(getattr(model, code_col_name).in_(codes))

            if keyword:
                base_where.append(getattr(model, name_col_name).ilike(f"%{keyword}%"))

            # JSONB pushdown: owner_type (top-level + ext_property for compat)
            data_col = model.data  # type: ignore[attr-defined]
            if owner_type:
                base_where.append(
                    or_(
                        data_col.op("->>")("owner_type") == owner_type,
                        data_col.op("->")("ext_property").op("->>")("owner_type")
                        == owner_type,
                    )
                )

            # JSONB pushdown: user_code (top-level + ext_property for compat)
            if user_code:
                base_where.append(
                    or_(
                        data_col.op("->>")("user_code") == user_code,
                        data_col.op("->")("ext_property").op("->>")("user_code")
                        == user_code,
                    )
                )

            # JSONB pushdown: ext_property key-value filter (AND semantics)
            if ext_property_filters:
                for key, val in ext_property_filters.items():
                    base_where.append(
                        data_col.op("->")("ext_property").op("->>")(key) == str(val)
                    )

            if ext_property_in_filters:
                for key, values in ext_property_in_filters.items():
                    if values:
                        json_value = data_col.op("->")("ext_property").op("->>")(key)
                        base_where.append(
                            json_value.in_([str(value) for value in values])
                        )

            # OR pushdown over top-level JSON keys: any (key, value) pair
            # matching passes (e.g. source_class = c OR target_class = c).
            if top_level_or_filters:
                or_conds = []
                for key, values in top_level_or_filters.items():
                    if not values:
                        continue
                    for value in values:
                        or_conds.append(data_col.op("->>")(key) == str(value))
                if or_conds:
                    base_where.append(or_(*or_conds))

            # Lightweight count query — reads no JSONB data
            count_stmt = (
                select(func.count(getattr(model, code_col_name)))
                .select_from(model)
                .where(*base_where)
            )
            total: int = session.execute(count_stmt).scalar() or 0

            if total == 0:
                return [], 0

            # Data query — reads only the requested page (all rows when
            # page_size is None)
            code_attr = getattr(model, code_col_name)
            data_stmt = select(model.data).where(*base_where).order_by(code_attr)  # type: ignore[attr-defined]
            if page_size is not None:
                data_stmt = data_stmt.limit(page_size).offset((page - 1) * page_size)
            rows = session.execute(data_stmt).all()
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
        """Return backend-independent index: ``{code: {code, name, base_id, ...}}``.

        For ``scenes`` the ``scene_code`` field is extracted from the JSONB
        ``data`` column so that ``_ensure_default_scene`` can locate the
        default scene across process restarts.
        """
        bid = base_id or self._default_base_id
        model = _ENTITY_TABLES[entity_type]
        code_col = _CODE_COLUMNS[entity_type]
        name_col = _NAME_COLUMNS[entity_type]

        from sqlalchemy import select
        from sqlalchemy.orm import Session

        with Session(self._engine) as session:
            stmt = select(model).where(model.base_id == bid)  # type: ignore[attr-defined]
            rows = session.execute(stmt).scalars().all()

        if entity_type == "scenes":
            return {
                getattr(r, code_col): {
                    "code": getattr(r, code_col),
                    "name": getattr(r, name_col) or getattr(r, code_col),
                    "scene_id": getattr(
                        r, code_col
                    ),  # alias for callers that use scene_id
                    "scene_name": getattr(r, name_col) or getattr(r, code_col),
                    "base_id": r.base_id,  # type: ignore[attr-defined]
                    "scene_code": (r.data or {}).get("scene_code", ""),  # type: ignore[attr-defined]
                }
                for r in rows
            }
        return {
            getattr(r, code_col): {
                "code": getattr(r, code_col),
                "name": getattr(r, name_col) or getattr(r, code_col),
                "base_id": r.base_id,  # type: ignore[attr-defined]
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
        # snake_case fallbacks (for normalized canonical data)
        name_fallback: dict[str, str] = {
            "objects": "object_name",
            "views": "view_name",
            "relations": "relation_name",
            "actions": "action_name",
            "datasources": "db_name",
        }
        key = name_map.get(entity_type, "")
        name: str = (
            data.get(key, "") or data.get(name_fallback.get(entity_type, ""), "") or ""
        )
        return name
