"""Unit tests for datacloud_agent.session.pg_opengauss.

Test map (source class / function → test class / functions):
────────────────────────────────────────────────────────────
OpenGaussSaver._fetch_blobs    → TestOpenGaussSaverFetchBlobs
OpenGaussSaver._fetch_writes   → TestOpenGaussSaverFetchWrites
OpenGaussSaver._assemble_row   → TestOpenGaussSaverAssembleRow
OpenGaussSaver.get_tuple       → TestOpenGaussSaverGetTuple
OpenGaussSaver.list            → TestOpenGaussSaverList
OpenGaussSaver.put             → TestOpenGaussSaverPut
OpenGaussSaver.put_writes      → TestOpenGaussSaverPutWrites
SyncPGCheckpointer             → TestSyncPGCheckpointer
ensure_tables_opengauss        → TestEnsureTablesOpengauss
get_checkpointer               → TestGetCheckpointer

All tests are pure-unit: no real DB connection, no network I/O.
A local ``_StubSaver`` provides the PostgresSaver parent interface so that
``OpenGaussSaver`` can be tested in complete isolation.
"""

from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest

from datacloud_agent.session.pg_opengauss import (
    OpenGaussSaver,
    SyncPGCheckpointer,
    ensure_tables_opengauss,
    get_checkpointer,
)


# ─────────────────────────────────────────────────────────────────────────────
# Local stub — provides the minimal PostgresSaver parent surface
# ─────────────────────────────────────────────────────────────────────────────

class _StubSaver(OpenGaussSaver):
    """Minimal parent-class stub for testing OpenGaussSaver in isolation.

    Provides only the methods that ``OpenGaussSaver`` calls on ``self``.
    No real DB connection is created.
    """

    def __init__(self, mock_cur: MagicMock) -> None:
        self._cur = mock_cur

    @contextmanager  # type: ignore[override]
    def _cursor(self, *, pipeline: bool = False):  # type: ignore[override]
        yield self._cur

    def _load_checkpoint_tuple(self, value: dict) -> dict:  # type: ignore[override]
        return value  # pass-through so tests can assert on the assembled dict

    def _search_where(self, config, filter, before):  # type: ignore[override]
        return ("", [])

    def _dump_blobs(self, *args):  # type: ignore[override]
        return []

    def _dump_writes(self, *args):  # type: ignore[override]
        return []


@pytest.fixture()
def mock_cursor() -> MagicMock:
    return MagicMock()


@pytest.fixture()
def stub_saver(mock_cursor: MagicMock) -> _StubSaver:
    return _StubSaver(mock_cursor)


# ─────────────────────────────────────────────────────────────────────────────
# OpenGaussSaver._fetch_blobs
# ─────────────────────────────────────────────────────────────────────────────

