"""DataCloud Mock 服务总入口：创建 FastAPI 应用并挂载各子系统路由。"""

from pathlib import Path

# 最先加载 .env，确保 DATACLOUD_DB_URL 等配置在 connection 模块导入前生效
_env_path = Path(__file__).resolve().parent.parent.parent / ".env"
if _env_path.exists():
    from dotenv import load_dotenv
    load_dotenv(_env_path)

# OpenGauss 兼容：必须在导入任何 db/connection 之前执行，否则 SQLAlchemy 解析版本会报错
from sqlalchemy.dialects.postgresql.base import PGDialect
_orig = PGDialect._get_server_version_info
def _opengauss_version(self, conn):
    try:
        return _orig(self, conn)
    except AssertionError:
        return (12, 0)
PGDialect._get_server_version_info = _opengauss_version

import json
import logging
import sys
import traceback

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from sales_analysis_demo import __version__

logger = logging.getLogger(__name__)

# 确保异常日志输出到控制台
if not logger.handlers:
    _h = logging.StreamHandler(sys.stderr)
    _h.setLevel(logging.ERROR)
    _h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logger.addHandler(_h)

# 最外层 ASGI 中间件：在 Starlette ServerErrorMiddleware 之前捕获异常并输出错误栈
class _ExceptionLoggingASGIMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        method = scope.get("method", "")

        async def _send(message):
            await send(message)

        try:
            await self.app(scope, receive, send)
        except Exception as exc:
            tb_lines = traceback.format_exception(type(exc), exc, exc.__traceback__)
            tb = "".join(tb_lines)
            msg = f"\n[sales-analysis-demo] 错误栈 {method} {path}:\n{tb}"
            logger.error("Unhandled exception on %s %s:\n%s", method, path, tb)
            print(msg, file=sys.stderr, flush=True)
            # 同时写入文件，确保可追溯（debugpy/uvicorn 可能吞掉 stderr）
            try:
                from pathlib import Path
                _err_log = Path(__file__).parent.parent.parent / "error.log"  # sales-analysis-demo/error.log
                with open(_err_log, "a", encoding="utf-8") as f:
                    f.write(msg + "\n")
            except Exception:
                pass
            body = json.dumps(
                {"detail": str(exc), "type": type(exc).__name__, "traceback": tb},
                ensure_ascii=False,
            ).encode()
            await send({
                "type": "http.response.start",
                "status": 500,
                "headers": [[b"content-type", b"application/json; charset=utf-8"]],
            })
            await send({"type": "http.response.body", "body": body})


app = FastAPI(
    title="sales-analysis-demo",
    description="DataCloud 2.0 数据仿真系统",
    version=__version__,
)


@app.exception_handler(Exception)
async def _global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """全局异常处理：返回 JSON 格式错误详情，便于排查 500 问题."""
    tb_lines = traceback.format_exception(type(exc), exc, exc.__traceback__)
    tb = "".join(tb_lines)
    logger.error("Unhandled exception on %s %s:\n%s", request.method, request.url.path, tb)
    print(f"\n[sales-analysis-demo] 错误栈 {request.method} {request.url.path}:\n{tb}", file=sys.stderr, flush=True)
    try:
        from pathlib import Path
        _err_log = Path(__file__).parent.parent.parent / "error.log"
        with open(_err_log, "a", encoding="utf-8") as f:
            f.write(f"\n[sales-analysis-demo] {request.method} {request.url.path}:\n{tb}\n")
    except Exception:
        pass
    return JSONResponse(
        status_code=500,
        content={
            "detail": str(exc),
            "type": type(exc).__name__,
            "traceback": tb,
        },
    )


# HTTP 中间件：在 ServerErrorMiddleware 之前捕获异常，返回 JSON 便于排查
@app.middleware("http")
async def _catch_exceptions_middleware(request: Request, call_next):
    try:
        return await call_next(request)
    except Exception as exc:
        tb_lines = traceback.format_exception(type(exc), exc, exc.__traceback__)
        tb = "".join(tb_lines)
        logger.error("Unhandled exception on %s %s:\n%s", request.method, request.url.path, tb)
        print(f"\n[sales-analysis-demo] 错误栈 {request.method} {request.url.path}:\n{tb}", file=sys.stderr, flush=True)
        try:
            _err_log = Path(__file__).resolve().parent.parent.parent / "error.log"
            with open(_err_log, "a", encoding="utf-8") as f:
                f.write(f"\n[sales-analysis-demo] {request.method} {request.url.path}:\n{tb}\n")
        except Exception:
            pass
        return JSONResponse(
            status_code=500,
            content={
                "detail": str(exc),
                "type": type(exc).__name__,
                "traceback": tb,
            },
        )


# 必须最先添加，作为最外层包裹整个 app
app.add_middleware(_ExceptionLoggingASGIMiddleware)


@app.get("/")
def root() -> dict:
    """健康与版本检查."""
    return {"service": "sales-analysis-demo", "version": __version__}


@app.get("/health")
def health() -> dict:
    """健康检查."""
    return {"status": "ok"}


@app.get("/_debug/raise")
def _debug_raise() -> None:
    """调试用：主动抛错，验证错误栈是否输出。"""
    raise RuntimeError("测试错误栈输出")


@app.get("/api/routes")
def list_api_routes() -> dict:
    """列出已注册的 API 路由（调试用）."""
    openapi = app.openapi()
    paths = openapi.get("paths", {})
    api_routes = [
        {"path": p, "methods": [m.upper() for m in meta.keys() if m != "parameters"]}
        for p, meta in sorted(paths.items())
        if p.startswith("/api") or p in ("/", "/health")
    ]
    return {"routes": api_routes, "count": len(api_routes)}


def _mount_subsystems() -> None:
    """挂载各子系统路由（按需取消注释或新增）。"""
    try:
        from sales_analysis_demo.apis import router as crm_router
        # 与 ontology objects_registry 一致：/api/v1/po/users/by-org 等
        app.include_router(crm_router, prefix="/api/v1", tags=["crm_demo"])
        # 兼容旧路径：/api/v1/crm_demo/po/users/by-org 等
        app.include_router(crm_router, prefix="/api/v1/crm_demo", tags=["crm_demo"])
    except ImportError:
        pass  # 子系统未实现时忽略


_mount_subsystems()
