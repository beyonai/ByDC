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
    create_ontology_build_routes,
)
from datacloud_platform.api.routers.workspace_routes import create_workspace_routes
from datacloud_platform.api.routers.ontology_routes import create_ontology_routes
from datacloud_platform.api.routers.query_routes import router as query_router
from datacloud_platform.api.routers.resource_routes import create_resource_routes
from datacloud_platform.api.routers.search_routes import create_search_routes
from datacloud_platform.api.routers.skills_routes import router as skills_router
from datacloud_platform.api.routers.term_routes import create_term_routes
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
    app = FastAPI(
        title="DataCloud Platform",
        version="0.1.0",
        lifespan=_lifespan,
        openapi_tags=[
            {
                "name": "OntologyBase",
                "description": "本体库管理 — 创建、查询、更新、删除本体库",
            },
            {
                "name": "Scene",
                "description": "场景管理 — 场景 CRUD、成员管理、本体分页查询",
            },
            {"name": "Object", "description": "对象类型管理 — 对象 CRUD 与详情查询"},
            {"name": "Relation", "description": "关系管理 — 对象间关系 CRUD"},
            {"name": "View", "description": "视图管理 — 视图 CRUD 与详情查询"},
            {
                "name": "Datasource",
                "description": "数据源管理 — 数据源 CRUD 与详情查询",
            },
            {"name": "Action", "description": "动作管理 — 对象动作 CRUD"},
            {"name": "Instance", "description": "实例查询 — 实例数据条件检索"},
            {"name": "Graph", "description": "图查询 — N 跳图查询与最短路径"},
            {"name": "Search", "description": "本体检索 — 跨场景/场景内全文与语义检索"},
            {
                "name": "Term",
                "description": "术语库管理 — 术语/术语类型/术语库/领域/关系/名称/知识 CRUD",
            },
            {"name": "Import", "description": "本体导入 — OWL 文件导入"},
            {
                "name": "Query",
                "description": "自然语言查询 — AI 驱动的自然语言数据查询",
            },
            {"name": "Download", "description": "文件下载 — 查询结果 CSV 导出下载"},
            {"name": "Terms", "description": "术语选项 — 前端表单术语下拉选项"},
            {"name": "Skills", "description": "技能包 — AI 技能包 JSON 生成"},
            {
                "name": "Ontology Manager",
                "description": "本体管理器 — 个人本体构建与术语管理",
            },
            {"name": "System", "description": "系统接口 — 健康检查与加载状态"},
        ],
    )

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
    app.include_router(create_term_routes(platform))

    # ── Simple routes (no platform dependency) ──────────────────────────────
    app.include_router(query_router, prefix="/api/v1")
    app.include_router(download_router, prefix="/api/v1")
    app.include_router(terms_router, prefix="/api/v1")
    app.include_router(skills_router, prefix="/api/v1/skills")

    # ── Factory route (needs platform, now using factory pattern) ───────────
    app.include_router(create_ontology_build_routes(platform))
    app.include_router(create_workspace_routes(platform))

    # ── MCP mount ───────────────────────────────────────────────────────────
    app.mount("/api/v1/mcp", mcp_asgi)

    # ── Health ──────────────────────────────────────────────────────────────
    @app.get("/health", tags=["System"])
    async def health() -> dict[str, Any]:
        runtime = getattr(app.state, "loader_runtime", None)
        if runtime is None:
            return {"status": "ok", "loaded_bases": []}
        status = runtime.status()
        return {"status": "ok", "loaded_bases": status.get("cached_bases", [])}

    @app.get("/api/v1/health", tags=["System"])
    async def health_v1() -> dict[str, Any]:
        return await health()

    # ── Loader status ───────────────────────────────────────────────────────
    @app.get("/api/v1/loader/status", tags=["System"])
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