class TestOpenGaussSaverFetchBlobs:
    """_fetch_blobs fetches all blobs for (thread, ns) and filters by version in Python."""

    def test_returns_none_when_channel_versions_empty(self, stub_saver, mock_cursor):
        result = stub_saver._fetch_blobs(mock_cursor, "t1", "", {})
        assert result is None
        mock_cursor.execute.assert_not_called()

    def test_executes_select_on_non_empty_channel_versions(self, stub_saver, mock_cursor):
        mock_cursor.fetchall.return_value = []
        stub_saver._fetch_blobs(mock_cursor, "t1", "ns", {"ch": "v1"})
        mock_cursor.execute.assert_called_once()
        sql, params = mock_cursor.execute.call_args[0]
        assert "checkpoint_blobs" in sql
        assert params == ("t1", "ns")

    def test_filters_by_matching_version(self, stub_saver, mock_cursor):
        mock_cursor.fetchall.return_value = [
            {"channel": "messages", "type": "msgpack", "blob": b"\x01", "version": "v1"},
            {"channel": "other",    "type": "msgpack", "blob": b"\x02", "version": "v999"},
        ]
        result = stub_saver._fetch_blobs(mock_cursor, "t1", "", {"messages": "v1", "other": "v2"})
        assert result is not None
        assert len(result) == 1
        assert result[0] == (b"messages", b"msgpack", b"\x01")

    def test_encodes_channel_and_type_to_bytes(self, stub_saver, mock_cursor):
        mock_cursor.fetchall.return_value = [
            {"channel": "ch", "type": "json", "blob": b"data", "version": "v1"},
        ]
        result = stub_saver._fetch_blobs(mock_cursor, "t1", "", {"ch": "v1"})
        assert result is not None
        ch_bytes, type_bytes, _ = result[0]
        assert isinstance(ch_bytes, bytes)
        assert isinstance(type_bytes, bytes)
        assert ch_bytes == b"ch"
        assert type_bytes == b"json"

    def test_returns_none_when_no_version_matches(self, stub_saver, mock_cursor):
        mock_cursor.fetchall.return_value = [
            {"channel": "ch", "type": "t", "blob": b"x", "version": "old"},
        ]
        result = stub_saver._fetch_blobs(mock_cursor, "t1", "", {"ch": "new"})
        assert result is None

    def test_blob_may_be_none_for_empty_type(self, stub_saver, mock_cursor):
        mock_cursor.fetchall.return_value = [
            {"channel": "ch", "type": "empty", "blob": None, "version": "v1"},
        ]
        result = stub_saver._fetch_blobs(mock_cursor, "t1", "", {"ch": "v1"})
        assert result is not None
        assert result[0] == (b"ch", b"empty", None)


# ─────────────────────────────────────────────────────────────────────────────
# OpenGaussSaver._fetch_writes
# ─────────────────────────────────────────────────────────────────────────────

class TestOpenGaussSaverFetchWrites:
    """_fetch_writes fetches pending writes for a single checkpoint."""

    def test_returns_none_when_no_rows(self, stub_saver, mock_cursor):
        mock_cursor.fetchall.return_value = []
        result = stub_saver._fetch_writes(mock_cursor, "t1", "", "cid")
        assert result is None

    def test_executes_select_with_correct_params(self, stub_saver, mock_cursor):
        mock_cursor.fetchall.return_value = []
        stub_saver._fetch_writes(mock_cursor, "thread1", "ns", "chk1")
        sql, params = mock_cursor.execute.call_args[0]
        assert "checkpoint_writes" in sql
        assert params == ("thread1", "ns", "chk1")

    def test_returns_encoded_4_tuples(self, stub_saver, mock_cursor):
        mock_cursor.fetchall.return_value = [
            {"task_id": "task1", "channel": "ch1", "type": "t1", "blob": b"blob1"},
            {"task_id": "task2", "channel": "ch2", "type": "t2", "blob": b"blob2"},
        ]
        result = stub_saver._fetch_writes(mock_cursor, "t1", "", "cid")
        assert result == [
            (b"task1", b"ch1", b"t1", b"blob1"),
            (b"task2", b"ch2", b"t2", b"blob2"),
        ]

    def test_encodes_text_fields_to_bytes(self, stub_saver, mock_cursor):
        mock_cursor.fetchall.return_value = [
            {"task_id": "t", "channel": "c", "type": "tp", "blob": b"b"},
        ]
        result = stub_saver._fetch_writes(mock_cursor, "t1", "", "cid")
        assert result is not None
        t_id, ch, tp, _blob = result[0]
        assert all(isinstance(x, bytes) for x in (t_id, ch, tp))


# ─────────────────────────────────────────────────────────────────────────────
# OpenGaussSaver._assemble_row
# ─────────────────────────────────────────────────────────────────────────────

