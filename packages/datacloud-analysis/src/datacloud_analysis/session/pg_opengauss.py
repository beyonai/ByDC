"""OpenGauss-compatible LangGraph checkpointer (framework-level, reusable).

Why this module exists
----------------------
``langgraph-checkpoint-postgres`` uses two PostgreSQL-specific constructs that
OpenGauss rejects at runtime:

1. **SELECT** — ``array_agg(array[col::bytea, col::bytea, blob])`` creates a
   ``bytea[][]`` (2-D bytea array).  OpenGauss raises
   ``UndefinedObject: could not find range type for data type bytea[]`` on
   every read, including the core ``get_tuple`` path.

2. **INSERT** — ``ON CONFLICT … DO NOTHING / DO UPDATE`` is not recognised
   by OpenGauss (``SyntaxError: syntax error at or near "CONFLICT"``).

``OpenGaussSaver`` is a mixin that overrides the four methods that use those
constructs (``get_tuple``, ``list``, ``put``, ``put_writes``) with plain SQL
that OpenGauss accepts.  It is combined with ``PostgresSaver`` at runtime via
``_make_opengauss_saver()``.

Windows ProactorEventLoop
-------------------------
``psycopg`` async I/O uses ``add_reader``/``add_writer`` which Windows'
default ``ProactorEventLoop`` does NOT support.  ``SyncPGCheckpointer`` wraps
the synchronous ``PostgresSaver`` (i.e. ``_OGSaver``) and delegates every
async call via ``loop.run_in_executor()``, making it event-loop-agnostic.

Checkpoint I/O uses a **sync** ``psycopg_pool.ConnectionPool``: LangGraph's
``PostgresSaver._cursor`` checks out a connection per operation via
``get_connection()``, so idle or dropped server sessions do not strand the whole
process on one dead ``Connection`` (contrast: a single long-lived connection).
The pool is created with ``check=ConnectionPool.check_connection`` so each
checkout validates the connection; broken sessions are discarded and replaced
per psycopg-pool's getconn loop (mitigates stale connections, not DB-wide outage).

Usage
-----
Reference from ``langgraph.json``::

    "checkpointer": {
        "backend": "custom",
        "path": "./checkpointer.py:get_checkpointer"
    }

The app-level ``checkpointer.py`` only needs::

    from datacloud_analysis.session.pg_opengauss import get_checkpointer
    __all__ = ["get_checkpointer"]
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, suppress
from typing import Any

from langgraph.checkpoint.base import BaseCheckpointSaver

from datacloud_analysis.config.db_url import (
    build_postgres_connection_uri,
    resolve_checkpoint_schema,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# OpenGaussSaver — mixin that replaces all incompatible SQL
# ---------------------------------------------------------------------------


def _normalize_db_text(value: Any) -> str:
    if isinstance(value, memoryview):
        value = bytes(value)
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return str(value)


def _normalize_db_blob(value: Any) -> bytes | None:
    if value is None:
        return None
    if isinstance(value, memoryview):
        return bytes(value)
    if isinstance(value, bytearray):
        return bytes(value)
    return value


class OpenGaussSaver:
    """Mixin that replaces every incompatible SQL statement for OpenGauss.

    Combined with ``PostgresSaver`` via ``_make_opengauss_saver()`` to produce
    a fully working checkpointer.  The parent class still handles serde,
    ``_dump_blobs``, ``_dump_writes``, ``_load_blobs``, ``_load_writes``,
    ``_load_checkpoint_tuple``, and all non-SQL logic.
    """

    # ── Simple checkpoint SELECT (no array_agg on bytea) ──────────────────
    _SEL_CHK = (
        "SELECT thread_id, checkpoint, checkpoint_ns, checkpoint_id, "
        "parent_checkpoint_id, metadata FROM checkpoints "
    )

    # ── INSERT SQLs (no ON CONFLICT) ───────────────────────────────────────
    _INS_BLOB = (
        "INSERT INTO checkpoint_blobs "
        "(thread_id, checkpoint_ns, channel, version, type, blob) "
        "VALUES (%s, %s, %s, %s, %s, %s)"
    )
    _INS_CHK = (
        "INSERT INTO checkpoints "
        "(thread_id, checkpoint_ns, checkpoint_id, parent_checkpoint_id, "
        "checkpoint, metadata) "
        "VALUES (%s, %s, %s, %s, %s, %s)"
    )
    _UPD_CHK = (
        "UPDATE checkpoints SET checkpoint=%s, metadata=%s "
        "WHERE thread_id=%s AND checkpoint_ns=%s AND checkpoint_id=%s"
    )
    _INS_WRITE = (
        "INSERT INTO checkpoint_writes "
        "(thread_id, checkpoint_ns, checkpoint_id, task_id, task_path, "
        "idx, channel, type, blob) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)"
    )
    _DEL_WRITE = (
        "DELETE FROM checkpoint_writes "
        "WHERE thread_id=%s AND checkpoint_ns=%s AND checkpoint_id=%s "
        "AND task_id=%s AND idx=%s"
    )

    # ── SELECT helpers ─────────────────────────────────────────────────────

    def _fetch_blobs(
        self, cur: Any, thread_id: str, checkpoint_ns: str, channel_versions: dict
    ) -> list | None:
        """Fetch channel blobs per-thread; filter by channel_versions in Python.

        Avoids ``array_agg(array[bytea, bytea, bytea])`` which triggers the
        OpenGauss range-type error.
        """
        if not channel_versions:
            return None
        expected_versions = {
            _normalize_db_text(channel): _normalize_db_text(version)
            for channel, version in channel_versions.items()
        }
        cur.execute(
            "SELECT channel, type, blob, version "
            "FROM checkpoint_blobs WHERE thread_id=%s AND checkpoint_ns=%s",
            (thread_id, checkpoint_ns),
        )
        result = []
        matched_channels: set[str] = set()
        for row in cur.fetchall():
            channel = _normalize_db_text(row["channel"])
            version = _normalize_db_text(row["version"])
            expected_version = expected_versions.get(channel)
            if expected_version != version:
                continue
            matched_channels.add(channel)
            result.append(
                (
                    channel.encode(),
                    _normalize_db_text(row["type"]).encode(),
                    _normalize_db_blob(row["blob"]),
                )
            )
        missing_channels = sorted(set(expected_versions) - matched_channels)
        if missing_channels:
            logger.warning(
                "OpenGaussSaver._fetch_blobs: missing blob rows for thread_id=%s checkpoint_ns=%s "
                "channels=%s",
                thread_id,
                checkpoint_ns,
                missing_channels[:20],
            )
        return result or None

    def _fetch_writes(
        self, cur: Any, thread_id: str, checkpoint_ns: str, checkpoint_id: str
    ) -> list | None:
        """Fetch pending writes for a checkpoint without array_agg."""
        cur.execute(
            "SELECT task_id, channel, type, blob "
            "FROM checkpoint_writes "
            "WHERE thread_id=%s AND checkpoint_ns=%s AND checkpoint_id=%s "
            "ORDER BY task_id, idx",
            (thread_id, checkpoint_ns, checkpoint_id),
        )
        rows = cur.fetchall()
        if not rows:
            return None
        return [
            (
                _normalize_db_text(r["task_id"]).encode(),
                _normalize_db_text(r["channel"]).encode(),
                _normalize_db_text(r["type"]).encode(),
                _normalize_db_blob(r["blob"]),
            )
            for r in rows
        ]

    def _assemble_row(self, cur: Any, row: Any) -> dict:
        """Attach channel_values and pending_writes to a checkpoint dict row."""
        value: dict = dict(row)
        channel_versions = value["checkpoint"].get("channel_versions", {})
        value["channel_values"] = self._fetch_blobs(
            cur, value["thread_id"], value["checkpoint_ns"], channel_versions
        )
        value["pending_writes"] = self._fetch_writes(
            cur, value["thread_id"], value["checkpoint_ns"], value["checkpoint_id"]
        )
        return value

    # ── get_tuple override ─────────────────────────────────────────────────

    def get_tuple(self, config: Any) -> Any:
        """OpenGauss-compatible get_tuple using separate queries."""
        from langgraph.checkpoint.base import get_checkpoint_id  # noqa: PLC0415

        thread_id = config["configurable"]["thread_id"]
        checkpoint_id = get_checkpoint_id(config)
        checkpoint_ns = config["configurable"].get("checkpoint_ns", "")

        if checkpoint_id:
            where = (
                "WHERE thread_id=%s AND checkpoint_ns=%s AND checkpoint_id=%s"
            )
            args: tuple = (thread_id, checkpoint_ns, checkpoint_id)
        else:
            where = (
                "WHERE thread_id=%s AND checkpoint_ns=%s "
                "ORDER BY checkpoint_id DESC LIMIT 1"
            )
            args = (thread_id, checkpoint_ns)

        with self._cursor() as cur:  # type: ignore[attr-defined]
            cur.execute(self._SEL_CHK + where, args)
            row = cur.fetchone()
            if row is None:
                return None
            return self._load_checkpoint_tuple(  # type: ignore[attr-defined]
                self._assemble_row(cur, row)
            )

    # ── list override ──────────────────────────────────────────────────────

    def list(  # type: ignore[override]
        self,
        config: Any,
        *,
        filter: Any = None,
        before: Any = None,
        limit: Any = None,
    ) -> Iterator[Any]:
        """OpenGauss-compatible list using separate queries."""
        where, args = self._search_where(config, filter, before)  # type: ignore[attr-defined]
        query = self._SEL_CHK + where + " ORDER BY checkpoint_id DESC"
        params: list = list(args)
        if limit is not None:
            query += " LIMIT %s"
            params.append(int(limit))

        with self._cursor() as cur:  # type: ignore[attr-defined]
            cur.execute(query, params)
            rows = cur.fetchall()
            if not rows:
                return
            for row in rows:
                yield self._load_checkpoint_tuple(  # type: ignore[attr-defined]
                    self._assemble_row(cur, row)
                )

    # ── put override (replaces ON CONFLICT DO UPDATE) ──────────────────────

    def put(self, config: Any, checkpoint: Any, metadata: Any, new_versions: Any) -> Any:
        """OpenGauss-compatible put — no ON CONFLICT."""
        from langgraph.checkpoint.base import (  # noqa: PLC0415
            get_serializable_checkpoint_metadata,
        )
        from psycopg import errors as pge  # noqa: PLC0415
        from psycopg.types.json import Jsonb  # noqa: PLC0415

        configurable = config["configurable"].copy()
        thread_id = configurable.pop("thread_id")
        checkpoint_ns = configurable.pop("checkpoint_ns")
        checkpoint_id = configurable.pop("checkpoint_id", None)
        copy = checkpoint.copy()
        copy["channel_values"] = copy["channel_values"].copy()

        next_config = {
            "configurable": {
                "thread_id": thread_id,
                "checkpoint_ns": checkpoint_ns,
                "checkpoint_id": checkpoint["id"],
            }
        }

        blob_values: dict = {}
        for k, v in checkpoint["channel_values"].items():
            if not (v is None or isinstance(v, (str, int, float, bool))):
                blob_values[k] = copy["channel_values"].pop(k)

        chk_data = Jsonb(copy)
        meta_data = Jsonb(get_serializable_checkpoint_metadata(config, metadata))

        with self._cursor() as cur:  # type: ignore[attr-defined]
            # blobs: INSERT, ignore duplicate (simulate ON CONFLICT DO NOTHING)
            if blob_versions := {
                k: v for k, v in new_versions.items() if k in blob_values
            }:
                for blob_row in self._dump_blobs(  # type: ignore[attr-defined]
                    thread_id, checkpoint_ns, blob_values, blob_versions
                ):
                    with suppress(pge.UniqueViolation):
                        cur.execute(self._INS_BLOB, blob_row)

            # checkpoint: INSERT; UPDATE on conflict (simulate ON CONFLICT DO UPDATE)
            try:
                cur.execute(
                    self._INS_CHK,
                    (
                        thread_id,
                        checkpoint_ns,
                        checkpoint["id"],
                        checkpoint_id,
                        chk_data,
                        meta_data,
                    ),
                )
            except pge.UniqueViolation:
                cur.execute(
                    self._UPD_CHK,
                    (chk_data, meta_data, thread_id, checkpoint_ns, checkpoint["id"]),
                )

        return next_config

    # ── put_writes override (replaces ON CONFLICT DO UPDATE / DO NOTHING) ──

    def put_writes(
        self, config: Any, writes: Any, task_id: str, task_path: str = ""
    ) -> None:
        """OpenGauss-compatible put_writes — no ON CONFLICT."""
        from langgraph.checkpoint.base import WRITES_IDX_MAP  # noqa: PLC0415
        from psycopg import errors as pge  # noqa: PLC0415

        thread_id = config["configurable"]["thread_id"]
        checkpoint_ns = config["configurable"]["checkpoint_ns"]
        checkpoint_id = config["configurable"]["checkpoint_id"]
        is_upsert = all(w[0] in WRITES_IDX_MAP for w in writes)

        rows = self._dump_writes(  # type: ignore[attr-defined]
            thread_id, checkpoint_ns, checkpoint_id, task_id, task_path, writes
        )

        with self._cursor() as cur:  # type: ignore[attr-defined]
            for row in rows:
                th, ns, chk_id, t_id, _t_path, idx = (
                    row[0], row[1], row[2], row[3], row[4], row[5]
                )
                if is_upsert:
                    # Simulate ON CONFLICT DO UPDATE: delete + re-insert
                    cur.execute(self._DEL_WRITE, (th, ns, chk_id, t_id, idx))
                    cur.execute(self._INS_WRITE, row)
                else:
                    # Simulate ON CONFLICT DO NOTHING
                    with suppress(pge.UniqueViolation):
                        cur.execute(self._INS_WRITE, row)


# ---------------------------------------------------------------------------
# Factory helpers
# ---------------------------------------------------------------------------

def make_opengauss_saver(conn: Any) -> Any:
    """Create an OpenGauss-compatible PostgresSaver instance.

    ``conn`` may be a psycopg ``Connection`` or a sync ``ConnectionPool``; the
    parent ``PostgresSaver`` checks out a connection per operation when given
    a pool.

    The returned object can be wrapped with ``SyncPGCheckpointer`` for use
    in environments where async psycopg is unavailable (e.g. Windows).
    """
    from langgraph.checkpoint.postgres import PostgresSaver  # noqa: PLC0415

    class _OGSaver(OpenGaussSaver, PostgresSaver):
        """OpenGauss-compatible saver: custom SQL overrides + standard serde."""

    return _OGSaver(conn=conn)


class SyncPGCheckpointer(BaseCheckpointSaver):
    """Async adapter wrapping a synchronous OpenGaussSaver.

    Every async method delegates via ``loop.run_in_executor()``, keeping the
    event loop unblocked regardless of loop type.  This makes it safe on
    Windows where ``ProactorEventLoop`` is the default and psycopg's async I/O
    (which requires ``add_reader``/``add_writer``) would fail.
    """

    def __init__(self, inner: Any) -> None:
        import inspect  # noqa: PLC0415

        super().__init__(serde=getattr(inner, "serde", None))
        self._inner = inner
        self._has_task_path = "task_path" in inspect.signature(inner.put_writes).parameters

    # ── async interface ────────────────────────────────────────────────────

    async def aget_tuple(self, config: Any) -> Any | None:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._inner.get_tuple, config)

    async def aget(self, config: Any) -> Any | None:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._inner.get, config)

    async def aput(
        self,
        config: Any,
        checkpoint: Any,
        metadata: Any,
        new_versions: Any,
    ) -> Any:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None, self._inner.put, config, checkpoint, metadata, new_versions
        )

    async def aput_writes(
        self,
        config: Any,
        writes: Any,
        task_id: str,
        task_path: str = "",
    ) -> None:
        loop = asyncio.get_running_loop()
        if self._has_task_path:
            await loop.run_in_executor(
                None, self._inner.put_writes, config, writes, task_id, task_path
            )
        else:
            await loop.run_in_executor(
                None, self._inner.put_writes, config, writes, task_id
            )

    async def alist(  # type: ignore[override]
        self,
        config: Any,
        *,
        filter: Any = None,
        before: Any = None,
        limit: Any = None,
    ) -> AsyncIterator[Any]:
        loop = asyncio.get_running_loop()
        items = await loop.run_in_executor(
            None,
            lambda: list(
                self._inner.list(config, filter=filter, before=before, limit=limit)
            ),
        )
        for item in items:
            yield item

    # ── sync interface ─────────────────────────────────────────────────────

    def get_tuple(self, config: Any) -> Any | None:
        return self._inner.get_tuple(config)

    def get(self, config: Any) -> Any | None:
        return self._inner.get(config)

    def put(self, config: Any, checkpoint: Any, metadata: Any, new_versions: Any) -> Any:
        return self._inner.put(config, checkpoint, metadata, new_versions)

    def put_writes(self, config: Any, writes: Any, task_id: str, task_path: str = "") -> None:
        if self._has_task_path:
            return self._inner.put_writes(config, writes, task_id, task_path)
        return self._inner.put_writes(config, writes, task_id)

    def list(self, config: Any, *, filter: Any = None, before: Any = None, limit: Any = None):
        yield from self._inner.list(config, filter=filter, before=before, limit=limit)


# ---------------------------------------------------------------------------
# DDL helpers
# ---------------------------------------------------------------------------

def ensure_tables_opengauss(conn: Any, schema: str) -> None:
    """Create checkpoint tables using OpenGauss-compatible DDL (sync conn).

    This mirrors the upstream checkpoint schema while avoiding PostgreSQL-only
    migration syntax such as ``ADD COLUMN IF NOT EXISTS``.
    """
    latest_migration = _get_latest_checkpoint_migration()
    ddl = [
        "CREATE TABLE IF NOT EXISTS checkpoint_migrations (v INTEGER PRIMARY KEY)",
        """
        CREATE TABLE IF NOT EXISTS checkpoints (
            thread_id            TEXT  NOT NULL,
            checkpoint_ns        TEXT  NOT NULL DEFAULT '',
            checkpoint_id        TEXT  NOT NULL,
            parent_checkpoint_id TEXT,
            type                 TEXT,
            checkpoint           JSONB NOT NULL,
            metadata             JSONB NOT NULL DEFAULT '{}',
            PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS checkpoint_blobs (
            thread_id     TEXT  NOT NULL,
            checkpoint_ns TEXT  NOT NULL DEFAULT '',
            channel       TEXT  NOT NULL,
            version       TEXT  NOT NULL,
            type          TEXT  NOT NULL,
            blob          BYTEA,
            PRIMARY KEY (thread_id, checkpoint_ns, channel, version)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS checkpoint_writes (
            thread_id     TEXT    NOT NULL,
            checkpoint_ns TEXT    NOT NULL DEFAULT '',
            checkpoint_id TEXT    NOT NULL,
            task_id       TEXT    NOT NULL,
            idx           INTEGER NOT NULL,
            channel       TEXT    NOT NULL,
            type          TEXT,
            blob          BYTEA   NOT NULL,
            task_path     TEXT    NOT NULL DEFAULT '',
            PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id, task_id, idx)
        )
        """,
        "ALTER TABLE checkpoint_blobs ALTER COLUMN blob DROP NOT NULL",
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_schema = current_schema()
                  AND table_name = 'checkpoint_writes'
                  AND column_name = 'task_path'
            ) THEN
                ALTER TABLE checkpoint_writes
                ADD COLUMN task_path TEXT NOT NULL DEFAULT '';
            END IF;
        END $$;
        """,
        "CREATE INDEX IF NOT EXISTS chk_thread    ON checkpoints(thread_id)",
        "CREATE INDEX IF NOT EXISTS blobs_thread  ON checkpoint_blobs(thread_id)",
        "CREATE INDEX IF NOT EXISTS writes_thread ON checkpoint_writes(thread_id)",
    ]

    with conn.cursor() as cur:
        for stmt in ddl:
            cur.execute(stmt)
        cur.execute(
            """
            INSERT INTO checkpoint_migrations(v)
            SELECT %s WHERE NOT EXISTS (
                SELECT 1 FROM checkpoint_migrations WHERE v = %s
            )
            """,
            (latest_migration, latest_migration),
        )

    logger.info("OpenGauss checkpoint tables ensured (schema=%s).", schema or "public")


