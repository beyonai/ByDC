"""SDK-level initialization (design §四).

This module is the **single entry point** for all one-time startup work:

1. Load & validate every environment variable (fail-fast via Pydantic).
2. Open the shared async PostgreSQL connection pool.
3. Create LangGraph checkpoint tables (``AsyncPostgresSaver.setup()``).
4. Initialize the datacloud-memory Store tables.

Callers (Worker processes, FastAPI lifespan, etc.) should call::

    await bootstrap.setup()

*once* at process startup.  Subsequent calls are silently ignored.

Thread / concurrency safety
---------------------------
``asyncio.Lock`` ensures that if multiple coroutines race to call ``setup()``
at startup only the first one executes; the rest wait and then exit because
``_initialized`` is already ``True``.

Re-entrancy guard layers
------------------------
Layer 1 – Logic:  ``_initialized`` bool  (fast path, zero overhead)
Layer 2 – Async:  ``asyncio.Lock``        (concurrency-safe during startup)
Layer 3 – DB:     ``CREATE TABLE IF NOT EXISTS`` inside LangGraph setup()
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from psycopg_pool import AsyncConnectionPool

logger = logging.getLogger(__name__)

_initialized: bool = False
_init_lock: asyncio.Lock | None = None
_pg_pool: "AsyncConnectionPool | None" = None


async def setup() -> None:
    """Initialize the SDK.  Safe to call multiple times; only runs once.

    Raises
    ------
    pydantic.ValidationError
        If any required environment variable is missing.
    psycopg.OperationalError
        If the PostgreSQL server is unreachable.
    """
    global _initialized, _init_lock, _pg_pool

    # Lazy-create the lock inside the running event loop.
    if _init_lock is None:
        _init_lock = asyncio.Lock()

    async with _init_lock:
        if _initialized:
            logger.debug("datacloud-analysis already initialized – skipping.")
            return

        logger.info("datacloud-analysis: starting SDK initialization …")

        # 1. Load & validate all env vars (raises ValidationError on misconfiguration).
        from datacloud_analysis.config.env import Settings  # noqa: PLC0415

        settings = Settings()
        logger.info("datacloud-analysis: environment variables validated.")

        # 2. Open shared async PG connection pool.
        from psycopg_pool import AsyncConnectionPool  # noqa: PLC0415

        _pg_pool = AsyncConnectionPool(
            settings.pg.checkpoint_uri,
            open=False,
            kwargs={"options": f"-c search_path={settings.pg.checkpoint_schema}"},
        )
        await _pg_pool.open()
        logger.info("datacloud-analysis: PG connection pool opened.")

        # 3. Create LangGraph checkpoint tables (idempotent – IF NOT EXISTS).
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver  # noqa: PLC0415

        async with AsyncPostgresSaver.from_conn_string(settings.pg.checkpoint_uri) as saver:
            await saver.setup()
        logger.info("datacloud-analysis: LangGraph checkpoint tables ready.")

        # 4. Initialize datacloud-memory Store (also idempotent).
        try:
            from datacloud_memory.store import init_store  # noqa: PLC0415

            await init_store(settings.pg.checkpoint_uri)
            logger.info("datacloud-analysis: datacloud-memory store initialized.")
        except ImportError:
            logger.warning(
                "datacloud-memory not installed or init_store not available – skipping."
            )

        _initialized = True
        logger.info("datacloud-analysis: initialization complete.")


def get_pg_pool() -> "AsyncConnectionPool":
    """Return the initialized PG connection pool.

    Raises
    ------
    RuntimeError
        If ``setup()`` has not been called yet.
    """
    if not _initialized or _pg_pool is None:
        raise RuntimeError(
            "datacloud-analysis is not initialized. "
            "Call `await bootstrap.setup()` at process startup before using the SDK."
        )
    return _pg_pool


async def teardown() -> None:
    """Close the PG pool gracefully (call on process shutdown)."""
    global _initialized, _pg_pool

    if _pg_pool is not None:
        await _pg_pool.close()
        logger.info("datacloud-analysis: PG connection pool closed.")
    _initialized = False
    _pg_pool = None