class TestOpenGaussSaverAssembleRow:
    """_assemble_row attaches channel_values and pending_writes to a checkpoint row."""

    def test_sets_channel_values_and_pending_writes(self, stub_saver, mock_cursor):
        row = {
            "thread_id": "t1",
            "checkpoint_ns": "",
            "checkpoint_id": "cid",
            "checkpoint": {"channel_versions": {"ch": "v1"}},
        }
        # fetchall called twice: once for blobs, once for writes
        mock_cursor.fetchall.side_effect = [
            [{"channel": "ch", "type": "json", "blob": b"x", "version": "v1"}],
            [],
        ]
        result = stub_saver._assemble_row(mock_cursor, row)
        assert "channel_values" in result
        assert "pending_writes" in result
        assert result["channel_values"] is not None
        assert result["pending_writes"] is None

    def test_channel_values_is_none_when_no_channel_versions(self, stub_saver, mock_cursor):
        row = {
            "thread_id": "t1",
            "checkpoint_ns": "",
            "checkpoint_id": "cid",
            "checkpoint": {"channel_versions": {}},
        }
        mock_cursor.fetchall.return_value = []
        result = stub_saver._assemble_row(mock_cursor, row)
        assert result["channel_values"] is None


# ─────────────────────────────────────────────────────────────────────────────
# OpenGaussSaver.get_tuple
# ─────────────────────────────────────────────────────────────────────────────

class TestOpenGaussSaverGetTuple:
    """get_tuple reads a single checkpoint via separate SELECT + blob/write queries."""

    def _base_config(self, checkpoint_id: str | None = None) -> dict:
        cfg: dict = {"configurable": {"thread_id": "t1", "checkpoint_ns": ""}}
        if checkpoint_id:
            cfg["configurable"]["checkpoint_id"] = checkpoint_id
        return cfg

    def _checkpoint_row(self, chk_id: str = "cid") -> dict:
        return {
            "thread_id": "t1",
            "checkpoint_ns": "",
            "checkpoint_id": chk_id,
            "parent_checkpoint_id": None,
            "checkpoint": {"v": 4, "channel_versions": {}},
            "metadata": {},
        }

    def test_returns_none_when_no_row_found(self, stub_saver, mock_cursor):
        mock_cursor.fetchone.return_value = None
        result = stub_saver.get_tuple(self._base_config())
        assert result is None

    def test_with_checkpoint_id_uses_exact_where_clause(self, stub_saver, mock_cursor):
        mock_cursor.fetchone.return_value = self._checkpoint_row("explicit-cid")
        mock_cursor.fetchall.return_value = []
        stub_saver.get_tuple(self._base_config("explicit-cid"))
        sql = mock_cursor.execute.call_args_list[0][0][0]
        assert "checkpoint_id=%s" in sql

    def test_without_checkpoint_id_uses_order_by_desc_limit_1(self, stub_saver, mock_cursor):
        mock_cursor.fetchone.return_value = self._checkpoint_row()
        mock_cursor.fetchall.return_value = []
        stub_saver.get_tuple(self._base_config())
        sql = mock_cursor.execute.call_args_list[0][0][0]
        assert "ORDER BY checkpoint_id DESC" in sql
        assert "LIMIT 1" in sql

    def test_returns_assembled_checkpoint_tuple(self, stub_saver, mock_cursor):
        mock_cursor.fetchone.return_value = self._checkpoint_row("cid1")
        mock_cursor.fetchall.return_value = []
        result = stub_saver.get_tuple(self._base_config())
        assert result is not None
        assert result["checkpoint_id"] == "cid1"


# ─────────────────────────────────────────────────────────────────────────────
# OpenGaussSaver.list
# ─────────────────────────────────────────────────────────────────────────────

