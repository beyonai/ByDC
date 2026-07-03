"""_ReaderBase — shared session factory and lazy schema check for reader Mixins."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from contextlib import AbstractContextManager

from sqlalchemy.orm import Session

from datacloud_knowledge.adapters.opengauss._db.connection import get_session

logger = logging.getLogger(__name__)

_SCHEMA_CHECKED = False
_LOCK = threading.Lock()


def _auto_ensure_schema() -> None:
    """Module-level lazy check: verify on first call, auto-create missing tables."""
    global _SCHEMA_CHECKED
    if _SCHEMA_CHECKED:
        return
    with _LOCK:
        if _SCHEMA_CHECKED:
            return
        try:
            from datacloud_knowledge.adapters import ensure_schema, verify_schema

            result = verify_schema()
            missing: list[str] = result.get("missing", [])
            if missing:
                logger.warning("Schema check: %d tables missing — auto-creating...", len(missing))
                ensure_schema(reset=False)
                logger.info("Schema auto-create complete")
            _SCHEMA_CHECKED = True
        except Exception:
            logger.exception("Schema auto-check failed — will retry on next call")


class _ReaderBase:
    """Base class for all reader Mixins. Provides session factory and lazy schema check."""

    def __init__(
        self,
        session_factory: Callable[[], AbstractContextManager[Session]] | None = None,
    ) -> None:
        self._session_factory: Callable[[], AbstractContextManager[Session]] = (
            session_factory if session_factory is not None else get_session
        )

    def _get_session(self) -> AbstractContextManager[Session]:
        """Get session context manager. Triggers lazy schema check on first call."""
        _auto_ensure_schema()
        return self._session_factory()
