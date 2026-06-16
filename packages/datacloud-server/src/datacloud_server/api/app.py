"""FastAPI application factory with dependency injection."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastapi import FastAPI

from datacloud_server.api.routes import router
from datacloud_server.services.ontology_service import OntologyService

if TYPE_CHECKING:
    from datacloud_server.registry.registry import OntologyBaseRegistry


def create_app(
    *,
    registry: OntologyBaseRegistry | None = None,
    local_adapter: Any = None,
    remote_adapter: Any = None,
) -> FastAPI:
    """Create FastAPI app with optional dependency overrides for testing."""
    from datacloud_server.api import deps as _deps  # noqa: PLC0415

    app = FastAPI(title="Ontology Service", version="0.1.0")
    app.include_router(router)

    if registry is not None and local_adapter is not None:
        service = OntologyService(
            registry=registry,
            local_adapter=local_adapter,
            remote_adapter=remote_adapter or local_adapter,
        )
        _deps.set_service(service)

    return app
