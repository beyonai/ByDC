"""Dependency injection - provides OntologyService singleton.

Separate from app.py to avoid circular import with routes.py.
"""
from __future__ import annotations

from datacloud_server.services.ontology_service import OntologyService  # noqa: TC001

_service: OntologyService | None = None


def set_service(service: OntologyService) -> None:
    """Set the global service instance (called by app factory)."""
    global _service  # noqa: PLW0603
    _service = service


def get_service() -> OntologyService:
    """Get the injected OntologyService instance."""
    if _service is None:
        raise RuntimeError("App not initialized. Call create_app() first.")
    return _service
