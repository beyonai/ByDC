"""反向代理服务器 — 把前端和 DeepAgent API 合并到同一端口（8765）。

- /app/* → 本地前端静态文件
- 其他所有请求 → 转发到 DeepAgent API（localhost:2024）

用法：
    python proxy.py
"""
from __future__ import annotations

import json
from pathlib import Path

import httpx
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import HTMLResponse, Response, StreamingResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

_FRONTEND_DIR = Path(__file__).parent / "frontend_dist"
_API_URL = "http://127.0.0.1:2026"
_INDEX_TEMPLATE = (_FRONTEND_DIR / "index.html").read_text(encoding="utf-8")

_client = httpx.AsyncClient(base_url=_API_URL, timeout=300.0)


async def serve_index(_request: Request) -> HTMLResponse:
    """注入 auth 和 API 地址后返回 index.html。"""
    config = json.dumps({
        "auth": "anonymous",
        "appName": "DataCloud BI",
        "assistantId": "agent",
    })
    html = _INDEX_TEMPLATE.replace(
        'window.__DEEPAGENTS_CONFIG__ = {"__PLACEHOLDER__":true};',
        f"window.__DEEPAGENTS_CONFIG__ = {config};",
    )
    return HTMLResponse(html)


async def proxy(request: Request) -> Response:
    """把所有非 /app 请求转发到 DeepAgent API。"""
    url = httpx.URL(
        path=request.url.path,
        query=request.url.query.encode("utf-8"),
    )
    body = await request.body()
    headers = dict(request.headers)
    headers.pop("host", None)

    rp_req = _client.build_request(
        method=request.method,
        url=url,
        headers=headers,
        content=body,
    )
    rp_resp = await _client.send(rp_req, stream=True)

    return StreamingResponse(
        rp_resp.aiter_raw(),
        status_code=rp_resp.status_code,
        headers=dict(rp_resp.headers),
        background=None,
    )


app = Starlette(
    routes=[
        Route("/app", lambda r: __import__("starlette.responses", fromlist=["RedirectResponse"]).RedirectResponse("/app/", status_code=308)),
        Route("/app/", serve_index),
        Mount("/app", app=StaticFiles(directory=str(_FRONTEND_DIR)), name="frontend"),
        Route("/{path:path}", proxy, methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"]),
    ],
)
