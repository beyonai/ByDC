"""Domain writer Mixin."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import delete, func, select, update

from datacloud_knowledge.adapters.opengauss._db.models import Domain, DomainLibrary, DomainTermType

from ._base import _WriterBase

logger = logging.getLogger(__name__)


class _DomainWriter(_WriterBase):
    """Domain write operations."""

    def create_domain(self, *, domain: dict[str, Any]) -> dict[str, Any]:
        """Create domain with junction tables in one transaction."""
        from datacloud_knowledge.contracts.types import DomainCreate

        model = DomainCreate.model_validate(domain)
        did = model.domain_id or self._new_id()
        now = self._now()

        self.session.add(
            Domain(
                domain_id=did,
                domain_name=model.domain_name,
                parent_id=model.parent_id,
                domain_desc=model.domain_desc,
                created_time=now,
                updated_time=now,
            )
        )
        for lid in model.library_ids:
            self.session.add(DomainLibrary(domain_id=did, library_id=lid))
        for tc in model.term_type_codes:
            self.session.add(DomainTermType(domain_id=did, type_code=tc))

        logger.info("Created domain: id=%s name=%s", did, model.domain_name)
        return self.get_domain(did)

    def update_domain(self, *, domain_id: str, updates: dict[str, Any]) -> None:
        """Update domain fields and replace junction data."""
        from datacloud_knowledge.contracts.types import DomainUpdate

        model = DomainUpdate.model_validate(updates)
        domain_fields = model.model_dump(
            exclude={"library_ids", "term_type_codes"}, exclude_unset=True
        )
        if domain_fields:
            domain_fields["updated_time"] = self._now()
            self.session.execute(
                update(Domain).where(Domain.domain_id == domain_id).values(**domain_fields)
            )
        if model.library_ids is not None:
            self.session.execute(delete(DomainLibrary).where(DomainLibrary.domain_id == domain_id))
            for lid in model.library_ids:
                self.session.add(DomainLibrary(domain_id=domain_id, library_id=lid))
        if model.term_type_codes is not None:
            self.session.execute(
                delete(DomainTermType).where(DomainTermType.domain_id == domain_id)
            )
            for tc in model.term_type_codes:
                self.session.add(DomainTermType(domain_id=domain_id, type_code=tc))

        logger.info("Updated domain: id=%s", domain_id)

    def delete_domain(self, *, domain_id: str) -> None:
        """Delete domain after checking for children."""
        count = self.session.execute(
            select(func.count()).select_from(Domain).where(Domain.parent_id == domain_id)
        ).scalar()
        if count:
            raise ValueError(f"Domain '{domain_id}' has child domains, cannot delete")
        self.session.execute(delete(DomainLibrary).where(DomainLibrary.domain_id == domain_id))
        self.session.execute(delete(DomainTermType).where(DomainTermType.domain_id == domain_id))
        self.session.execute(delete(Domain).where(Domain.domain_id == domain_id))
        logger.info("Deleted domain: id=%s", domain_id)

    def get_domain(self, domain_id: str) -> dict[str, Any]:
        """Internal: read back domain after create. Used by create_domain for echo."""
        row = self.session.execute(
            select(Domain).where(Domain.domain_id == domain_id)
        ).scalar_one_or_none()
        if row is None:
            return {}
        lib_rows = (
            self.session.execute(
                select(DomainLibrary.library_id).where(DomainLibrary.domain_id == domain_id)
            )
            .scalars()
            .all()
        )
        type_rows = (
            self.session.execute(
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
            "created_time": row.created_time.isoformat(),
            "updated_time": row.updated_time.isoformat(),
        }
