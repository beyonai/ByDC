"""Pytest fixtures for datacloud-analysis tests.

Shared fixtures
---------------
initialized_sdk     Session-scoped: call bootstrap.setup() once for the whole
                    test session (integration tests only).  Requires real env vars.
"""

from __future__ import annotations

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


@pytest.fixture
def temp_tenant_id() -> str:
    """Generate a temporary tenant ID for test isolation."""
    return f"test-tenant-{uuid.uuid4().hex[:8]}"


@pytest.fixture(scope="session")
async def initialized_sdk() -> None:
    """Bootstrap the SDK once for the entire test session.

    Only for integration tests that require a live PostgreSQL database.
    Requires the following env vars to be set:
        DATACLOUD_DB_URL
    """
    import datacloud_analysis.bootstrap as boot  # noqa: PLC0415

    await boot.setup()
    yield
    await boot.teardown()
