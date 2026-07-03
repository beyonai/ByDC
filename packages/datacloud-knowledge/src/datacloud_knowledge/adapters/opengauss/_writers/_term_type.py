"""_TermTypeWriter — Mixin providing TermType write operations for the OpenGauss adapter."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import delete, update

from datacloud_knowledge.adapters.opengauss._db.models import TermType
from datacloud_knowledge.adapters.opengauss._writers._base import _pick_key, _WriterBase

logger = logging.getLogger(__name__)


class _TermTypeWriter(_WriterBase):
    """Mixin that writes ``term_type`` table rows via the shared writer base.

    Usage::

        with _TermTypeWriter(session=my_session) as writer:
            writer.create_term_type(term_type={"type_code": "VIEW", ...})
            writer.update_term_type(type_code="VIEW", updates={"type_name": "New"})
            writer.delete_term_type(type_code="VIEW")
    """

    def create_term_type(self, *, term_type: dict[str, Any]) -> dict[str, Any]:
        """Insert a new term type definition.

        Args:
            term_type: Dict with keys:
                - ``type_code`` or ``typeCode`` (required)
                - ``type_name`` or ``typeName``
                - ``type_desc`` or ``typeDesc``
                - ``type_category`` or ``typeCategory``
                - ``is_builtin`` or ``isBuiltin``

        Returns:
            Echo dict with: type_code, type_name, type_desc, type_category,
            is_builtin.
        """
        type_code_ = _pick_key(term_type, "typeCode", "type_code")
        type_name_ = _pick_key(term_type, "typeName", "type_name")
        type_desc_ = _pick_key(term_type, "typeDesc", "type_desc")
        type_category_ = _pick_key(term_type, "typeCategory", "type_category")
        is_builtin_ = _pick_key(term_type, "isBuiltin", "is_builtin")

        if not type_code_:
            raise ValueError("term_type dict must contain 'type_code' or 'typeCode'")

        row = TermType(
            type_code=str(type_code_),
            type_name=str(type_name_) if type_name_ is not None else "",
            type_desc=str(type_desc_) if type_desc_ is not None else None,
            type_category=int(type_category_) if type_category_ is not None else 0,
            is_builtin=bool(is_builtin_) if is_builtin_ is not None else False,
        )
        self.session.add(row)
        self.session.flush()

        logger.info("create_term_type: type_code=%s", type_code_)

        return {
            "type_code": row.type_code,
            "type_name": row.type_name,
            "type_desc": row.type_desc,
            "type_category": row.type_category,
            "is_builtin": row.is_builtin,
        }

    def update_term_type(self, *, type_code: str, updates: dict[str, Any]) -> None:
        """Update a term type definition by its code.

        Only non-None fields in ``updates`` are applied.

        Args:
            type_code: The term type code to update.
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

        if not values:
            return

        stmt = update(TermType).where(TermType.type_code == type_code).values(**values)
        result = self.session.execute(stmt)
        rowcount: int = result.rowcount  # type: ignore[attr-defined]

        if rowcount == 0:
            logger.warning("update_term_type: type_code=%s not found", type_code)
        else:
            logger.info(
                "update_term_type: type_code=%s updated=%d fields=%s",
                type_code,
                rowcount,
                list(values.keys()),
            )

    def delete_term_type(self, *, type_code: str) -> None:
        """Delete a term type definition by its code.

        Args:
            type_code: The term type code to delete.
        """
        stmt = delete(TermType).where(TermType.type_code == type_code)
        result = self.session.execute(stmt)
        rowcount: int = result.rowcount  # type: ignore[attr-defined]

        if rowcount == 0:
            logger.warning("delete_term_type: type_code=%s not found", type_code)
        else:
            logger.info(
                "delete_term_type: type_code=%s deleted=%d",
                type_code,
                rowcount,
            )
