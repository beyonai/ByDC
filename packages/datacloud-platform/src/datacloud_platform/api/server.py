"""FastAPI application factory for datacloud-platform.

Usage::

    from datacloud_platform import DatacloudPlatform, OntologyBaseRegistry
    from datacloud_platform.api import create_app

    registry = OntologyBaseRegistry()
    platform = DatacloudPlatform(_base_registry=registry)
    app = create_app(platform)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import FastAPI

from datacloud_platform.api.import_routes import create_import_routes
from datacloud_platform.api.ontology_routes import create_ontology_routes
from datacloud_platform.api.resource_routes import create_resource_routes
from datacloud_platform.api.search_routes import create_search_routes

if TYPE_CHECKING:
    from datacloud_platform.platform import DatacloudPlatform


def create_app(platform: DatacloudPlatform) -> FastAPI:
    """Create a fully assembled FastAPI application from a DatacloudPlatform instance.

    Args:
        platform: A fully configured DatacloudPlatform instance.

    Returns:
        FastAPI app with all route groups mounted.
    """
    app = FastAPI(title="DataCloud Platform", version="0.1.0")

    app.include_router(create_ontology_routes(platform))
    app.include_router(create_resource_routes(platform))
    app.include_router(create_search_routes(platform))
    app.include_router(create_import_routes(platform))

    return app