def _get_latest_checkpoint_migration() -> int:
    """Return the upstream migration version bundled with PostgresSaver."""
    from langgraph.checkpoint.postgres import PostgresSaver  # noqa: PLC0415

    migrations = getattr(PostgresSaver, "MIGRATIONS", ())
    if not migrations:
        logger.warning(
            "PostgresSaver.MIGRATIONS is unavailable; falling back to checkpoint migration v9."
        )
        return 9
    return len(migrations) - 1


# ---------------------------------------------------------------------------
# langgraph dev factory (asynccontextmanager)
# ---------------------------------------------------------------------------

def _ensure_tables_from_pool(pool: Any, schema: str) -> None:
    """Run OpenGauss DDL fallback using one checkout from the checkpoint pool."""

    with pool.connection() as conn:
        ensure_tables_opengauss(conn, schema)


@asynccontextmanager
async def get_checkpointer(
    checkpoint_uri: str = "",
    checkpoint_schema: str | None = None,
) -> AsyncIterator[SyncPGCheckpointer]:
    """Async context manager yielding an OpenGauss-compatible checkpointer.

    The underlying ``PostgresSaver`` is backed by a **sync**
    ``psycopg_pool.ConnectionPool``.  Each read/write checks out a connection
    for the duration of that operation (LangGraph ``_cursor`` / ``get_connection``),
    which avoids a single long-lived ``Connection`` dying with
    ``the connection is closed`` / ``AdminShutdown`` with no recovery.
    Checkout uses ``ConnectionPool.check_connection`` so idle-killed TCP sessions
    are detected before the real checkpoint SQL runs when possible.

    Designed to be referenced from ``langgraph.json``::

        "checkpointer": {
            "backend": "custom",
            "path": "./checkpointer.py:get_checkpointer"
        }

    The app-level ``checkpointer.py`` should simply re-export this function::

        from datacloud_analysis.session.pg_opengauss import get_checkpointer
        __all__ = ["get_checkpointer"]

    Keep the context manager entered for the process lifetime (as ``bootstrap``
    does); on ``__aexit__`` the pool is closed.

    Parameters
    ----------
    checkpoint_uri:
        psycopg-format connection string. Falls back to a DSN built from
        ``DATACLOUD_DB_URL`` / ``DATACLOUD_DB_USER`` / ``DATACLOUD_DB_PASSWORD``
        when not provided (e.g. when called directly from ``langgraph.json``).
    checkpoint_schema:
        Schema to use for checkpoint tables. Falls back to the schema inferred
        from ``DATACLOUD_DB_URL`` when ``None`` (not provided).
        Pass ``""`` to explicitly use the default ``public`` schema without
        reading the environment variable.
    """
    from psycopg import Connection, sql  # noqa: PLC0415
    from psycopg.rows import dict_row  # noqa: PLC0415
    from psycopg_pool import ConnectionPool  # noqa: PLC0415

    # Fall back to unified DB env vars only when called without explicit args.
    if not checkpoint_uri:
        checkpoint_uri = build_postgres_connection_uri()
    if checkpoint_schema is None:
        checkpoint_schema = resolve_checkpoint_schema("")

    if not checkpoint_uri:
        raise RuntimeError(
            "DATACLOUD_DB_URL is not set. "
            "Set DATACLOUD_DB_URL / DATACLOUD_DB_USER / DATACLOUD_DB_PASSWORD in .env "
            "or remove the checkpointer from langgraph.json "
            "to fall back to in-memory storage."
        )

    logger.info(
        "Opening OpenGauss checkpoint pool (sync, schema=%s)…",
        checkpoint_schema or "public",
    )

    if checkpoint_schema:
        with Connection.connect(checkpoint_uri, autocommit=True) as admin:
            ident = sql.Identifier(checkpoint_schema)
            admin.execute(sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(ident))

    connect_kwargs: dict[str, Any] = {
        "autocommit": True,
        "prepare_threshold": 0,
        "row_factory": dict_row,
    }
    if checkpoint_schema:
        connect_kwargs["options"] = f"-c search_path={checkpoint_schema},public"

    pool: Any = None
    try:
        pool = ConnectionPool(
            checkpoint_uri,
            kwargs=connect_kwargs,
            min_size=1,
            max_size=20,
            open=True,
            name="datacloud-checkpoint",
            check=ConnectionPool.check_connection,
        )

        saver = make_opengauss_saver(pool)
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, _ensure_tables_from_pool, pool, checkpoint_schema)
        logger.info("Checkpoint tables ready (OpenGauss-compatible setup).")

        wrapped = SyncPGCheckpointer(saver)
        logger.info(
            "PG checkpointer ready (pool + OpenGaussSaver + SyncPGCheckpointer) — "
            "conversations will persist to OpenGauss."
        )
        yield wrapped

    finally:
        if pool is not None:
            try:
                pool.close()
            except Exception:
                logger.exception("Failed to close checkpoint ConnectionPool.")
            else:
                logger.debug("Checkpoint ConnectionPool closed.")


__all__ = [
    "OpenGaussSaver",
    "SyncPGCheckpointer",
    "make_opengauss_saver",
    "ensure_tables_opengauss",
    "get_checkpointer",
]
