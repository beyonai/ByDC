"""_ReaderBase — shared session factory, lazy schema check, and domain helpers for reader Mixins."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from contextlib import AbstractContextManager
from typing import Any

from sqlalchemy import select
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
    """Base class for all reader Mixins.

    Provides session factory, lazy schema check, and shared domain/term name
    resolution helpers used by _TermReader, _TermTypeReader, and _RelationReader.
    """

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

    # ── shared domain code ↔ id translation helpers ─────────────────

    def _resolve_domain_code(self, library_id: str, domain_code: str) -> str | None:
        """Resolve domain_code to domain_id within a library."""
        from datacloud_knowledge.adapters.opengauss._db.models import TermDomain

        try:
            with self._get_session() as session:
                row = session.execute(
                    select(TermDomain.domain_id).where(
                        TermDomain.library_id == library_id,
                        TermDomain.domain_code == domain_code,
                    )
                ).scalar_one_or_none()
            return str(row) if row is not None else None
        except Exception:
            logger.exception(
                "_resolve_domain_code failed: library_id=%s domain_code=%s",
                library_id,
                domain_code,
            )
            return None

    def _batch_resolve_domain_codes(
        self, library_id: str, domain_ids: set[str]
    ) -> dict[str, dict[str, str]]:
        """Batch resolve domain_ids to {code, name} dicts.

        Returns:
            {domain_id: {"code": domain_code, "name": domain_name}} mapping.
        """
        if not domain_ids:
            return {}
        from datacloud_knowledge.adapters.opengauss._db.models import TermDomain

        try:
            with self._get_session() as session:
                rows = session.execute(
                    select(
                        TermDomain.domain_id,
                        TermDomain.domain_code,
                        TermDomain.domain_name,
                    ).where(
                        TermDomain.library_id == library_id,
                        TermDomain.domain_id.in_(list(domain_ids)),
                    )
                ).all()
        except Exception:
            logger.exception(
                "_batch_resolve_domain_codes failed: library_id=%s",
                library_id,
            )
            return {}

        return {str(row[0]): {"code": str(row[1]), "name": str(row[2])} for row in rows}

    def _batch_get_term_names(self, session: Any, term_ids: set[str]) -> dict[str, str]:
        """Batch resolve term_id → term_name."""
        if not term_ids:
            return {}
        from datacloud_knowledge.adapters.opengauss._db.models import Term

        rows = session.execute(
            select(Term.term_id, Term.term_name).where(Term.term_id.in_(list(term_ids)))
        ).all()
        return {str(r[0]): str(r[1]) for r in rows}

    def _batch_get_type_names(self, session: Any, type_codes: set[str]) -> dict[str, str]:
        """Batch resolve type_code → type_name."""
        if not type_codes:
            return {}
        from datacloud_knowledge.adapters.opengauss._db.models import TermType

        rows = session.execute(
            select(TermType.type_code, TermType.type_name).where(
                TermType.type_code.in_(list(type_codes))
            )
        ).all()
        return {str(r[0]): str(r[1]) for r in rows}

    @staticmethod
    def _build_domain_list(
        domain_ids: list[str], domain_map: dict[str, dict[str, str]]
    ) -> list[dict[str, str]]:
        """Build domain [{code, name}] list from domain_ids and lookup map."""
        result: list[dict[str, str]] = []
        for did in domain_ids:
            info = domain_map.get(did)
            if info:
                result.append(info)
        return result

    @staticmethod
    def _datetime_to_epoch(value: Any) -> int:
        """Convert a datetime value to epoch milliseconds, or 0."""
        if value is None:
            return 0
        if hasattr(value, "timestamp"):
            return int(value.timestamp() * 1000)
        return 0

    @staticmethod
    def _format_time(value: Any) -> str | None:
        """Format a datetime value to ISO string, or None."""
        if value is None:
            return None
        if hasattr(value, "isoformat"):
            return value.isoformat()  # type: ignore[no-any-return]
        return str(value)
