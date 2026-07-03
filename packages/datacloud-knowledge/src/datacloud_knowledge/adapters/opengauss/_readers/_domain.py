"""Domain reader Mixin."""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select

from datacloud_knowledge.adapters.opengauss._db.models import Domain, DomainLibrary, DomainTermType

from ._base import _ReaderBase


class _DomainReader(_ReaderBase):
    """Domain read operations."""

    def list_domains(self, *, parent_id: str | None = None) -> list[dict[str, Any]]:
        """List domains, optionally filtered by parent_id."""
        with self._get_session() as session:
            stmt = select(Domain)
            if parent_id is not None:
                stmt = stmt.where(Domain.parent_id == parent_id)
            stmt = stmt.order_by(Domain.domain_name)
            rows = session.execute(stmt).scalars().all()
        return [
            {
                "domain_id": r.domain_id,
                "domain_name": r.domain_name,
                "parent_id": r.parent_id,
                "domain_desc": r.domain_desc,
                "created_time": r.created_time.isoformat(),
                "updated_time": r.updated_time.isoformat(),
            }
            for r in rows
        ]

    def get_domain(self, *, domain_id: str) -> dict[str, Any] | None:
        """Get single domain by ID with junction data."""
        with self._get_session() as session:
            row = session.execute(
                select(Domain).where(Domain.domain_id == domain_id)
            ).scalar_one_or_none()
            if row is None:
                return None
            # Get children count
            children_count = (
                session.execute(
                    select(func.count()).select_from(Domain).where(Domain.parent_id == domain_id)
                ).scalar()
                or 0
            )
            # Get linked library IDs
            lib_rows = (
                session.execute(
                    select(DomainLibrary.library_id).where(DomainLibrary.domain_id == domain_id)
                )
                .scalars()
                .all()
            )
            # Get linked type codes
            type_rows = (
                session.execute(
                    select(DomainTermType.type_code).where(DomainTermType.domain_id == domain_id)
                )
                .scalars()
                .all()
            )
        return {
            "domain_id": row.domain_id,
            "domain_name": row.domain_name,
            "parent_id": row.parent_id,
            "domain_desc": row.domain_desc,
            "library_ids": list(lib_rows),
            "term_type_codes": list(type_rows),
            "children_count": children_count,
            "created_time": row.created_time.isoformat(),
            "updated_time": row.updated_time.isoformat(),
        }

    def list_domain_term_types(self, *, domain_id: str) -> list[dict[str, Any]]:
        """List term types linked to a domain."""
        with self._get_session() as session:
            rows = (
                session.execute(
                    select(DomainTermType.type_code).where(DomainTermType.domain_id == domain_id)
                )
                .scalars()
                .all()
            )
        return [{"type_code": r} for r in rows]
