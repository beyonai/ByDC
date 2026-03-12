"""Integration-test fixtures for tests/datacloud-agent/integration/.

These fixtures may create real DB connections.  They require the following
environment variables to be set before running:

    DATACLOUD_PG_CHECKPOINT_URI      psycopg-format connection string
    DATACLOUD_WORKSPACE_PUBLIC_ROOT  path to public workspace root
    DATACLOUD_WORKSPACE_PRIVATE_ROOT path to private workspace root

Run integration tests with::

    uv run pytest tests/datacloud-agent/integration -m integration
"""

from __future__ import annotations

import pytest


@pytest.fixture(scope="session")
async def initialized_sdk():
    """Bootstrap the SDK once for the entire integration-test session.

    Calls ``bootstrap.setup()`` / ``bootstrap.teardown()`` around the session.
    Requires a live PostgreSQL / OpenGauss database.
    """
    import datacloud_agent.bootstrap as boot  # noqa: PLC0415

    await boot.setup()
    yield
    await boot.teardown()