class TestOpenGaussSaverList:
    """list yields checkpoint tuples; applies LIMIT when provided."""

    def _config(self) -> dict:
        return {"configurable": {"thread_id": "t1", "checkpoint_ns": ""}}

    def _make_row(self, chk_id: str) -> dict:
        return {
            "thread_id": "t1", "checkpoint_ns": "",
            "checkpoint_id": chk_id, "parent_checkpoint_id": None,
            "checkpoint": {"v": 4, "channel_versions": {}}, "metadata": {},
        }

    def test_yields_nothing_when_table_empty(self, stub_saver, mock_cursor):
        mock_cursor.fetchall.return_value = []
        assert list(stub_saver.list(self._config())) == []

    def test_yields_one_item_per_row(self, stub_saver, mock_cursor):
        rows = [self._make_row("c1"), self._make_row("c2")]
        # First fetchall = main SELECT; subsequent pairs for blob/write per row
        mock_cursor.fetchall.side_effect = [rows, [], [], [], []]
        result = list(stub_saver.list(self._config()))
        assert len(result) == 2

    def test_appends_limit_to_query(self, stub_saver, mock_cursor):
        mock_cursor.fetchall.return_value = []
        list(stub_saver.list(self._config(), limit=5))
        sql = mock_cursor.execute.call_args_list[0][0][0]
        params = mock_cursor.execute.call_args_list[0][0][1]
        assert "LIMIT %s" in sql
        assert 5 in params

    def test_no_limit_clause_when_limit_is_none(self, stub_saver, mock_cursor):
        mock_cursor.fetchall.return_value = []
        list(stub_saver.list(self._config(), limit=None))
        sql = mock_cursor.execute.call_args_list[0][0][0]
        assert "LIMIT" not in sql


# ─────────────────────────────────────────────────────────────────────────────
# OpenGaussSaver.put
# ─────────────────────────────────────────────────────────────────────────────

class TestOpenGaussSaverPut:
    """put saves a checkpoint; falls back to UPDATE when INSERT conflicts."""

    def _config(self, chk_id: str = "prev-cid") -> dict:
        return {"configurable": {"thread_id": "t1", "checkpoint_ns": "", "checkpoint_id": chk_id}}

    def _checkpoint(self, chk_id: str = "new-cid") -> dict:
        return {"id": chk_id, "channel_values": {}, "v": 4}

    def test_inserts_checkpoint_row(self, stub_saver, mock_cursor):
        stub_saver.put(self._config(), self._checkpoint(), {}, {})
        sqls = [c[0][0] for c in mock_cursor.execute.call_args_list]
        assert any("INSERT INTO checkpoints" in s for s in sqls)

    def test_returns_next_config_with_new_checkpoint_id(self, stub_saver, mock_cursor):
        result = stub_saver.put(self._config(), self._checkpoint("cid-new"), {}, {})
        assert result["configurable"]["checkpoint_id"] == "cid-new"
        assert result["configurable"]["thread_id"] == "t1"

    def test_updates_on_unique_violation(self, stub_saver, mock_cursor):
        import psycopg.errors

        def execute_side(sql, *_args, **_kwargs):
            if "INSERT INTO checkpoints" in sql:
                raise psycopg.errors.UniqueViolation()

        mock_cursor.execute.side_effect = execute_side
        stub_saver.put(self._config(), self._checkpoint(), {}, {})
        sqls = [c[0][0] for c in mock_cursor.execute.call_args_list]
        assert any("UPDATE checkpoints" in s for s in sqls)

    def test_blob_unique_violation_is_silently_ignored(self, stub_saver, mock_cursor):
        import psycopg.errors

        stub_saver._dump_blobs = lambda *a: [("t1", "", "ch", "v1", "json", b"data")]

        def execute_side(sql, *_args, **_kwargs):
            if "INSERT INTO checkpoint_blobs" in sql:
                raise psycopg.errors.UniqueViolation()

        mock_cursor.execute.side_effect = execute_side
        stub_saver.put(self._config(), self._checkpoint(), {}, {"ch": "v1"})
        # No exception raised means blob conflict was properly ignored

    def test_inserts_blob_when_non_primitive_channel_value(self, stub_saver, mock_cursor):
        checkpoint = {
            "id": "cid",
            "channel_values": {"messages": [{"role": "user", "content": "hi"}]},
            "v": 4,
        }
        stub_saver._dump_blobs = lambda *a: [("t1", "", "messages", "v1", "msgpack", b"x")]
        stub_saver.put(self._config(), checkpoint, {}, {"messages": "v1"})
        sqls = [c[0][0] for c in mock_cursor.execute.call_args_list]
        assert any("INSERT INTO checkpoint_blobs" in s for s in sqls)

    def test_no_blob_insert_when_all_primitive_values(self, stub_saver, mock_cursor):
        checkpoint = {"id": "cid", "channel_values": {"flag": True, "count": 3}, "v": 4}
        stub_saver.put(self._config(), checkpoint, {}, {})
        sqls = [c[0][0] for c in mock_cursor.execute.call_args_list]
        assert not any("checkpoint_blobs" in s for s in sqls)


