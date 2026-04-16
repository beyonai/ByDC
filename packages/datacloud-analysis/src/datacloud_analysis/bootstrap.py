"""SDK bootstrap helpers.

This module centralizes one-time startup and shutdown concerns:
1. Validate environment settings.
2. Initialize and register the LangGraph checkpointer.
3. Initialize the optional datacloud-memory store.
4. Expose a lazily created shared async PostgreSQL pool.
"""

from __future__ import annotations

import asyncio
import logging
import sys
from typing import Any

from psycopg_pool import AsyncConnectionPool

logger = logging.getLogger(__name__)

_initialized: bool = False
_init_lock: asyncio.Lock | None = None
_pg_checkpoint_cm: Any = None
_pg_pool: AsyncConnectionPool[Any] | None = None


async def setup() -> None:
    """Initialize SDK resources once per process."""
    global _initialized, _init_lock, _pg_checkpoint_cm

    if _init_lock is None:
        _init_lock = asyncio.Lock()

    async with _init_lock:
        if _initialized:
            logger.debug("datacloud-analysis already initialized, skipping.")
            return

        from datacloud_analysis.config.env import Settings  # noqa: PLC0415
        from datacloud_analysis.session.checkpointer import set_checkpointer  # noqa: PLC0415
        from datacloud_analysis.session.pg_opengauss import (  # noqa: PLC0415
            get_checkpointer as og_get_checkpointer,
        )

        settings = Settings()
        logger.info("datacloud-analysis: environment variables validated.")

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

        try:
            from datacloud_memory.store import init_store  # noqa: PLC0415
        except ImportError:
            logger.warning("datacloud-memory not installed or init_store not available, skipping.")
        else:
            await init_store(settings.pg.checkpoint_uri)
            logger.info("datacloud-analysis: datacloud-memory store initialized.")

        _initialized = True
        logger.info("datacloud-analysis: initialization complete.")


def get_pg_pool() -> AsyncConnectionPool[Any]:
    """Return a shared async PostgreSQL pool bound to the checkpoint URI.

    The pool is created lazily and cached process-wide.
    """
    global _pg_pool

    if _pg_pool is not None:
        return _pg_pool

    from datacloud_analysis.config.env import Settings  # noqa: PLC0415

    settings = Settings()
    _pg_pool = AsyncConnectionPool(
        conninfo=settings.pg.checkpoint_uri,
        min_size=1,
        max_size=10,
        open=False,
    )
    logger.info("datacloud-analysis: shared async PG pool created.")
    return _pg_pool


async def teardown() -> None:
    """Tear down SDK resources on process shutdown."""
    global _initialized, _pg_checkpoint_cm, _pg_pool

    from datacloud_analysis.session.checkpointer import reset_checkpointer  # noqa: PLC0415

    if _pg_pool is not None:
        try:
            await _pg_pool.close()
        finally:
            _pg_pool = None
        logger.info("datacloud-analysis: shared async PG pool closed.")

    if _pg_checkpoint_cm is not None:
        try:
            await _pg_checkpoint_cm.__aexit__(None, None, None)
        finally:
            _pg_checkpoint_cm = None
            reset_checkpointer()
        logger.info("datacloud-analysis: checkpointer context exited.")

    _initialized = False
