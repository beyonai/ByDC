"""FastAPI application factory for datacloud-platform.

Usage::

    from datacloud_platform import DatacloudPlatform, OntologyBaseRegistry
    from datacloud_platform.api import create_app

    registry = OntologyBaseRegistry()
    platform = DatacloudPlatform(_base_registry=registry)
    app = create_app(platform)
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from datacloud_platform.api.deps import set_platform
from datacloud_platform.api.mcp_handler import (
    create_mcp_asgi_app,
    create_mcp_session_manager,
    set_loader_runtime_ref,
)
from datacloud_platform.api.routers.download_routes import router as download_router
from datacloud_platform.api.routers.import_routes import create_import_routes
from datacloud_platform.api.routers.ontology_build_routes import (
    router as ont_build_router,
)
from datacloud_platform.api.routers.ontology_routes import create_ontology_routes
from datacloud_platform.api.routers.query_routes import router as query_router
from datacloud_platform.api.routers.resource_routes import create_resource_routes
from datacloud_platform.api.routers.search_routes import create_search_routes
from datacloud_platform.api.routers.skills_routes import router as skills_router
from datacloud_platform.api.routers.terms_routes import router as terms_router
from datacloud_platform.config import get_settings

if TYPE_CHECKING:
    from datacloud_platform.platform import DatacloudPlatform

logger = logging.getLogger(__name__)


def create_app(
    platform: DatacloudPlatform,
    *,
    datasource_configs: dict[str, Any] | None = None,
    loader_override: Any | None = None,
) -> FastAPI:
    """Create a fully assembled FastAPI application from a DatacloudPlatform instance.

    Args:
        platform: A fully configured DatacloudPlatform instance.
        datasource_configs: Optional datasource config overrides.
        loader_override: Optional loader override for testing.

    Returns:
        FastAPI app with all route groups, MCP endpoint, and health checks mounted.
    """
    from datacloud_platform.loader_runtime import LoaderRuntimeManager

    settings = get_settings()

    # ── MCP ─────────────────────────────────────────────────────────────────
    session_manager = create_mcp_session_manager()
    mcp_asgi = create_mcp_asgi_app(session_manager)

    # ── Lifespan ────────────────────────────────────────────────────────────
    @asynccontextmanager
    async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
        runtime = LoaderRuntimeManager(platform=platform, settings=settings)
        app.state.loader_runtime = runtime
        set_loader_runtime_ref(lambda: runtime)
        logger.info("LoaderRuntimeManager initialized and stored in app.state")
        try:
            yield
        finally:
            logger.info("LoaderRuntimeManager shutdown")

    # ── App ─────────────────────────────────────────────────────────────────
    app = FastAPI(title="DataCloud Platform", version="0.1.0", lifespan=_lifespan)

    # ── CORS ────────────────────────────────────────────────────────────────
    cors_val = settings.cors_origins.strip()
    if cors_val:
        if cors_val == "*":
            app.add_middleware(
                CORSMiddleware,
                allow_origins=["*"],
                allow_credentials=False,
                allow_methods=["GET", "POST", "OPTIONS"],
                allow_headers=["*"],
            )
        else:
            origins = [o.strip() for o in cors_val.split(",") if o.strip()]
            if origins:
                app.add_middleware(
                    CORSMiddleware,
                    allow_origins=origins,
                    allow_credentials=True,
                    allow_methods=["GET", "POST", "OPTIONS"],
                    allow_headers=["*"],
                )

    # ── Platform instance ───────────────────────────────────────────────────
    set_platform(platform)

    # ── Factory routes (require platform instance) ──────────────────────────
    app.include_router(create_ontology_routes(platform))
    app.include_router(create_resource_routes(platform))
    app.include_router(create_search_routes(platform))
    app.include_router(create_import_routes(platform))

    # ── Simple routes (no platform dependency) ──────────────────────────────
    app.include_router(query_router, prefix="/api/v1")
    app.include_router(download_router, prefix="/api/v1")
    app.include_router(terms_router, prefix="/api/v1")
    app.include_router(skills_router, prefix="/api/v1/skills")
    app.include_router(ont_build_router, prefix="/api/v1/ontology-manager")

    # ── MCP mount ───────────────────────────────────────────────────────────
    app.mount("/api/v1/mcp", mcp_asgi)

    # ── Health ──────────────────────────────────────────────────────────────
    @app.get("/health")
    async def health() -> dict[str, Any]:
        runtime = getattr(app.state, "loader_runtime", None)
        if runtime is None:
            return {"status": "ok", "loaded_bases": []}
        status = runtime.status()
        return {"status": "ok", "loaded_bases": status.get("cached_bases", [])}

    @app.get("/api/v1/health")
    async def health_v1() -> dict[str, Any]:
        return await health()

    # ── Loader status ───────────────────────────────────────────────────────
    @app.get("/api/v1/loader/status")
    async def loader_status() -> dict[str, Any]:
        runtime = getattr(app.state, "loader_runtime", None)
        if runtime is None:
            return {"initialized": False}
        return runtime.status()  # type: ignore[no-any-return]

    # ── GraphQL (conditional on registry file existence) ────────────────────
    graphql_registry = (
        Path(__file__).resolve().parents[3]
        / "resources"
        / "ontology"
        / "crm_demo_graphql"
        / "objects_registry.json"
    )
    if graphql_registry.exists():
        from datacloud_data_sdk.graphql.server import get_graphql_router
        from datacloud_data_sdk.ontology.loader import OntologyLoader
        from datacloud_data_sdk.sql_executor.data_source_manager import (
            DataSourceManager,
        )

        graphql_loader = OntologyLoader()
        graphql_loader.load_from_path(graphql_registry)
        ds_manager = DataSourceManager(graphql_loader._config.datasource_configs)
        graphql_router = get_graphql_router(graphql_loader, ds_manager)
        app.include_router(graphql_router, prefix="/graphql")
        logger.info("GraphQL endpoint mounted at /graphql from %s", graphql_registry)
    else:
        logger.info(
            "GraphQL ontology not found at %s, GraphQL endpoint disabled",
            graphql_registry,
        )

    return app