# ─────────────────────────────────────────────────────────────────────────────
# OpenGaussSaver.put_writes
# ─────────────────────────────────────────────────────────────────────────────

class TestOpenGaussSaverPutWrites:
    """put_writes saves task writes; DELETE+INSERT for upsert channels, INSERT-ignore for others."""

    def _config(self) -> dict:
        return {"configurable": {"thread_id": "t1", "checkpoint_ns": "", "checkpoint_id": "cid"}}

    def _write_row(self) -> tuple:
        return ("t1", "", "cid", "task1", "", 0, "ch", "json", b"data")

    def test_upsert_case_deletes_then_inserts(self, stub_saver, mock_cursor):
        stub_saver._dump_writes = lambda *a: [self._write_row()]
        from langgraph.checkpoint.base import WRITES_IDX_MAP  # noqa: PLC0415

        upsert_channel = next(iter(WRITES_IDX_MAP))
        stub_saver.put_writes(self._config(), [(upsert_channel, "value")], "task1")
        sqls = [c[0][0] for c in mock_cursor.execute.call_args_list]
        assert any("DELETE FROM checkpoint_writes" in s for s in sqls)
        assert any("INSERT INTO checkpoint_writes" in s for s in sqls)

    def test_regular_channel_only_inserts_no_delete(self, stub_saver, mock_cursor):
        stub_saver._dump_writes = lambda *a: [self._write_row()]
        stub_saver.put_writes(self._config(), [("regular_channel", "value")], "task1")
        sqls = [c[0][0] for c in mock_cursor.execute.call_args_list]
        assert not any("DELETE" in s for s in sqls)
        assert any("INSERT INTO checkpoint_writes" in s for s in sqls)

    def test_unique_violation_on_regular_write_is_ignored(self, stub_saver, mock_cursor):
        import psycopg.errors

        stub_saver._dump_writes = lambda *a: [self._write_row()]
        mock_cursor.execute.side_effect = psycopg.errors.UniqueViolation()
        stub_saver.put_writes(self._config(), [("regular", "val")], "task1")
        # No exception raised

    def test_no_writes_means_no_db_calls(self, stub_saver, mock_cursor):
        stub_saver._dump_writes = lambda *a: []
        stub_saver.put_writes(self._config(), [], "task1")
        mock_cursor.execute.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────────
# SyncPGCheckpointer
# ─────────────────────────────────────────────────────────────────────────────

