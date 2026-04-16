"""Integration test: bootstrap.setup() creates PG checkpoint tables.

Requires a running PostgreSQL instance.  Set the env var:
    DATACLOUD_DB_URL=jdbc:postgresql://...

Run selectively:
    pytest tests/integration/test_bootstrap_pg.py -v -m integration
"""

from __future__ import annotations

import pytest
from datacloud_analysis.config.db_url import build_postgres_connection_uri

_PG_CHECKPOINT_URI = build_postgres_connection_uri()

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not _PG_CHECKPOINT_URI,
        reason="DATACLOUD_DB_URL is required for integration bootstrap tests",
    ),
]


@pytest.mark.asyncio
async def test_setup_creates_tables(initialized_sdk: None) -> None:
    """After bootstrap.setup(), the checkpoint tables must exist."""
    import psycopg  # noqa: PLC0415

    uri = build_postgres_connection_uri()
    async with await psycopg.AsyncConnection.connect(uri) as conn, conn.cursor() as cur:
        await cur.execute("SELECT tablename FROM pg_tables WHERE tablename = 'checkpoints'")
        row = await cur.fetchone()
    assert row is not None, "Table 'checkpoints' should have been created by setup()."


@pytest.mark.asyncio
async def test_setup_is_idempotent(monkeypatch: pytest.MonkeyPatch) -> None:
    """Calling bootstrap.setup() a second time must be a no-op (no errors)."""
    import datacloud_analysis.bootstrap as boot  # noqa: PLC0415

    # Reset so we can call setup() again in this test.
    original = boot._initialized  # noqa: SLF001
    try:
        await boot.setup()  # second call
        assert boot._initialized is True  # noqa: SLF001
    finally:
        boot._initialized = original  # noqa: SLF001
