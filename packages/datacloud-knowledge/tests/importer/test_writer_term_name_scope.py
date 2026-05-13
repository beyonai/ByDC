"""Importer writer tests for scoped ``term_name`` synchronization."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast
from unittest.mock import patch

from datacloud_knowledge.ingestion.owl_import.importer import writer
from psycopg import Cursor

PACKAGE_ROOT = Path(__file__).resolve().parents[2]


class RecordingCursor:
    """Minimal cursor double that records SQL calls."""

    def __init__(self, rows: list[tuple[Any, ...]] | None = None) -> None:
        self.rows = rows or []
        self.calls: list[tuple[str, Any]] = []
        self.rowcount = 0

    def execute(self, query: str, params: Any = None) -> None:
        self.calls.append((query, params))
        self.rowcount = 1 if "INSERT INTO term_name" in query else 0

    def fetchall(self) -> list[tuple[Any, ...]]:
        return self.rows


class TestWriterTermNameScope:
    """Regression coverage for prop term names leaking through global scope."""

    def test_delete_global_prop_term_names_only_deletes_global_scope(self) -> None:
        cursor = RecordingCursor()

        deleted = writer._delete_global_prop_term_names(
            cast("Cursor[Any]", cursor),
            [("LIB#prop#enterprise_tax_rate", "企业实际税负率（%）", [])],
        )

        assert deleted == 0
        sql, params = cursor.calls[0]
        assert "DELETE FROM term_name" in sql
        assert "search_scope @> %s::jsonb" in sql
        assert "search_scope = '{}'::jsonb" in sql
        assert params == (["LIB#prop#enterprise_tax_rate"], '{"scope": "global"}')

    def test_relation_term_name_idempotency_includes_search_scope(self) -> None:
        cursor = RecordingCursor(
            rows=[
                (
                    "rel-1",
                    "LIB#view#scene_grid_analysis",
                    "LIB#prop#phy_grid_tax_rate",
                    '{"field_alias":"物理网格实际税负率（%）"}',
                )
            ]
        )

        with (
            patch.object(writer, "_next_snowflake_ids", return_value=["name-1"]),
            patch.object(writer, "_execute_values"),
        ):
            inserted = writer._batch_insert_relation_term_names(
                cast("Cursor[Any]", cursor),
                ["rel-1"],
            )

        assert inserted == 1
        insert_sql = next(sql for sql, _params in cursor.calls if "INSERT INTO term_name" in sql)
        assert "tn.term_id = t.term_id" in insert_sql
        assert "tn.name_text = t.name_text" in insert_sql
        assert "tn.search_scope @> t.search_scope::jsonb" in insert_sql

    def test_relation_update_only_still_syncs_scoped_term_names(self) -> None:
        cursor = RecordingCursor(
            rows=[
                (
                    "rel-1",
                    "LIB#view#scene_grid_analysis",
                    "LIB#prop#phy_grid_tax_rate",
                    '{"field_alias":"物理网格实际税负率（%）"}',
                )
            ]
        )
        stats = {
            "relations": {
                "deleted": 0,
                "updated": 0,
                "inserted": 0,
            }
        }

        with (
            patch.object(writer, "_next_snowflake_ids", return_value=["name-1"]),
            patch.object(writer, "_execute_values"),
        ):
            writer._batch_process_relation(
                cast("Cursor[Any]", cursor),
                [
                    {
                        "op": "update",
                        "relation_code": "rel-1",
                        "relation_name": "HAS_FIELD",
                        "ext_field": '{"field_alias":"物理网格实际税负率（%）"}',
                    }
                ],
                stats,
            )

        assert any(
            "FROM term_relation" in sql and "WHERE relation_id = ANY" in sql
            for sql, _ in cursor.calls
        )
        assert any("INSERT INTO term_name" in sql for sql, _ in cursor.calls)

    def test_schema_allows_same_name_in_different_search_scopes(self) -> None:
        ddl = (PACKAGE_ROOT / "db/ddl/whale_datacloud/99_indexes_constraints.sql").read_text(
            encoding="utf-8"
        )
        migration = (PACKAGE_ROOT / "db/migrations/99_update_term_name_scope_unique.sql").read_text(
            encoding="utf-8"
        )

        assert "DROP INDEX IF EXISTS uq_term_name_text" in ddl
        assert "ON term_name(term_id, name_text, search_scope)" in ddl
        assert "DELETE FROM term_name tn" in migration
        assert "t.term_type_code = 'prop'" in migration
        assert "tn.search_scope = '{}'::jsonb" in migration
        assert "ON term_name(term_id, name_text, search_scope)" in migration
