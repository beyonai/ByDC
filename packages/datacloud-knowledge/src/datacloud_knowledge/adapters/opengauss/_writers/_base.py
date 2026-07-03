"""_WriterBase — shared session management, snowflake ID, and timestamp helpers."""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from contextlib import AbstractContextManager
from datetime import UTC, datetime
from typing import Any, Self

from sqlalchemy.orm import Session

from datacloud_knowledge.adapters.opengauss._db.connection import get_session
from datacloud_knowledge.adapters.opengauss._readers._base import _auto_ensure_schema

logger = logging.getLogger(__name__)


def _pick_key(data: dict[str, Any], *keys: str) -> Any:
    """Pick the first available key from a dict, returning None if none found."""
    for k in keys:
        val = data.get(k)
        if val is not None:
            return val
    return None


class _WriterBase:
    """Base class for all writer Mixins. Provides shared session and ID generation."""

    def __init__(
        self,
        session: Session | None = None,
        session_factory: Callable[[], AbstractContextManager[Session]] | None = None,
    ) -> None:
        if session is not None:
            self._session: Session = session
            self._session_factory: Callable[[], AbstractContextManager[Session]] | None = None
        else:
            self._session_factory = session_factory if session_factory is not None else get_session
            self._session = None  # type: ignore[assignment]
        self._owns_ctx: bool = False
        self._ctx: AbstractContextManager[Session] | None = None

    @property
    def session(self) -> Session:
        """Get current Session (only valid inside context manager)."""
        if self._session is not None:
            return self._session
        raise RuntimeError(
            "Writer not bound to session. Use inside context manager or pass session to constructor."
        )

    def _get_session_ctx(self) -> AbstractContextManager[Session]:
        """Get session context manager."""
        if self._session is not None:
            from contextlib import nullcontext

            return nullcontext(self._session)
        if self._session_factory is not None:
            return self._session_factory()
        raise RuntimeError("Writer not configured with session or session_factory")

    def __enter__(self) -> Self:
        if self._session is not None:
            self._owns_ctx = False
            return self
        ctx = self._get_session_ctx()
        self._session = ctx.__enter__()
        self._ctx = ctx
        self._owns_ctx = True
        # Lazy schema check on first write
        _auto_ensure_schema()
        return self

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        if self._owns_ctx:
            if self._ctx is None:
                raise RuntimeError("_ctx must be set when _owns_ctx is True")
            self._ctx.__exit__(exc_type, exc_val, exc_tb)  # type: ignore[arg-type]
            self._session = None  # type: ignore[assignment]

    @staticmethod
    def _now() -> datetime:
        """Current UTC timestamp."""
        return datetime.now(tz=UTC)

    @staticmethod
    def _new_id() -> str:
        """Generate a snowflake-style ID. For now uses UUID v4, replace with real snowflake later."""
        return str(uuid.uuid4())
