"""API layer — FastAPI factory routers.

Usage::

    from datacloud_platform.api import create_app, create_ontology_routes

    # Option A: full app (includes all route groups)
    app = create_app(platform)

    # Option B: selective assembly
    from datacloud_platform.api.ontology_routes import create_ontology_routes
    app.include_router(create_ontology_routes(platform))
"""

from __future__ import annotations

from datacloud_platform.api.import_routes import create_import_routes
from datacloud_platform.api.ontology_routes import create_ontology_routes
from datacloud_platform.api.resource_routes import create_resource_routes
from datacloud_platform.api.search_routes import create_search_routes
from datacloud_platform.api.server import create_app

__all__ = [
    "create_app",
    "create_import_routes",
    "create_ontology_routes",
    "create_resource_routes",
    "create_search_routes",
]
