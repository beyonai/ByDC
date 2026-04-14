"""亦庄产业大脑 Mock 服务入口。

提供知识导入回调通知接口。
"""

from __future__ import annotations

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

from datetime import datetime
from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel

from e_commerce_demo import __version__

app = FastAPI(
    title="e_commerce_demo",
    description="亦庄产业大脑 Mock 服务",
    version=__version__,
)

# 内存存储最新通知（单例）
_latest_notify: dict[str, Any] = {}


class NotifyPayload(BaseModel):
    """知识导入通知载荷。"""

    status: str
    folder_path: str | None = None
    stats: dict[str, dict[str, int]] | None = None
    precheck_errors: list[dict[str, Any]] | None = None


@app.get("/")
def root() -> dict:
    """健康与版本检查。"""
    return {"service": "e_commerce_demo", "version": __version__}


@app.get("/health")
def health() -> dict:
    """健康检查。"""
    return {"status": "ok"}


@app.post("/api/v1/knowledge/ingest/notify")
def post_notify(payload: NotifyPayload) -> dict:
    """接收知识导入通知。"""
    global _latest_notify
    _latest_notify = {
        "status": payload.status,
        "folder_path": payload.folder_path,
        "stats": payload.stats,
        "precheck_errors": payload.precheck_errors,
        "received_at": datetime.now().isoformat(),
    }
    return {"ack": True, "status": payload.status}


@app.get("/api/v1/knowledge/ingest/notify/latest")
def get_latest_notify() -> dict:
    """获取最新通知。"""
    return _latest_notify.copy() if _latest_notify else {}


@app.delete("/api/v1/knowledge/ingest/notify/latest")
def clear_latest_notify() -> dict:
    """清除最新通知。"""
    global _latest_notify
    _latest_notify = {}
    return {"ack": True}
