"""API layer — FastAPI factory routers.

Usage::

    from datacloud_platform.api import create_app

    # Option A: full app (includes all route groups)
    app = create_app(platform)
"""

from __future__ import annotations

from datacloud_platform.api.routers.import_routes import create_import_routes
from datacloud_platform.api.routers.resource_routes import create_resource_routes
from datacloud_platform.api.routers.search_routes import create_search_routes
from datacloud_platform.api.server import create_app

__all__ = [
    "create_app",
    "create_import_routes",
    "create_resource_routes",
    "create_search_routes",
]
