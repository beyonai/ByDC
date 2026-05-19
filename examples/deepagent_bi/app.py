"""本地前端服务 — 把 deepagents 内置前端挂载到 /app/，注入 API 地址。

用法：
    uvicorn app:app --port 3000
"""
from __future__ import annotations

import json
from pathlib import Path

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

_FRONTEND_DIR = Path(__file__).parent / "frontend_dist"
_API_URL = "http://127.0.0.1:2024"

_INDEX_TEMPLATE = (_FRONTEND_DIR / "index.html").read_text(encoding="utf-8")


async def healthz(_request: Request) -> JSONResponse:
    return JSONResponse({"ok": True})


async def app_root_redirect(_request: Request) -> RedirectResponse:
    return RedirectResponse(url="/app/", status_code=308)


async def serve_index(_request: Request) -> HTMLResponse:
    """注入 API 地址后返回 index.html。"""
    config = json.dumps({"apiUrl": _API_URL, "baseUrl": _API_URL})
    html = _INDEX_TEMPLATE.replace(
        'window.__DEEPAGENTS_CONFIG__ = {"__PLACEHOLDER__":true};',
        f"window.__DEEPAGENTS_CONFIG__ = {config};",
    )
    return HTMLResponse(html)


app = Starlette(
    routes=[
        Route("/healthz", healthz),
        Route("/app", app_root_redirect),
        Route("/app/", serve_index),
        Mount(
            "/app",
            app=StaticFiles(directory=str(_FRONTEND_DIR)),
            name="frontend",
        ),
    ],
)