class TestSyncPGCheckpointer:
    """SyncPGCheckpointer wraps a sync saver and exposes an async interface via run_in_executor."""

    def _config(self) -> dict:
        return {"configurable": {"thread_id": "t1", "checkpoint_ns": ""}}

    def _make_inner(self, **attrs) -> MagicMock:
        inner = MagicMock()
        inner.serde = None  # BaseCheckpointSaver.__init__ accepts this
        for k, v in attrs.items():
            setattr(inner, k, v)
        return inner

    async def test_aget_tuple_delegates_to_inner_get_tuple(self):
        inner = self._make_inner()
        inner.get_tuple.return_value = {"checkpoint_id": "c1"}
        wrapper = SyncPGCheckpointer(inner)
        result = await wrapper.aget_tuple(self._config())
        inner.get_tuple.assert_called_once_with(self._config())
        assert result == {"checkpoint_id": "c1"}

    async def test_aget_returns_none_when_not_found(self):
        inner = self._make_inner()
        inner.get.return_value = None
        wrapper = SyncPGCheckpointer(inner)
        result = await wrapper.aget(self._config())
        assert result is None

    async def test_aput_delegates_to_inner_put(self):
        inner = self._make_inner()
        inner.put.return_value = {"configurable": {"thread_id": "t1"}}
        wrapper = SyncPGCheckpointer(inner)
        chk = {"id": "c1", "channel_values": {}}
        await wrapper.aput(self._config(), chk, {}, {})
        inner.put.assert_called_once_with(self._config(), chk, {}, {})

    async def test_alist_yields_items_in_order(self):
        items = [{"checkpoint_id": "c1"}, {"checkpoint_id": "c2"}]
        inner = self._make_inner()
        inner.list.return_value = iter(items)
        wrapper = SyncPGCheckpointer(inner)
        collected = [x async for x in wrapper.alist(self._config())]
        assert collected == items

    async def test_alist_yields_nothing_when_empty(self):
        inner = self._make_inner()
        inner.list.return_value = iter([])
        wrapper = SyncPGCheckpointer(inner)
        collected = [x async for x in wrapper.alist(self._config())]
        assert collected == []

    def test_sync_get_tuple_passthrough(self):
        inner = self._make_inner()
        inner.get_tuple.return_value = "sentinel"
        assert SyncPGCheckpointer(inner).get_tuple(self._config()) == "sentinel"

    def test_sync_put_passthrough(self):
        inner = self._make_inner()
        inner.put.return_value = "next_cfg"
        chk = {"id": "c1", "channel_values": {}}
        assert SyncPGCheckpointer(inner).put(self._config(), chk, {}, {}) == "next_cfg"

    def test_sync_list_yields_from_inner(self):
        inner = self._make_inner()
        inner.list.return_value = iter([1, 2, 3])
        result = list(SyncPGCheckpointer(inner).list(self._config()))
        assert result == [1, 2, 3]


# ─────────────────────────────────────────────────────────────────────────────
# ensure_tables_opengauss
# ─────────────────────────────────────────────────────────────────────────────

class TestEnsureTablesOpengauss:
    """ensure_tables_opengauss creates all checkpoint tables via OpenGauss-compatible DDL."""

    def _make_conn(self):
        conn = MagicMock()
        cur = MagicMock()
        conn.cursor.return_value.__enter__ = MagicMock(return_value=cur)
        conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        return conn, cur

    def test_executes_multiple_ddl_statements(self):
        conn, cur = self._make_conn()
        ensure_tables_opengauss(conn, "")
        assert cur.execute.call_count >= 5

    def test_creates_checkpoints_table(self):
        conn, cur = self._make_conn()
        ensure_tables_opengauss(conn, "")
        sqls = [c[0][0] for c in cur.execute.call_args_list]
        assert any("checkpoints" in s and "CREATE TABLE" in s for s in sqls)

    def test_creates_checkpoint_blobs_table(self):
        conn, cur = self._make_conn()
        ensure_tables_opengauss(conn, "")
        sqls = [c[0][0] for c in cur.execute.call_args_list]
        assert any("checkpoint_blobs" in s and "CREATE TABLE" in s for s in sqls)

    def test_creates_checkpoint_writes_table(self):
        conn, cur = self._make_conn()
        ensure_tables_opengauss(conn, "")
        sqls = [c[0][0] for c in cur.execute.call_args_list]
        assert any("checkpoint_writes" in s and "CREATE TABLE" in s for s in sqls)

    def test_inserts_migration_version_9(self):
        conn, cur = self._make_conn()
        ensure_tables_opengauss(conn, "")
        sqls = [c[0][0] for c in cur.execute.call_args_list]
        assert any("checkpoint_migrations" in s and "INSERT" in s for s in sqls)

    def test_creates_thread_id_indexes(self):
        conn, cur = self._make_conn()
        ensure_tables_opengauss(conn, "")
        sqls = [c[0][0] for c in cur.execute.call_args_list]
        assert any("CREATE INDEX" in s and "thread_id" in s for s in sqls)


