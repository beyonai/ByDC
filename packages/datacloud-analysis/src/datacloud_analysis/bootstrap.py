"""SDK-level initialization (design §四).

This module is the **single entry point** for all one-time startup work:

1. Load & validate every environment variable (fail-fast via Pydantic).
2. Create LangGraph checkpoint tables via OpenGauss-compatible checkpointer.
3. Initialize the datacloud-memory Store tables.

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
import sys
from typing import Any

logger = logging.getLogger(__name__)

_initialized: bool = False
_init_lock: asyncio.Lock | None = None
# Keeps ``pg_opengauss.get_checkpointer()`` context alive for process lifetime.
_pg_checkpoint_cm: Any = None


async def setup() -> None:
    """Initialize the SDK.  Safe to call multiple times; only runs once.

    Raises
    ------
    pydantic.ValidationError
        If any required environment variable is missing.
    psycopg.OperationalError
        If the PostgreSQL server is unreachable.
    """
    global _initialized, _init_lock, _pg_checkpoint_cm

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

        # 2. OpenGauss-compatible LangGraph checkpointer: create tables and register
        #    a process-wide instance so ``create_agent(..., checkpointer=get_checkpointer())`` works.
        from datacloud_analysis.session.checkpointer import set_checkpointer  # noqa: PLC0415
        from datacloud_analysis.session.pg_opengauss import get_checkpointer as og_get_checkpointer  # noqa: PLC0415

        _pg_checkpoint_cm = og_get_checkpointer(
            checkpoint_uri=settings.pg.checkpoint_uri,
            checkpoint_schema=settings.pg.checkpoint_schema,
        )
        try:
            saver = await _pg_checkpoint_cm.__aenter__()
            set_checkpointer(saver)
        except BaseException:
            await _pg_checkpoint_cm.__aexit__(*sys.exc_info())
            _pg_checkpoint_cm = None
            raise
        logger.info(
            "datacloud-analysis: LangGraph checkpoint tables ready; checkpointer registered."
        )

        # 3. Initialize datacloud-memory Store (also idempotent).
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


def get_pg_pool() -> None:
    """Return an async PG connection pool.

    NOTE: Not currently used internally.  Reserved for future consumers
    (e.g. datacloud-memory) that need a shared async pool.  The pool is
    not created by ``setup()`` — callers must create their own pool or
    wait until this API is wired up.

    Raises
    ------
    NotImplementedError
        Always, until a pool is wired up.
    """
    raise NotImplementedError(
        "get_pg_pool() is not yet wired up. "
        "Create an AsyncConnectionPool directly or wait for datacloud-memory integration."
    )


async def teardown() -> None:
    """Close the PG pool gracefully (call on process shutdown)."""
    global _initialized, _pg_checkpoint_cm

    from datacloud_analysis.session.checkpointer import reset_checkpointer  # noqa: PLC0415

    if _pg_checkpoint_cm is not None:
        try:
            await _pg_checkpoint_cm.__aexit__(None, None, None)
        finally:
            _pg_checkpoint_cm = None
            reset_checkpointer()
        logger.info("datacloud-analysis: checkpointer context exited.")

    _initialized = False
