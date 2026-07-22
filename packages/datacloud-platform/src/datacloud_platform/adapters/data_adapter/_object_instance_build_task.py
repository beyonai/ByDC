"""DB adapter for object_instance_build_task records."""

from __future__ import annotations

import json
import logging
import threading
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Column, DateTime, Integer, String, Text, update
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Session

logger = logging.getLogger(__name__)


class _TaskBase(DeclarativeBase):
    pass


class ObjectInstanceBuildTaskRow(_TaskBase):
    """SQLAlchemy row for object_instance_build_task."""

    __tablename__ = "object_instance_build_task"

    task_id = Column(String(64), primary_key=True)
    status = Column(String(32), nullable=False)
    instance_ids = Column(JSONB, nullable=False, default=list)
    batch_size = Column(Integer, nullable=False, default=20)
    total_count = Column(Integer, nullable=False, default=0)
    success_count = Column(Integer, nullable=False, default=0)
    failed_count = Column(Integer, nullable=False, default=0)
    error_message = Column(Text, nullable=True)
    errors = Column(JSONB, nullable=False, default=list)
    created_by = Column(String(128), nullable=True)
    created_time = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
    updated_time = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )


_engine_cache: dict[str, Any] = {}
_engine_lock = threading.Lock()


def _get_task_engine(schema: str | None = None) -> Any:
    """Return a cached SQLAlchemy Engine, creating the task table if needed."""
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
            _TaskBase.metadata.create_all(engine, checkfirst=True)
            _engine_cache[key] = engine
        return _engine_cache[key]


class ObjectInstanceBuildTaskAdapter:
    """DB operations for object_instance_build_task."""

    def __init__(self, schema: str | None = None) -> None:
        self._schema = schema

    def _engine(self) -> Any:
        return _get_task_engine(self._schema)

    def create(self, record: dict[str, Any]) -> dict[str, Any]:
        """Insert a task row."""
        row = ObjectInstanceBuildTaskRow(
            task_id=record["task_id"],
            status=record["status"],
            instance_ids=record.get("instance_ids") or [],
            batch_size=record.get("batch_size", 20),
            total_count=record.get("total_count", 0),
            success_count=record.get("success_count", 0),
            failed_count=record.get("failed_count", 0),
            error_message=record.get("error_message"),
            errors=record.get("errors") or [],
            created_by=record.get("created_by"),
            created_time=record.get("created_time") or datetime.now(UTC),
            updated_time=record.get("updated_time") or datetime.now(UTC),
        )
        engine = self._engine()
        with Session(engine) as session:
            session.add(row)
            session.commit()
            session.refresh(row)
            data = _row_to_dict(row)
        logger.info("ObjectInstanceBuildTaskAdapter.create: task_id=%s", row.task_id)
        return data

    def get(self, task_id: str) -> dict[str, Any] | None:
        """Get a task row by task_id."""
        engine = self._engine()
        with Session(engine) as session:
            row = session.get(ObjectInstanceBuildTaskRow, task_id)
            if row is None:
                return None
            return _row_to_dict(row)

    def update(self, task_id: str, updates: dict[str, Any]) -> dict[str, Any]:
        """Update a task row and return the latest data."""
        if not updates:
            existing = self.get(task_id)
            if existing is None:
                raise KeyError(f"object instance build task not found: {task_id}")
            return existing

        updates = dict(updates)
        updates["updated_time"] = datetime.now(UTC)
        engine = self._engine()
        with Session(engine) as session:
            result = session.execute(
                update(ObjectInstanceBuildTaskRow)
                .where(ObjectInstanceBuildTaskRow.task_id == task_id)
                .values(**updates)
            )
            if result.rowcount == 0:  # type: ignore[attr-defined]
                session.rollback()
                raise KeyError(f"object instance build task not found: {task_id}")
            session.commit()
            row = session.get(ObjectInstanceBuildTaskRow, task_id)
            if row is None:
                raise KeyError(f"object instance build task not found: {task_id}")
            return _row_to_dict(row)


def _row_to_dict(row: ObjectInstanceBuildTaskRow) -> dict[str, Any]:
    instance_ids = _json_value(row.instance_ids, [])
    errors = _json_value(row.errors, [])
    return {
        "task_id": row.task_id,
        "status": row.status,
        "instance_ids": instance_ids if isinstance(instance_ids, list) else [],
        "batch_size": row.batch_size,
        "total_count": row.total_count,
        "success_count": row.success_count,
        "failed_count": row.failed_count,
        "error_message": row.error_message or "",
        "errors": errors if isinstance(errors, list) else [],
        "created_by": row.created_by or "",
        "created_time": row.created_time,
        "updated_time": row.updated_time,
    }


def _json_value(value: Any, default: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return default
    return value if value is not None else default
