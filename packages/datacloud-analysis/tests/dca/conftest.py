"""Pytest fixtures for datacloud-analysis tests.

Shared fixtures
---------------
initialized_sdk     Session-scoped: call bootstrap.setup() once for the whole
                    test session (integration tests only).  Requires real env vars.
"""

from __future__ import annotations

import asyncio
import sys
import uuid
from pathlib import Path

import pytest


def _ensure_backend_demo_import_path() -> None:
    repo_root = Path(__file__).resolve().parents[4]
    backend_root = repo_root / "examples" / "e_commerce_demo" / "backend"
    backend_root_str = str(backend_root)
    if backend_root.exists() and backend_root_str not in sys.path:
        sys.path.insert(0, backend_root_str)


_ensure_backend_demo_import_path()


@pytest.fixture(autouse=True)
def _ensure_event_loop_for_sync_tests() -> None:
    """确保每个同步测试执行时存在可用的 event loop。

    Python 3.12+ 中 asyncio.get_event_loop() 在没有 running loop 时会抛
    RuntimeError（3.13 尤其明显）。pytest-asyncio AUTO 模式在每个 async 测试
    结束后会关闭 loop，导致后续同步测试用 asyncio.get_event_loop() 时失败。

    本 fixture 在每个同步测试前检查并恢复 event loop，使旧式写法
    `asyncio.get_event_loop().run_until_complete(...)` 可以正常工作。
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop is None or loop.is_closed():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)


@pytest.fixture
def temp_tenant_id() -> str:
    """Generate a temporary tenant ID for test isolation."""
    return f"test-tenant-{uuid.uuid4().hex[:8]}"


@pytest.fixture(scope="session")
async def initialized_sdk() -> None:
    """Bootstrap the SDK once for the entire test session.

    Only for integration tests that require a live PostgreSQL database.
    Requires the following env vars to be set:
        DATACLOUD_DB_HOST / DATACLOUD_DB_DATABASE / DATACLOUD_DB_USER /
        DATACLOUD_DB_PASSWORD
    """
    import datacloud_analysis.bootstrap as boot  # noqa: PLC0415

    await boot.setup()
    yield
    await boot.teardown()
