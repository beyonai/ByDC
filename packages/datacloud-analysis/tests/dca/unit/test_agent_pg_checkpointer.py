"""Unit tests for agent graph compilation and PG checkpointer helpers."""

from __future__ import annotations

import asyncio
import sys
import types

import pytest


def test_create_agent_raises_when_checkpointer_uninitialized() -> None:
    """``create_agent()`` should fail-fast when checkpointer is not initialized."""
    from datacloud_analysis.agent import create_agent

    with pytest.raises(RuntimeError, match="Checkpointer is required"):
        create_agent()


def test_get_checkpointer_raises_when_uri_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    """pg_opengauss.get_checkpointer() should raise RuntimeError if URI is unset."""
    from datacloud_analysis.session.pg_opengauss import get_checkpointer

    monkeypatch.delenv("DATACLOUD_DB_HOST", raising=False)
    monkeypatch.delenv("DATACLOUD_DB_PORT", raising=False)
    monkeypatch.delenv("DATACLOUD_DB_DATABASE", raising=False)
    monkeypatch.delenv("DATACLOUD_DB_SCHEMA", raising=False)
    monkeypatch.delenv("DATACLOUD_DB_USER", raising=False)
    monkeypatch.delenv("DATACLOUD_DB_PASSWORD", raising=False)

    async def _run() -> None:
        async with get_checkpointer():
            pass

    with pytest.raises(RuntimeError, match="DATACLOUD_DB_HOST|DATACLOUD_DB_DATABASE"):
        asyncio.run(_run())


def test_ensure_tables_opengauss_uses_compatible_task_path_migration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """兼容迁移不应依赖 OpenGauss 不支持的 ADD COLUMN IF NOT EXISTS。"""
    from datacloud_analysis.session import pg_opengauss

    monkeypatch.setattr(pg_opengauss, "_get_latest_checkpoint_migration", lambda: 12)

    statements: list[tuple[str, object | None]] = []

    class _FakeCursor:
        def __enter__(self) -> _FakeCursor:
            return self

        def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
            _ = exc_type, exc, tb

        def execute(self, stmt: str, params: object | None = None) -> None:
            statements.append((stmt, params))

    class _FakeConn:
        def cursor(self) -> _FakeCursor:
            return _FakeCursor()

    pg_opengauss.ensure_tables_opengauss(_FakeConn(), "whale_datacloud")

    sql_text = "\n".join(stmt for stmt, _ in statements)
    assert "ADD COLUMN IF NOT EXISTS" not in sql_text
    assert "table_name = 'checkpoint_writes'" in sql_text
    assert "column_name = 'task_path'" in sql_text
    assert "DO $$" in sql_text
    assert any(params == (12, 12) for _, params in statements)


@pytest.mark.asyncio
async def test_get_checkpointer_uses_compatible_setup_without_saver_setup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """OpenGauss 初始化应直接走兼容 DDL，而不是先触发上游迁移语法错误。"""
    from datacloud_analysis.session import pg_opengauss

    ensure_calls: list[tuple[object, str]] = []
    pool_instances: list[object] = []

    class _FakeSaver:
        serde = None

        def setup(self) -> None:
            raise AssertionError("saver.setup() should not be called")

        def get_tuple(self, config: object) -> None:
            _ = config
            return None

        def get(self, config: object) -> None:
            _ = config
            return None

        def put(
            self,
            config: object,
            checkpoint: object,
            metadata: object,
            new_versions: object,
        ) -> object:
            _ = config, checkpoint, metadata, new_versions
            return {}

        def put_writes(
            self,
            config: object,
            writes: object,
            task_id: str,
            task_path: str = "",
        ) -> None:
            _ = config, writes, task_id, task_path

        def list(
            self,
            config: object,
            *,
            filter: object = None,
            before: object = None,
            limit: object = None,
        ):
            _ = config, filter, before, limit
            if False:
                yield None

    class _FakePool:
        check_connection = staticmethod(lambda conn: conn)

        def __init__(self, *args: object, **kwargs: object) -> None:
            _ = args, kwargs
            self.closed = False
            pool_instances.append(self)

        def close(self) -> None:
            self.closed = True

    class _FakeConnection:
        @staticmethod
        def connect(*args: object, **kwargs: object):
            _ = args, kwargs

            class _AdminConn:
                def __enter__(self) -> _AdminConn:
                    return self

                def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
                    _ = exc_type, exc, tb

                def execute(self, stmt: object) -> None:
                    _ = stmt

            return _AdminConn()

    class _FakeSQL:
        def __init__(self, value: str) -> None:
            self._value = value

        def format(self, ident: object) -> str:
            return self._value.format(ident)

    fake_psycopg = types.ModuleType("psycopg")
    fake_psycopg.Connection = _FakeConnection
    fake_psycopg.sql = types.SimpleNamespace(
        Identifier=lambda value: value,
        SQL=_FakeSQL,
    )

    fake_rows = types.ModuleType("psycopg.rows")
    fake_rows.dict_row = object()

    fake_pool_mod = types.ModuleType("psycopg_pool")
    fake_pool_mod.ConnectionPool = _FakePool

    monkeypatch.setitem(sys.modules, "psycopg", fake_psycopg)
    monkeypatch.setitem(sys.modules, "psycopg.rows", fake_rows)
    monkeypatch.setitem(sys.modules, "psycopg_pool", fake_pool_mod)
    monkeypatch.setattr(pg_opengauss, "make_opengauss_saver", lambda pool: _FakeSaver())
    monkeypatch.setattr(
        pg_opengauss,
        "_ensure_tables_from_pool",
        lambda pool, schema: ensure_calls.append((pool, schema)),
    )

    async with pg_opengauss.get_checkpointer(
        checkpoint_uri="postgresql://example/db",
        checkpoint_schema="",
    ) as checkpointer:
        assert isinstance(checkpointer, pg_opengauss.SyncPGCheckpointer)

    assert len(pool_instances) == 1
    assert ensure_calls == [(pool_instances[0], "")]
    assert pool_instances[0].closed is True
