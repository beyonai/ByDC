"""Type1: tests for schema DDL preparation and execution."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import quote_plus
from urllib.parse import urlparse

import pytest
from sqlalchemy.dialects.postgresql.base import PGDialect
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from dotenv import dotenv_values

from fixtures.db_client import create_test_engine, execute_sql_script

# e_commerce_demo：DDL 为 PostgreSQL/OpenGauss 风格，此处 schema 即数据库名
SCHEMA = "e_commerce_demo"
TABLES = ("dws_enterprise_wide", "dws_grid_wide", "dws_industry_wide")


@pytest.mark.type1_schema
def test_ddl_file_exists_and_contains_core_tables(mock_env_root: Path) -> None:
    table_sql_paths = _resolve_table_sql_paths(mock_env_root)
    assert table_sql_paths, "no SQL files found under db/pg/ddl/tables/"
    ddl = _read_ddl_from_table_files(table_sql_paths)
    for table in TABLES:
        # PostgreSQL：CREATE TABLE IF NOT EXISTS schema.table (...)
        expected = f"CREATE TABLE IF NOT EXISTS {SCHEMA}.{table}"
        assert expected in ddl, (
            f"DDL 中未找到 {expected}，"
            "请检查 db/pg/ddl/tables/ 下的 .sql 文件"
        )


@pytest.mark.type1_schema
@pytest.mark.integration
def test_database_connection_with_env_example(mock_env_root: Path) -> None:
    database_dsn, db_name = _build_database_dsn_from_env_example(mock_env_root)
    _patch_opengauss_version_parser()

    try:
        engine = create_test_engine(database_dsn)
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1"))
            assert result.scalar_one() == 1
    except OperationalError as exc:
        raise AssertionError(
            f"cannot connect target database '{db_name}'. "
            "Please verify DATACLOUD_DB_URL/DATACLOUD_DB_USER/DATACLOUD_DB_PASSWORD in .env.example. "
            f"detail: {exc}"
        ) from exc


@pytest.mark.type1_schema
@pytest.mark.integration
def test_drop_then_create_tables_with_env_example(mock_env_root: Path) -> None:
    database_dsn, db_name = _build_database_dsn_from_env_example(mock_env_root)
    _patch_opengauss_version_parser()
    print(f"[type1] connecting database: {db_name}")
    engine = create_test_engine(database_dsn)

    table_sql_paths = _resolve_table_sql_paths(mock_env_root)
    ddl = _read_ddl_from_table_files(table_sql_paths)
    print(f"[type1] ddl tables dir: {table_sql_paths[0].parent}")

    drop_statements = [
        f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}",
        *[f"DROP TABLE IF EXISTS {SCHEMA}.{t} CASCADE" for t in TABLES],
    ]

    try:
        with engine.begin() as conn:
            print("[type1] dropping existing tables...")
            for stmt in drop_statements:
                conn.execute(text(stmt))
    except OperationalError as exc:
        raise AssertionError(
            f"cannot connect target database '{db_name}'. "
            f"Please create database first, then rerun DDL test. detail: {exc}"
        ) from exc

    print("[type1] applying DDL...")
    execute_sql_script(engine, ddl)

    with engine.connect() as conn:
        for table_name in TABLES:
            result = conn.execute(
                text(
                    """
                    SELECT count(*) AS cnt
                    FROM information_schema.tables
                    WHERE table_schema = :schema AND table_name = :table_name
                    """
                ),
                {"schema": SCHEMA, "table_name": table_name},
            )
            assert result.scalar_one() == 1, (
                f"table {SCHEMA}.{table_name} not found after DDL execution"
            )
    print("[type1] drop + create verification passed")


# ──────────────────────────────────────────────────────────────────────────────
# helpers
# ──────────────────────────────────────────────────────────────────────────────

def _resolve_table_sql_paths(mock_env_root: Path) -> list[Path]:
    tables_dir = mock_env_root / "db" / "pg" / "ddl" / "tables"
    if not tables_dir.exists():
        raise FileNotFoundError(f"tables ddl dir not found: {tables_dir}")
    paths = sorted(tables_dir.glob("*.sql"))
    if not paths:
        raise FileNotFoundError(f"no table ddl sql files found under: {tables_dir}")
    return paths


def _read_ddl_from_table_files(table_sql_paths: list[Path]) -> str:
    chunks = [path.read_text(encoding="utf-8") for path in table_sql_paths]
    return "\n\n".join(chunks)


def _build_database_dsn_from_env_example(mock_env_root: Path) -> tuple[str, str]:
    env_path = mock_env_root / ".env.example"
    cfg = dotenv_values(env_path)
    db_url = cfg.get("DATACLOUD_DB_URL")
    db_user = cfg.get("DATACLOUD_DB_USER")
    db_password = cfg.get("DATACLOUD_DB_PASSWORD")
    assert all([db_url, db_user, db_password]), (
        f"missing DATACLOUD_DB_* config in {env_path}"
    )
    parsed = urlparse(str(db_url).removeprefix("jdbc:"))
    encoded_password = quote_plus(str(db_password))
    database_dsn = (
        f"postgresql+psycopg2://{db_user}:{encoded_password}@"
        f"{parsed.hostname or 'localhost'}:{parsed.port or 5432}/{parsed.path.lstrip('/') or 'postgres'}"
    )
    return database_dsn, parsed.path.lstrip("/") or "postgres"


def _patch_opengauss_version_parser() -> None:
    if getattr(PGDialect, "_datacloud_opengauss_patched", False):
        return

    original = PGDialect._get_server_version_info

    def _opengauss_version(self, conn):  # type: ignore[no-untyped-def]
        try:
            return original(self, conn)
        except AssertionError:
            return (12, 0)

    PGDialect._get_server_version_info = _opengauss_version  # type: ignore[assignment]
    setattr(PGDialect, "_datacloud_opengauss_patched", True)
