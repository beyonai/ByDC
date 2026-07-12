"""_TermTypeWriter — Mixin providing TermType write operations for the OpenGauss adapter."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import delete, func, select, update

from datacloud_knowledge.adapters.opengauss._db.models import Term, TermDomain, TermType
from datacloud_knowledge.adapters.opengauss._writers._base import _pick_key, _WriterBase

logger = logging.getLogger(__name__)


class _TermTypeWriter(_WriterBase):
    """Mixin that writes ``term_type`` table rows via the shared writer base.

    Usage::

        with _TermTypeWriter(session=my_session) as writer:
            writer.create_term_type(term_type={...}, library_id="lib1")
            writer.update_term_type(type_code="VIEW", library_id="lib1", updates={...})
            writer.delete_term_type(type_code="VIEW", library_id="lib1")
    """

    def create_term_type(self, *, term_type: dict[str, Any], library_id: str) -> dict[str, Any]:
        """Insert a new term type definition scoped to a library.

        Args:
            term_type: Dict with keys:
                - ``type_code`` or ``typeCode`` (required)
                - ``type_name`` or ``typeName``
                - ``type_desc`` or ``typeDesc``
                - ``type_category`` or ``typeCategory``
                - ``is_builtin`` or ``isBuiltin``
                - ``domain_ids`` or ``domainIds`` (optional list of domain IDs)
                - ``domain_codes`` or ``domainCodes`` (optional list of domain codes)
            library_id: The library ID this type belongs to.

        Returns:
            Echo dict with: type_code, type_name, type_desc, type_category,
            is_builtin, domain_ids, library_id.
        """
        type_code_ = _pick_key(term_type, "typeCode", "type_code")
        type_name_ = _pick_key(term_type, "typeName", "type_name")
        type_desc_ = _pick_key(term_type, "typeDesc", "type_desc")
        type_category_ = _pick_key(term_type, "typeCategory", "type_category")
        is_builtin_ = _pick_key(term_type, "isBuiltin", "is_builtin")
        domain_ids_raw = _pick_key(term_type, "domainIds", "domain_ids") or []
        domain_codes_raw = _pick_key(term_type, "domainCodes", "domain_codes") or []

        if not type_code_:
            raise ValueError("term_type dict must contain 'type_code' or 'typeCode'")

        # Resolve domain codes to IDs if needed
        domain_ids: list[str] = list(domain_ids_raw) if domain_ids_raw else []
        if domain_codes_raw and not domain_ids_raw:
            domain_ids = self._resolve_domain_codes_to_ids(library_id, list(domain_codes_raw))

        now = self._now()
        row = TermType(
            type_code=str(type_code_),
            type_name=str(type_name_) if type_name_ is not None else "",
            type_desc=str(type_desc_) if type_desc_ is not None else None,
            type_category=int(type_category_) if type_category_ is not None else 0,
            is_builtin=bool(is_builtin_) if is_builtin_ is not None else False,
            library_id=library_id,
            domain_ids=domain_ids,
            created_time=now,
            updated_time=now,
        )
        self.session.add(row)
        self.session.flush()

        logger.info("create_term_type: type_code=%s library_id=%s", type_code_, library_id)

        return {
            "type_code": row.type_code,
            "type_name": row.type_name,
            "type_desc": row.type_desc,
            "type_category": row.type_category,
            "is_builtin": row.is_builtin,
            "domain_ids": row.domain_ids,
            "library_id": row.library_id,
        }

    def update_term_type(self, *, type_code: str, library_id: str, updates: dict[str, Any]) -> None:
        """Update a term type definition by its code and library.

        Only non-None fields in ``updates`` are applied.
        Supports domain_codes → domain_ids translation.

        Args:
            type_code: The term type code to update.
            library_id: The library ID (used in WHERE clause and domain resolution).
            updates: Dict — may contain camelCase keys (typeName/typeDesc/...)
                or snake_case keys (type_name/type_desc/...).
                Only non-None values are updated.
        """
        values: dict[str, Any] = {}
        for src_key, col_attr in (
            ("typeName", "type_name"),
            ("type_name", "type_name"),
            ("typeDesc", "type_desc"),
            ("type_desc", "type_desc"),
            ("typeCategory", "type_category"),
            ("type_category", "type_category"),
            ("isBuiltin", "is_builtin"),
            ("is_builtin", "is_builtin"),
        ):
            val = updates.get(src_key)
            if val is not None:
                values[col_attr] = val

        # Handle domain_ids / domain_codes update
        domain_ids_raw = _pick_key(updates, "domainIds", "domain_ids")
        domain_codes_raw = _pick_key(updates, "domainCodes", "domain_codes")
        if domain_ids_raw is not None:
            values["domain_ids"] = list(domain_ids_raw) if domain_ids_raw else []
        elif domain_codes_raw is not None:
            if domain_codes_raw:
                values["domain_ids"] = self._resolve_domain_codes_to_ids(
                    library_id, list(domain_codes_raw)
                )
            else:
                values["domain_ids"] = []

        if not values:
            return

        values["updated_time"] = self._now()

        stmt = (
            update(TermType)
            .where(TermType.type_code == type_code, TermType.library_id == library_id)
            .values(**values)
        )
        result = self.session.execute(stmt)
        rowcount: int = result.rowcount  # type: ignore[attr-defined]

        if rowcount == 0:
            logger.warning(
                "update_term_type: type_code=%s library_id=%s not found",
                type_code,
                library_id,
            )
        else:
            logger.info(
                "update_term_type: type_code=%s library_id=%s updated=%d fields=%s",
                type_code,
                library_id,
                rowcount,
                list(values.keys()),
            )

    def delete_term_type(self, *, type_code: str, library_id: str) -> None:
        """Delete a term type definition by its code and library.

        Performs safety checks:
        - 403: Cannot delete builtin types
        - 409: Cannot delete types with associated terms

        Args:
            type_code: The term type code to delete.
            library_id: The library ID.
        """
        # Check is_builtin → 403
        existing = self.session.execute(
            select(TermType.is_builtin).where(
                TermType.type_code == type_code,
                TermType.library_id == library_id,
            )
        ).scalar_one_or_none()

        if existing is None:
            logger.warning(
                "delete_term_type: type_code=%s library_id=%s not found",
                type_code,
                library_id,
            )
            return

        if existing:
            raise PermissionError(
                f"Cannot delete builtin term type '{type_code}' in library '{library_id}'"
            )

        # Check for associated terms → 409
        term_count = int(
            self.session.execute(
                select(func.count(Term.term_id)).where(
                    Term.library_id == library_id,
                    Term.term_type_code == type_code,
                )
            ).scalar_one()
        )
        if term_count > 0:
            raise ValueError(
                f"Cannot delete type '{type_code}': "
                f"{term_count} term(s) still use this type in library '{library_id}'"
            )

        stmt = delete(TermType).where(
            TermType.type_code == type_code, TermType.library_id == library_id
        )
        result = self.session.execute(stmt)
        rowcount: int = result.rowcount  # type: ignore[attr-defined]

        logger.info(
            "delete_term_type: type_code=%s library_id=%s deleted=%d",
            type_code,
            library_id,
            rowcount,
        )

    # ── internal helpers ──────────────────────────────────────────

    def _resolve_domain_codes_to_ids(self, library_id: str, domain_codes: list[str]) -> list[str]:
        """Resolve a list of domain_codes to domain_ids within a library."""
        if not domain_codes:
            return []
        rows = (
            self.session.execute(
                select(TermDomain.domain_id).where(
                    TermDomain.library_id == library_id,
                    TermDomain.domain_code.in_(domain_codes),
                )
            )
            .scalars()
            .all()
        )
        return [str(r) for r in rows]
