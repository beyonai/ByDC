"""集成测试 fixtures — 真实 OpenGauss 环境。

加载 byclaw-data/.env，调用 bootstrap.setup()，提供真实 checkpointer。
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest


def _load_byclaw_env() -> None:
    """从 byclaw-data/.env 加载真实 OpenGauss 连接配置。"""
    env_path = Path(__file__).resolve().parents[6] / "byclaw-all" / "byclaw-data" / ".env"
    if not env_path.exists():
        return
    from dotenv import load_dotenv  # noqa: PLC0415

    load_dotenv(env_path, override=False)


_load_byclaw_env()


def _has_db_env() -> bool:
    return all(
        os.getenv(k, "").strip()
        for k in ("DATACLOUD_DB_HOST", "DATACLOUD_DB_DATABASE", "DATACLOUD_DB_USER")
    )


# ── 集成测试 fixtures ──────────────────────────────────────────────────────────


@pytest.fixture(scope="session")
async def og_checkpointer(initialized_sdk: None):  # type: ignore[no-untyped-def]
    """Session 级 OpenGauss checkpointer（依赖 initialized_sdk 完成 setup）。"""
    from datacloud_analysis.session.checkpointer import get_checkpointer  # noqa: PLC0415

    return get_checkpointer()


skipif_no_db = pytest.mark.skipif(
    not _has_db_env(),
    reason=(
        "OpenGauss env vars not set. "
        "需要 byclaw-data/.env 或 DATACLOUD_DB_HOST/DATABASE/USER 手动设置"
    ),
)
