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
        from datacloud_data_sdk.ontology.loader import OntologyLoader

        settings = get_settings()
        if loader_override is not None:
            loader = loader_override
            logger.info("Using loader_override for OntologyLoader")
        else:
            loader = OntologyLoader()
            ontology_path = Path(settings.ontology_path)
            if ontology_path.exists():
                loader.load_from_owl_directory(ontology_path)
                logger.info("Loaded ontology from %s", ontology_path)

            # scene_path = Path(settings.scene_path)
            # if scene_path.exists():
            #     loader.load_scene_from_path(scene_path)
            #     logger.info("Loaded scene from %s", scene_path)

        from datacloud_data_service.tools.virtual_action_injector import (
            inject_virtual_actions,
        )

        inject_virtual_actions(loader)
        logger.info("Injected virtual actions for DB/KB objects")

        if settings.llm_api_key:
            try:
                from datacloud_data_sdk.plan.query_plan_generator import LangGraphPlanGenerator

                plan_gen = LangGraphPlanGenerator(
                    model=settings.llm_model,
                    base_url=settings.llm_base_url,
                    api_key=settings.llm_api_key,
                    temperature=settings.llm_temperature,
                    max_retries=settings.max_plan_retries,
                )
                loader.configure(plan_generator=plan_gen)
                logger.info("Configured LangGraphPlanGenerator with model=%s", settings.llm_model)
            except ImportError as e:
                logger.warning(
                    "langchain-openai not installed, LLM plan generation disabled: %s",
                    e,
                    exc_info=True,
                )
        else:
            logger.warning("DC_LLM_API_KEY not set, LLM plan generation disabled")

        # configs = datasource_configs if datasource_configs is not None else _build_datasource_configs(settings)
        # if configs:
        #     loader.configure(datasource_configs=configs)

        from datacloud_data_sdk.events.bus import EventBus
        from datacloud_data_sdk.events.handlers import register_query_handlers
        from datacloud_data_sdk.events.trace_logger import EventTraceLogger
        from datacloud_data_sdk.events.tracing import TracingMiddleware

        bus = EventBus()
        tracing = TracingMiddleware(bus)
        perf_handler, _ = _make_performance_log_handler()
        tracing.on_span_complete(perf_handler)
        register_query_handlers(bus, tracing=tracing)
        if settings.trace_enabled:
            trace_logger = EventTraceLogger(
                trace_log_path=settings.trace_log_path,
                enabled=True,
            )
            trace_logger.register(bus)
        loader.configure(event_bus=bus)

        app.state.event_bus = bus  # 供测试在替换 loader 时注入 event_bus

        loader.configure(csv_base_dir=settings.csv_base_dir)
        loader.configure(sql_execution_mode=settings.sql_execution_mode)
        loader.configure(
            query_result_csv_threshold=settings.query_result_csv_threshold,
            query_result_preview_rows=settings.query_result_preview_rows,
        )

        from datacloud_data_sdk.ontology.term_loader import TermLoader

        term_loader = TermLoader.from_config({})
        loader.configure(term_loader=term_loader)
        logger.info("Configured TermLoader")

        app.state.loader = loader
        logger.info("OntologyLoader initialized and stored in app.state")

        from datacloud_data_service.api.mcp_sdk_handler import set_loader_ref

        set_loader_ref(lambda: app.state.loader)
        async with _mcp_session_manager.run():
            yield

    app = FastAPI(title="DataCloud Data Service", version="0.1.0", lifespan=_lifespan)

    from datacloud_data_service.config import get_settings
    from fastapi.middleware.cors import CORSMiddleware

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
            except asyncio.TimeoutError:
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
