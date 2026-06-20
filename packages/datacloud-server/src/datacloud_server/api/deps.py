"""Dependency injection — provides 3 domain Service singletons.

Separate from app.py to avoid circular import with routes.py.
"""

from __future__ import annotations

from datacloud_server.services.ontology_base_service import OntologyBaseService  # noqa: TC001
from datacloud_server.services.ontology_resource_service import (
    OntologyResourceService,  # noqa: TC001
)
from datacloud_server.services.ontology_search_service import OntologySearchService  # noqa: TC001

_base_service: OntologyBaseService | None = None
_resource_service: OntologyResourceService | None = None
_search_service: OntologySearchService | None = None


def set_services(
    base_service: OntologyBaseService,
    resource_service: OntologyResourceService,
    search_service: OntologySearchService,
) -> None:
    """Set all three service instances (called by app factory)."""
    global _base_service, _resource_service, _search_service  # noqa: PLW0603
    _base_service = base_service
    _resource_service = resource_service
    _search_service = search_service


def get_base_service() -> OntologyBaseService:
    if _base_service is None:
        raise RuntimeError("App not initialized. Call create_app() first.")
    return _base_service


def get_resource_service() -> OntologyResourceService:
    if _resource_service is None:
        raise RuntimeError("App not initialized. Call create_app() first.")
    return _resource_service


def get_search_service() -> OntologySearchService:
    if _search_service is None:
        raise RuntimeError("App not initialized. Call create_app() first.")
    return _search_service


# ── backward-compat alias for existing callers ──


def get_service() -> OntologyBaseService:
    """Backward-compat: returns the first service (same behavior for list_bases)."""
    return get_base_service()