# ─────────────────────────────────────────────────────────────────────────────
# get_checkpointer (factory)
# ─────────────────────────────────────────────────────────────────────────────

class TestGetCheckpointer:
    """get_checkpointer is an asynccontextmanager that yields a SyncPGCheckpointer.

    ``Connection`` is imported locally inside the function, so we patch at
    the ``psycopg`` module level: ``patch("psycopg.Connection.connect")``.
    """

    async def test_raises_runtime_error_when_uri_missing(self, monkeypatch):
        monkeypatch.delenv("DATACLOUD_PG_CHECKPOINT_URI", raising=False)
        with pytest.raises(RuntimeError, match="DATACLOUD_PG_CHECKPOINT_URI"):
            async with get_checkpointer():
                pass

    async def test_raises_runtime_error_when_uri_is_blank(self, monkeypatch):
        monkeypatch.setenv("DATACLOUD_PG_CHECKPOINT_URI", "   ")
        with pytest.raises(RuntimeError, match="DATACLOUD_PG_CHECKPOINT_URI"):
            async with get_checkpointer():
                pass

    async def test_yields_sync_pg_checkpointer_on_success(self, monkeypatch):
        monkeypatch.setenv("DATACLOUD_PG_CHECKPOINT_URI", "postgresql://test/db")
        monkeypatch.delenv("DATACLOUD_PG_CHECKPOINT_SCHEMA", raising=False)

        mock_conn = MagicMock()
        mock_saver = MagicMock()
        mock_saver.serde = None
        mock_saver.setup.return_value = None

        with (
            patch("psycopg.Connection.connect", return_value=mock_conn),
            patch(
                "datacloud_agent.session.pg_opengauss.make_opengauss_saver",
                return_value=mock_saver,
            ),
        ):
            async with get_checkpointer() as cp:
                assert isinstance(cp, SyncPGCheckpointer)
                assert cp._inner is mock_saver

    async def test_closes_connection_on_normal_exit(self, monkeypatch):
        monkeypatch.setenv("DATACLOUD_PG_CHECKPOINT_URI", "postgresql://test/db")
        monkeypatch.delenv("DATACLOUD_PG_CHECKPOINT_SCHEMA", raising=False)

        mock_conn = MagicMock()
        mock_saver = MagicMock()
        mock_saver.serde = None
        mock_saver.setup.return_value = None

        with (
            patch("psycopg.Connection.connect", return_value=mock_conn),
            patch(
                "datacloud_agent.session.pg_opengauss.make_opengauss_saver",
                return_value=mock_saver,
            ),
        ):
            async with get_checkpointer():
                pass

        mock_conn.close.assert_called_once()

    async def test_closes_connection_even_when_body_raises(self, monkeypatch):
        monkeypatch.setenv("DATACLOUD_PG_CHECKPOINT_URI", "postgresql://test/db")
        monkeypatch.delenv("DATACLOUD_PG_CHECKPOINT_SCHEMA", raising=False)

        mock_conn = MagicMock()
        mock_saver = MagicMock()
        mock_saver.serde = None
        mock_saver.setup.return_value = None

        with (
            patch("psycopg.Connection.connect", return_value=mock_conn),
            patch(
                "datacloud_agent.session.pg_opengauss.make_opengauss_saver",
                return_value=mock_saver,
            ),
        ):
            with pytest.raises(ValueError):
                async with get_checkpointer():
                    raise ValueError("body error")

        mock_conn.close.assert_called_once()
