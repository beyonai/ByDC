"""Type1: tests for schema DDL preparation and execution."""

from __future__ import annotations

import pytest
from sqlalchemy import text

from tests.fixtures.db_client import create_test_engine, execute_sql_script


@pytest.mark.type1_schema
def test_ddl_file_exists_and_contains_core_tables(ddl_sql_path) -> None:
    assert ddl_sql_path.exists()
    ddl = ddl_sql_path.read_text(encoding="utf-8")
    assert "CREATE TABLE crm_demo.po_users" in ddl
    assert "CREATE TABLE crm_demo.po_organization" in ddl


@pytest.mark.type1_schema
@pytest.mark.integration
def test_apply_ddl_to_database(ddl_sql_path, integration_enabled, database_dsn) -> None:
    if not integration_enabled:
        pytest.skip("integration disabled, set DATACLOUD_ENABLE_INTEGRATION_TESTS=1")
    if not database_dsn:
        pytest.skip("missing DATACLOUD_TEST_DATABASE_DSN")

    engine = create_test_engine(database_dsn)
    ddl = ddl_sql_path.read_text(encoding="utf-8")
    execute_sql_script(engine, ddl)

    with engine.connect() as conn:
        result = conn.execute(
            text(
                """
                SELECT count(*) AS cnt
                FROM information_schema.tables
                WHERE table_schema = 'crm_demo' AND table_name = 'po_users'
                """
            )
        )
        assert result.scalar_one() == 1
