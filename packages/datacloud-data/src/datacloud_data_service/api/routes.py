"""
FastAPI 应用工厂模块

本模块提供 FastAPI 应用的创建和配置功能，包括：
- 应用生命周期管理
- 路由注册
- 性能日志记录
- MCP 服务集成

使用示例：
    app = create_app()
    # 或带自定义配置
    app = create_app(datasource_configs={...})
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections import defaultdict
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")
load_dotenv(Path(__file__).resolve().parents[3] / ".env")

from fastapi import FastAPI

logger = logging.getLogger(__name__)

HEALTH_CHECK_TIMEOUT = 3.0


def _configure_package_logger(logger_name: str) -> None:
    """为项目包 logger 配置稳定的控制台输出。"""
    package_logger = logging.getLogger(logger_name)
    package_logger.setLevel(logging.INFO)
    package_logger.propagate = False
    if package_logger.handlers:
        return

    handler = logging.StreamHandler()
    handler.setLevel(logging.INFO)
    handler.setFormatter(logging.Formatter("%(levelname)s:%(name)s:%(message)s"))
    package_logger.addHandler(handler)


def _make_performance_log_handler() -> tuple[Any, dict[str, list]]:
    """
    创建性能日志处理器

    生成 on_span_complete 回调函数，用于记录查询性能指标。

    Returns:
        tuple: (回调函数, 按请求 ID 分组的 span 字典)
    """
    spans_by_request: dict[str, list] = defaultdict(list)

    def on_span(span: Any) -> None:
        """
        Span 完成回调

        当查询流程完成时，汇总并记录性能日志。

        Args:
            span: 性能 span 对象
        """
        rid = getattr(span, "request_id", "") or ""
        if not rid:
            return
        spans_by_request[rid].append(span)
        if getattr(span, "event_in", "") in ("AggregationCompleted", "PlanValidationFailed"):
            stages = [
                {
                    "module": getattr(s, "module", ""),
                    "event_in": getattr(s, "event_in", ""),
                    "duration_ms": getattr(s, "duration_ms", 0),
                    "input": getattr(s, "input_summary", None) or {},
                    "output": getattr(s, "output_summary", None) or {},
                }
                for s in spans_by_request[rid]
            ]
            total_ms = sum(getattr(s, "duration_ms", 0) for s in spans_by_request[rid])
            try:
                log_line = json.dumps(
                    {
                        "event": "query_performance",
                        "request_id": rid,
                        "trace_id": getattr(span, "trace_id", ""),
                        "stages": stages,
                        "total_ms": round(total_ms, 2),
                    },
                    ensure_ascii=False,
                )
                logger.info(log_line)
                logging.getLogger().warning(log_line)
            except Exception:
                pass
            del spans_by_request[rid]

    return on_span, spans_by_request


def create_app(
    *,
    datasource_configs: dict | None = None,
    loader_override: Any | None = None,
) -> FastAPI:
    """
    创建 FastAPI 应用实例

    工厂函数，创建并配置完整的 FastAPI 应用。

    Args:
        datasource_configs: 数据源配置（可选，用于测试覆盖）
        loader_override: 本体加载器实例（可选，用于测试）

    Returns:
        FastAPI: 配置完成的 FastAPI 应用实例
    """
    from datacloud_data_service.api.mcp_sdk_handler import (
        create_mcp_asgi_app,
        create_mcp_session_manager,
    )

    _mcp_session_manager = create_mcp_session_manager()
    _mcp_asgi_app = create_mcp_asgi_app(_mcp_session_manager)

    _configure_package_logger("datacloud_data_service")
    _configure_package_logger("datacloud_data_sdk")

    @asynccontextmanager
    async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
        from datacloud_data_service.config import get_settings
        from datacloud_data_service.loader_runtime import LoaderRuntimeManager

        settings = get_settings()
        runtime = LoaderRuntimeManager(
            settings=settings,
            datasource_configs=datasource_configs,
            loader_override=loader_override,
            performance_handler_factory=_make_performance_log_handler,
            on_publish=lambda snapshot: _sync_app_loader(app, snapshot),
        )
        await runtime.start()
        loader = runtime.current_loader
        app.state.loader_runtime = runtime
        app.state.loader = loader
        app.state.event_bus = getattr(getattr(loader, "_config", None), "event_bus", None)
        logger.info("OntologyLoader runtime initialized and stored in app.state")

        from datacloud_data_service.api.mcp_sdk_handler import (
            set_loader_ref,
            set_loader_runtime_ref,
        )

        set_loader_runtime_ref(lambda: getattr(app.state, "loader_runtime", None))
        set_loader_ref(lambda: getattr(app.state, "loader", None))
        async with _mcp_session_manager.run():
            try:
                yield
            finally:
                await runtime.stop()

    app = FastAPI(title="DataCloud Data Service", version="0.1.0", lifespan=_lifespan)

    from fastapi.middleware.cors import CORSMiddleware

    from datacloud_data_service.config import get_settings

    settings_for_cors = get_settings()
    cors_val = settings_for_cors.cors_origins.strip()
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

    async def _health_handler() -> dict:
        result: dict = {"status": "ok"}
        loader = getattr(app.state, "loader", None)
        if loader is None:
            return result
        configs = getattr(loader._config, "datasource_configs", None)
        if configs is None:
            configs = {}
        if not configs:
            return result
        from datacloud_data_sdk.sql_executor.data_source_manager import DataSourceManager

        manager = DataSourceManager(configs)
        datasources_status: dict[str, str] = {}
        for alias in configs:
            try:
                connector = manager.get_connector(alias)
                await asyncio.wait_for(connector.test_connection(), timeout=HEALTH_CHECK_TIMEOUT)
                datasources_status[alias] = "ok"
            except TimeoutError:
                datasources_status[alias] = "timeout"
            except Exception:
                datasources_status[alias] = "error"
        await manager.close_all()
        result["datasources"] = datasources_status
        return result

    @app.get("/health")
    async def health() -> dict:
        return await _health_handler()

    @app.get("/api/v1/health")
    async def health_v1() -> dict:
        return await _health_handler()

    @app.get("/api/v1/loader/status")
    async def loader_status() -> dict:
        runtime = getattr(app.state, "loader_runtime", None)
        if runtime is None:
            return {"initialized": getattr(app.state, "loader", None) is not None}
        return runtime.status()

    app.mount("/api/v1/mcp", _mcp_asgi_app)

    from datacloud_data_service.api.query import router as query_router

    app.include_router(query_router, prefix="/api/v1")

    from datacloud_data_service.api.download import router as download_router

    app.include_router(download_router, prefix="/api/v1")

    from datacloud_data_service.api.skills import router as skills_router

    app.include_router(skills_router, prefix="/api/v1/skills")

    # GraphQL 端点：从 crm_demo_graphql 加载独立 loader（与主 loader 分离）
    graphql_registry = (
        Path(__file__).resolve().parents[3]
        / "resources"
        / "ontology"
        / "crm_demo_graphql"
        / "objects_registry.json"
    )
    if graphql_registry.exists():
        from datacloud_data_sdk.ontology.loader import OntologyLoader
        from datacloud_data_sdk.sql_executor.data_source_manager import DataSourceManager

        graphql_loader = OntologyLoader()
        graphql_loader.load_from_path(graphql_registry)
        ds_manager = DataSourceManager(graphql_loader._config.datasource_configs)
        from datacloud_data_sdk.graphql.server import get_graphql_router

        graphql_router = get_graphql_router(graphql_loader, ds_manager)
        app.include_router(graphql_router, prefix="/graphql")
        logger.info("GraphQL endpoint mounted at /graphql from %s", graphql_registry)
    else:
        logger.warning(
            "GraphQL ontology not found at %s, GraphQL endpoint disabled", graphql_registry
        )

    return app


def _sync_app_loader(app: FastAPI, snapshot: Any) -> None:
    app.state.loader = snapshot.loader
    app.state.event_bus = getattr(getattr(snapshot.loader, "_config", None), "event_bus", None)
