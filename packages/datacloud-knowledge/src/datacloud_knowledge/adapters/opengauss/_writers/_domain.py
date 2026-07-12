"""TermDomain writer Mixin — operates on the new ``term_domain`` table.

Replaces the old Domain + DomainLibrary + DomainTermType three-table design.
Provides create/update/delete with safety checks and code→id translation helpers.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import delete, func, select, text, update

from datacloud_knowledge.adapters.opengauss._db.models import TermDomain, TermType

from ._base import _WriterBase

logger = logging.getLogger(__name__)


class _DomainWriter(_WriterBase):
    """TermDomain write operations on the ``term_domain`` table."""

    def create_domain(self, *, domain: dict[str, Any]) -> dict[str, Any]:
        """Create a domain row in term_domain.

        Args:
            domain: Dict with keys:
                - ``domain_code`` or ``domainCode`` (required)
                - ``domain_name`` or ``domainName`` (required)
                - ``library_id`` or ``libraryId`` (required)
                - ``parent_id`` or ``parentId`` (optional)
                - ``domain_desc`` or ``domainDesc`` (optional)
                - ``domain_id`` or ``domainId`` (optional — auto-generated if absent)

        Returns:
            Echo dict of the created domain row.
        """
        domain_id = domain.get("domainId") or domain.get("domain_id") or self._new_id()
        domain_code = domain.get("domainCode") or domain.get("domain_code", "")
        domain_name = domain.get("domainName") or domain.get("domain_name", "")
        library_id = domain.get("libraryId") or domain.get("library_id", "")
        parent_id = domain.get("parentId") or domain.get("parent_id")
        domain_desc = domain.get("domainDesc") or domain.get("domain_desc")

        if not domain_code:
            raise ValueError("domain dict must contain 'domain_code' or 'domainCode'")
        if not domain_name:
            raise ValueError("domain dict must contain 'domain_name' or 'domainName'")
        if not library_id:
            raise ValueError("domain dict must contain 'library_id' or 'libraryId'")

        now = self._now()
        row = TermDomain(
            domain_id=str(domain_id),
            domain_code=str(domain_code),
            domain_name=str(domain_name),
            parent_id=str(parent_id) if parent_id is not None else None,
            library_id=str(library_id),
            domain_desc=str(domain_desc) if domain_desc is not None else None,
            created_time=now,
            updated_time=now,
        )
        self.session.add(row)
        self.session.flush()

        logger.info(
            "Created domain: id=%s code=%s name=%s library=%s",
            domain_id,
            domain_code,
            domain_name,
            library_id,
        )
        return self.get_domain(domain_id)

    def update_domain(self, *, library_id: str, domain_code: str, updates: dict[str, Any]) -> None:
        """Update a domain row in term_domain by (library_id, domain_code).

        Resolves domain_code to domain_id first, then updates.
        Only non-None fields are applied. Supports:
        - domain_code / domainCode
        - domain_name / domainName
        - parent_id / parentId
        - domain_desc / domainDesc

        Args:
            library_id: The library ID.
            domain_code: The domain's code.
            updates: Dict with camelCase or snake_case keys.
        """
        domain_id = self.resolve_domain_code_to_id(library_id, domain_code)
        if domain_id is None:
            raise ValueError(f"Domain not found: library_id={library_id} domain_code={domain_code}")

        values: dict[str, Any] = {}
        for src_key, col_attr in (
            ("domainCode", "domain_code"),
            ("domain_code", "domain_code"),
            ("domainName", "domain_name"),
            ("domain_name", "domain_name"),
            ("parentId", "parent_id"),
            ("parent_id", "parent_id"),
            ("domainDesc", "domain_desc"),
            ("domain_desc", "domain_desc"),
        ):
            val = updates.get(src_key)
            if val is not None:
                values[col_attr] = val

        if not values:
            return

        values["updated_time"] = self._now()
        stmt = update(TermDomain).where(TermDomain.domain_id == domain_id).values(**values)
        result = self.session.execute(stmt)
        rowcount: int = result.rowcount  # type: ignore[attr-defined]

        if rowcount == 0:
            logger.warning("update_domain: domain_id=%s not found", domain_id)
        else:
            logger.info(
                "update_domain: domain_id=%s updated=%d fields=%s",
                domain_id,
                rowcount,
                list(values.keys()),
            )

    def delete_domain(self, *, library_id: str, domain_code: str) -> None:
        """Delete a domain from term_domain by (library_id, domain_code).

        Resolves domain_code to domain_id first, then deletes.
        Safety checks:
        - 409: Cannot delete if child domains exist (parent_id references)
        - 409: Cannot delete if any term_type references this domain via domain_ids @>
        - Cleanup: Remove domain_id from term.domain_ids[] (zombie reference prevention)

        Args:
            library_id: The library ID.
            domain_code: The domain's code.

        Raises:
            ValueError: If domain not found, child domains, or type references exist.
        """
        domain_id = self.resolve_domain_code_to_id(library_id, domain_code)
        if domain_id is None:
            raise ValueError(f"Domain not found: library_id={library_id} domain_code={domain_code}")
        # Check for child domains
        child_count = int(
            self.session.execute(
                select(func.count())
                .select_from(TermDomain)
                .where(TermDomain.parent_id == domain_id)
            ).scalar_one()
        )
        if child_count > 0:
            raise ValueError(
                f"Cannot delete domain '{domain_id}': {child_count} child domain(s) exist"
            )

        # Check for type references via domain_ids @> (raises if any)
        type_count = int(
            self.session.execute(
                select(func.count())
                .select_from(TermType)
                .where(text("term_type.domain_ids @> ARRAY[:did]::varchar[]")),
                {"did": domain_id},
            ).scalar_one()
        )
        if type_count > 0:
            raise ValueError(
                f"Cannot delete domain '{domain_id}': "
                f"{type_count} term type(s) still reference this domain"
            )

        # Clean term.domain_ids[] — remove the deleted domain_id from all referencing terms
        self.session.execute(
            text(
                "UPDATE term SET domain_ids = array_remove(domain_ids, :did) "
                "WHERE domain_ids @> ARRAY[:did]::varchar[]"
            ),
            {"did": domain_id},
        )

        stmt = delete(TermDomain).where(TermDomain.domain_id == domain_id)
        result = self.session.execute(stmt)
        rowcount: int = result.rowcount  # type: ignore[attr-defined]

        if rowcount == 0:
            logger.warning("delete_domain: domain_id=%s not found", domain_id)
        else:
            logger.info("delete_domain: domain_id=%s deleted=%d", domain_id, rowcount)

    def get_domain(self, domain_id: str) -> dict[str, Any]:
        """Internal: read back a domain row by ID. Used by create_domain for echo."""
        row = self.session.execute(
            select(TermDomain).where(TermDomain.domain_id == domain_id)
        ).scalar_one_or_none()
        if row is None:
            return {}

        return {
            "domain_id": row.domain_id,
            "domain_code": row.domain_code,
            "domain_name": row.domain_name,
            "parent_id": row.parent_id,
            "library_id": row.library_id,
            "domain_desc": row.domain_desc,
            "created_time": row.created_time.isoformat(),
            "updated_time": row.updated_time.isoformat(),
        }

    # ── code → id translation helpers ───────────────────────────

    def resolve_domain_code_to_id(self, library_id: str, domain_code: str) -> str | None:
        """Resolve a single domain_code to domain_id within a library."""
        row = self.session.execute(
            select(TermDomain.domain_id).where(
                TermDomain.library_id == library_id,
                TermDomain.domain_code == domain_code,
            )
        ).scalar_one_or_none()
        return str(row) if row is not None else None

    def bulk_resolve_domain_codes_to_ids(
        self, library_id: str, domain_codes: list[str]
    ) -> dict[str, str]:
        """Resolve a list of domain_codes to {code: id} mapping within a library."""
        if not domain_codes:
            return {}
        rows = self.session.execute(
            select(TermDomain.domain_code, TermDomain.domain_id).where(
                TermDomain.library_id == library_id,
                TermDomain.domain_code.in_(domain_codes),
            )
        ).all()
        return {str(r[0]): str(r[1]) for r in rows}
